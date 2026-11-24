# 夜鳴き鐘 (Yonaki Kane) — engine

The scenario format and the story are in `DESIGN.md`; this file is the engine: the ROM (`src/yonaki/`), the
build (`tools/yonaki/`) and the tests (`tests/yonaki/`).

## Build and test

```
make yonaki          # build/yonaki/yonaki.sfc from data/yonaki/scenario + endings.txt + pictures + sound
make yonaki-test     # Snes9x fixture and real routes, then bsnes fixture replay
python3 -I tests/yonaki/bsnes.py --real  # replay fixture and real routes on bsnes
make yonaki-clean
YONAKI_FLAGS="--allow-missing-art --strict" make yonaki
```

`tools/yonaki/build.py` options: `--scenario DIR` (default `data/yonaki/scenario`, every `*.txt` sorted by
name), `--endings FILE` (default: `endings.txt` beside the scenario directory), `--allow-missing-art` (a missing
background is black, a missing silhouette a plain figure), `--strict` (warnings are errors),
`--unknown-sound-error`, `--out DIR`, `--omake-endings N` (default 10), `--debug-start` (review builds).
Diagnostics go to stderr and `build/yonaki/report.txt`; `build/yonaki/previews/` has every picture as the SNES
shows it.  Python needs Pillow and numpy: `python3 -m pip install --target tools/vendor/pylib pillow numpy`
(the tools add that directory to `sys.path`, so `python3 -I` works).

Review tools:
- `python3 -I tests/yonaki/shots.py LABEL ...` — pages from a label (review ROM, はじめから (new game) starts there);
  `--ending E05` follows the route to that ending; `--follow`, `--pages N`, `--all-labels`.  PNGs and an
  `index.png` contact sheet under `build/yonaki-shots/<label>/`.
- `python3 -I tests/yonaki/routes.py [build/yonaki]` — the choice path to every ending (exact VM rules), in an
  order that can be played with the battery kept (unlocks first).
- `python3 -I tools/yonaki/pictures.py bell bus` — dither comparison (FS / Bayer / none) in `build/yonaki/dither/`.

## Files

| file | role |
|---|---|
| `tools/yonaki/script.py` | parser, text normalization, wrapping (kinsoku), checks, VM simulation / routes |
| `tools/yonaki/build.py` | encoding, bank layout, `const.inc`, `data.inc`, `yonaki.cfg`, `layout.json` |
| `tools/yonaki/pictures.py` | photos → 240 colours (112 + their translucent-figure versions where silhouettes appear) + 8bpp tiles; silhouettes → masks (cached in `build/yonaki/cache`) |
| `tools/yonaki/font.py`, `logo.py` | Shinonome 12-dot glyphs; the title logo |
| `tools/yonaki/romfix.py` | header checks and checksum |
| `tools/yonaki/audio.py` (+ music, songs, sfx, spc) | the sound driver and music (music agent) |
| `src/yonaki/yonaki.s` | header, reset, NMI, DMA queue, PPU setup |
| `src/yonaki/frame.inc` | frame scheduler, wait conditions, pad sampling and carry |
| `src/yonaki/text.inc` | 2bpp text bitmap: glyphs with shadow, strings, highlight |
| `src/yonaki/pic.inc` | colour math / effects (Tick), fades, picture loads, silhouette compositing |
| `src/yonaki/vm.inc` | the script VM (all ops), typewriter, waits, choices |
| `src/yonaki/ui.inc` | title, START menu, bookmarks screen, 結末の一覧 (list of endings), chapter card, ending |
| `src/yonaki/save.inc` | battery SRAM |
| `src/yonaki/audio.inc` | SPC700 upload and commands |

## Screen

Mode 4.  BG1: 8bpp photo, 256×192 at screen y 16–207 (map rows 2–25 → tiles 0–767; rows outside → tile 768,
which is blank).  BG2: 2bpp text bitmap 240×192 (30×24 tiles) at screen x 8, y 16, tiles with the priority
bit (above BG1).  The BG3 map pointer (offset-per-tile in mode 4) points at zero words.  No OBJ.

