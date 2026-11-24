# Studio project format v1

A project is a UTF-8 `studio.json` document with `version: 1`, a nonempty `name`, and an `assets` object. An existing directory with this manifest is a project. A portable ZIP contains exactly one root entry, `studio.json`. Studio writes a stored entry with fixed timestamp and permissions and accepts stored or deflated input. Binary exchange files are generated from the manifest or imported into it.

Canonical JSON uses two-space indentation and a final newline. Asset IDs and dictionary keys are sorted. Array order is meaningful and retained. Stable IDs are case-sensitive and match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. References use IDs. Renaming an ID requires updating its references in the same edit. Frame, layer and track IDs must be unique within their parent. Unknown versions are rejected before assets are decoded. Inputs and canonical manifests are limited to 64 MiB. Rendered images are limited to 4,096 pixels per side and 4 megapixels.

Each entry is an object with a `kind` discriminator and a `data` object.

```json
{
  "version": 1,
  "name": "Example",
  "assets": {
    "greens": {
      "kind": "palette",
      "data": {
        "colors": [0, 928, 16752, 32767],
        "transparent": 0
      }
    }
  }
}
```

## Graphics and layouts

- **palette** has `colors`, a list of 1–256 BGR555 integers, and `transparent`, an index or `null`. Red occupies bits 0–4, green bits 5–9, and blue bits 10–14. RGB8 converts to the nearest five-bit channel value and expands through bit replication for display. A palette asset represents one subpalette. The intended hardware slot is assigned by the artifact that uses it. Studio warns when an authoring subpalette marks a nonzero transparent index.
- **tile** has `bpp` (2, 4 or 8), `palette` (subpalette ID), and `pixels` (64 row-major indices). Visible index zero is available for authoring an opaque image. Consider the target graphics mode's treatment of zero before using that image on hardware.
- **metatile** has `width` and `height` in base tiles and `cells`, a row-major array. A cell is `null` or an object with `tile`, optional `palette` override, and `flip_x` and `flip_y` defaulting to false.
- **tileset** has ordered `tiles` and `metatiles` arrays of IDs. The CHR exporter uses the base tile order. Each member ID occurs once.
- **map** has a `tileset` ID, `width` and `height` in cells, and `cell_width` and `cell_height` in base tiles. Its `layers` array is ordered from back to front. Each layer has `id`, `visible` and `cells`, with exactly `width × height` row-major items. A cell is `null` or an object with an `asset` ID belonging to the tileset, optional `palette` override, and optional `flip_x` and `flip_y` booleans. The placed tile or metatile must match the cell dimensions. A map cell's palette override takes precedence over subpalette overrides inside a metatile. Maps, layers and individual cells can carry an optional `metadata` object with arbitrary JSON values. Store integers beyond ±(2⁵³−1) as strings to preserve precision in the browser.
- **sprite** has canvas `width` and `height` (1–256 pixels), a hardware `size_mode` (0–7), and ordered `frames`. Each frame has `id`, `duration_ms` (1–65535), and up to 128 `objects` in OAM order. Each object has signed `x` (−256 to 255), `y` (−128 to 255, taken modulo 256), `large` (chooses the large size within the mode), and row-major `tiles` (4bpp tile IDs). Other fields are `palette` (subpalette ID with index zero transparent), `palette_slot` (0–7), `priority` (0–3, relative to backgrounds on hardware), `flip_x` and `flip_y`. Earlier OAM entries win sprite overlaps in the preview. Vertical flip on a rectangular OBJ mirrors each square half independently. Scanline warnings cover the non-interlaced 256×239 active area and its 32 OBJ / 34 tile-fetch limits. The preview shows the full authored frame even when a line exceeds those limits.
- **font** has a `glyphs` object keyed by single Unicode scalar values, each with a `tile` ID and `advance` from 1 to 32 pixels. The text preview advances horizontally by this amount, with an 8-pixel line height. It reports missing glyphs. The atlas follows scalar order.
- **vram** has a `regions` object keyed by stable IDs. Each region has `start` and `bytes`, with an exclusive end, and `purpose` (`bg_tiles`, `bg_map`, `obj_tiles` or `other`). Their base alignments are 8,192, 2,048, 16,384 and 1 byte respectively. Regions must fit in 65,536 bytes without overlap. The visualization lays out addresses sequentially in rows of 256 bytes.

## Audio

- **sample** has `sample_rate` in Hz (1–192,000), signed 16-bit mono `pcm` (up to 3,840,000 samples), and `loop_start` as a sample index or `null`. A loop plays from its start through the end. Trimming preserves the loop start when that position is inside the kept interval.
- **sequence** has `usage` (`music` or `sfx`), `bpm` (20–600), `ticks_per_beat` (1–960) and 1–64 `tracks`. A track has `id`, `voice` and `notes`. A voice is `{"type":"square"}`, `{"type":"triangle"}`, or `{"type":"sample","asset":"sample-id","root_note":60}`. Notes have `tick`, `length`, `pitch` (MIDI 0–127) and `velocity` (0–127). Notes within a track are sorted and do not overlap. Preview is integer-mixed 32 kHz mono at a single tempo for up to 120 seconds. The sequencer is a driver-independent preview with simple oscillators and nearest-sample playback. Games implement their own driver conversion and timing constraints.

## Exchange formats

