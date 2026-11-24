import init, { Studio, fingerprint, inspect_rom, obj_size, palette_rgb, quantize_color, rle } from "./pkg/studio_web.js";
import { readFileBytes, saveFolderManifest } from "./folder-save.js";
import { assetDefaults, inspector, mapBrushes, names } from "./inspector.js";
import { $, button, checkbox, download, el, field, input, message, number, pretty, select, textarea } from "./ui.js";

let studio;
let project;
let selected;
let cleanRevision;
let dirty = false;
let directory;
let diskRevision;
let folderSaveSequence = 0;
let completedFolderSave = 0;
let playing = 0;
let clipboard;
let gesture;
let capture;
let selection;
let renderError;
let state = {};
const canvas = $("preview");
const context = canvas.getContext("2d");
const dialog = $("dialog");
const form = $("dialog-content");

const formats = {
  palette: ["png", "palette"],
  tile: ["png", "indexed-png", "chr"],
  tileset: ["png", "chr"],
  metatile: ["png"],
  map: ["png"],
  sprite: ["png", "oam", "obj-chr", "obj-cgram"],
  font: ["png"],
  sample: ["wav", "brr", "png"],
  sequence: ["wav", "png"],
  vram: ["png"],
};
const extensions = { "indexed-png": "png", "obj-chr": "chr", "obj-cgram": "cgram", palette: "pal" };

function status(text, error = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", error);
  if (dialog.open && error) {
    const details = $("dialog-error");
    if (details) details.textContent = text;
  }
}

async function guarded(callback) {
  try {
    await callback();
    return true;
  } catch (error) {
    if (error?.name !== "AbortError") status(message(error), true);
    return false;
  }
}

function modal(title, fields, label, submit, extra, onCancel) {
  const heading = el("h2", title, { id: "dialog-title" });
  const cancel = button(submit ? "Cancel" : "Close", (event) => {
    onCancel?.(event);
    if (!event.defaultPrevented) dialog.close();
  });
  const apply = submit ? button(label, null, { className: "primary", type: "submit" }) : null;
  const actions = el("div", [
    extra instanceof HTMLButtonElement ? extra : null,
    cancel, apply,
  ], { className: "actions" });
  form.replaceChildren(heading,
    extra instanceof HTMLButtonElement ? null : extra,
    ...fields.map(([label, node]) => field(label, node)),
    el("p", "", { id: "dialog-error", role: "alert" }), actions);
  dialog.setAttribute("aria-labelledby", heading.id);
  dialog.oncancel = onCancel ?? null;
  form.onsubmit = async (event) => {
    event.preventDefault();
    if (!submit) { dialog.close(); return; }
    if (apply.disabled) return;
    $("dialog-error").textContent = "";
    apply.disabled = true;
    if (await guarded(() => submit(fields.map((item) => item[1])))) {
      if (form.firstElementChild === heading) dialog.close();
    } else if (form.firstElementChild === heading) apply.disabled = false;
  };
  if (!dialog.open) dialog.showModal();
  return { cancel, apply };
}

function dataChanged() {
  project = JSON.parse(studio.manifest());
  dirty = studio.revision() !== cleanRevision;
  if (selected && !Object.hasOwn(project.assets, selected)) selectAsset(undefined);
  else refresh();
}

function commands(edits) {
  if (studio.apply(JSON.stringify(edits))) {
    stopAnimation();
    dataChanged();
    status("Edit applied");
  }
}

function selectAsset(id) {
  stopAnimation();
  selected = id;
  selection = null;
  const item = id && project.assets[id];
  const data = item?.data;
  state = {
    zoom: item?.kind === "tile" ? 32 : item?.kind === "metatile" || item?.kind === "sprite" || item?.kind === "font" ? 12 : item?.kind === "vram" ? 2 : ["sample", "sequence"].includes(item?.kind) ? 1 : 5,
    frame: data?.frames?.[0]?.id,
    layer: data?.layers?.at(-1)?.id,
    brush: item?.kind === "map" ? mapBrushes(project, data)[0]?.[0] ?? "" : Object.keys(project.assets).find((id) => project.assets[id].kind === "tile") ?? "",
    metadata: {}, palette: "", flipX: false, flipY: false, tool: "paint", paint: 1,
    grid: ["tile", "map", "metatile"].includes(item?.kind), cursor: { x: 0, y: 0 }, text: "",
  };
  refresh();
}