CGRAM 0–15: 0 black (backdrop), BG2 palette 0 = 1 text white, 2 shadow, 3 grey; palette 1 (highlighted line) =
5 yellow-white, 6 shadow, 7; silhouettes 8/9 white (ghost) body/rim, 10/11 red, 12/13 blue.  CGRAM 16–255: the
photo's 240 colours.  A photo that silhouettes appear on has 112 colours (CGRAM 16–127) and, at CGRAM 144–255, the
same colours seen through a translucent blue figure (`pictures.TINTS`: 60% of (36, 52, 176)); the white (45% of
(232, 236, 255)) and red versions are in a second block (PicTable+75) and replace them while such a figure is on
screen.

Text: 18 full-width characters (216 px) per line from screen x 20, 12 lines, line n at screen y 18 + 16n
(each line is exactly two tile rows, so a choice is highlighted by switching those map rows to palette 1).
Glyphs are white with a 1-pixel dark shadow right, down and diagonal.

Colour math: the photo can be dimmed under text by subtracting a fixed colour from BG1 (`DIM_TEXT`, ramped 1 a frame;
0 now, so text sits on the full-brightness photo and relies on the glyph shadow);
`@fx dark` and silhouette updates take it to 31 (black).  The silhouette colours 8–13 are raised by about half
the dim (table `SilComp`) so solid figures keep their brightness under text and still go black in
the dark; a translucent figure is part of the photo and dims with it.
Flashes and the white transition add a fixed colour to every layer.  Shake moves BG1; the ripple is HDMA
channel 7 on BG1HOFS (a 2-px sine, table in bank 0); mosaic uses MOSAIC on BG1; fades use master brightness.

## Memory

VRAM (word addresses): `$0000-$5FFF` BG1 tiles 0–767; `$6000-$601F` BG2 tiles 0–3 = zero (also BG1 tile 768
and the BG3 offset row); `$6020-$769F` bitmap tiles 4–723; `$7800` BG1 map; `$7C00` BG2 map.

WRAM: `$0000-$00FF` direct page, `$0100-$1DFF` variables, `$1E00-$1FFF` stack; `$7E:2000` text bitmap
(11 520 bytes, tile (c, r) at (r·30 + c)·16); `$7E:5000` BG2 map shadow; `$7E:5800` the bitmap under the
START menu; `$7F:0000-$BFFF` the photo tiles (silhouettes are composited here).

ROM: LoROM, FastROM ($30), up to 4 MiB; code and tables in bank 0 (`$00:8000`), data banks read at `$81:8000…`.
Bank order: font (32 bytes a glyph: 12 rows as words, bit 15 leftmost, byte 24 = width; 1024 glyphs a bank),
script (ops never cross a bank; a bank ends with GOTO to the next), resume tables (text id / choice id → op
address), pictures (48 KiB each, 2 KiB rows that never cross a bank), palettes, packed silhouette masks and
the SPC image. Each mask row stores the first covered column and the number of tiles through its last covered
column, then 16 bytes per tile (8 pairs of cover and rim bytes). An empty row stores two zero bytes. Each
packed mask fits in one bank. The ROM size is rounded up to 512 KiB / 1 / 2 / 4 MiB.

SRAM (8 KiB at `$70:0000`, all little-endian, every block with a 16-bit sum and its complement):

| offset | content |
|---|---|
| `$0000` | global: "YNKG", version, text speed, endings seen (32 bits), global flags (32 bits), the names (+16, 20 bytes), sum at +252 |
| `$0100/$0200/$0300` | bookmarks 1–3: "YNKS", version, build id, kind (1 paragraph / 2 choice), text or choice id, paragraph to redraw before a choice, picture, song, chapter, dark, ripple, ambience, 4 silhouette slots, 512 local flags, the names (+128), sum at +252 |
| `$0400` | read marks: "YNKR", build id, one bit per paragraph ($0408–$1FFB, 57 248 paragraphs), sum at $1FFC (kept up to date one bit at a time) |

At power-on the global block and the read marks are checked (magic, version, sum, ranges, build id for the
marks) and reset when broken; a bookmark is checked field by field when it is listed and shown as empty when
broken or made by another build (the build id is a hash of the script and the font).