| Format | Representation |
| --- | --- |
| RGBA PNG | Rendered asset, straight RGBA8, with transparent pixels where applicable. A tile can require a chosen preview bit depth. Studio reports an error if its stored indices exceed that depth. |
| Indexed PNG | Single-tile export at 2, 4 or 8 bits per index. Import accepts tile sheets with dimensions divisible by 8. Preserve-indices mode keeps the input palette and index order, linked to a new Studio subpalette. Studio supports one fully transparent PNG entry. The palette is quantized to BGR555. General PNG import converts grayscale, RGB, indexed or alpha-bearing PNGs into an existing subpalette using squared distance in the five-bit RGB space, with ties resolved by the first index. Alpha below 128 uses the transparent entry. The generated IDs use `tileset-id-NNNN` with row-major tile numbering starting at zero. |
| CHR | SNES planar 8×8 tiles, with pairs of bitplanes interleaved by row. The leftmost pixel occupies bit 7. Output is 16, 32 or 64 bytes per tile. Mixed tileset bit depths require an explicit common depth. |
| Palette / OBJ CGRAM | Little-endian 16-bit BGR555 words. A plain palette writes its entries in order. Sprite CGRAM writes eight padded 16-entry OBJ slots (256 bytes) for CGRAM entries 128–255. |
| OBJ OAM and CHR | 544 bytes of OAM, and 16,384 bytes of 4bpp tile data arranged as two contiguous pages of 16×16 tiles. Load the pages at a 16 KiB-aligned OBJ base with a zero name-select register field. Use the sprite's `size_mode` for OBSEL. Empty slots use offscreen X. A deterministic first-fit packer puts larger rectangles first and reuses identical rectangles. Frames can have different page and palette data, so export matching files for each frame. |
| WAV | RIFF PCM format 1, 16-bit mono. One optional forward, continuous `smpl` loop ends on the final sample. |
| BRR | Raw S-DSP blocks of nine bytes for 16 samples, with filters and range encoded in each block header. Studio tests legal shifts and predictors and uses a history-independent first and loop-target block. One-shot exports pad a partial last audio block with silence and append a silent END block, which Studio omits from the imported PCM. Looping exports require both the loop start and loop length to be divisible by 16 samples and set END and LOOP on the last audio block. Store the sample rate and loop offset externally. Rate defaults to 32 kHz on import. The byte offset of a loop is `loop_start / 16 × 9`. Import requires that explicit offset for looping data. |
| Studio RLE | Magic bytes `53 52 4c 01` and a little-endian 32-bit decoded length. A packet header's low seven bits hold length minus one. A clear high bit precedes that many literal bytes. A set high bit precedes one byte to repeat. This is an interchange codec. An engine chooses whatever runtime codec it supports. |
| ROM header inspection | Read-only inspection uses explicit LoROM, HiROM or ExHiROM offsets. File length modulo 32 KiB detects a possible 512-byte copier header. The checksum-pair flag compares the two header words. It does not recompute a cartridge checksum. The report includes the reset vector and decodes the title as lossy UTF-8. |

## Edit transactions

`sfc-studio edit` accepts a JSON array of records. The operations run in order, and the project is validated as a whole before the batch is accepted. The core library types are the executable specification for the transaction and its result.

| `op` | Fields |
| --- | --- |
| `name` | `name` |
| `put` | `id`, `asset` as a complete `{kind,data}` object |
| `remove` | `id` |
| `set_color` | Palette `id`, `index`, `rgb` as three RGB8 integers |
| `set_transparency` | Palette `id`, `index` or `null` |
| `set_pixel` | Tile `id`, zero-based `x` and `y`, `index` |
| `set_metatile_cell` | Metatile `id`, `x`, `y`, `cell` or `null` |
| `resize_metatile`, `resize_map` | `id`, `width`, `height` and preserve cells inside the new top-left-anchored bounds |
| `set_map_settings` | Map `id`, `tileset`, `cell_width`, `cell_height`, and optional `metadata_json` containing a JSON object as text |
| `add_map_layer` | Map `id` and new `layer_id`. Appends an empty, visible layer. |
| `move_map_layer` | Map `id`, `layer` ID, and its new zero-based `index` in the layer order. |
| `remove_map_layer` | Map `id` and `layer` ID. The map must retain at least one layer after the batch. |
| `set_map_layer_settings` | Map `id`, current `layer` ID, resulting `layer_id`, `visible`, and optional `metadata_json` containing a JSON object as text |
| `place`, `fill` | Map `id`, `layer` ID, `x`, `y`, `cell` or `null`. Fill follows four-way neighbors identical to the starting cell, including its metadata. |
| `paste` | Map `id`, `layer` ID, destination `x`, `y`, `selection` with `width`, `height` and row-major `cells`. The full selection must fit. |
| `trim_sample` | Sample `id`, inclusive `start` and exclusive `end` sample offsets |

Omitting `metadata_json` from a settings edit preserves existing metadata. Pass `"{}"` to clear it.

Diagnostics contain `severity`, `code`, `path` and `message`. Paths within a manifest use JSON Pointer escaping. `diff` and `edit --dry-run` report an ordered list of JSON Pointer paths with `before` and `after` values. An added or deleted value omits the unavailable field. A changed array length reports the whole array, while equal-length arrays report individual changes.
