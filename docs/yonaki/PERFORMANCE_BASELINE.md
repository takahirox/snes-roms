# Yonaki performance baseline and Kamaitachi no Yoru research

This baseline supports future Yonaki engine work. The largest Yonaki ROM cost is the 8bpp photo tile data, at about 84% of the emitted payload. The published Kamaitachi no Yoru research establishes that Chunsoft compressed its script and several graphics formats. Matching its cartridge size is a poor performance target because the games have different content, rendering paths and ROM layout. [Issue #6](https://github.com/takahirox/snes-roms/issues/6)

## Kamaitachi no Yoru on Super Famicom

The reference is the original Japanese SHVC-EU cartridge. The translation project's documented input is a headerless 3 MiB Japanese image, with SHA-256 `3228a3b35f7d234a7bf91f8159ccc56518199222e84d258c14a153f54f9fcbc7`. SNES Central records an SHVC-EU-0 board with LoROM mapping and 64 Kibit (8 KiB) of battery-backed SRAM. No legally supplied dump was available in this run. The following findings come from public analysis and firsthand accounts. [Translation project ROM identification](https://github.com/ButThouMust/kamaitachi-sfc-english/tree/eb95e92e1d3cef80de17b5b1251dadde7f45789d#how-to-patch) · [Cartridge record](https://snescentral.com/article.php?id=1163) · [Board record](https://snescentral.com/pcbboards.php?chip=SHVC-BA3M-10)

| Area | Public evidence | Open runtime measurement |
| --- | --- | --- |
| Script and font | The fan translation author's notes and working dumper document Huffman-coded symbols, a bitstream reader, control codes and 24-bit branch targets expressed as bit offsets. The documented Japanese script span is 293,805 bytes. The font is bit-packed with separate metadata tables. [Script format](https://github.com/ButThouMust/kamaitachi-sfc-english/blob/eb95e92e1d3cef80de17b5b1251dadde7f45789d/notes/script%20format/script%20format%20notes.txt) · [ROM layout](https://github.com/ButThouMust/kamaitachi-sfc-english/blob/eb95e92e1d3cef80de17b5b1251dadde7f45789d/notes/misc/kamaitachi%20ROM%20data%20layout.txt) | Decode time, glyph draw time, and input-to-page timing. The span alone cannot give a compression ratio against a different script. |
| Backgrounds and silhouettes | The same analysis documents compressed tilesets and a background tilemap decoder that reconstructs tile index, palette and flip fields in separate passes. It describes silhouettes drawn mainly with OBJ and sometimes converted to a BG tilemap. [Tilemap format](https://github.com/ButThouMust/kamaitachi-sfc-english/blob/eb95e92e1d3cef80de17b5b1251dadde7f45789d/notes/background%20graphics/kamaitachi%20tilemap%20compression%20format.txt) · [Silhouette notes](https://github.com/ButThouMust/kamaitachi-sfc-english/tree/eb95e92e1d3cef80de17b5b1251dadde7f45789d/notes/silhouettes) | PPU modes and layer enables by scene, VRAM/CGRAM/OAM addresses and bytes, DMA/HDMA payloads and timing, and use of forced blank. A decoded tilemap does not establish the active PPU mode. |
| Save and reset | The board record establishes the installed SRAM capacity. The anniversary interview describes continuous autosaving during play and a route that advances on console reset using retained state. [Cartridge record](https://snescentral.com/article.php?id=1163) · [30th anniversary interview, part one](https://www.4gamer.net/games/999/G999903/20240410061/) | Save ranges, write cadence, validation, and the memory and reset checks used by that route. |
| Sound | Nakamura recalls building a sound program for the original, and Nakajima recalls working around storage and hardware limits. Kato describes editing and sampling a synthesizer patch for a bass sound. The fan ROM map labels sound tables and tentatively identifies a driver region. [Nakamura and Nakajima interview](https://www.gamer.ne.jp/news/201305310004/) · [30th anniversary interview, part two](https://www.4gamer.net/games/999/G999903/20240410075/) · [ROM layout](https://github.com/ButThouMust/kamaitachi-sfc-english/blob/eb95e92e1d3cef80de17b5b1251dadde7f45789d/notes/misc/kamaitachi%20ROM%20data%20layout.txt) | IPL payload size, any subsequent uploads, ARAM allocation, DSP voice/echo use, and cue latency. |

Nakamura also recalls removing objects from backgrounds to fit capacity and color limits. Asano asked for music to build emotion from the moment a cue began, because long introductions were hard to synchronize to reading. The engine hypotheses worth testing are whether graphics compression saves space at an acceptable CPU cost, and whether changing the upload schedule changes the frame at which a cue or scene is presented. [Nakamura and Nakajima interview](https://www.gamer.ne.jp/news/201305310004/) · [30th anniversary interview, part two](https://www.4gamer.net/games/999/G999903/20240410075/)

### Debugger procedure when a legally obtained dump is available

Record the cartridge revision, headerless SHA-256, debugger version, NTSC settings and input sequence. Start with a cold boot and record the title, ordinary text, a choice, a full background transition, a silhouette change, progress saved automatically and resumed after a power cycle, and the first changes of music and ambience. Use the same classes of events on Yonaki and record frame and scanline boundaries for each. Mesen's SNES debugger, event viewer and trace facilities can drive the inspection. [Mesen project and documentation](https://github.com/SourMesen/Mesen2) · [Mesen scripting API](https://github.com/SourMesen/Mesen2/blob/master/UI/Debugger/Documentation/LuaDocumentation.json)

1. Break on writes to `$2100`, `$2105` and `$212C–$212D` for blanking, mode and layer enables. At stable frames record the BG/OBJ tiles and maps, palette allocations and active OAM entries. Check color math and direct color settings at `$2130–$2131`. Watch `$2116–$2119`, `$2121–$2122` and `$2102–$2104` for VRAM, CGRAM and OAM addressing and data.
2. At each `$420B` or `$420C` trigger, capture the enabled channels and `$43x0–$43xA` state. Sum payload bytes by target and frame, treating an MDMA length of zero as 65,536 bytes, and record the first and last bus events relative to forced blank or V-blank. Count HDMA data bytes and table overhead individually. Include CPU writes when reporting total graphics traffic.
3. Trace the documented script reader on a normal line and through a taken choice. Time the range from consuming a script symbol or command to the resulting render or branch. Record aggregate cycles, glyph counts and branch behavior.
4. Snapshot SRAM before confirming an ordinary choice, then trace SRAM writes through the first paragraph on the chosen branch. Record the timing of the autosave writes, the changed SRAM address ranges and the number of bytes changed. Carry over only the resulting battery SRAM into a cold boot and resume. Expect the saved progress on the chosen branch to survive, and record the exact resume point to establish the game's checkpoint granularity.
5. At the reset-route cue, trigger a console soft reset and record whether the hidden route advances and what state is retained. Repeat from the same point with a cold boot and compare the resulting route and retained state.
6. Capture writes to the CPU APU ports `$2140–$2143` from reset through the IPL handshake and during later cues. Count transferred payload and frames to acknowledgment, then inspect ARAM ranges and voice and echo registers for music plus effects and ambience. Keep the dump, save images, screenshots, extracted data and traces containing proprietary bytes local. Publish only hashes, aggregate counts, addresses and observations.

## Yonaki build and resource use

The build used arm64 macOS 27.2.1, Python 3.13.13 and the repository-pinned cc65 2.19, Pillow 13.0.0, NumPy 2.5.4, Snes9x 1.63 and bsnes 115 sources. The built ROM is a 4,194,304-byte headerless FastROM LoROM image with 8 KiB of battery SRAM. It matches `dist/yonaki.sfc` byte for byte, with SHA-256 `b0b90ecf9d853f8c975f9c0045712966f114b1463e973a7b91434a97a141c3c7`. [Source commit `6da6766`](https://github.com/takahirox/snes-roms/commit/6da6766b66cc3d7f3d699f8391ceea5fb4e71f92)

| ROM component | Bytes | Basis |
| --- | ---: | --- |
| Code, fixed tables and header | 23,243 | CODE, RODATA and HEADER linker segments |
| Glyphs | 40,992 | 1,281 × 32 bytes |
| Scenario bytecode | 93,080 | 2,480 paragraphs and 49 choices, including control and branch data |
| Resume indices | 7,587 | 3 bytes per paragraph and choice |
| Photo tiles | 2,064,384 | 42 stored pictures × 49,152 bytes, plus two synthetic pictures generated without a tile blob |
| Photo palettes and tint alternatives | 34,112 | 44 × 480 bytes plus 29 × 448 bytes |
| Silhouette masks | 154,512 | 106 masks, 16 bytes per tile |
| SPC image | 48,523 | Two sound banks, excluding linker fill |
| Alignment inside bank blobs | 605 | Difference between payload and linked segments |
| Linker fill | 1,727,266 | Includes 50 completely unused banks |
| **ROM file** | **4,194,304** | **78 occupied 32 KiB banks out of 128** |

Read the segment sizes from `build/yonaki/yonaki.map` and the data sizes from `build/yonaki/layout.json`, `const.inc` and `data.inc`. Count actual photo rows and tint blocks from `PicTable` and compute each mask's size from `sil_size`. `bank*.bin` sizes include in-bank alignment. A bank name describes its first allocation and can include subsequent resource types. The engine uses byte-aligned opcodes and one- or two-byte glyph codes, with ROM addresses in the resume tables. SRAM reserve comprises one 256-byte global block, three 256-byte bookmarks and 7,168 bytes for the read-mark block. [Yonaki engine](ENGINE.md) · [Bank packing and encoding](../../tools/yonaki/build.py)

### Graphics and timing

The engine sets Mode 4 with 8bpp BG1 photos and a 2bpp BG2 text bitmap. BG1 tiles use 49,152 bytes and BG2 text uses 11,520 bytes. Their two maps occupy 2,048 bytes each. CGRAM uses 32 bytes for UI and silhouette colors and 480 for picture colors, with up to 224 bytes of tinted colors replaced in place. The main/subscreen masks keep OBJ disabled. [PPU setup](../../src/yonaki/yonaki.s) · [Picture paths](../../src/yonaki/pic.inc)

A full photo load stages 49,152 bytes in WRAM in slices of up to 8,192 bytes before uploading to VRAM. The forced-blank path uses three 16,384-byte VRAM transfers. The visible path shares a 3,072-byte NMI queue with palette and text work. A text tile row is 480 bytes. Color math hides silhouette compositing work and lets the engine upload affected columns only. The ripple effect uses HDMA channel 7 to write BG1 horizontal scroll. Startup also clears all 65,536 VRAM bytes by DMA, uploads the BG2 map by DMA, writes the BG1 map with the CPU, and clears and initializes CGRAM with CPU writes. [Reset and NMI](../../src/yonaki/yonaki.s) · [Picture paths](../../src/yonaki/pic.inc)

A separate instrumented Snes9x 1.63 build replayed three existing pad traces. The table reports DMA payload bytes across each complete trace, including startup in each column. Each replay finished with the original Snes9x battery image. The boot trace reaches a fully lit title after 212 frontend frames, including the driver's four settling frames.

| Transfer destination | Fixture boot (214 frames) | Fixture effects (1,301 frames) | Full scenario E06 (14,210 frames) |
| --- | ---: | ---: | ---: |
| VRAM clear | 65,536 | 65,536 | 65,536 |
| VRAM BG1 photo tiles | 49,152 | 350,080 | 4,545,728 |
| VRAM BG2 text tiles | 24,000 | 414,240 | 8,856,480 |
| VRAM tilemaps | 4,096 | 24,576 | 114,688 |
| CGRAM | 480 | 3,744 | 66,048 |
| OAM | 0 | 0 | 0 |
| WRAM | 195,072 | 668,800 | 6,972,608 |
| BG1 scroll HDMA | 0 | 16,200 | 114,750 |

The largest measured single-frame totals by destination were 16,384 BG1 tile bytes after boot clear, 2,880 BG2 tile bytes, 2,048 map bytes, 704 CGRAM bytes and 450 HDMA payload bytes. These peaks come from different frames. The effects and E06 traces each hit the 3,072-byte NMI queue budget. All sampled general PPU DMA started during V-blank or forced blank. The regression counter also recorded zero NMI overruns. These measurements include requested DMA and HDMA data bytes, with CPU I/O writes and HDMA table fetches outside the totals. The sample covers starts and scanline-level NMI completion, with end dots and startup/direct DMA end times still to measure.

To reproduce the traffic sample, replay `boot.json`, `effects.json` and `real_E06.json` with their `.in.srm` images from `build/yonaki-test/traces/` in a separate profile build of the pinned core. At `S9xDoDMA` record channel, direction, transfer size, B-bus target, `PPU.VMA.Address` in words, forced blank and vertical counter. Sum CPU-to-B-bus payload for `$2118` (VRAM), `$2122` (CGRAM), `$2104` (OAM) and `$2180` (WRAM). Classify VRAM by its starting word address as BG1 below `$6000`, BG2 tiles below `$7800`, and maps from `$7800`. Count the channel 0 zero-length startup transfer separately as the 65,536-byte clear. At `S9xDoHDMA` count data only when `DoTransfer` is set, using the core's mode byte count. Reset the per-frame totals before each `retro_run()` and compare final SRAM with the trace's `.out.srm`. [Pinned Snes9x DMA implementation](https://github.com/snes9xgit/snes9x/blob/1.63/dma.cpp)

### Audio

The generated 48,523-byte SPC image loads at `$0200` and ends at `$BF8B` (exclusive), leaving 8,309 bytes before the 8,192-byte echo buffer at `$E000–$FFFF`. The image contains 3,657 bytes of driver code and tables, 32,229 bytes of BRR samples, 1,284 bytes of effect data and 10,608 bytes of sequence bodies. The remaining 745 bytes cover the directory, alignment and song headers/pointers. It provides 18 songs, 32 effects and two ambience programs using 35 samples. Voices 2–7 play music and voices 0–1 play effects, with rain sharing voice 1. The sequence and samples are resident after the boot IPL transfer. Runtime cues use two port writes per command, up to one command per frame. [Audio builder](../../tools/yonaki/audio.py) · [CPU transfer and command protocol](../../src/yonaki/audio.inc)

`python3 -I tools/yonaki/audio.py` produces `build/yonaki-audio/info.json`. The generated `spc.bin` matches the ROM bytes at `SPC_ADDR` for `SPC_LEN` bytes. The boot, effects and E06 profiles each measured 103 game NMI ticks through SPC ready, with the ready flag first observed on frontend frame 108. The engine waits for 150 boot NMI ticks before continuing PPU and save initialization. The respective traces sent 2, 8 and 65 post-boot commands (WRAM `snd_sent`). These are command counts and boot timing. Cue-to-sound latency, DSP load under simultaneous voices and hardware audio quality still need capture.

## Regression results

Run from the repository root with the stock pinned cores.

```sh
python3 tools/bootstrap.py --with-emulator
make yonaki-test
python3 -I tests/yonaki/bsnes.py --real
```

`make yonaki-test` runs Snes9x with the fixture and full scenario, followed by the fixture-only bsnes replay. The explicit `--real` replay includes both sets. The fixture ROM SHA-256 is `3c1363c36b8af08c76e2c77b0a9f434c2bd9da9573a4880a4e5f1483f8f8aa7b`.

Snes9x passed all 11 test groups, including all six fixture endings, all 20 full scenario endings, both ending-list pages, bookmarks across reload, name entry, fast-forward stopping at unread text, text settings and visual effects. In the held-B fixture test, the driver reached the first unread paragraph 550 frontend frames after confirming the names and stayed there for a further 90 frames of held B. Among the 40 sessions with `finish()` counters (19 fixture and 21 full scenario), the largest NMI end lines were 251 and 255, respectively, against the test's NTSC V-blank window of lines 225–261. Six full scanlines (256–261) remained before the counter wrapped in the worst observed case. The completion dot is unmeasured. The peak queued payload was 3,072 bytes for both ROMs, with zero overruns, deferred jobs and clipped glyphs. The highest `lag_count` was 11 per fixture session and 14 per full scenario session. This counter records NMIs reached before the main thread sets `frame_ready` and can include initialization. It is distinct from a V-blank overrun.

| bsnes 115 replay | Passed | Frontend frames | Screenshot comparisons | Byte-equal final SRAM | Max RGB channel difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixture traces | 20/20 | 18,076 | 51 | 20/20 | 2 |
| Full scenario, all endings and ending list | 21/21 | 264,534 | 22 | 21/21 | 2 |

The standard target completed the fixture replay. The 21 full-scenario traces above ran in parallel groups with the same replay driver and pinned core, each group using its own output directory. The Snes9x command writes `build/yonaki-test/tests.json`. The bsnes command writes `build/yonaki-test/bsnes/RESULTS.json`. The bsnes harness compares SRAM and captured frames at fixed input frame numbers. Cycle timing and PCM equality are outside that check. [Snes9x test driver](../../tests/yonaki/run.py) · [bsnes replay driver](../../tests/yonaki/bsnes.py)

## Follow-up acceptance criteria

1. Prioritize a controlled photo compression trial if ROM size matters. Use the current 8bpp tile bytes as input and require byte-identical decoded tiles, palettes and representative rendered frames. Measure packed banks, decoder work and peak WRAM use, and report any additional transition frames. The build emits power-of-two ROM sizes. Reaching its 2 MiB tier requires fitting in 64 banks, down from 78, including packing and alignment. Text encoding is a smaller ROM target at 93,080 bytes and a change would also affect random access, wrapping and bookmark compatibility.
2. Compare upload scheduling on the same pad traces and events. Require zero V-blank overruns, deferred queue jobs and clipped glyphs. Record worst NMI completion time as a scanline and dot, alongside forced-blank duration and input-to-visible-frame latency. Preserve the established frame schedule for text, choices, transitions and audio cues unless separately approved. Report any proposed timing trade-off with measurements from both cores.
3. Preserve the full scenario, text, choices, routes, endings, art, music and intended presentation. Replay all existing regression sessions across both pinned cores. Require byte-equal final batteries and a maximum RGB channel difference of 2 at recorded frames across cores. Verify existing bookmarks, settings, read marks and ending flags survive an upgrade and a power cycle. Treat any save format change as separate work.
4. Establish the hardware baseline with this ROM on an NTSC Super Famicom using a verified LoROM/FastROM cartridge or flash cartridge with persistent 8 KiB SRAM. Record board/console revision, loader and controller, and repeat on a second PPU revision where available. Use frame-synchronized video and stereo audio capture with an input marker. Include cold boot, sustained typewriter and held-B advance, choices, the worst full and partial photo updates, ripple, and music, ambience and effect overlap. Require no visible tearing, stray tiles, palette corruption, hangs or audible dropouts over three cold boots and runs of each timing case. Compare boot, input-to-draw, transitions and cue onset against hardware baseline captures with a one-frame tolerance for externally measured events. Use a debugger trace or hardware bus trace to check transfer timing, including at the highest observed load with ripple enabled. Require general PPU DMA to start and complete within V-blank or forced blank. For ripple HDMA, verify that both BG1 horizontal-scroll writes fit within the H-blank window of each scanline that transfers data.
5. On the hardware baseline and each candidate, save a paragraph and a choice, power off long enough to discharge console WRAM, and verify restored names, choices, read marks and settings. Repeat with a save seeded by the baseline ROM and verify the ending list and unlock flags. Record hardware failures and console revisions separately from emulator results. Hardware timing, SRAM retention and listening checks remain open until captured.
