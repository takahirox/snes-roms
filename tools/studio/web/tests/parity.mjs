import assert from "node:assert/strict";
import { execFile, execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const temp = mkdtempSync(join(tmpdir(), "studio-parity-"));
const projectFile = join(root, "fixtures", "demo", "studio.json");
const editFile = join(root, "fixtures", "paint.json");
const cliExecutable = process.argv[2] ?? join(root, "target", "debug", process.platform === "win32" ? "sfc-studio.exe" : "sfc-studio");
const cli = (...args) => execFileSync(cliExecutable, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
const write = (name, content) => {
  const path = join(temp, name);
  writeFileSync(path, content);
  return path;
};

try {
  // A .mjs copy loads the bundler-free browser glue in Node without package.json.
  const glue = join(temp, "studio_web.mjs");
  copyFileSync(join(root, "_site", "pkg", "studio_web.js"), glue);
  const wasm = await import(pathToFileURL(glue).href);
  wasm.initSync({ module: readFileSync(join(root, "_site", "pkg", "studio_web_bg.wasm")) });

  const original = readFileSync(projectFile);
  const studio = new wasm.Studio(original);
  const validation = JSON.parse(cli("validate", projectFile));
  assert.deepEqual(JSON.parse(studio.diagnostics()), validation.diagnostics);
  assert.equal(wasm.fingerprint(original), validation.revision);
  assert.deepEqual(Buffer.from(studio.save(false)), original);
  const archive = join(temp, "demo.zip");
  cli("pack", projectFile, archive);
  assert.deepEqual(Buffer.from(studio.save(true)), readFileSync(archive));
  const reloaded = new wasm.Studio(readFileSync(archive));
  assert.equal(reloaded.manifest(), studio.manifest());
  reloaded.free();

  const dry = JSON.parse(cli("edit", archive, editFile, "--dry-run"));
  assert.equal(dry.changes.length, 2);
  const nativeEdited = join(temp, "native.json");
  cli("edit", archive, editFile, "--output", nativeEdited);
  assert.equal(studio.apply(readFileSync(editFile, "utf8")), true);
  assert.deepEqual(Buffer.from(studio.save(false)), readFileSync(nativeEdited));
  assert.equal(studio.undo(), true);
  assert.deepEqual(Buffer.from(studio.save(false)), original);
  assert.equal(studio.redo(), true);
  const clip = JSON.stringify({ x: 4, y: 4, width: 2, height: 2 });
  assert.deepEqual(JSON.parse(cli("copy", nativeEdited, "chromatic-lab", "signals", "4", "4", "2", "2")),
    JSON.parse(studio.copy("chromatic-lab", "signals", clip)));

  for (const [index, options] of [
    ["chromatic-lab", { format: "png" }],
    ["signals", { format: "png" }],
    ["console-grid", { format: "png" }],
    ["signal-light", { format: "png", frame: "dim" }, ["--frame", "dim"]],
    ["signal-light", { format: "oam", frame: "dim" }, ["--frame", "dim"]],
    ["signal-light", { format: "obj-chr" }],
    ["signal-light", { format: "obj-cgram" }],
    ["lab-font", { format: "png", text: "SFC" }, ["--text", "SFC"]],
    ["compass", { format: "png", bpp: 8 }, ["--bpp", "8"]],
    ["compass", { format: "indexed-png", bpp: 4 }, ["--bpp", "4"]],
    ["lab-tiles", { format: "chr" }],
    ["lab-chime", { format: "wav" }],
    ["signal-ping", { format: "wav" }],
    ["test-pulse", { format: "brr" }],
    ["test-pulse", { format: "png" }],
    ["vram-plan", { format: "png" }],
  ].entries()) {
    const [asset, flags, args = []] = options;
    const result = join(temp, `export-${index}`);
    cli("export", nativeEdited, asset, flags.format, result, ...args);
    assert.deepEqual(Buffer.from(studio.export(asset, JSON.stringify(flags))), readFileSync(result), asset + " " + flags.format);
  }

  const png = join(temp, "indexed.png");
  cli("export", nativeEdited, "compass", "indexed-png", png);
  const importedImage = join(temp, "image-import.json");
  cli("import-image", nativeEdited, png, "sheet", "new-colors", "--preserve-indices", "--output", importedImage);
  studio.importImage(readFileSync(png), JSON.stringify({ tileset: "sheet", palette: "new-colors", bpp: 4, preserve_indices: true }));
  assert.deepEqual(Buffer.from(studio.save(false)), readFileSync(importedImage));

  const brr = join(temp, "loop.brr");
  cli("export", importedImage, "test-pulse", "brr", brr);
  const importedAudio = join(temp, "audio-import.zip");
  cli("import-sample", importedImage, brr, "loop", "brr", "--loop-offset", "0", "--output", importedAudio);
  studio.importSample(readFileSync(brr), "loop", '"brr"', undefined, 0);
  assert.deepEqual(Buffer.from(studio.save(true)), readFileSync(importedAudio));

  const broken = JSON.parse(studio.manifest());
  broken.assets.compass.data.pixels[0] = 87;
  const brokenFile = write("broken.json", JSON.stringify(broken));
  const invalid = new wasm.Studio(readFileSync(brokenFile));
  assert.throws(() => cli("validate", brokenFile), (error) => {
    assert.equal(error.status, 2);
    assert.deepEqual(JSON.parse(error.stdout).diagnostics, JSON.parse(invalid.diagnostics()));
    return true;
  });
  invalid.free();
  studio.free();

  const directory = join(temp, "working-copy");
  mkdirSync(directory);
  const workingFile = join(directory, "studio.json");
  copyFileSync(projectFile, workingFile);
  const revision = JSON.parse(cli("validate", directory)).revision;
  const humanEdit = write("human.json", '[{"op":"name","name":"Human revision"}]');
  const machineUpdate = write("machine.json", '[{"op":"name","name":"Machine revision"}]');
  const concurrents = await Promise.all([humanEdit, machineUpdate].map((file) => new Promise((resolve) => {
    execFile(cliExecutable, ["edit", directory, file, "--expect", revision], (error, stdout, stderr) => {
      resolve(error ? { code: error.code, payload: JSON.parse(stderr) } : { code: 0, payload: JSON.parse(stdout) });
    });
  })));
  assert.deepEqual(concurrents.map((run) => run.code).sort(), [0, 4]);
  const success = concurrents.find((run) => run.code === 0);
  assert.equal(wasm.fingerprint(readFileSync(workingFile)), success.payload.saved_revision);
  assert.throws(() => cli("pack", projectFile, workingFile), (error) => error.status === 4);
  console.log("Native/WASM edits, formats, validation and conflict protection match.");
} finally {
  rmSync(temp, { recursive: true, force: true });
}
