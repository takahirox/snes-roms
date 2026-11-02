# 夜鳴き鐘 (Yonaki Kane) — engine

The scenario format and the story are in `DESIGN.md`; this file is the engine: the ROM (`src/yonaki/`), the
build (`tools/yonaki/`) and the tests (`tests/yonaki/`).

## Build and test

```
make yonaki          # build/yonaki/yonaki.sfc from data/yonaki/scenario + endings.txt + pictures + sound
make yonaki-test     # fixture tests + every ending of the real scenario on Snes9x, then the traces on bsnes
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
| `src/yonaki/yonaki.s` | header, reset, NMI, frame loop, DMA queue, pad, PPU setup |
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
address), pictures (48 KiB each, 2 KiB rows that never cross a bank), palettes, silhouette masks (16 bytes a
tile: 8 × (cover, rim)), the SPC image.  The ROM size is rounded up to 512 KiB / 1 / 2 / 4 MiB.

SRAM (8 KiB at `$70:0000`, all little-endian, every block with a 16-bit sum and its complement):

| offset | content |
|---|---|
| `$0000` | global: "YNKG", version, text speed, endings seen (32 bits), global flags (32 bits), the names (+16, 20 bytes), sum at +252 |
| `$0100/$0200/$0300` | bookmarks 1–3: "YNKS", version, build id, kind (1 paragraph / 2 choice), text or choice id, paragraph to redraw before a choice, picture, song, chapter, dark, ripple, ambience, 4 silhouette slots, 512 local flags, the names (+128), sum at +252 |
| `$0400` | read marks: "YNKR", build id, one bit per paragraph ($0408–$1FFB, 57 248 paragraphs), sum at $1FFC (kept up to date one bit at a time) |

At power-on the global block and the read marks are checked (magic, version, sum, ranges, build id for the
marks) and reset when broken; a bookmark is checked field by field when it is listed and shown as empty when
broken or made by another build (the build id is a hash of the script and the font).

## Frame protocol and timing

The game is one thread that calls `WaitFrame` once a frame.  `WaitFrame` runs `Tick` (effects → register
shadows), `PumpUploads` (palette, BG2 map, dirty photo rows, dirty text rows → DMA jobs within 3072 bytes),
one sound command, then waits for the NMI.  The NMI runs the jobs only when the thread is parked in `WaitFrame`,
writes the shadows, and records its end line (`nmi_end_line_max`, `vblank_overrun_count`).

Long work is cut into frames so no frame overruns and the game takes the same frames on every core: at most
5 glyphs (`GLYPHS_PER_FRAME`) and 12 silhouette tiles a frame, page clears and ROM→WRAM picture rows (≤ 8 KiB)
right after a frame starts, the menu's bitmap copy in 8 slices, the boot a fixed 150 frames (the SPC upload
takes about 103).  Presses made during that paced work are kept for the next input check, except that a
cursor or a wait mark never takes a press made before it appeared.  The test traces replay frame-identically
on bsnes 115 (same battery images, same screenshots).

Picture changes: `fade` = brightness down (2 frames a step), forced blank, ROM → WRAM rows, composite,
WRAM → VRAM 16 KiB a frame, brightness up; `cut` = the same without the fades; `white` = colour addition to
white, upload in V-blank slices, back; `mosaic` = mosaic up, fade, load, fade in while the mosaic goes down.
A `@bg` clears the page and the silhouettes; `@sil` lines right after it go into the new picture before it
appears.  Silhouette changes (`@sil`, `@silclear`; consecutive ones are batched) dim BG1 out in about 5 frames,
restore the covered tile columns from ROM, composite every slot and upload only those columns, then dim back.

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
second page.  Every session must end with no V-blank overrun, no deferred DMA job and no clipped glyph.
`bsnes.py` replays the traces on bsnes 115 and compares the battery and the screenshots.
Results: `build/yonaki-test/tests.json`, `build/yonaki-test/bsnes/RESULTS.json`, screenshots in
`build/yonaki-test/shots/` and `build/yonaki/shots/` (real endings).
