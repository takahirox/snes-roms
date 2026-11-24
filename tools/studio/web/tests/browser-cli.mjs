import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const [chrome = "google-chrome", cli = resolve(root, process.env.CARGO_TARGET_DIR ?? "target", "debug",
  process.platform === "win32" ? "sfc-studio.exe" : "sfc-studio")] = process.argv.slice(2);
const suite = "/web/tests/folder-workflows.html";
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".wasm": "application/wasm", ".json": "application/json" };
const temp = await mkdtemp(join(tmpdir(), "studio-browser-"));
const result = Promise.withResolvers();

const server = createServer(async (request, response) => {
  try {
    const { pathname } = new URL(request.url, "http://localhost");
    if (request.method === "GET" && (pathname === suite || pathname.startsWith("/_site/"))) {
      const bytes = await readFile(join(root, pathname));
      response.setHeader("Content-Type", types[extname(pathname)] ?? "application/octet-stream");
      response.end(bytes);
    } else if (request.method === "POST" && ["/cli-diff", "/test-result"].includes(pathname)) {
      request.setEncoding("utf8");
      let body = "";
      for await (const chunk of request) body += chunk;
      const payload = JSON.parse(body);
      if (pathname === "/test-result") {
        response.end();
        result.resolve(payload);
      } else {
        const before = join(temp, "before.json");
        const after = join(temp, "after.json");
        await Promise.all([writeFile(before, payload.before), writeFile(after, payload.after)]);
        response.end(execFileSync(cli, ["diff", before, after]));
      }
    } else {
      response.writeHead(404).end();
    }
  } catch (error) {
    response.writeHead(500).end(error.message);
  }
});

let browser;
let timeout;
try {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const url = `http://127.0.0.1:${server.address().port}${suite}?cli`;
  browser = spawn(chrome, ["--headless", "--no-first-run", "--autoplay-policy=no-user-gesture-required",
    `--user-data-dir=${join(temp, "chrome")}`, url], { stdio: "ignore" });
  const stopped = once(browser, "exit").then(([code]) => { throw new Error(`Chrome exited with status ${code}`); });
  timeout = setTimeout(() => result.reject(new Error("Timed out waiting for the browser tests")), 30_000);
  const { state, text } = await Promise.race([result.promise, stopped]);
  assert.equal(state, "passed", text);
  console.log(text);
} finally {
  clearTimeout(timeout);
  server.close();
  server.closeAllConnections();
  if (browser?.pid && browser.exitCode === null && browser.signalCode === null) {
    browser.kill();
    await once(browser, "exit");
  }
  await rm(temp, { recursive: true, force: true, maxRetries: 3 });
}
