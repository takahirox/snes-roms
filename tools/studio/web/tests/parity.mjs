import assert from "node:assert/strict";
import { execFile, execFileSync } from "node:child_process";
import { webcrypto } from "node:crypto";
import { closeSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, openSync, readFileSync, readdirSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { deflateSync } from "node:zlib";

globalThis.crypto ??= webcrypto;

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

function pngChunk(type, data) {
  const body = Buffer.concat([Buffer.from(type), data]);
  let crc = 0xffffffff;
  for (const byte of body) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE((~crc) >>> 0);
  return Buffer.concat([length, body, checksum]);
}

// Model the browser's staged write over the same files that the real CLI sees.
function folderHandle(directory, { beforeWrite, beforeClose } = {}) {
  return {
    async *keys() { yield* readdirSync(directory); },
    async getFileHandle(name, { create = false } = {}) {
      const path = join(directory, name);
      if (create) closeSync(openSync(path, "a"));
      else if (!existsSync(path)) throw new DOMException("Missing file", "NotFoundError");
      return {
        path,
        async isSameEntry(other) { return path === other.path; },
        async getFile() { return new Blob([readFileSync(path)]); },
        async createWritable() {
          let pending;
          return {
            async write(content) {
              await beforeWrite?.();
              pending = content;
            },
            async close() {
              await beforeClose?.();
              writeFileSync(path, pending);
            },
            async abort() { pending = undefined; },
          };
        },
      };
    },
    async removeEntry(name) { unlinkSync(join(directory, name)); },
  };
}

try {
  // Load the unmodified workbench modules and generated browser glue in Node.
  write("package.json", '{"type":"module"}');
  mkdirSync(join(temp, "pkg"));
  const glue = join(temp, "pkg", "studio_web.js");
  copyFileSync(join(root, "_site", "pkg", "studio_web.js"), glue);
  const folderModule = join(temp, "folder-save.js");
  copyFileSync(join(root, "_site", "folder-save.js"), folderModule);
  const wasm = await import(pathToFileURL(glue).href);
  wasm.initSync({ module: readFileSync(join(root, "_site", "pkg", "studio_web_bg.wasm")) });
  const { saveFolderManifest } = await import(pathToFileURL(folderModule).href);

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

  const tiles = Array.from({ length: 4097 }, (_, i) => `tile-${i}`);
  const lastTile = tiles.at(-1);
  const glyphCount = 8193;
  const glyphs = Object.fromEntries(Array.from({ length: glyphCount }, (_, i) => [
    String.fromCodePoint(0x1000 + i), { tile: i === glyphCount - 1 ? lastTile : tiles[0], advance: 8 },
  ]));
  const largeProject = write("large-previews.json", JSON.stringify({ version: 1, name: "Preview limits", assets: {
    colors: { kind: "palette", data: { colors: [0, 31, 992], transparent: 0 } },
    ...Object.fromEntries(tiles.map((id) => [id, {
      kind: "tile", data: { bpp: 2, palette: "colors", pixels: Array(64).fill(id === lastTile ? 2 : 1) },
    }])),
    "wide-tiles": { kind: "tileset", data: { tiles, metatiles: [] } },
    "wide-font": { kind: "font", data: { glyphs } },
    "fast-loop": { kind: "sample", data: {
      sample_rate: 192000, pcm: [...Array(16).fill(0), -30000, 1000, 20000], loop_start: 16,
    } },
    "fast-note": { kind: "sequence", data: { usage: "sfx", ticks_per_beat: 1, bpm: 120, tracks: [{
      id: "sample", voice: { type: "sample", asset: "fast-loop", root_note: 0 },
      notes: [{ tick: 0, length: 30, pitch: 127, velocity: 127 }],
    }] } },
  } }));
  const large = new wasm.Studio(readFileSync(largeProject));
  const loopMessage = "BRR export requires a loop length divisible by 16 samples";
  const loopWarning = [{ severity: "warning", code: "brr_loop_length", path: "/assets/fast-loop/data", message: loopMessage }];
  assert.deepEqual(JSON.parse(cli("validate", largeProject)).diagnostics, loopWarning);
  assert.deepEqual(JSON.parse(large.diagnostics()), loopWarning);
  const exportError = [{ severity: "error", code: "invalid_input", path: "", message: loopMessage }];
  const invalidBrr = join(temp, "fast-loop.brr");
  assert.throws(() => cli("export", largeProject, "fast-loop", "brr", invalidBrr), (error) => {
    assert.equal(error.status, 2);
    assert.deepEqual(JSON.parse(error.stderr), { ok: false, diagnostics: exportError });
    return true;
  });
  assert.equal(existsSync(invalidBrr), false);
  assert.throws(() => large.export("fast-loop", '{"format":"brr"}'), (error) => {
    assert.deepEqual(JSON.parse(error), exportError);
    return true;
  });
  const fastWav = join(temp, "fast-note.wav");
  cli("export", largeProject, "fast-note", "wav", fastWav);
  const expectedWav = readFileSync(fastWav);
  assert.equal(expectedWav.length, 44 + 480000 * 2);
  assert.deepEqual(Buffer.from(large.export("fast-note", '{"format":"wav"}')), expectedWav);
  for (const [id, count] of [["wide-tiles", tiles.length], ["wide-font", glyphCount]]) {
    const rendered = join(temp, `${id}.png`);
    cli("render", largeProject, id, rendered);
    const png = readFileSync(rendered);
    assert.deepEqual(Buffer.from(large.export(id, '{"format":"png"}')), png);
    const preview = Buffer.from(large.preview(id));
    const width = preview.readUInt32LE(0);
    const height = preview.readUInt32LE(4);
    assert.deepEqual([width, height], [png.readUInt32BE(16), png.readUInt32BE(20)]);
    assert.ok(width <= 4096 && height <= 4096 && width * height <= 4 * 1024 * 1024);
    const columns = width / 8;
    const last = count - 1;
    const offset = 8 + (Math.floor(last / columns) * 8 * width + last % columns * 8) * 4;
    assert.deepEqual([...preview.subarray(offset, offset + 4)], [0, 255, 0, 255]);
  }
  large.free();

  const png = join(temp, "indexed.png");
  cli("export", nativeEdited, "compass", "indexed-png", png);
  const importedImage = join(temp, "image-import.json");
  cli("import-image", nativeEdited, png, "sheet", "new-colors", "--preserve-indices", "--output", importedImage);
  studio.importImage(readFileSync(png), JSON.stringify({ tileset: "sheet", palette: "new-colors", bpp: 4, preserve_indices: true }));
  assert.deepEqual(Buffer.from(studio.save(false)), readFileSync(importedImage));

  // A supported indexed image can expand into more than 64 MiB of canonical JSON.
  const side = 2048;
  const header = Buffer.alloc(13);
  header.writeUInt32BE(side, 0);
  header.writeUInt32BE(side, 4);
  header[8] = 8;
  header[9] = 3;
  const oversized = Buffer.concat([
    Buffer.from("89504e470d0a1a0a", "hex"),
    pngChunk("IHDR", header),
    pngChunk("PLTE", Buffer.from([0, 0, 0])),
    pngChunk("IDAT", deflateSync(Buffer.alloc(side * (side + 1)))),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
  const limited = new wasm.Studio(original);
  assert.equal(limited.apply('[{"op":"name","name":"Redo name"}]'), true);
  assert.equal(limited.undo(), true);
  const beforeImport = limited.revision();
  const limitDiagnostic = [{ severity: "error", code: "invalid_input", path: "", message: "Canonical project manifest exceeds 64 MiB" }];
  assert.throws(() => limited.importImage(oversized, JSON.stringify({
    tileset: "large-sheet", palette: "large-colors", bpp: 4, preserve_indices: true,
  })), (error) => {
    assert.deepEqual(JSON.parse(error), limitDiagnostic);
    return true;
  });
  assert.equal(limited.revision(), beforeImport);
  assert.equal(limited.canUndo(), false);
  assert.equal(limited.canRedo(), true);
  assert.deepEqual(Buffer.from(limited.save(false)), original);
  assert.deepEqual(Buffer.from(limited.save(true)), readFileSync(archive));
  limited.free();

  const oversizedPng = write("oversized-manifest.png", oversized);
  assert.throws(() => cli("import-image", projectFile, oversizedPng, "large-sheet", "large-colors",
    "--bpp", "4", "--preserve-indices", "--dry-run"), (error) => {
    assert.equal(error.status, 2);
    assert.deepEqual(JSON.parse(error.stderr), { ok: false, diagnostics: limitDiagnostic });
    return true;
  });
  assert.deepEqual(readFileSync(projectFile), original);

  // Two individually valid samples fit in compact JSON but exceed the canonical limit.
  const sample = { kind: "sample", data: { sample_rate: 32000, pcm: Array(2_800_000).fill(0) } };
  const compact = write("compact-oversized.json", JSON.stringify({
    version: 1, name: "Oversized samples", assets: { first: sample, second: sample },
  }));
  const unsavable = new wasm.Studio(readFileSync(compact));
  const diagnostics = JSON.parse(unsavable.diagnostics());
  assert.deepEqual(diagnostics.filter(({ severity }) => severity === "error"), limitDiagnostic);
  assert.throws(() => cli("validate", compact), (error) => {
    assert.equal(error.status, 2);
    const validation = JSON.parse(error.stdout);
    assert.equal(validation.ok, false);
    assert.deepEqual(validation.diagnostics, diagnostics);
    return true;
  });
  assert.throws(() => unsavable.save(true), (error) => {
    assert.deepEqual(JSON.parse(error), limitDiagnostic);
    return true;
  });
  const repairedZip = join(temp, "repaired.zip");
  assert.throws(() => cli("pack", compact, repairedZip), (error) => {
    assert.equal(error.status, 2);
    assert.deepEqual(JSON.parse(error.stderr), { ok: false, diagnostics: limitDiagnostic });
    return true;
  });
  assert.equal(existsSync(repairedZip), false);
  assert.equal(unsavable.apply('[{"op":"remove","id":"first"},{"op":"remove","id":"second"}]'), true);
  assert.deepEqual(JSON.parse(unsavable.diagnostics()), []);
  cli("pack", write("repaired.json", unsavable.save(false)), repairedZip);
  assert.deepEqual(Buffer.from(unsavable.save(true)), readFileSync(repairedZip));
  unsavable.free();

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

  copyFileSync(projectFile, workingFile);
  const browserStudio = new wasm.Studio(original);
  browserStudio.apply(readFileSync(humanEdit, "utf8"));
  const browserRevision = Buffer.from(browserStudio.save(false));
  browserStudio.free();
  const overlappingFolder = folderHandle(directory, {
    beforeClose() {
      // Enter the real CLI after the browser's last fingerprint check, while the
      // browser's staged data has yet to replace studio.json.
      assert.throws(() => cli("edit", workingFile, machineUpdate, "--expect", revision), (error) => {
        assert.equal(error.status, 4);
        const [diagnostic] = JSON.parse(error.stderr).diagnostics;
        return diagnostic.code === "conflict" && diagnostic.message.includes("holds a marker");
      });
      assert.deepEqual(readFileSync(workingFile), original);
    },
  });
  assert.equal(await saveFolderManifest(overlappingFolder, browserRevision, revision), undefined);
  assert.deepEqual(readFileSync(workingFile), browserRevision);
  assert.deepEqual(readdirSync(directory).sort(), ["studio.json", "studio.json.lock"]);

  const folder = folderHandle(directory);
  const heldMarker = join(directory, "studio.json.save-test.lock");
  writeFileSync(heldMarker, "");
  const savedRevision = wasm.fingerprint(browserRevision);
  await assert.rejects(saveFolderManifest(folder, original, savedRevision), /holds a marker/);
  assert.deepEqual(readFileSync(workingFile), browserRevision);
  assert.ok(existsSync(heldMarker));
  unlinkSync(heldMarker);
  cli("edit", directory, machineUpdate, "--expect", savedRevision);
  await assert.rejects(saveFolderManifest(folder, browserRevision, savedRevision), /changed on disk/);
  assert.equal(JSON.parse(readFileSync(workingFile)).name, "Machine revision");
  assert.deepEqual(readdirSync(directory).sort(), ["studio.json", "studio.json.lock"]);

  const newDirectory = join(temp, "new-folder");
  mkdirSync(newDirectory);
  const failedWrite = new Error("Simulated browser write failure");
  const failingFolder = folderHandle(newDirectory, { beforeWrite() { throw failedWrite; } });
  await assert.rejects(saveFolderManifest(failingFolder, original, null), failedWrite);
  assert.deepEqual(readdirSync(newDirectory), []);
  const controller = new AbortController();
  const canceledFolder = folderHandle(newDirectory, { beforeWrite() { controller.abort(); } });
  await assert.rejects(saveFolderManifest(canceledFolder, original, null, { signal: controller.signal }), { name: "AbortError" });
  assert.deepEqual(readdirSync(newDirectory), []);
  const newFolder = folderHandle(newDirectory);
  const newManifest = join(newDirectory, "studio.json");
  assert.equal(await saveFolderManifest(newFolder, original, null), undefined);
  assert.deepEqual(readFileSync(newManifest), original);
  await assert.rejects(saveFolderManifest(failingFolder, browserRevision, wasm.fingerprint(original)), failedWrite);
  assert.deepEqual(readFileSync(newManifest), original);

  writeFileSync(newManifest, "");
  await assert.rejects(saveFolderManifest(newFolder, original, null), /already has a studio.json/);
  assert.equal(readFileSync(newManifest).length, 0);
  unlinkSync(newManifest);

  const externalWrite = folderHandle(newDirectory, {
    beforeWrite() {
      writeFileSync(newManifest, browserRevision);
      throw failedWrite;
    },
  });
  await assert.rejects(saveFolderManifest(externalWrite, original, null), failedWrite);
  assert.deepEqual(readFileSync(newManifest), browserRevision);
  assert.deepEqual(readdirSync(newDirectory), ["studio.json"]);

  console.log("Native/WASM edits, formats, validation and conflict protection match.");
} finally {
  rmSync(temp, { recursive: true, force: true });
}
