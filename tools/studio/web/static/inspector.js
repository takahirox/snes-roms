import { $, button, checkbox, clone, details, el, field, hex, input, number, pretty, rgb, select, textarea } from "./ui.js";

const row = (...children) => el("div", children, { className: "actions" });
const bitDepths = [2, 4, 8];
const assetOption = (id) => [id, id];
const optional = [["", "Use default"]];
const purposes = [["bg_tiles", "BG tiles"], ["bg_map", "BG map"], ["obj_tiles", "OBJ tiles"], ["other", "Other"]];

export const names = {
  map: "Maps",
  tileset: "Tilesets",
  metatile: "Metatiles",
  tile: "Tiles",
  palette: "Subpalettes",
  sprite: "Sprites & animation",
  font: "Bitmap fonts",
  sample: "Samples",
  sequence: "Music & sound effects",
  vram: "VRAM layouts",
};

export function assetDefaults(project, kind) {
  const first = (kind) => Object.keys(project.assets).find((id) => project.assets[id].kind === kind) ?? "";
  switch (kind) {
    case "palette": return { colors: [0, 8609, 24538, 32767], transparent: 0 };
    case "tile": return { bpp: 4, palette: first("palette"), pixels: Array(64).fill(0) };
    case "metatile": return { width: 2, height: 2, cells: Array(4).fill(null) };
    case "tileset": return { tiles: [], metatiles: [] };
    case "map": return {
      tileset: first("tileset"), width: 8, height: 8, cell_width: 1, cell_height: 1,
      layers: [{ id: "ground", visible: true, cells: Array(64).fill(null) }],
    };
    case "sprite": return { width: 32, height: 32, size_mode: 0, frames: [{ id: "idle", duration_ms: 160, objects: [] }] };
    case "font": return { glyphs: { A: { tile: first("tile"), advance: 8 } } };
    case "sample": return { sample_rate: 32000, pcm: Array(16).fill(0), loop_start: null };
    case "sequence": return { usage: "music", bpm: 120, ticks_per_beat: 96, tracks: [{ id: "lead", voice: { type: "triangle" }, notes: [] }] };
    case "vram": return { regions: {} };
  }
}

export function mapBrushes(project, map) {
  const tileset = project.assets[map.tileset];
  if (tileset?.kind !== "tileset") return [];
  return [...tileset.data.tiles, ...tileset.data.metatiles].filter((id) => {
    const asset = project.assets[id];
    const size = asset?.kind === "tile" ? [1, 1] : [asset?.data?.width, asset?.data?.height];
    return size[0] === map.cell_width && size[1] === map.cell_height;
  }).map(assetOption);
}

