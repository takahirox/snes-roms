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
`--unknown-sound-error`, `--out DIR`, `--omake-endings N` (default 10), `--debug-start` (review builds),
`--benchmark-assets` (write compression measurements to `assets-benchmark.json`).
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
| `tools/yonaki/asset_codec.py` | silhouette span encoding, tile dictionaries and compression benchmarks |
| `tools/yonaki/pictures.py` | photos → 240 colours (112 + their translucent-figure versions where silhouettes appear) + 8bpp tiles; silhouettes → masks (cached in `build/yonaki/cache`) |
| `tools/yonaki/font.py`, `logo.py` | Shinonome 12-dot glyphs; the title logo |
| `tools/yonaki/romfix.py` | header checks and checksum |
| `tools/yonaki/audio.py` (+ music, songs, sfx, spc) | the sound driver and music (music agent) |
| `src/yonaki/yonaki.s` | header, reset, NMI, DMA queue, PPU setup |
| `src/yonaki/frame.inc` | frame scheduler, wait conditions, pad sampling and carry |
| `src/yonaki/text.inc` | 2bpp text bitmap: glyphs with shadow, strings, highlight |
| `src/yonaki/pic.inc` | colour math / effects (Tick), fades, picture loads, silhouette compositing |
| `src/yonaki/vm.inc` | the script VM (all ops), typewriter, waits, choices |
| `src/yonaki/ui.inc` | title, START menu, bookmarks screen, 結末の一覧 (list of endings), ending |
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

Text: 18 full-width characters (216 px) per line from screen x 20.  Story pages are laid out in tile rows
(`page_line`, `RowY`): a line is `LINE_ROWS` = 3 rows (24 px apart), 7 lines a page (`PAGE_LINES`), an empty script
line and the space before the options are one row (`GAP_ROWS`), and the options may go down to row 24 (8 lines on
an empty page, `CHOICE_ROWS`).  The menus and the name entry use `LineY` lines (two rows, 16 px apart, 12 lines).
A choice is highlighted by switching the map rows of its lines to palette 1 (`HighlightRows`).
Story text and choices use a one-pixel dark outline around the glyphs; menus use the existing drop shadow.

Colour math: the photo keeps its own brightness (every photo is lifted by the same gamma at build time,
`pictures.GAMMA`); text does not dim it.  BG1 is dimmed (a fixed-colour subtract, ramping one level a frame) only
by the START menu (`DIM_MENU` 15), `@fx dark` (31, until `@fx light` or the next `@bg`) and R held (`DIM_READ`
13).  Holding L masks BG2 in the main-screen register shadow (the photo and figures alone); L and R together do
both.  The buttons apply during scene fades and bookmark resume.
Flashes and the white transition add a fixed colour to every layer.  Shake moves BG1; the ripple is HDMA
channel 7 on BG1HOFS (a 2-px sine, table in bank 0); mosaic uses MOSAIC on BG1; fades use master brightness.

## Memory

VRAM (word addresses): `$0000-$5FFF` BG1 tiles 0–767; `$6000-$601F` BG2 tiles 0–3 = zero (also BG1 tile 768
and the BG3 offset row); `$6020-$769F` bitmap tiles 4–723; `$7800` BG1 map; `$7C00` BG2 map.

WRAM: `$0000-$00FF` direct page, `$0100-$1DFF` variables, `$1E00-$1FFF` stack; `$7E:2000` text bitmap
(11 520 bytes, tile (c, r) at (r·30 + c)·16); `$7E:5000` BG2 map shadow; `$7E:5800` the bitmap under the
START menu; `$7F:0000-$BFFF` the photo tiles (silhouettes are composited here).
The previous picture tiles used during a dissolve are split between `$7E:8500-$FFFF`,
`$7F:C000-$FFFF`, and a 20-tile tail in the variable area.