function load(bytes, { initial = false, folder = null, revision = null } = {}) {
  const next = bytes ? new Studio(bytes) : Studio.empty();
  studio?.free();
  studio = next;
  directory = folder;
  diskRevision = revision;
  project = JSON.parse(studio.manifest());
  cleanRevision = studio.revision();
  dirty = false;
  clipboard = null;
  selectAsset(initial ? "chromatic-lab" : Object.keys(project.assets).find((id) => project.assets[id].kind === "map") ?? Object.keys(project.assets)[0]);
  const diagnostics = JSON.parse(studio.diagnostics());
  status(diagnostics.length ? `Loaded · ${diagnostics.length} diagnostics` : initial ? "Demo loaded" : "Project ready");
}

function assets() {
  const filter = $("search").value.trim().toLowerCase();
  const groups = [];
  if (!filter) {
    const overview = button("Project settings", () => selectAsset(undefined), { className: "asset-item" });
    overview.setAttribute("aria-current", String(!selected));
    groups.push(overview);
  }
  for (const [kind, label] of Object.entries(names)) {
    const items = Object.entries(project.assets)
      .filter(([id, asset]) => asset.kind === kind && (`${label} ${id}`).toLowerCase().includes(filter))
      .map(([id]) => {
        const node = button(id, () => selectAsset(id), { className: "asset-item" });
        node.setAttribute("aria-current", String(id === selected));
        return node;
      });
    if (items.length) groups.push(el("h3", label), ...items);
  }
  $("assets").replaceChildren(...groups);
}

function refresh() {
  const item = selected ? project.assets[selected] : undefined;
  document.title = `${project.name} · SFC Studio`;
  $("project-title").textContent = project.name + (dirty ? " · Edited" : "");
  $("asset-title").textContent = selected ?? "Project settings";
  $("asset-kind").textContent = item ? names[item.kind] : "";
  $("export-asset").disabled = !item;
  $("undo").disabled = !studio.canUndo();
  $("redo").disabled = !studio.canRedo();
  const diagnostics = JSON.parse(studio.diagnostics());
  $("validation").textContent = diagnostics.length ? `Validation (${diagnostics.length})` : "Validation";
  assets();
  toolbar(item);
  try {
    inspector({
      state, project, id: selected, commands, guarded, refresh, modal, selectAsset,
      paletteRgb: palette_rgb, quantizeColor: quantize_color, objSize: obj_size,
    }, item);
  } catch (error) {
    if (!diagnostics.some((item) => item.severity === "error")) throw error;
    $("inspector").replaceChildren(el("p", "Repair the project through Tools → Apply JSON edits. See Validation for details."));
  }
  renderPreview();
}