## Frame scheduling

The VM runs opcodes in order until one needs a frame boundary or a blocking wait. Its call stack retains the
continuation while `WaitEvent` advances frames and checks one named condition. The VM resumes on the frame
that satisfies the condition. Immediate opcodes can publish several requests during the same frame. Register
effects use state fields, uploads use dirty flags and a DMA list, and sound uses a FIFO. Each channel keeps
its existing capacity and ordering.

Every `WaitFrame`, including frames used by menus and long drawing routines, follows the same sequence.

1. Reset the glyph and silhouette work counters, then run `Tick` to advance effects and prepare PPU shadows.
2. Build DMA jobs from the UI palette, photo palette, tint override, BG2 map, dirty photo spans, and dirty
   text rows, in that order. Spans and rows are scheduled from top to bottom within each bitmap. Jobs that
   do not fit the 3072-byte budget remain pending for a later frame.
3. Pump one command in request order when the SPC is ready. The eight-entry FIFO keeps earlier commands
   when full. Repeated song or ambience requests for the current selection are coalesced at the producer.
4. Publish the DMA list and park for NMI. NMI consumes the published jobs, applies the PPU shadows, and
   records its end line in `nmi_end_line_max` and any overrun in `vblank_overrun_count`.
5. Sample the pad after auto-joypad read completes, then evaluate the active condition in the main thread.

Long work is paced at 5 glyphs and 12 silhouette tiles per frame. Page clears and ROM-to-WRAM picture loads
run at the start of a frame, with at most 8 KiB per picture-load slice. The menu bitmap copy runs in eight
slices. Boot remains fixed at 150 frames, including the SPC upload. `PacedWait` carries newly pressed
buttons across drawing slices and preserves the input snapshot of its caller. The paragraph wait and choice
entry flush those carried presses before accepting input. Held buttons and the direction repeat timer
continue to follow the sampled pad.

### Blocking operations

| Operation | Completion and input |
|---|---|
| `TEXT` typewriter | Waits one frame per typing step. An A edge reveals the rest of the text. Held B sets fast-forward for read text. |
| Paragraph and page-chunk advance | Checks A, held B over read text, then START. The mark blinks while waiting. If fast-forward is active and B is held on entry, the page gets two full frames before advance. |
| `CHOICE` | Draws the options and flushes drawing input. Checks Up then Down with repeat when there are multiple options, followed by an A edge and a START edge. Menu return resumes the wait. |
| `PAGE`, `BG`, and silhouette batches | Page clears, forced-blank DMA, and picture compositing use paced frame boundaries. Fades and mosaic use fixed frame steps. Silhouette batches wait for full dim. Streaming waits for dirty flags and the DMA list to drain, with the existing 600-frame watchdog. A white transition waits for colour addition to decay after uploading. |
| `FX` | Shake waits 24 frames, flash waits for colour addition to reach zero, dark waits for full dim, light waits 40 frames, and ripple changes state immediately. `@fx wait N` completes after N frames or on the first sampled frame with fast-forward active and B held. |
| `CHAPTER`, `END`, `HALT` | Chapter cards drain uploads and fade in before waiting up to 150 frames for A. Endings keep their 40-frame dim and 90-frame display delay, then wait for A or START before fading out. HALT fades out and returns to the title. |

The bytecode and compiler are shared with the previous runtime. The sound FIFO advances during every wait,
including two-frame text fast-forward and timed waits. Fast-forward stops on unread text and at choices.
Entering a menu happens after the active input wait returns, so the menu can run its own frame waits.

Picture changes: `fade` = brightness down (2 frames a step), forced blank, ROM → WRAM rows, composite,
WRAM → VRAM 16 KiB a frame, brightness up; `cut` = the same without the fades; `white` = colour addition to
white, upload in V-blank slices, back; `mosaic` = mosaic up, fade, load, fade in while the mosaic goes down.
A `@bg` clears the page and the silhouettes; `@sil` lines right after it go into the new picture before it
appears. Consecutive `@sil` and `@silclear` ops are batched. A batch dims BG1 to black, restores the previous
figures' tile spans from ROM, composites the new slots in order, and uploads the union of the old and new
spans before restoring brightness. The engine keeps two 24-entry span tables in WRAM. Each entry is a
first column and exclusive end column, or zero for an empty row. Full picture loads use full-width spans.
The upload wait checks the one-word photo flag and the DMA queue. The span cursor can stay at the end of
the table after the final transfer.

