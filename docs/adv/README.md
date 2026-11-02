# 潮鳴りの密室 (Shionari no Misshitsu)

An original command-selection mystery adventure for the Super Famicom. In November of Showa 62 (1987), on the night a storm has just cleared at the fictional fishing port 汐見港 (Shiomi Harbor), the chairman of a shipping company is found dead in his warehouse office, locked from the inside. A detective from the prefectural police, 「わたし」 ("I", the player), works with 波多野 (Hatano) of the 汐見署 (Shiomi police station) to establish the truth before dawn.

- ROM: [`dist/shionari.sfc`](../../dist/shionari.sfc) (LoROM 512 KiB, no copier header, 8 KiB battery-backed SRAM). The SHA-256 is in [`dist/shionari.sfc.sha256`](../../dist/shionari.sfc.sha256). Labels, map and manifest are `dist/shionari.*`.
- Music and opening: at power-on, a fiction disclaimer → four pictures with captions (harbor, lighthouse, signal station, warehouse) → title. Each scene plays its own song (investigation, night sea, café, deduction, dawn), and the music is lowered by 10 dB during dialogue. Notes: [music/README.md](music/README.md).
- Speech sound: while the body text of a page spoken by a character (the six people and 「わたし」) is being typed out, a round, voice-like blip of twenty-odd ms plays about once every two characters, with a slightly different pitch and timbre per speaker. It does not play for narration, names, headings, menus, punctuation, waits, or when 「おと：なし」 (sound: off) is set. It is not a reading voice. Design: [speech-sound/DESIGN.md](speech-sound/DESIGN.md).
- Lip sync: only while typing the body text of a page spoken by the person whose portrait is on screen, the mouth moves closed / half-open / open, pauses briefly at punctuation, and closes at the page wait. The motion follows the text speed, not phonemes. Design: [lipsync/DESIGN.md](lipsync/DESIGN.md).
- Verified only on emulators (Snes9x 1.63 and bsnes 115); not verified on real hardware.

## How to play
- Up/Down to select, A to confirm. B goes back one step (during a message it advances, like A). L/R (or Left/Right) pages through lists.
- はなす (talk): ask the person here. しらべる (examine): examine this place. みせる (show): show a clue from the notebook (items and testimony). いどう (move): go somewhere else. てちょう (notebook): しょうこ (evidence), しょうげん (testimony), ヒント (hint), すいりする (deduce), きろくする (save), おと (sound).
- Once you have the clues, answer the chain of reasoning with 「すいりする」 in 「てちょう」. Wrong answers can be retried any number of times.
- Save from 「きろくする」 in 「てちょう」. Resume with 「つづきから」 (continue) on the title screen.

## Build and test
```
make adv            # build/adv/shionari.sfc (data, cc65 2.19, checksum)
make adv-test       # pad-input-only tests on Snes9x 1.63, lip-sync test, speech-sound test (PCM of the actual audio output) + bsnes 115 replay of the same input recordings
make adv-release    # rebuild the test-passing ROM in build/adv-clean, confirm it matches, and copy to dist/
```

## Files
- `src/adv/` the 65816 engine (`shionari.s`: boot / NMI / DMA / pad; `text.inc` glyph drawing; `ui.inc` screen parts and messages; `mouth.inc` lip sync; `voice.inc` speech sound; `game.inc` modes, lists, deduction, fades, portraits, title, ending; `vm.inc` script VM; `save.inc` SRAM; `audio.inc` communication with the SPC700), `adv.cfg` (ld65)
- `data/adv/story.txt` the script (scenes, people, clues, examinable items, topics, reactions to shown clues, hints, deduction, ending). See the explanation at the top of the file for the format
- `data/adv/mouths.txt` half-open and open mouths for the six people (small patches around the mouth; closed is the original portrait unchanged)
- `data/adv/voices.txt` speech-sound voices (per-speaker timbre, pitch, length, volume and interval; silent characters; phrase intonation)
- `tools/adv/` `build.py` (script → tables and script bytecode, text layout and checks, reachability checks), `story.py`, `quantize.py` (background quantization, compositing portraits and mouth shapes, text-layer template, title logo), `mouth.py` (loading and checking mouth data, enlarged preview), `spc.py` (SPC700 driver), `voice.py` (speech-sound waveform synthesis and BRR conversion), `romfix.py`, `preview.py`, `release.py`, `music.py` / `songs.py` (music)
- `tests/adv/` `run.py` (tests), `drive.py` / `emu.py` (driver that operates only through the pad), `routes.py` (investigation routes), `bsnes.py` (replay and comparison on bsnes), `lipsync.py` (lip-sync test), `speech.py` / `pcm.py` / `wavesheet.py` (speech-sound test, PCM analysis, waveform sheets), `devshot.py` / `clipfind.py` (development aids), `compat/` (ROMs and saves from older versions, used to test that an old save can be resumed with 「つづきから」)
- `docs/adv/` `DESIGN.md` (the truth of the story, clue dependency graph, screen, VRAM, SRAM, data), `WALKTHROUGH.md` (spoilers), `REFERENCE_NOTES.md` (reference material consulted), `lipsync/` and `speech-sound/` (lip-sync and speech-sound design), `music/` (music notes and recordings)

## Assets and licenses
- Backgrounds and portraits: newly created with image generation. Their sources and generation prompts are in [ART.json](../../assets/adv/ART.json), and the record of downscaling the originals to hardware size is in [PREPARED.json](../../assets/adv/PREPARED.json). The build inputs are the downscaled files (`assets/adv/{harbor-night,warehouse,signal,cafe,lighthouse,station,harbor}-256.png` and `portrait-*-72.png`), quantized to 240 colors at build time. No artwork, music, cases or dialogue from existing works are used.

## Limitations (at release)
Not verified on real hardware. The speech sound was checked on the actual audio output via waveforms and numbers, but has not been evaluated by listening. Redrawing the whole screen can take up to 6–7 frames of processing wait (VBlank overruns: 0). There is no reading voice and no facial-expression or blinking animation (the lip sync follows the text speed). Progress through the deduction questions is not saved. Play time by a human has not been measured (15–25 minutes is an estimate).
- Font: Shinonome bitmap font, 12 dots (public domain, `assets/shinonome/`). The ▶ cursor is original.
- Music and sound effects: original instruments, scores and driver made with `tools/adv/music.py`, `songs.py` and `spc.py`. Speech sound: original waveforms generated from formulas by `tools/adv/voice.py` (no sounds or recordings from commercial games are used).