function toolbar(item) {
  const root = $("toolbar");
  root.replaceChildren();
  if (!item) return;
  const { kind, data } = item;
  const controls = [];
  const control = (label, node) => el("label", [el("span", label), node]);
  const options = (label, values, value, change) => control(label, select(values, value, change));
  if (kind === "tile") {
    controls.push(options("Preview", [["", `Stored ${data.bpp}bpp`], [2, "2bpp"], [4, "4bpp"], [8, "8bpp"]], state.bpp,
      (value) => {
        state.bpp = value ? Number(value) : undefined;
        const paletteSize = project.assets[data.palette]?.data.colors.length ?? 1;
        state.paint = Math.min(state.paint, paletteSize - 1, (1 << Math.min(data.bpp, state.bpp ?? data.bpp)) - 1);
        refresh();
      }));
  }
  if (kind === "map") {
    if (!data.layers.some((layer) => layer.id === state.layer)) state.layer = data.layers[0]?.id;
    controls.push(options("Layer", data.layers.map((layer) => [layer.id, layer.id + (layer.visible ? "" : " (hidden)")]), state.layer, (layer) => {
      state.layer = layer;
      selection = null;
      refresh();
    }), options("Tool", [["paint", "Paint"], ["fill", "Fill"], ["select", "Select"]],
      state.tool, (tool) => { state.tool = tool; drawOverlay(); }),
    button("Copy", () => guarded(copy)), button("Paste", () => guarded(paste), { disabled: !clipboard }));
  }
  if (kind === "sprite") {
    if (!data.frames.some((frame) => frame.id === state.frame)) state.frame = data.frames[0]?.id;
    controls.push(options("Frame", data.frames.map((frame) => [frame.id, `${frame.id} · ${frame.duration_ms} ms`]), state.frame, (frame) => {
      stopAnimation(); state.frame = frame; refresh();
    }), button(playing ? "Stop" : "Play", animation, { disabled: data.frames.length < 2 }));
  }
  if (kind === "font") {
    const text = input(state.text, { placeholder: "Atlas", maxLength: 512 });
    text.addEventListener("input", () => { state.text = text.value; renderPreview(); });
    controls.push(control("Preview text", text));
  }
  if (["sample", "sequence"].includes(kind)) controls.push(button("Play audio", () => guarded(playAudio)));
  const grid = checkbox(state.grid);
  grid.onchange = () => { state.grid = grid.checked; drawOverlay(); };
  if (["tile", "map", "metatile"].includes(kind)) controls.push(control("Grid", grid));
  controls.push(options("Zoom", [.25, .5, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 24, 32].map((value) => [value, `${value}×`]), state.zoom, (zoom) => {
    state.zoom = Number(zoom); drawOverlay(); sizeCanvas();
  }));
  root.append(...controls);
}

function geometry() {
  const asset = selected && project.assets[selected];
  if (asset?.kind === "tile") return { stepX: 1, stepY: 1, width: 8, height: 8 };
  if (asset?.kind === "metatile") return { stepX: 8, stepY: 8, width: asset.data.width, height: asset.data.height };
  if (asset?.kind === "map") return { stepX: asset.data.cell_width * 8, stepY: asset.data.cell_height * 8, width: asset.data.width, height: asset.data.height };
  return undefined;
}

function renderPreview(animationFrame) {
  $("board").hidden = true;
  renderError = undefined;
  if (!selected) {
    $("stage-message").textContent = "Choose an asset or create one from the Project assets panel.";
    drawOverlay();
    return;
  }
  const { kind } = project.assets[selected];
  const options = [kind === "sprite" ? animationFrame ?? state.frame : undefined, kind === "font" && state.text ? state.text : undefined];
  try {
    let bytes;
    let notice = "";
    try {
      bytes = studio.preview(selected, ...options, kind === "tile" ? state.bpp : undefined);
    } catch (error) {
      if (kind !== "tile" || !state.bpp || !String(error).includes('"code":"tile_preview_bpp"')) throw error;
      notice = message(error) + ". Showing the stored bit depth.";
      bytes = studio.preview(selected, ...options, undefined);
    }
    const size = new DataView(bytes.buffer, bytes.byteOffset, 8);
    canvas.width = size.getUint32(0, true);
    canvas.height = size.getUint32(4, true);
    context.putImageData(new ImageData(new Uint8ClampedArray(bytes.buffer, bytes.byteOffset + 8), canvas.width, canvas.height), 0, 0);
    canvas.setAttribute("aria-label", geometry()
      ? `${selected} preview. Arrow keys move the cursor. Enter applies the brush or selection.`
      : `${selected} preview`);
    $("board").hidden = false;
    $("stage-message").textContent = notice;
    sizeCanvas();
  } catch (error) {
    renderError = message(error);
    $("stage-message").textContent = renderError.split("\n")[0];
  }
  drawOverlay();
}

function sizeCanvas() {
  canvas.style.width = `${canvas.width * state.zoom}px`;
  canvas.style.height = `${canvas.height * state.zoom}px`;
}