Silhouettes are staged per scene: for each background / character / position the scenario uses, the background
photo was edited by image generation to hold the person in a fitting pose (sitting in a bus seat behind the seat
backs, kneeling at a tray, waist-deep in the tub), painted flat magenta (`assets/yonaki/stage.json`,
`tools/yonaki/gen_stage.py`, `assets/yonaki/src/stage/`).  The build finds the background of each `@sil` by
following the script's flow (`script.bg_flow`), cuts the magenta out as the mask and keeps its place: SilTable
holds the top row and the op the column.  Without a staged picture a `@sil` falls back to the standing figure
(`assets/yonaki/src/sil/`) on the bottom edge at its l / c / r column.

Figures are translucent: compositing keeps the photo's pixel under the figure and sets its bit 7 (colour + 128,
the tinted version), rim included, so it has no outline.  Only one tint is in CGRAM at a time: white
before red before blue among the slots (`PickTint`); a figure of another colour, or any figure on a picture without
tinted colours (black, white, the title), is drawn solid in colours 8–13 as before.

### Silhouette performance

The Snes9x 1.63 fixture `effects` trace was recorded on the baseline (`6da6766`) and on the packed-span
renderer. The frame counts below follow `hide_bg1` from assertion to release. They include the ramp into
black. Restoration and upload bytes come from the ROM-derived tile counts and the live WRAM span tables,
at 64 bytes per tile. Compositor visits count tiles passed to the paced pixel loop, including empty tiles
inside a span. The separate tint palette job is 224 bytes per batch on these fixture photos.

| Batch | ROM → WRAM bytes | Compositor tile visits | WRAM → VRAM photo bytes | Frames in `ApplySils` |
|---|---:|---:|---:|---:|
| First figure | 5,760 → 0 | 60 → 29 | 5,760 → 1,856 | 13 → 9 |
| Add two figures with a tint change | 34,560 → 1,856 | 420 → 306 | 34,560 → 28,288 | 63 → 42 |
| Remove the centre figure | 34,560 → 28,288 | 360 → 277 | 34,560 → 28,288 | 58 → 43 |
| Clear remaining figures | 29,440 → 26,944 | 0 → 0 | 29,440 → 26,944 | 18 → 17 |
| Total | 104,320 → 57,088 | 840 → 612 | 104,320 → 85,376 | 152 → 111 |