LoROM uses FastROM ($30) for data banks starting at `$81:8000`. Code and tables are in bank 0 (`$00:8000`).
The font, script and SPC image each start at a bank boundary. A full font bank holds 1,024 glyphs of
32 bytes each, with 12 row words (bit 15 leftmost) and the width at byte 24. Script ops fit within one bank
and a GOTO links each full script bank to the next. The builder places resume tables, 2 KiB photo rows,
palettes and packed masks into available bank tails, largest blob first. Each blob fits within one bank.
The resume tables stay together and map text and choice IDs to op addresses.

Each mask row stores the first covered column and the tile count through its last covered column. An empty
row stores two zero bytes. Tile data follows the row header as either 16 bytes per tile (eight cover and rim
pairs) or one index byte per tile. For indexed masks the dictionary follows the last row and the word at
`SilTable+6` holds its address within the same bank. Zero selects raw spans.

The file size rounds up to 512 KiB, 1 MiB, 2 MiB, 3 MiB or 4 MiB. For a 3 MiB image the header uses
`$0C` and the checksum counts the upper MiB twice. [Nintendo SNES Development Manual, Book I, pp. 1-2-19 to 1-2-21](https://floating.muncher.se/bot/manual/book1_text.pdf)

## Save format and recovery

SRAM is 8 KiB at `$70:0000`. Words and long values are little-endian. Version 2 uses the following layout.

| Offset | Content |
|---|---|
| `$0000 / $0400` | Global record primary and mirror |
| `$0100 / $0500`, `$0200 / $0600`, `$0300 / $0700` | Primary and mirror for bookmarks 1–3 |
| `$0800–$0807` | Read-mark header: `YR`, version (16 bits), build ID (32 bits) |
| `$0808–$13F7`, `$1400–$1FEF` | Read-mark bitmaps, one bit per paragraph ID in each copy |
| `$13F8–$13FF`, `$1FF0–$1FFF` | Reserved. Review ROMs use `$1FF0–$1FF5` for the debug start address. |

Each journal record has `YN` at +0, a logical record number at +2 (0 global, 1–3 bookmarks), version at +4,
32-bit build ID at +6, 16-bit generation at +48, and CRC-16/CCITT-FALSE (initial value `$FFFF`, polynomial
`$1021`) at +148 covering bytes +2 through +147. The bytes after the CRC in each 256-byte allocation are reserved.

| Record | Payload |
|---|---|
| Global | +10 text speed, +12 endings seen (32 bits), +16 global flags (32 bits), +20 names (20 bytes) |
| Bookmark | +10 kind (1 paragraph, 2 choice), +12 resume ID, +14 paragraph to redraw for a choice, +16 picture, +18 song, +20 chapter, +22 dark, +24 ripple, +26 ambience, +32 four silhouette slots (four bytes each), +64 local flags (64 bytes), +128 names (20 bytes). Absent paragraph, song, chapter and ambience use `$FFFF`. |

Each update writes the other copy. It first clears the first magic byte, then writes the payload and CRC,
and commits with a single store of `Y`. The game verifies the result. An earlier valid record stays selectable
through an interruption before that final store. Loading checks both copies for the marker, version, record
number, build ID, CRC and field ranges, then uses the newest valid generation. Generations wrap at 65,536.
For equal generations or a difference of exactly 32,768, the primary wins. If both copies fail validation,
the game uses default global data or shows that bookmark as empty. Other logical records are independent.
Names use their existing per-name glyph validation and default substitution.

A paragraph counts as read once its bit is set in both bitmaps. An interruption between the two byte stores
can leave the current paragraph unread while preserving previously committed bits. A flipped bit in one
bitmap cannot make an unread paragraph count as read and may make a read paragraph unread. Damage at the
same bit in both copies can affect that paragraph. A bad read header clears both bitmaps at boot, with
the header's first magic byte committed only after the clear completes.

Paragraph and choice IDs are sequential indices assigned by the scenario compiler. They resolve through ROM
tables to VM instructions. The build ID is a truncated SHA-256 over the compiled script, font and saved-index
mappings. A battery written by any other build (another scenario, font or save version) is not read: the game
starts with defaults, empty slots and no read marks. Saves are never carried across builds.

The bookmark payload captures the VM at a paragraph or choice boundary, including local flags and scene state.
Resumed choices use the current global unlocks. The payload can serve as the starting point for a future
checkpoint system. Read marks can answer whether a paragraph
was read, but lose visit order, repeated visits and branch decisions. A future backlog would need an ordered
visit log. Chapter navigation would need separately defined entry checkpoints with the appropriate flags and
scene state. The previous journal copy exists for recovery and has no user-facing navigation.

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
| `PAGE`, `BG`, and silhouette batches | Page clears, forced-blank DMA, and picture compositing use paced frame boundaries. Fades and mosaic use fixed frame steps. Silhouette batches prepare the target in WRAM and dissolve changed tiles. Streaming waits for dirty flags and the DMA list to drain, with the existing 600-frame watchdog. A white transition waits for colour addition to decay after uploading. |
| `FX` | Shake waits 24 frames, flash waits for colour addition to reach zero, dark waits for full dim, light waits 40 frames, and ripple changes state immediately. `@fx wait N` completes after N frames or on the first sampled frame with fast-forward active and B held. |
| `CHAPTER`, `END`, `HALT` | Chapter markers update the bookmark label and continue immediately. Endings keep their 40-frame dim and 90-frame display delay, then wait for A or START before fading out. HALT fades out and returns to the title. |

The bytecode and compiler are shared with the previous runtime. The sound FIFO advances during every wait,
including two-frame text fast-forward and timed waits. Fast-forward stops on unread text and at choices.
Entering a menu happens after the active input wait returns, so the menu can run its own frame waits.

Picture changes: `fade` = brightness down (2 frames a step), forced blank, ROM → WRAM rows, composite,
WRAM → VRAM 16 KiB a frame, brightness up; `cut` = the same without the fades; `white` = colour addition to
white, upload in V-blank slices, back; `mosaic` = mosaic up, fade, load, fade in while the mosaic goes down.
A `@bg` clears the page and the silhouettes; `@sil` lines right after it go into the new picture before it
appears. Consecutive `@sil` and `@silclear` ops are batched. The existing photo remains visible while the engine
backs up the union of the covered bounds, restores the old packed spans, and composites the target slots
in WRAM. The engine uploads only changed tiles across eight ordered dissolve stages, with at least
four frames per stage, and interpolates the tint aliases when their palette changes. Scene uploads
continue to use one span per row (first column and exclusive end; zero for an empty row).


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

## Script VM

Ops (byte code, `tools/yonaki/build.py`): `TEXT id16 lines8 [counts] <string>` (lines bit 7: shown at once and no wait —
the echo of an inline choice; bit 6: 16 line counts by name lengths follow), `BLANK`, `PAGE`, `BG pic mode` (mode 0 cut, 1 fade, 2 white, 3 mosaic, 4 keep: the
photo goes dark under the text and the new one comes up under it; every `BG` ends the darkness of `@fx dark`),
`SIL key sil x colour` (sil `$FF` = remove the key), `SILCLEAR`, `BGM n` (`$FE` stop, `$FF` fade),
`SE n`, `AMB k` (`$FF` off), `FX kind arg16`, `SET/CLR flag16`, `SETG/CLRG g`, `IF cond16 addr24`,
`GOTO addr24`, `CHOICE id16 n {nconds conds… addr24 lines8 <string>}` (n bit 7: inline), `END ending`,
`CHAPTER ch`, `HALT`, `ASK n {len8 glyph16… addr24}… default24 <question>`.

Inline choices (`@choice inline`): the parser sends each option to an echo paragraph after the program (its text,
re-wrapped, `nowait`) that goes on to the option's target. After the choice the VM erases the options and the blank
line before them (`ClearFrom`) instead of the page, so the chosen sentence follows the text above it. When the
options do not fit under the text, `ChoicePage` starts a new page with the paragraph before the choice drawn again
(the bookmark redraw), so the options never lose the sentence they finish.

`@ask` (`OpAsk`): the name entry grid in answer mode (`AskEntry`, `ne_ask`): the question on line 0, a grey hint
and the answer (field 2, `names+20`) under it, over the darkened scene (`dark_on`, restored after). START or 決定
with something typed ends it (B on an empty answer does nothing). The answer is compared with each spelling of the
op (glyph indices of the grid); the first equal one is taken, else the default. The test driver types answers on
the grid (`drive.type_answer`); `routes.py` treats an `@ask` as a choice whose options are the first spelling of
each answer and `*` (the default).
A condition word: bit 15 negated, bit 14 global (index < 32 a global flag, 32 + e ending e seen), else a local flag.
Strings: `$00` end, `$01` new line, `$02` next page chunk, `$03` / `$04` the player's names (the given
names of 主人公 結城 and ヒロイン 早瀬, whose family names are fixed: the script writes the default names 航 / 千尋, `script.NAME_VARS`;
`ReadCode` hands out the name's glyphs from `names`), `$05` / `$06 mask16` a new line / page chunk only for the
name lengths in the mask, `$10-$EF` the 224 most frequent glyphs, `$F0-$FF xx` the others (up to 4320 glyphs).
A text with a name is laid out for each of the 16 pairs of name lengths (1-4 characters each, `script.NAME_LENS`);
where their line breaks differ the string has `$05` / `$06` with the pairs that break there (bit
(hero − 1) × 4 + heroine − 1, `NameIndex`), so every line is filled for the names actually set.  When the line
count differs too, the lines byte of `TEXT` and of a `CHOICE` option has bit 6 set and 16 counts follow it.

Text flow: a paragraph that does not fit the rest of the page starts a new page; one longer than 7 lines is
split into page chunks at build time.  After each paragraph the VM waits for A with a blinking mark: ▽-like
(paragraph) or a double mark when the next paragraph will start a new page (it looks ahead over silhouette /
sound / flag ops, `@bg … keep` and jumps).  An empty line in the script adds a gap when the page is not empty.
Speeds (START menu): 遅い (slow) 1 glyph / 2 frames, 普通 (normal) 1, 速い (fast) 2, 瞬間 (instant) all.  A finishes the paragraph at once.
B held: read paragraphs (read marks in SRAM) are shown at once and passed after 2 frames; it stops at the first
unread one.  Choices are drawn under the text (a gap first), each after its letter Ａ, Ｂ, … in the order shown, up / down / A; after a choice the page
clears.  START at a paragraph wait or a choice: しおりをはさむ (insert a bookmark) / 文字の速さ (text speed) / タイトルへ (to the title) / もどる (back).
A bookmark resumes at the paragraph (shown again on a fresh page) or at the choice (the paragraph before it
is redrawn first).

Title: after the boot the far bell (`bell_far`) rings on black for `TITLE_BELL` frames; the title picture fades
in (`TITLE_FADE` frames a step) and the menu is drawn after it.  `DEMO_IDLE` frames (20 s) on the title without a
button start the demo: the VM runs from `*demo` (a scenario without it has no demo) and `ReadPad` plays it,
pressing A `DEMO_WAIT` frames into each paragraph wait and choice (the first option) while nothing else is held.
A button, or the first wait after `DEMO_FRAMES` (60 s), returns to the title (`DemoExit`, only at a wait); an
`@end` or `@ask` ends it at once.  The demo marks nothing read and skips `@setg` / `@clrg`.

Guest register (`NameConfirm`, state `ST_WELCOME`): はじめから first shows the names in the inn's register over the
inn at dusk (`REGISTER_BG` in build.py; このまま始める / 名前を書きなおす; B back to the title).

Name entry (`NameEntry`, ui.inc, state `ST_NAME`): 名前を書きなおす asks for the given names of 主人公 and ヒロイン (1-4 glyphs each,
shown with ＿ for the free places, the fixed family names 結城 / 早瀬 grey before them and （名前） ("given name")
after them) on a dark screen: 8 rows of 10 characters a page (かな, カナ, 3 pages of name
kanji, `NameGrid` from build.py `NAME_PAGES` / `NAME_KANJI`) and the commands かな カナ 漢字 けす 決定 (hiragana, katakana, kanji, erase, confirm).  Arrows move
(wrapping), A types / runs the command, B deletes the last character (on an empty name: the first name again, or
back to the title), L / R change the page, START decides.  The names are checked at power-on and at a bookmark load
(length and glyph range; a broken one becomes its default) and saved in the global block when both are decided.

Endings: `@end ID` records the ending (and `cleared_<scenario>`: main only by a `true` ending, the other
scenarios by any of theirs), shows 終 ("The End"; Noto Serif rendering), the title and its kind over the darkened picture,
waits for A and returns to the title.  The title shows おまけ (bonus; jumps to `*omake`) once `--omake-endings`
endings (10) have been seen.  The `@chapter 序章　霧見沢` marker sets the chapter name shown in bookmarks.

## ROM asset measurements

Independent reverse-engineering notes on *Kamaitachi no Yoru* describe separate compression for background
tilesets, tilemaps and silhouettes, with an LZSS variant for name-entry font graphics. Notes on Konami's SFC
games describe a combination of RLE and LZ-style references. Those examples informed the comparisons below.
Yonaki uses its own mask format. [Kamaitachi no Yoru research notes](https://github.com/ButThouMust/kamaitachi-sfc-english#graphics-compression-formats) ·
[Konami SFC compression notes](https://github.com/gocha/sfc-goemon-3-disassembly/blob/main/docs/konami-snes-compression.md)

Run `YONAKI_FLAGS="--benchmark-assets --quiet" make yonaki` to reproduce the codec measurements.
The input blocks are 2 KiB photo rows, rectangular cached masks and script banks. The PackBits model uses
packets of up to 128 bytes and repeat runs from length three. Raw DEFLATE at zlib's default level provides
an LZ77-based size reference. Figures exclude pointer metadata and omit solid photo fills, which use zero
tile bytes.

| Input | Blocks | Raw bytes | PackBits model | Raw DEFLATE | Stored bytes |
|---|---:|---:|---:|---:|---:|
| Photo rows | 1,008 | 2,064,384 | 1,900,482 | 1,673,646 | 2,064,384 |
| Silhouette masks | 106 | 154,512 | 89,872 | 32,895 | 79,402 |
| Script banks | 3 | 93,080 | 93,803 | 60,808 | 93,080 |

- **Photos.** All 32,256 stored tiles are distinct. PackBits saves about 8% and can generate 145 packets
  in one row. Its savings would still leave the payload above 2 MiB. A row decoder could require up to
  2 KiB of output storage and would add work when restoring selected columns. Raw rows let DMA read a
  column span directly. A full forced-blank scene change uses six 8 KiB restore slices and three 16 KiB
  VRAM upload slices.
- **Masks.** The builder compares each indexed span stream with its raw spans and chooses the dictionary
  for 96 of 106 production masks. Raw spans handle dictionaries exceeding 256 unique tiles and cases
  where indexing would use at least as many bytes. The builder round-trips each encoded mask to its
  original rectangular cover and rim bytes. The compositor reads one index per visited tile for indexed
  spans, uses two additional WRAM bytes for the cursor and keeps the 12-tile frame quota. A DEFLATE
  decoder would add a decode step and could use up to 12 KiB of output storage for a full-screen mask.
- **Script.** PackBits grows the glyph-coded script. Bank-wide DEFLATE would save about 32 KiB with up to
  32 KiB of output storage and a decode on first access or a bank cache miss. Direct reads preserve random
  access for VM jumps, lookahead, choices and bookmarks.

| Real scenario ROM category | `main` (`ff5fe48`), bytes | With indexing and bank packing, bytes |
|---|---:|---:|
| Code, resident tables and header | 23,770 | 23,815 |
| Font | 40,992 | 40,992 |
| Script | 93,080 | 93,080 |
| Resume tables | 7,587 | 7,587 |
| Photo rows | 2,064,384 | 2,064,384 |
| Photo palettes and tint tables | 34,112 | 34,112 |
| Silhouette masks | 102,732 | 79,402 |
| SPC image | 48,523 | 48,523 |
| **Payload** | **2,415,180** | **2,391,895** |
| Padding inside occupied banks | 75,188 | 32,937 |
| Whole empty banks | 1,703,936 | 720,896 |
| **Linked ROM** | **4,194,304** | **3,145,728** |

Indexing saves 23,330 mask bytes (22.7%) beyond the spans already on `main`. The combined changes reduce
occupied banks from 76 to 74 and select the 3 MiB size tier. `manifest.json` records data payload and
padding for the packed build, and the linker map records bank 0 payload. The baseline's occupied-bank
padding includes 605 bytes to align the first photo row. An audit of both linked ROMs recovered
byte-identical photos, palettes, masks, font, script, resume pointers and SPC image. Mask placements and
the production save build ID (`2CCE7228`) also matched. The linked packed ROM's SHA-256 is
`87f7d70d9deafdf3d0881088de6f9466d5a7ac5f31640af24be466d278c9faba`.

## Build checks

Errors: syntax, unknown command, undefined label / duplicate label, `@end` not in endings.txt, a choice option
over 2 lines (17 full-width characters each, the cursor takes the 18th), more than 8 options or 11 lines of
options, more than 4 conditions on an option, characters not in the font (JIS X 0208 + ASCII), a chapter title
over 18 characters, an ending title over 14, the program running off its end, a background / silhouette without
a picture (unless `--allow-missing-art`), more than 32 endings / global flags, 512 local flags.
Warnings: labels unreachable from `*start` / `*omake` / `*demo`, endings not reachable (global-flag branches count as both
ways), flags tested but never set, kinsoku that could not be kept, unknown bg / sil names (not in
`assets/yonaki/prompts.json`), unknown song / effect / ambience names (`--unknown-sound-error` makes them errors).
Notes (report.txt): labels only reached by falling through, flags set but never tested.

Normalization: `—`→`―`, `～`→`〜`, `－`→`−`; `!` / `?` in Japanese text become `！` / `？` and the space
after them a full-width space; other ASCII stays half width (6 px).  Kinsoku: no line starts with
`、。，．・：；？！ー…‥」』）］｝〕〉》】` or small kana / `々〜`; no line ends with `「『（［｛〔〈《【`;
`……` and `――` are never split; ASCII words are not split.

## Tests (`tests/yonaki/`)

`run.py` (Snes9x 1.63 libretro, pad input only; WRAM read by label; the battery carried like a `.srm`):
coverage of the fixture, boot with an empty and a random battery, the title's demo (it plays itself, keeps nothing and
returns on a button or its time), every fixture ending in route order with the
gated option checked before / after the unlock and おまけ after 3 endings, 結末の一覧, bookmarks at a paragraph
and at a choice across a power cycle, B fast-forward stopping at unread text, text speed kept in the battery,
and the effects (screenshots of every page). The save tests compare the resumed scene, local flags, names and
visible choices. Recovery cases boot from battery images captured before and after real overwrites, with cuts
after invalidation, during the payload and immediately before commit. They also cover a bad CRC, an invalid
field with a valid CRC, two unusable copies, a wrapped generation and a read bit stored in only one bitmap.
The scheduler fixture drives overlapping sound, text DMA and graphics requests, checks palette, map and row
ordering, and tests simultaneous input, input flushes and skip timing.
With `--real`, `run.py` also plays every ending of the real scenario and opens the ending list's second page.
Every session must end with no V-blank overrun, no deferred DMA job and no clipped glyph.
`bsnes.py` replays the traces on bsnes 115 and compares the battery and screenshots. Pass `--real` to include
the real scenario traces.
`run.py` writes `build/yonaki-test/tests.json` and `bsnes.py` writes `build/yonaki-test/bsnes/RESULTS.json`.
The drivers save screenshots under `build/yonaki-test/shots/`, `build/yonaki-test/scheduler/shots/`, and
`build/yonaki/shots/` (real endings).