function rectangle(a, b) {
  return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(a.x - b.x) + 1, height: Math.abs(a.y - b.y) + 1 };
}

function drawOverlay() {
  const overlay = $("overlay");
  overlay.replaceChildren();
  overlay.classList.remove("grid");
  const grid = geometry();
  if (grid && !$("board").hidden) {
    const sx = grid.stepX * state.zoom;
    const sy = grid.stepY * state.zoom;
    overlay.style.setProperty("--grid-x", `${sx}px`);
    overlay.style.setProperty("--grid-y", `${sy}px`);
    overlay.classList.toggle("grid", state.grid && Math.min(sx, sy) >= 4);
    const rect = selection ?? rectangle(state.cursor, state.cursor);
    if (rect.x < grid.width && rect.y < grid.height) {
      const outline = el("div", null, { className: "selection" });
      Object.assign(outline.style, {
        left: `${rect.x * sx}px`, top: `${rect.y * sy}px`,
        width: `${Math.min(rect.width, grid.width - rect.x) * sx}px`, height: `${Math.min(rect.height, grid.height - rect.y) * sy}px`,
      });
      overlay.append(outline);
    }
  }
  const item = selected && project.assets[selected];
  if (item?.kind === "vram" && state.zoom >= 1 && !$("board").hidden) {
    for (const [id, region] of Object.entries(item.data.regions)) {
      const label = el("span", id, { className: "vram-label" });
      label.style.left = `${(region.start % 256) * state.zoom}px`;
      label.style.top = `${Math.floor(region.start / 256) * state.zoom}px`;
      overlay.append(label);
    }
  }
  $("coordinates").textContent = $("board").hidden ? "" : grid
    ? `${state.cursor.x}, ${state.cursor.y}  ·  ${grid.width}×${grid.height} ${grid.stepX === 1 ? "pixels" : "cells"}${selection ? `  ·  Selection ${selection.width}×${selection.height}` : ""}`
    : `${canvas.width}×${canvas.height} px`;
}

function cursorFrom(event) {
  const grid = geometry();
  const rect = canvas.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(grid.width - 1, Math.floor((event.clientX - rect.left) * grid.width / rect.width))),
    y: Math.max(0, Math.min(grid.height - 1, Math.floor((event.clientY - rect.top) * grid.height / rect.height))),
  };
}

function brushEdit({ x, y }) {
  const id = selected;
  const asset = project.assets[id];
  const { kind, data } = asset;
  if (kind === "tile") {
    const palette = project.assets[data.palette]?.data;
    const index = Math.min(state.paint, (palette?.colors.length ?? 1) - 1, (1 << Math.min(data.bpp, state.bpp ?? data.bpp)) - 1);
    return { op: "set_pixel", id, x, y, index };
  }
  const attributes = { palette: state.palette || null, flip_x: state.flipX, flip_y: state.flipY };
  if (kind === "metatile") return { op: "set_metatile_cell", id, x, y, cell: state.brush ? { ...attributes, tile: state.brush } : null };
  const cell = state.brush ? { ...attributes, asset: state.brush, metadata: state.metadata } : null;
  return { op: state.tool === "fill" ? "fill" : "place", id, layer: state.layer, x, y, cell };
}

function addStroke(from, to) {
  const increments = Math.max(Math.abs(to.x - from.x), Math.abs(to.y - from.y), 1);
  for (let i = 0; i <= increments; i++) {
    const x = Math.round(from.x + (to.x - from.x) * i / increments);
    const y = Math.round(from.y + (to.y - from.y) * i / increments);
    gesture.set(`${x},${y}`, brushEdit({ x, y }));
  }
}
canvas.addEventListener("pointerdown", (event) => {
  if (!geometry() || renderError || event.button !== 0 || capture !== undefined) return;
  canvas.focus({ preventScroll: true });
  canvas.setPointerCapture(event.pointerId);
  capture = event.pointerId;
  const point = cursorFrom(event);
  state.cursor = point;
  if (state.tool === "select") {
    gesture = point;
    selection = rectangle(point, point);
  } else if (state.tool === "fill") {
    selection = null;
    gesture = null;
  } else {
    selection = null;
    gesture = new Map();
    addStroke(point, point);
  }
  drawOverlay();
});