At the 12-tile quota, the four batches take 67 → 50 compositor waits. The photo DMA payload drops from
208,640 to 142,464 bytes across both directions, about 529,000 master clocks saved at eight per byte,
before per-job setup. The fixture's cut and fade use the same forced-blank durations. The white transition
holds full white for 38 frames, down from 42, with the same ramp durations. The mosaic sequence takes
83 frames in both builds. [Snes9x 1.63 DMA timing implementation](https://github.com/snes9xgit/snes9x/blob/1.63/dma.cpp)

Across the 106 production masks, the cached cover and rim bytes pack from 154,512 to 102,732 ROM bytes,
including row headers. All 106 packed masks decoded byte-for-byte to the original cover and rim data
in a ROM audit. The builder derives spans from the existing mask cache. This adds 74 bytes of runtime
variables overall and reduces occupied ROM from 78 to 76 banks within the same 4 MiB image.

- **Exact tile runs.** In the three-figure fixture batch the upload spans cover 442 tiles in 20 jobs.
  Exact coverage would use 288 tiles in 49 jobs. That saves 9,856 bytes but requires tracking multiple
  runs per row and scheduling their setup within the 24-job and 3,072-byte VBlank limits.
- **Incremental redraw.** Removing the centre figure changes only 29 of the 442 uploaded tiles in that
  batch. Tracking changed slots could narrow the update. Each dirty tile would still need the surviving
  overlaps replayed in slot order, and a tint selection change can change the drawing mode of a slot whose
  position and silhouette are unchanged. Retaining one span per row keeps restoration and upload bounded
  by 24 jobs per direction and avoids retaining additional photo or mask copies in WRAM.

`make yonaki-test` passed on both builds. Snes9x passed all 11 checks, including all 20 production
endings. All 73 existing Snes9x captures and all 41 final battery images were identical across the
builds. The fixture's full `effects` trace went from 1,301 to 1,256 frames. A separate fixture run with
overlapping, right-clipped figures and a white-to-red tint change matched all 31 screenshots.

Both bsnes 115 runs passed all 20 standard replays. Every battery image matched Snes9x, with no more
than 2 RGB levels of difference per channel across 51 captures. The Snes9x suite recorded zero VBlank
overruns or deferred DMA jobs. Peak NMI end lines were 251 → 248 on the fixture and 255 → 257 on
production routes, within the NTSC VBlank range of 225–261. Peak DMA was 3,072 bytes on the production
routes and 3,072 → 3,008 on the `effects` trace. A read-only check of the bsnes `effects` trace's
serialized WRAM found the same DMA peaks and NMI end lines, with zero overruns or deferrals. The
production C02 replay reached line 257 and 3,040 DMA bytes on both cores, with zero overruns or deferrals.

### PPU layout alternatives

The current Mode 4 layout uses 49,152 photo bytes, 11,520 text bytes, 64 shared blank tile bytes and
4,096 map bytes. That leaves 704 of the 65,536 VRAM bytes. The active-width BG budget is 32 visible
8-pixel columns per layer, with an edge fetch when scrolled. The shipped layout uses zero OBJ slots
or OBJ fetches. These estimates use Yonaki's assets and the documented SNES hardware.
[Nintendo SNES Development Manual, Book I](https://archive.org/details/SNESDevManual)

| Layout | VRAM and scanline budget | Presentation considerations |
|---|---|---|
| Mode 4 with OBJ masks | The free bytes fit at most 22 4bpp tiles by size, before OBJ base alignment. At one 8×8 OBJ per nonempty tile, the three-figure fixture would need 295 OAM entries and 23 slivers on its busiest scanline. One production figure reaches 17 slivers. The hardware allows 32 OBJ and 34 slivers per scanline, with 128 OAM entries across the screen. | Larger OBJ can reduce OAM entries but consume fetches for blank slivers. Photo shake, mosaic and ripple would have to keep the overlay aligned. |
| Mode 1 with BG1 photo, BG2 masks and BG3 text | Full-size 4bpp photo and overlay cost 24,576 bytes each. 2bpp text costs 11,520 and three maps cost 6,144. The 66,816-byte total exceeds VRAM by 1,280 bytes before blank tiles. Sparse overlay tiles can reduce storage and use up to 32 visible columns on that BG. | A 4bpp photo requires per-tile palette quantization. Text priority and palette assignments also need rework. |
| Mode 3 with an 8bpp photo and a 4bpp second BG | Photo, text and two maps alone total 76,288 bytes before blank tiles or overlay art. A separate mask BG would need a different mode. | Preserving the current photo and text shapes would require factoring or sharing tile data. |
| Main/subscreen colour math with an OBJ or BG mask | Mask storage and fetches follow the selected layout. A mask on the subscreen alone still requires that layer's tile and map or OAM storage. | Half-add gives a 50% mix. The authored tints use 45% or 60%, and the hardware math path also drives the existing dim and flashes. Matching the palette rounding and the effects would require additional work. |

The limits and blend behaviour can also be checked in the pinned core's sources.
[bsnes OBJ evaluator](https://github.com/libretro/bsnes/blob/63ee22f7af8f5d1ada295c2c98fd7bf261fa62a7/bsnes/sfc/ppu/object.cpp)
[bsnes screen compositor](https://github.com/libretro/bsnes/blob/63ee22f7af8f5d1ada295c2c98fd7bf261fa62a7/bsnes/sfc/ppu/screen.cpp)

Small tile-local pose or prop updates could reuse the packed spans with incremental redraw. Two changed
8bpp tiles cost 128 VRAM bytes, against a theoretical 48 tile transfers per VBlank at the current payload
limit before text, palette and job costs. The compositor quota is 12 tile visits per frame. Palette-only
animation could transfer as little as a few CGRAM words, provided it reserves palette indices whose
other uses should animate together. Large moving figures would need measured overlap and DMA budgets
before choosing a frame rate.

### Future scheduling capabilities

A future concurrent cue could carry a target frame and a script-order sequence number, with waits for a
specific upload or sound dispatch. DMA admission would still honor the byte budget. The SPC command handoff
could serve as a dispatch signal, with separate acknowledgement for playback completion. An additional skip
policy would need to define which cues are delivered, which can be coalesced, and how to reach the same final
text, graphics and audio state at the next wait. The current scheduler uses one continuation and the existing
per-channel requests to preserve the timing of the current bytecode.

## Script VM

Ops (byte code, `tools/yonaki/build.py`): `TEXT id16 lines8 <string>`, `BLANK`, `PAGE`, `BG pic mode`,
`SIL key sil x colour` (sil `$FF` = remove the key), `SILCLEAR`, `BGM n` (`$FE` stop, `$FF` fade),
`SE n`, `AMB k` (`$FF` off), `FX kind arg16`, `SET/CLR flag16`, `SETG/CLRG g`, `IF cond16 addr24`,
`GOTO addr24`, `CHOICE id16 n {nconds conds… addr24 lines8 <string>}`, `END ending`, `CHAPTER ch`, `HALT`.
A condition word: bit 15 negated, bit 14 global (index < 32 a global flag, 32 + e ending e seen), else a local flag.
Strings: `$00` end, `$01` new line, `$02` next page chunk (+ line count), `$03` / `$04` the player's names (主人公の
名字 "the protagonist's family name" / ヒロインの名前 "the heroine's given name": the script writes the default names 結城 / 千尋, `script.NAME_VARS`; lines are laid out as if
each were `NAME_MAX` = 4 characters; `ReadCode` hands out the name's glyphs from `names`), `$10-$EF` the 224 most frequent
glyphs, `$F0-$FF xx` the others (up to 4320 glyphs).

Text flow: a paragraph that does not fit the rest of the page starts a new page; one longer than 12 lines is
split into page chunks at build time.  After each paragraph the VM waits for A with a blinking mark: ▽-like
(paragraph) or a double mark when the next paragraph will start a new page (it looks ahead over silhouette /
sound / flag ops and jumps).  An empty line in the script adds a blank line when the page is not empty.
Speeds (START menu): 遅い (slow) 1 glyph / 2 frames, 普通 (normal) 1, 速い (fast) 2, 瞬間 (instant) all.  A finishes the paragraph at once.
B held: read paragraphs (read marks in SRAM) are shown at once and passed after 2 frames; it stops at the first
unread one.  Choices are drawn under the text (a blank line first), each after its letter Ａ, Ｂ, … in the order shown, up / down / A; after a choice the page
clears.  START at a paragraph wait or a choice: しおりをはさむ (insert a bookmark) / 文字の速さ (text speed) / タイトルへ (to the title) / もどる (back).
A bookmark resumes at the paragraph (shown again on a fresh page) or at the choice (the paragraph before it
is redrawn first).

Name entry (`NameEntry`, ui.inc, state `ST_NAME`): はじめから asks for 主人公の名字 and ヒロインの名前 (1-4 glyphs each,
shown with ＿ for the free places, the fixed family name 早瀬 grey before the heroine's name and （名字） ("family name") /
（名前） ("given name") after them) on a dark screen: 8 rows of 10 characters a page (かな, カナ, 3 pages of name
kanji, `NameGrid` from build.py `NAME_PAGES` / `NAME_KANJI`) and the commands かな カナ 漢字 けす 決定 (hiragana, katakana, kanji, erase, confirm).  Arrows move
(wrapping), A types / runs the command, B deletes the last character (on an empty name: the first name again, or
back to the title), L / R change the page, START decides.  The names are checked at power-on and at a bookmark load
(length and glyph range; a broken one becomes its default) and saved in the global block when both are decided.

Endings: `@end ID` records the ending (and `cleared_<scenario>`: main only by a `true` ending, the other
scenarios by any of theirs), shows 終 ("The End"; Noto Serif rendering), the title and its kind over the darkened picture,
waits for A and returns to the title.  The title shows おまけ (bonus; jumps to `*omake`) once `--omake-endings`
endings (10) have been seen.  Chapter cards: `@chapter 序章　霧見沢` — black screen, the part before the first
full-width space letter-spaced, the rest below; the old picture comes back unless a `@bg` follows.

## Build checks

Errors: syntax, unknown command, undefined label / duplicate label, `@end` not in endings.txt, a choice option
over 2 lines (17 full-width characters each, the cursor takes the 18th), more than 8 options or 11 lines of
options, more than 4 conditions on an option, characters not in the font (JIS X 0208 + ASCII), a chapter title
over 18 characters, an ending title over 14, the program running off its end, a background / silhouette without
a picture (unless `--allow-missing-art`), more than 32 endings / global flags, 512 local flags.
Warnings: labels unreachable from `*start` / `*omake`, endings not reachable (global-flag branches count as both
ways), flags tested but never set, kinsoku that could not be kept, unknown bg / sil names (not in
`assets/yonaki/prompts.json`), unknown song / effect / ambience names (`--unknown-sound-error` makes them errors).
Notes (report.txt): labels only reached by falling through, flags set but never tested.

Normalization: `—`→`―`, `～`→`〜`, `－`→`−`; `!` / `?` in Japanese text become `！` / `？` and the space
after them a full-width space; other ASCII stays half width (6 px).  Kinsoku: no line starts with
`、。，．・：；？！ー…‥」』）］｝〕〉》】` or small kana / `々〜`; no line ends with `「『（［｛〔〈《【`;
`……` and `――` are never split; ASCII words are not split.

## Tests (`tests/yonaki/`)

`run.py` (Snes9x 1.63 libretro, pad input only; WRAM read by label; the battery carried like a `.srm`):
coverage of the fixture, boot with an empty and a random battery, every fixture ending in route order with the
gated option checked before / after the unlock and おまけ after 3 endings, 結末の一覧, bookmarks at a paragraph
and at a choice across a power cycle, B fast-forward stopping at unread text, text speed kept in the battery,
the effects (screenshots of every page), and with `--real` every ending of the real scenario plus the list's
second page. The scheduler fixture drives overlapping sound, text DMA and graphics requests, checks palette,
map and row ordering, and tests simultaneous input, input flushes and skip timing. Every session must end with
no V-blank overrun, no deferred DMA job and no clipped glyph.
`bsnes.py` replays the traces on bsnes 115 and compares the battery and the screenshots.
Results: `build/yonaki-test/tests.json`, `build/yonaki-test/bsnes/RESULTS.json`, screenshots in
`build/yonaki-test/shots/` and `build/yonaki/shots/` (real endings).

### Scheduler regression results for issue #4

The scheduler was tested on top of main at `4dbf917`. Snes9x ran with `run.py --real` and
`bsnes.py` replayed all generated traces.

- **Snes9x 1.63** passed all 12 tests, including all 20 real endings and both pages of the real ending list.
  The reported maximums were 3072 DMA bytes and NMI end line 257. V-blank overruns, deferred DMA jobs and
  clipped glyphs were all zero.
- **bsnes 115** passed all 45 replays, including 24 fixture and 21 real scenario traces. Across 273,127
  frames, final battery images matched in every replay. The largest RGB channel difference across
  82 captures was 2 on the 0–255 scale.
- **Comparison with main** matched all 41 existing Snes9x traces across 271,467 frames, including controller
  masks, capture frames, all 73 screenshot files, and initial and final battery images. The 75 generated
  production data banks and 20 fixture data banks matched byte for byte.
- **Scheduler fixture** sent commands `$41`, `$01` and `$70` on consecutive frames with text DMA and ripple
  active. The white transition held through all 24 photo row transfers and started clearing as soon as the
  final DMA job drained, with the span cursor still at the end of the table. Both skip runs reached unread
  text 120 frames after the fixture driver's new-game setup. Releasing B at the timed wait restored its
  12-frame duration.
