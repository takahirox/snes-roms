import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";

const [address] = process.argv.slice(2);
assert(address, "Usage: node pages-smoke.mjs <Studio URL>");
const base = new URL(address);
const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(base.hostname);
assert(base.protocol === "https:" || (base.protocol === "http:" && loopback),
  "Studio smoke tests require HTTPS or loopback HTTP");
if (!base.pathname.endsWith("/")) base.pathname += "/";

const checksums = new Map();
for (const line of (process.env.STUDIO_SITE_CHECKSUMS ?? "").trim().split("\n").filter(Boolean)) {
  const [, hash, path] = /^([a-f0-9]{64})  (.+)$/.exec(line) ?? [];
  assert(hash, "Invalid Studio site checksum");
  checksums.set(path, hash);
}

const javascript = /^(?:application|text)\/javascript(?:;|$)/i;
const resources = {
  "index.html": /^text\/html(?:;|$)/i,
  "studio.css": /^text\/css(?:;|$)/i,
  "studio.js": javascript,
  "folder-save.js": javascript,
  "inspector.js": javascript,
  "ui.js": javascript,
  "pkg/studio_web.js": javascript,
  "pkg/studio_web_bg.wasm": /^application\/wasm(?:;|$)/i,
  "demo/studio.json": /^application\/json(?:;|$)/i,
};
const responses = {};
for (const [path, mime] of Object.entries(resources)) {
  const url = new URL(path === "index.html" ? "./" : path, base);
  const response = await fetch(url, { cache: "no-store", redirect: "error", signal: AbortSignal.timeout(10_000) });
  assert.equal(response.status, 200, `${url} returned HTTP ${response.status}`);
  assert.match(response.headers.get("content-type") ?? "", mime, `${url} has incorrect MIME type`);
  const bytes = Buffer.from(await response.arrayBuffer());
  assert(bytes.length > 0, `${url} is empty`);
  if (checksums.size) {
    assert.equal(createHash("sha256").update(bytes).digest("hex"), checksums.get(path),
      `${url} differs from the built site`);
  }
  responses[path] = bytes;
}
assert.equal(responses["pkg/studio_web_bg.wasm"].subarray(0, 8).toString("hex"), "0061736d01000000");
const fixture = await readFile(new URL("../../fixtures/demo/studio.json", import.meta.url));
assert(responses["demo/studio.json"].equals(fixture), "The site demo differs from the original fixture");
const demo = JSON.parse(fixture);
console.log(`HTTP checks passed for ${base.href} (HTML, CSS, JavaScript, WebAssembly and demo JSON)`);

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  page.setDefaultTimeout(10_000);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(base.href, { timeout: 15_000 });
  assert.equal(page.url(), base.href);
  assert.equal(await page.evaluate(() => window.isSecureContext), true);
  await page.getByRole("heading", { name: "chromatic-lab", exact: true }).waitFor();
  assert.equal(await page.locator("#project-title").textContent(), demo.name);

  await page.getByRole("button", { name: "compass", exact: true }).click();
  await page.locator("#preview").press("Enter");
  assert.equal(await page.locator("#status").textContent(), "Edit applied");
  assert.equal(await page.locator("#project-title").textContent(), `${demo.name} · Edited`);

  await page.getByRole("button", { name: "Save / export", exact: true }).click();
  await page.getByLabel("Destination").selectOption("json");
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Save", exact: true }).click(),
  ]);
  assert.equal(download.suggestedFilename(), "studio.json");
  const exported = JSON.parse(await readFile(await download.path(), "utf8"));
  const original = demo.assets.compass.data.pixels;
  assert.notEqual(original[0], 1, "Smoke test requires a demo pixel different from the default brush");
  assert.equal(exported.name, demo.name);
  assert.deepEqual(exported.assets.compass.data.pixels, [1, ...original.slice(1)]);
  assert.deepEqual(errors, []);
  console.log("Headless Chromium loaded the demo, painted a tile pixel and exported the edited project");
} finally {
  await browser.close();
}