canvas.addEventListener("pointermove", (event) => {
  if (!geometry() || event.pointerId !== capture) return;
  const point = cursorFrom(event);
  if (state.tool === "select") selection = rectangle(gesture, point);
  else if (gesture) addStroke(state.cursor, point);
  state.cursor = point;
  drawOverlay();
});
canvas.addEventListener("pointerup", (event) => {
  if (event.pointerId !== capture) return;
  capture = undefined;
  const edits = state.tool === "select" ? [] : gesture ? Array.from(gesture.values()) : [brushEdit(state.cursor)];
  gesture = undefined;
  if (edits.length) guarded(() => commands(edits));
});
canvas.addEventListener("lostpointercapture", () => { capture = undefined; gesture = undefined; });
canvas.addEventListener("keydown", (event) => {
  const grid = geometry();
  if (!grid) return;
  const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  if (Object.hasOwn(arrows, event.key)) {
    const [dx, dy] = arrows[event.key];
    const previous = state.cursor;
    state.cursor = {
      x: Math.max(0, Math.min(grid.width - 1, previous.x + dx)),
      y: Math.max(0, Math.min(grid.height - 1, previous.y + dy)),
    };
    if (state.tool === "select" && event.shiftKey) {
      state.anchor ??= previous;
      selection = rectangle(state.anchor, state.cursor);
    } else { selection = null; state.anchor = undefined; }
    drawOverlay();
  } else if (event.key === "Enter" || event.key === " ") {
    if (state.tool === "select") {
      state.anchor ??= state.cursor;
      selection = rectangle(state.anchor, state.cursor);
      drawOverlay();
    } else guarded(() => commands([brushEdit(state.cursor)]));
  } else return;
  event.preventDefault();
});

function copy() {
  const rect = selection ?? rectangle(state.cursor, state.cursor);
  clipboard = JSON.parse(studio.copy(selected, state.layer, JSON.stringify(rect)));
  toolbar(project.assets[selected]);
  status(`Copied ${rect.width}×${rect.height} cells from ${state.layer}`);
}
function paste() {
  if (!clipboard) return;
  commands([{ op: "paste", id: selected, layer: state.layer, ...state.cursor, selection: clipboard }]);
  selection = rectangle(state.cursor, { x: state.cursor.x + clipboard.width - 1, y: state.cursor.y + clipboard.height - 1 });
  drawOverlay();
}

function stopAnimation() {
  if (playing) cancelAnimationFrame(playing);
  playing = 0;
}
function animation() {
  if (playing) { stopAnimation(); refresh(); return; }
  const start = performance.now();
  let displayed;
  function step(now) {
    const frame = studio.frameAt(selected, Math.floor(now - start));
    if (displayed !== frame) {
      renderPreview(frame);
      displayed = frame;
    }
    if (renderError) { stopAnimation(); toolbar(project.assets[selected]); }
    else playing = requestAnimationFrame(step);
  }
  playing = requestAnimationFrame(step);
  toolbar(project.assets[selected]);
}

function history(forward) {
  if (forward ? studio.redo() : studio.undo()) {
    stopAnimation();
    dataChanged();
    status(forward ? "Edit redone" : "Edit undone");
  }
}

function playAudio() {
  const { kind, data } = project.assets[selected];
  if (kind === "sample" && data.loop_start != null) {
    playSampleLoop(data);
    return;
  }
  const bytes = studio.export(selected, JSON.stringify({ format: "wav" }));
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  const audio = el("audio", null, { src: url, controls: true });
  modal(`Play ${selected}`, [], null, null, audio);
  stopAudioOnClose(audio, () => { audio.pause(); URL.revokeObjectURL(url); });
  audio.play().catch(() => {});
}

