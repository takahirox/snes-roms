import { fingerprint } from "./pkg/studio_web.js";

const markerPrefix = "studio.json.save-";
const markerSuffix = ".lock";

export async function readFileBytes(file) {
  if (file.size > 66 * 1024 * 1024) throw new Error("Input exceeds 66 MiB");
  return new Uint8Array(await file.arrayBuffer());
}

async function writeManifest(folder, content, expected, { signal, beginCommit }) {
  signal?.throwIfAborted();
  const isNew = expected === null;
  const original = expected ?? fingerprint(new Uint8Array());
  let handle;
  if (isNew) {
    try {
      await folder.getFileHandle("studio.json");
      throw new Error("The folder already has a studio.json. Open it first or choose another folder.");
    } catch (error) {
      if (error.name !== "NotFoundError") throw error;
    }
    signal?.throwIfAborted();
    handle = await folder.getFileHandle("studio.json", { create: true });
  } else handle = await folder.getFileHandle("studio.json");

  const ensureUnchanged = async () => {
    if (fingerprint(await readFileBytes(await handle.getFile())) !== original) {
      throw new Error("The folder’s studio.json changed on disk. Export a copy for comparison.");
    }
  };
  let writable;
  try {
    signal?.throwIfAborted();
    await ensureUnchanged();
    signal?.throwIfAborted();
    writable = await handle.createWritable({ mode: "exclusive" });
    signal?.throwIfAborted();
    await writable.write(content);
    signal?.throwIfAborted();
    await ensureUnchanged();
    signal?.throwIfAborted();
    // Closing publishes the staged file. Disable cancellation before calling it.
    beginCommit?.();
    await writable.close();
  } catch (error) {
    await writable?.abort().catch(() => {});
    if (isNew) {
      // Creating the handle exposes an empty file before the staged write commits.
      try {
        const current = await folder.getFileHandle("studio.json");
        if (await handle.isSameEntry(current) && (await current.getFile()).size === 0) {
          await folder.removeEntry("studio.json");
        }
      } catch (cause) {
        if (cause.name !== "NotFoundError") {
          throw new Error("Folder save failed. Could not clean up the empty studio.json.", { cause });
        }
      }
    }
    throw error;
  }
}

export async function saveFolderManifest(folder, content, expected, { signal, beginCommit } = {}) {
  signal?.throwIfAborted();
  // Publish a unique marker before checking for competitors. The CLI follows
  // the same protocol, so a writer arriving after this check sees our marker.
  const marker = markerPrefix + crypto.randomUUID() + markerSuffix;
  await folder.getFileHandle(marker, { create: true });
  let committed = false;
  let cleanupWarning;
  try {
    for await (const name of folder.keys()) {
      signal?.throwIfAborted();
      if (name !== marker && name.startsWith(markerPrefix) && name.endsWith(markerSuffix)) {
        throw new Error("Another Studio save holds a marker in this folder. Export a copy or review the project before retrying.");
      }
    }
    await writeManifest(folder, content, expected, { signal, beginCommit });
    committed = true;
  } finally {
    try {
      await folder.removeEntry(marker);
    } catch (cause) {
      cleanupWarning = `Could not remove the save marker ${marker}.`;
      if (!committed) throw new Error(`Folder save failed. ${cleanupWarning}`, { cause });
    }
  }
  return cleanupWarning;
}