export function inspector(app, asset) {
  const { state, project, id, commands, guarded, refresh, paletteRgb, quantizeColor, objSize, modal, setMapLayer } = app;
  const root = $("inspector");
  root.replaceChildren();
  if (!asset) {
    const name = input(project.name, { required: true });
    root.append(form(() => commands([{ op: "name", name: name.value }]), field("Project name", name), button("Rename", null, { type: "submit" })));
    return;
  }
  const { kind, data } = asset;
  const ids = (kind) => Object.keys(project.assets).filter((id) => project.assets[id].kind === kind).map(assetOption);
  const choice = (kind, value, empty) => select([...(empty ? optional : []), ...ids(kind)], value);
  const edit = (op, fields) => commands([{ op, id, ...fields }]);
  const update = (change) => {
    const next = clone(data);
    change(next);
    edit("put", { asset: { kind, data: next } });
  };

  function form(submit, ...children) {
    const node = el("form", children);
    node.addEventListener("submit", (event) => {
      event.preventDefault();
      guarded(submit);
    });
    return node;
  }

  const apply = () => button("Apply", null, { type: "submit" });
  const openAsset = (asset) => app.selectAsset(asset);
  const palettes = () => ids("palette");
  const swatches = (palette, limit) => el("div", palette.colors.slice(0, limit).map((color, index) => {
    const swatch = button(index, () => { state.paint = index; refresh(); }, {
      title: `Index ${index} · BGR555 $${color.toString(16).padStart(4, "0").toUpperCase()}`,
    });
    swatch.style.setProperty("--swatch", hex(paletteRgb(color)));
    swatch.setAttribute("aria-pressed", String(index === state.paint));
    if (palette.transparent === index) swatch.textContent += " ·";
    return swatch;
  }), { className: "swatches" });

  function dimensions(map = false) {
    const width = number(data.width, 1, 512);
    const height = number(data.height, 1, 512);
    return details("Grid size", form(() => edit(map ? "resize_map" : "resize_metatile", {
      width: width.valueAsNumber, height: height.valueAsNumber,
    }), field("Columns", width), field("Rows", height), button("Resize", null, { type: "submit" })));
  }

  if (kind === "palette") {
    const index = Math.min(state.paint, data.colors.length - 1);
    const color = input(hex(paletteRgb(data.colors[index])), { type: "color" });
    const transparent = checkbox(data.transparent === index);
    const sample = input("#88ffb0", { type: "color" });
    const depth = select(bitDepths, 4);
    const result = el("output", "");
    root.append(swatches(data, 256), el("p", `Index ${index} · BGR555 $${data.colors[index].toString(16).padStart(4, "0").toUpperCase()}`),
      form(() => commands([
        { op: "set_color", id, index, rgb: rgb(color.value) },
        { op: "set_transparency", id, index: transparent.checked ? index : data.transparent === index ? null : data.transparent },
      ]), field("RGB color", color), field("Transparent index", transparent), apply()),
      row(
        button("Add color", () => guarded(() => update((d) => d.colors.push(0))), { disabled: data.colors.length >= 256 }),
        button("Remove last", () => guarded(() => {
          update((d) => { if (d.transparent === d.colors.length - 1) d.transparent = null; d.colors.pop(); });
        }), { disabled: data.colors.length <= 1 }),
      ),
      details("Quantize", form(() => {
        result.textContent = `Nearest entry: ${quantizeColor(JSON.stringify(data), Uint8Array.of(...rgb(sample.value), 255), Number(depth.value))}`;
      }, field("Input color", sample), field("Bit depth", depth), row(button("Find index", null, { type: "submit" }), result))),
    );
  } else if (kind === "tile") {
    const palette = project.assets[data.palette]?.data;
    const depth = select(bitDepths, data.bpp);
    const paletteId = choice("palette", data.palette);
    if (palette) root.append(swatches(palette, 1 << Math.min(data.bpp, state.bpp ?? data.bpp)));
    root.append(form(() => update((d) => {
      d.bpp = Number(depth.value);
      d.palette = paletteId.value;
    }), field("Stored bit depth", depth), field("Subpalette", paletteId), apply()),
    button("Edit subpalette", () => openAsset(data.palette), { disabled: !palette }));
  } else if (kind === "metatile") {
    const brush = select([["", "Empty"], ...ids("tile")], state.brush, (value) => { state.brush = value; });
    const palette = select([...optional, ...palettes()], state.palette, (value) => { state.palette = value; });
    const flipX = checkbox(state.flipX);
    const flipY = checkbox(state.flipY);
    flipX.onchange = () => { state.flipX = flipX.checked; };
    flipY.onchange = () => { state.flipY = flipY.checked; };
    root.append(details("Brush", field("Tile", brush), field("Subpalette override", palette), field("Flip horizontally", flipX), field("Flip vertically", flipY)), dimensions());
  } else if (kind === "tileset") {
    const lists = ["tiles", "metatiles"].map((key) => {
      const available = ids(key === "tiles" ? "tile" : "metatile");
      const choose = select(available.filter(([id]) => !data[key].includes(id)), "");
      const members = data[key].map((member, index) => row(
        button(member, () => openAsset(member)),
        button("↑", () => guarded(() => update((d) => {
          [d[key][index - 1], d[key][index]] = [d[key][index], d[key][index - 1]];
        })), { disabled: index === 0, title: "Move earlier" }),
        button("Remove", () => guarded(() => update((d) => d[key].splice(index, 1)))),
      ));
      return details(key === "tiles" ? "Base tiles" : "Metatiles", ...members, row(choose,
        button("Add", () => guarded(() => { if (choose.value) update((d) => d[key].push(choose.value)); }))));
    });
    root.append(...lists);
  } else if (kind === "map") {
    const metadataField = (layer, rows) => el("textarea", null, {
      defaultValue: app.mapMetadata(layer), rows, spellcheck: false,
    });
    const changedMetadata = (field) => field.value === field.defaultValue ? undefined : field.value;
    const choices = mapBrushes(project, data);
    if (state.brush && !choices.some(([id]) => id === state.brush)) state.brush = "";
    const layer = data.layers.find((layer) => layer.id === state.layer) ?? data.layers[0];
    const selectBrush = select([["", "Empty"], ...choices], state.brush, (value) => { state.brush = value; });
    const flipX = checkbox(state.flipX);
    const flipY = checkbox(state.flipY);
    flipX.onchange = () => { state.flipX = flipX.checked; };
    flipY.onchange = () => { state.flipY = flipY.checked; };
    const cellData = textarea(state.metadata, 3);
    cellData.onchange = () => guarded(() => {
      const metadata = JSON.parse(cellData.value);
      if (!metadata || Array.isArray(metadata) || typeof metadata !== "object") throw new Error("Cell metadata must be a JSON object");
      state.metadata = metadata;
    });
    const palette = select([...optional, ...palettes()], state.palette, (value) => { state.palette = value; });
    root.append(details("Brush", field("Artwork", selectBrush), field("Subpalette override", palette), field("Flip horizontally", flipX), field("Flip vertically", flipY), field("Cell metadata", cellData),
      button("Pick from cursor", () => guarded(() => {
        const { x, y } = state.cursor;
        const cell = x < data.width && y < data.height ? layer?.cells[y * data.width + x] : null;
        if (!cell) throw new Error("The active layer has no artwork at the cursor");
        Object.assign(state, { brush: cell.asset, palette: cell.palette ?? "", flipX: cell.flip_x, flipY: cell.flip_y, metadata: cell.metadata ?? {} });
        refresh();
      }))));
    const visible = checkbox(layer?.visible);
    const layerId = input(layer?.id, { required: true });
    const layerMeta = layer ? metadataField(layer.id, 3) : null;
    const layerIndex = data.layers.indexOf(layer);
    const moveLayer = (direction) => update((d) => {
      const other = layerIndex + direction;
      [d.layers[layerIndex], d.layers[other]] = [d.layers[other], d.layers[layerIndex]];
    });
    root.append(details("Layers", layer ? form(() => {
      edit("set_map_layer_settings", {
        layer: layer.id, layer_id: layerId.value, visible: visible.checked, metadata_json: changedMetadata(layerMeta),
      });
      setMapLayer(layerId.value);
      refresh();
    }, field("Layer ID", layerId), field("Visible", visible), field("Layer metadata", layerMeta), apply()) : null,
    row(
      button("Add", () => modal("Add map layer", [
        ["Layer ID", input("", { required: true })],
      ], "Add layer", ([newId]) => {
        update((d) => d.layers.push({ id: newId.value, visible: true, cells: Array(d.width * d.height).fill(null) }));
        setMapLayer(newId.value); refresh();
      })),
      button("Earlier", () => guarded(() => moveLayer(-1)), { disabled: layerIndex <= 0 }),
      button("Later", () => guarded(() => moveLayer(1)), { disabled: layerIndex < 0 || layerIndex >= data.layers.length - 1 }),
      button("Remove", () => guarded(() => update((d) => d.layers.splice(layerIndex, 1))), { disabled: data.layers.length <= 1 }),
    )));
    const tileset = choice("tileset", data.tileset);
    const cellWidth = number(data.cell_width, 1, 512);
    const cellHeight = number(data.cell_height, 1, 512);
    const metadata = metadataField(undefined, 4);
    root.append(dimensions(true), details("Map settings", form(() => edit("set_map_settings", {
      tileset: tileset.value, cell_width: cellWidth.valueAsNumber, cell_height: cellHeight.valueAsNumber,
      metadata_json: changedMetadata(metadata),
    }), field("Tileset", tileset), field("Cell width in tiles", cellWidth), field("Cell height in tiles", cellHeight), field("Map metadata", metadata), apply())));
  } else if (kind === "sprite") {
    const width = number(data.width, 1, 256);
    const height = number(data.height, 1, 256);
    const sizes = select(Array.from({ length: 8 }, (_, mode) => {
      const size = (large) => Array.from(objSize(mode, large)).join("×");
      return [mode, `${mode} · ${size(false)} / ${size(true)}`];
    }), data.size_mode);
    root.append(details("OBJ layout", form(() => update((d) => Object.assign(d, {
      width: width.valueAsNumber, height: height.valueAsNumber, size_mode: Number(sizes.value),
    })), field("Canvas width", width), field("Canvas height", height), field("Size mode", sizes), apply())));
    const frameIndex = Math.max(0, data.frames.findIndex((frame) => frame.id === state.frame));
    const frame = data.frames[frameIndex];
    if (frame) {
      const frameId = input(frame.id, { required: true });
      const duration = number(frame.duration_ms, 1, 65535);
      const objects = frame.objects.map((object, index) => row(button(`OBJ ${index + 1} · (${object.x}, ${object.y})`, () => objectDialog(object, index))));
      root.append(details("Frame", form(() => {
        update((d) => Object.assign(d.frames[frameIndex], { id: frameId.value, duration_ms: duration.valueAsNumber }));
        state.frame = frameId.value; refresh();
      }, field("Frame ID", frameId), field("Duration (ms)", duration), apply()),
      row(button("Add frame", () => modal("Add animation frame", [["Frame ID", input("", { required: true })]], "Add frame", ([id]) => {
        update((d) => d.frames.splice(frameIndex + 1, 0, { id: id.value, duration_ms: 160, objects: clone(frame.objects) }));
        state.frame = id.value; refresh();
      })), button("Remove frame", () => guarded(() => update((d) => d.frames.splice(frameIndex, 1))), { disabled: data.frames.length <= 1 })),
      ...objects, button("Add OBJ", () => objectDialog(null, frame.objects.length))));
    }
    function objectDialog(object, index) {
      const tiles = ids("tile").filter(([id]) => project.assets[id].data.bpp === 4);
      const obj = object ?? {
        x: 0, y: 0, large: false, tiles: [], palette: palettes()[0]?.[0] ?? "",
        palette_slot: 0, priority: 0, flip_x: false, flip_y: false,
      };
      const large = checkbox(obj.large);
      const x = number(obj.x, -256, 255);
      const y = number(obj.y, -128, 255);
      const palette = choice("palette", obj.palette);
      const slot = number(obj.palette_slot, 0, 7);
      const priority = number(obj.priority, 0, 3);
      const flipX = checkbox(obj.flip_x);
      const flipY = checkbox(obj.flip_y);
      const order = number(index + 1, 1, object ? frame.objects.length : frame.objects.length + 1);
      const tileGrid = el("div", null, { className: "obj-tiles" });
      function showTiles(values) {
        const [width, height] = objSize(data.size_mode, large.checked);
        tileGrid.style.setProperty("--columns", width / 8);
        tileGrid.replaceChildren(...Array.from({ length: (width * height) / 64 }, (_, i) => {
          const tile = select(tiles, values[i] ?? tiles[0]?.[0]);
          tile.setAttribute("aria-label", `Tile ${i + 1}`);
          return tile;
        }));
      }
      const tileValues = () => Array.from(tileGrid.children, (node) => node.value);
      showTiles(obj.tiles);
      large.onchange = () => showTiles(tileValues());
      modal(object ? `Edit OBJ ${index + 1}` : "Add OBJ", [
        ["X", x], ["Y", y], ["Large object", large], ["Subpalette", palette], ["Palette slot", slot], ["Priority", priority],
        ["Flip horizontally", flipX], ["Flip vertically", flipY], ["OAM order", order], ["Tiles in row order", tileGrid],
      ], "Apply OBJ", () => update((d) => {
        if (object) d.frames[frameIndex].objects.splice(index, 1);
        d.frames[frameIndex].objects.splice(order.valueAsNumber - 1, 0, {
          x: x.valueAsNumber, y: y.valueAsNumber, large: large.checked, tiles: tileValues(),
          palette: palette.value, palette_slot: slot.valueAsNumber, priority: priority.valueAsNumber, flip_x: flipX.checked, flip_y: flipY.checked,
        });
      }), object ? button("Remove OBJ", () => guarded(() => {
        update((d) => d.frames[frameIndex].objects.splice(index, 1));
        $("dialog").close();
      })) : null);
    }
  } else if (kind === "font") {
    for (const [glyph, value] of Object.entries(data.glyphs)) {
      root.append(row(button(glyph, () => glyphDialog(glyph)), button("Edit tile", () => openAsset(value.tile))));
    }
    root.append(button("Add glyph", () => glyphDialog(null)));
    function glyphDialog(glyph) {
      const character = input(glyph, { required: true });
      const tile = choice("tile", data.glyphs[glyph]?.tile ?? ids("tile")[0]?.[0]);
      const advance = number(data.glyphs[glyph]?.advance ?? 8, 1, 32);
      modal(glyph ? "Edit glyph" : "Add glyph", [["Character", character], ["Tile", tile], ["Advance pixels", advance]], "Apply glyph", () => {
        if (Array.from(character.value).length !== 1) throw new Error("Enter one Unicode character");
        if (character.value !== glyph && Object.hasOwn(data.glyphs, character.value)) throw new Error("Glyph already exists");
        update((d) => {
          if (glyph) delete d.glyphs[glyph];
          d.glyphs[character.value] = { tile: tile.value, advance: advance.valueAsNumber };
        });
      }, glyph ? button("Remove glyph", () => guarded(() => {
        update((d) => delete d.glyphs[glyph]); $("dialog").close();
      })) : null);
    }
  } else if (kind === "sample") {
    const rate = number(data.sample_rate, 1, 192000);
    const loop = number(data.loop_start, 0, data.pcm.length - 1);
    loop.required = false;
    const start = number(0, 0, data.pcm.length - 1);
    const end = number(data.pcm.length, 1, data.pcm.length);
    root.append(el("p", `${data.pcm.length.toLocaleString()} samples · ${(1000 * data.pcm.length / data.sample_rate).toFixed(1)} ms`),
      form(() => update((d) => { d.sample_rate = rate.valueAsNumber; d.loop_start = loop.value === "" ? null : loop.valueAsNumber; }),
        field("Sample rate (Hz)", rate), field("Loop start (optional)", loop), apply()),
      details("Trim", form(() => edit("trim_sample", { start: start.valueAsNumber, end: end.valueAsNumber }),
        field("First sample", start), field("End (exclusive)", end), button("Trim", null, { type: "submit" }))));
  } else if (kind === "sequence") {
    const usage = select([["music", "Music"], ["sfx", "Sound effect"]], data.usage);
    const bpm = number(data.bpm, 20, 600);
    const ticks = number(data.ticks_per_beat, 1, 960);
    root.append(form(() => update((d) => Object.assign(d, {
      usage: usage.value, bpm: bpm.valueAsNumber, ticks_per_beat: ticks.valueAsNumber,
    })), field("Usage", usage), field("Tempo (BPM)", bpm), field("Ticks per beat", ticks), apply()));
    for (const [index, track] of data.tracks.entries()) {
      root.append(details(track.id, el("p", `${track.notes.length} notes · ${track.voice.type}`),
        row(button("Edit track", () => trackDialog(track, index)), button("Add note", () => noteDialog(index, null))),
        ...track.notes.map((note, i) => button(`${note.pitch} · tick ${note.tick} · ${note.length} ticks`, () => noteDialog(index, i)))));
    }
    root.append(button("Add track", () => trackDialog(null, data.tracks.length)));
    function trackDialog(track, index) {
      const trackId = input(track?.id ?? "", { required: true });
      const type = select(["triangle", "square", "sample"], track?.voice.type ?? "triangle");
      const sample = choice("sample", track?.voice.asset ?? ids("sample")[0]?.[0]);
      const root = number(track?.voice.root_note ?? 60, 0, 127);
      modal("Sequence track", [["Track ID", trackId], ["Voice", type], ["Sample asset (for sample voice)", sample], ["Root MIDI note", root]], "Apply track", () => {
        const voice = type.value === "sample" ? { type: "sample", asset: sample.value, root_note: root.valueAsNumber } : { type: type.value };
        update((d) => { d.tracks[index] = { id: trackId.value, voice, notes: track?.notes ?? [] }; });
      }, track ? button("Remove track", () => guarded(() => {
        update((d) => d.tracks.splice(index, 1)); $("dialog").close();
      })) : null);
    }
    function noteDialog(trackIndex, index) {
      const track = data.tracks[trackIndex];
      const note = track.notes[index];
      const last = track.notes.at(-1);
      const tick = number(note?.tick ?? (last ? last.tick + last.length : 0), 0, 1152000);
      const length = number(note?.length ?? 24, 1, 1152000);
      const pitch = number(note?.pitch ?? 60, 0, 127);
      const velocity = number(note?.velocity ?? 96, 0, 127);
      modal("MIDI note", [["Start tick", tick], ["Length in ticks", length], ["Pitch", pitch], ["Velocity", velocity]], "Apply note", () => update((d) => {
        const notes = d.tracks[trackIndex].notes;
        notes[index ?? notes.length] = { tick: tick.valueAsNumber, length: length.valueAsNumber, pitch: pitch.valueAsNumber, velocity: velocity.valueAsNumber };
        notes.sort((a, b) => a.tick - b.tick);
      }), note ? button("Remove note", () => guarded(() => {
        update((d) => d.tracks[trackIndex].notes.splice(index, 1)); $("dialog").close();
      })) : null);
    }
  } else if (kind === "vram") {
    for (const [id, region] of Object.entries(data.regions)) {
      root.append(row(button(id, () => regionDialog(id)), el("span", `$${region.start.toString(16).toUpperCase()} · ${region.bytes} B`)));
    }
    root.append(button("Add region", () => regionDialog(null)));
    function regionDialog(id) {
      const region = data.regions[id];
      const regionId = input(id, { required: true });
      const start = number(region?.start ?? 0, 0, 65535);
      const bytes = number(region?.bytes ?? 2048, 1, 65536);
      const purpose = select(purposes, region?.purpose ?? "bg_tiles");
      modal("VRAM region", [["Region ID", regionId], ["Start byte", start], ["Length in bytes", bytes], ["Purpose", purpose]], "Apply region", () => {
        if (regionId.value !== id && Object.hasOwn(data.regions, regionId.value)) throw new Error("Region ID already exists");
        update((d) => {
          if (id) delete d.regions[id];
          Object.defineProperty(d.regions, regionId.value, { enumerable: true, value: {
            start: start.valueAsNumber, bytes: bytes.valueAsNumber, purpose: purpose.value,
          } });
        });
      }, id ? button("Remove region", () => guarded(() => {
        update((d) => delete d.regions[id]); $("dialog").close();
      })) : null);
    }
  }
  const advanced = el("details", [el("summary", "Asset JSON")]);
  advanced.addEventListener("toggle", () => {
    if (!advanced.open || advanced.children.length > 1) return;
    const dataField = textarea(data, 9);
    advanced.append(form(() => edit("put", { asset: { kind, data: JSON.parse(dataField.value) } }), field("Asset data", dataField), apply()));
  });
  root.append(advanced, row(button("Delete asset", () => modal("Delete asset", [], "Delete", () => edit("remove", {}), el("p", `Delete ${id} from this project?`)))));
}