function stopAudioOnClose(control, stop) {
  dialog.addEventListener("close", function cleanup() {
    // A queued close event can belong to the previous use of the dialog.
    if (dialog.open && form.contains(control)) return;
    dialog.removeEventListener("close", cleanup);
    stop();
  });
}

function playSampleLoop(sample) {
  const pcm = studio.audioPreviewPcm(selected);
  const playback = new AudioContext();
  try {
    // Store one buffer frame per authored PCM sample, even at rates that
    // AudioBuffer does not accept. The source rate restores the authored timing.
    const buffer = playback.createBuffer(1, pcm.length, playback.sampleRate);
    buffer.copyToChannel(pcm, 0);
    const source = playback.createBufferSource();
    source.buffer = buffer;
    source.playbackRate.value = sample.sample_rate / buffer.sampleRate;
    source.loop = true;
    source.loopStart = sample.loop_start / buffer.sampleRate;
    source.connect(playback.destination);

    const toggle = button(playback.state === "running" ? "Pause" : "Play", () => guarded(() =>
      playback.state === "running" ? playback.suspend() : playback.resume()));
    playback.onstatechange = () => { toggle.textContent = playback.state === "running" ? "Pause" : "Play"; };
    source.start();
    modal(`Play ${selected}`, [], null, null, toggle);
    stopAudioOnClose(toggle, () => { void playback.close(); });
    playback.resume().catch(() => {});
  } catch (error) {
    void playback.close();
    throw error;
  }
}

function checkReplace() {
  return !dirty || window.confirm("Discard this session’s edits and open a different project?");
}

function prepareProjectOpen() {
  if (!checkReplace()) return;
  const openingStudio = studio;
  const openingRevision = studio.revision();
  return () => studio === openingStudio && (studio.revision() === openingRevision || checkReplace());
}

function chooseProjectFile() {
  const canReplace = prepareProjectOpen();
  if (!canReplace) return;
  const picker = $("project-file");
  picker.onchange = () => guarded(async () => {
    picker.onchange = null;
    const [file] = picker.files;
    picker.value = "";
    if (!file) return;
    const content = await readFileBytes(file);
    if (canReplace()) load(content);
  });
  picker.click();
}

async function openFolder() {
  if (!window.showDirectoryPicker) throw new Error("Folder access is unavailable here. Open studio.json or a project ZIP.");
  const canReplace = prepareProjectOpen();
  if (!canReplace) return;
  const folder = await window.showDirectoryPicker({ mode: "readwrite" });
  const handle = await folder.getFileHandle("studio.json");
  const content = await readFileBytes(await handle.getFile());
  if (canReplace()) load(content, { folder, revision: fingerprint(content) });
}

async function saveFolder(asNew, options) {
  if (!window.showDirectoryPicker) throw new Error("Folder access is unavailable here. Download JSON or ZIP instead.");
  const saveSequence = ++folderSaveSequence;
  const savingStudio = studio;
  const savingRevision = savingStudio.revision();
  const content = savingStudio.save(false);
  const expected = asNew ? null : diskRevision;
  const folder = asNew ? await window.showDirectoryPicker({ mode: "readwrite" }) : directory;
  const warning = await saveFolderManifest(folder, content, expected, options);
  if (studio !== savingStudio || saveSequence < completedFolderSave) return;
  completedFolderSave = saveSequence;
  directory = folder;
  diskRevision = fingerprint(content);
  cleanRevision = savingRevision;
  dataChanged();
  const saved = `Saved studio.json in ${folder.name}`;
  status(warning ? `${saved}. ${warning}` : saved, Boolean(warning));
}

