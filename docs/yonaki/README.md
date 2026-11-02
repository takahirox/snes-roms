# 夜鳴き鐘 (Yonaki Kane)

An original sound novel for the Super Famicom. On the last night of 水明館 (Suimeikan), a lone inn deep in the mountains that still carries the air of the Shōwa era, a typhoon cuts the inn off, and people die as if re-enacting the legend of おゆらさま (Oyura-sama). "I" (僕), a rookie reporter for a travel magazine, chases the truth with the photographer 早瀬千尋 (Hayase Chihiro).

- ROM: [`dist/yonaki.sfc`](../../dist/yonaki.sfc) (LoROM 4 MiB, 8 KiB battery-backed SRAM, no copier header)
- Design (spoilers): [DESIGN.md](DESIGN.md). Engine: [ENGINE.md](ENGINE.md). Music: [music/README.md](music/README.md)

## How to play
- A: advance text / select. Up/down: choices (each is prefixed with a letter A, B, C…). Hold B: fast-forward through text already read (stops at unread text). START: menu (しおりをはさむ "insert a bookmark", 文字の速さ "text speed", タイトルへ "to the title").
- Title: はじめから (new game) / しおりから (continue from a bookmark) / 結末の一覧 (list of endings) / おまけ (bonus; after it is unlocked).
- はじめから: choose the protagonist's family name (initially 結城 (Yūki); his given name never appears in the story) and the given name of the heroine 早瀬○○ (initially 千尋 (Chihiro); the family name 早瀬 is fixed), up to 4 characters each. Pick a character with the D-pad and enter it with A; B erases one character; L / R or the かな / カナ / 漢字 (hiragana / katakana / kanji) buttons below switch the character set; START or 決定 (confirm) decides. The chosen names are pre-filled from then on and are also stored in bookmarks.
- The story branches on your choices; guide it badly and you reach a bad ending without getting to the truth.
- After you see the true ending of the main story, new options appear among the main story's choices and lead into other scenarios.

## Contents
| | |
|---|---|
| Scenario | Main story (prologue to chapter 5), おゆら篇 (the Oyura chapter; supernatural), 千鶴篇 (the Chizuru chapter; Shōwa 44 = 1969), bonus 編集部篇 (the editorial-office chapter). About 65,000 characters, about 2,400 paragraphs, 49 choice points |
| Endings | 20 (main story 14, おゆら篇 3, 千鶴篇 2, bonus 1) |
| Backgrounds | 43 photo-like backgrounds (made with Codex CLI image generation; sources and prompts in [ART.json](../../assets/yonaki/ART.json)) |
| Characters | 100-odd per-scene silhouettes (generated to match each background photo, in poses such as sitting in a seat, kneeling formally before a meal tray, or standing in the bath. [stage.json](../../assets/yonaki/stage.json). Shown in blue, white or red) |
| Sound | 18 original songs, 32 sound effects, rain and storm ambience (synthesized from formulas for the SPC700) |

## Build and test
```
make yonaki          # build/yonaki/yonaki.sfc
make yonaki-test     # test playing to all 20 endings with pad input only on Snes9x 1.63 + replay on bsnes 115
make yonaki-release  # copy the ROM that passed the tests to dist/
python3 -I tests/yonaki/shots.py LABEL --follow    # take screenshots from a script label
python3 -I tests/yonaki/routes.py                  # the path of choices to each ending
python3 -I tests/yonaki/music_review.py            # recordings of the songs and sound effects (docs/yonaki/music/review/)
```

## Assets and licenses
- Backgrounds and silhouettes: newly made with Codex CLI's built-in image generation. For the silhouettes, a person was painted into the background photo and that shape was cut out (`tools/yonaki/gen_stage.py`). No real photographs or artwork from existing works are used.
- The title lettering 夜鳴き鐘 and 終 ("The End"): images rendered from Noto Serif CJK JP (SIL Open Font License 1.1) ([assets/yonaki/logo/](../../assets/yonaki/logo/)).
- Body text glyphs: Shinonome bitmap font, 12 dots (public domain).
- Songs, sound effects, story and characters: all newly made in this repository. No story, characters, lines or music from existing works are used.

## Limitations
- Not tested on real hardware (only on the emulators Snes9x 1.63 and bsnes 115).
- The songs and sound effects were checked through waveforms and numbers, but have not been evaluated by human listening.
- The text is about 65,000 characters, which is short compared with large commercial titles.
- There are no menu sounds.