function saveProject() {
  const supportsFolder = Boolean(window.showDirectoryPicker);
  const options = [
    ["json", "Download studio.json"],
    ["zip", "Download project ZIP"],
    ...(supportsFolder ? [["new-folder", "Save in a new folder"]] : []),
    ...(directory ? [["folder", `Save in ${directory.name}`]] : []),
  ];
  const mode = select(options, directory ? "folder" : "zip");
  let pendingSave;
  const { cancel, apply } = modal("Save project", [["Destination", mode]], "Save", async () => {
    if (mode.value.endsWith("folder")) {
      pendingSave = new AbortController();
      try {
        await saveFolder(mode.value === "new-folder", {
          signal: pendingSave.signal,
          beginCommit() {
            cancel.disabled = true;
            apply.textContent = "Saving…";
          },
        });
      } finally {
        pendingSave = undefined;
        cancel.disabled = false;
        apply.textContent = "Save";
      }
    } else {
      const archive = mode.value === "zip";
      download(studio.save(archive), archive ? "studio-project.zip" : "studio.json", archive ? "application/zip" : "application/json");
      status(archive ? "Downloaded project ZIP" : "Downloaded studio.json");
    }
  }, undefined, (event) => {
    if (cancel.disabled) event.preventDefault();
    else pendingSave?.abort();
  });
}

function exportAsset() {
  const item = project.assets[selected];
  const format = select(formats[item.kind], formats[item.kind][0]);
  const extras = [];
  let depth;
  if (["tile", "tileset"].includes(item.kind)) {
    depth = select([["", "Stored"], 2, 4, 8], state.bpp);
    extras.push([item.kind === "tile" ? "Bit depth override" : "Bit depth for CHR", depth]);
  }
  modal(`Export ${selected}`, [["Format", format], ...extras], "Download", () => {
    const variant = format.value;
    const options = {
      format: variant,
      frame: item.kind === "sprite" ? state.frame : undefined,
      text: item.kind === "font" && state.text ? state.text : undefined,
      bpp: (["chr", "indexed-png"].includes(variant) || variant === "png" && item.kind === "tile") && depth?.value ? Number(depth.value) : undefined,
    };
    const filename = `${selected}.${extensions[variant] ?? variant}`;
    download(studio.export(selected, JSON.stringify(options)), filename);
    status(`Downloaded ${filename}`);
  });
}

function addAsset() {
  const kind = select(Object.entries(names), "palette");
  const id = input("", { required: true, pattern: "[a-zA-Z0-9][a-zA-Z0-9._\\-]{0,63}" });
  const data = textarea(assetDefaults(project, kind.value), 8);
  kind.addEventListener("change", () => { data.value = pretty(assetDefaults(project, kind.value)); });
  modal("Add an asset", [["Type", kind], ["Asset ID", id], ["Initial asset data", data]], "Create asset", () => {
    if (Object.hasOwn(project.assets, id.value)) throw new Error("Asset ID already exists");
    commands([{ op: "put", id: id.value, asset: { kind: kind.value, data: JSON.parse(data.value) } }]);
    selectAsset(id.value);
  });
}

function fileInput(accept) { return input("", { type: "file", required: true, accept }); }

function toolsMenu() {
  const tool = select([
    ["new", "New project"], ["demo", "Open demo"], ["image", "Import PNG tiles"],
    ["sample", "Import WAV / BRR"], ["edits", "Apply JSON edits"], ["rom", "Inspect ROM header"], ["rle", "RLE compression"],
  ], "image");
  modal("Tools", [["Action", tool]], "Continue", () => {
    switch (tool.value) {
      case "new": if (checkReplace()) load(); break;
      case "demo": return openDemo();
      case "image": imageDialog(); break;
      case "sample": sampleDialog(); break;
      case "edits": {
        const edits = textarea([], 10);
        modal("Apply JSON edits", [["Edit array", edits]], "Apply edits", () => commands(JSON.parse(edits.value))); break;
      }
      case "rom": romDialog(); break;
      case "rle": codecDialog(); break;
    }
  });
}

function imageDialog() {
  const file = fileInput("image/png");
  const set = input("imported-tiles", { required: true });
  const palette = input(Object.keys(project.assets).find((id) => project.assets[id].kind === "palette") ?? "imported-colors", { required: true });
  const depth = select([2, 4, 8], 4);
  const preserve = checkbox(false);
  modal("Import PNG tiles", [
    ["PNG file", file], ["New tileset ID", set], ["Subpalette ID", palette], ["Bit depth", depth],
    ["Preserve PNG indices and create a new subpalette", preserve],
  ], "Import PNG", async () => {
    studio.importImage(await readFileBytes(file.files[0]), JSON.stringify({
      tileset: set.value, palette: palette.value, bpp: Number(depth.value), preserve_indices: preserve.checked,
    }));
    dataChanged(); selectAsset(set.value); status("PNG imported");
  });
}
function sampleDialog() {
  const file = fileInput(".wav,.brr");
  const id = input("sample", { required: true });
  const format = select(["wav", "brr"], "wav");
  const rate = number("", 1, 192000);
  const offset = number("", 0, 2160000);
  rate.required = offset.required = false;
  modal("Import audio sample", [["Audio file", file], ["Asset ID", id], ["Format", format], ["BRR source rate (optional)", rate], ["BRR loop byte offset (optional)", offset]], "Import sample", async () => {
    studio.importSample(await readFileBytes(file.files[0]), id.value, JSON.stringify(format.value),
      rate.value ? rate.valueAsNumber : undefined, offset.value ? offset.valueAsNumber : undefined);
    dataChanged(); selectAsset(id.value); status("Sample imported");
  });
}
function romDialog() {
  const file = fileInput(".smc,.sfc,.bin,.rom");
  const mapping = select([["lo_rom", "LoROM"], ["hi_rom", "HiROM"], ["ex_hi_rom", "ExHiROM"]], "lo_rom");
  modal("Inspect ROM header", [["ROM file", file], ["Mapping", mapping]], "Read header", async () => {
    const header = inspect_rom(await readFileBytes(file.files[0]), JSON.stringify(mapping.value));
    modal("ROM header", [], null, null, el("pre", pretty(JSON.parse(header))));
  });
}
function codecDialog() {
  const file = fileInput("");
  const mode = select([["compress", "Compress"], ["decompress", "Decompress"]], "compress");
  modal("Studio RLE v1", [["File", file], ["Mode", mode]], "Download result", async () => {
    const name = file.files[0].name;
    const decompress = mode.value === "decompress";
    download(rle(await readFileBytes(file.files[0]), decompress), decompress ? name.replace(/\.srl$/i, "") + ".decoded" : name + ".srl");
    status("Downloaded RLE result");
  });
}

async function openDemo() {
  const canReplace = prepareProjectOpen();
  if (!canReplace) return;
  const response = await fetch("./demo/studio.json");
  if (!response.ok) throw new Error("The demo project could not be loaded");
  const content = new Uint8Array(await response.arrayBuffer());
  if (canReplace()) load(content, { initial: true });
}

$("open").onclick = chooseProjectFile;
$("directory").onclick = () => guarded(openFolder);
$("save").onclick = saveProject;
$("tools").onclick = toolsMenu;
$("export-asset").onclick = exportAsset;
$("search").oninput = assets;
$("add").onclick = addAsset;
$("undo").onclick = () => history(false);
$("redo").onclick = () => history(true);
$("validation").onclick = () => {
  const diagnostics = JSON.parse(studio.diagnostics());
  modal("Validation", [], null, null, el("pre", diagnostics.length ? diagnostics.map((d) => `${d.severity.toUpperCase()} [${d.code}] ${d.path}\n${d.message}`).join("\n\n") : "No diagnostics"));
};
window.addEventListener("keydown", (event) => {
  if (dialog.open || !(event.ctrlKey || event.metaKey) || event.target.matches?.("input, textarea, select") || event.key.toLowerCase() !== "z") return;
  event.preventDefault();
  history(event.shiftKey);
});
window.addEventListener("beforeunload", (event) => { if (dirty) event.preventDefault(); });

if (await guarded(init)) {
  $("directory").hidden = !window.showDirectoryPicker;
  $("preview").setAttribute("aria-describedby", "coordinates");
  load();
  $("project-title").textContent = "Loading demo…";
  await guarded(openDemo);
  for (const node of document.querySelectorAll("[inert]")) node.inert = false;
} else $("project-title").textContent = "Studio could not start";
