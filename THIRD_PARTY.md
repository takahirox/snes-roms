# Third-party materials

## In the ROMs

- **Font**: Shinonome 12-dot Gothic (`assets/shinonome/shnmk12.bdf`, `shnm6x12r.bdf`), public domain (The Electronic Font Open Laboratory; `assets/shinonome/LICENSE`, EUC-JP). Taken from the Debian source archive `xfonts-shinonome_0.9.11.orig.tar.gz` (sha256 `b5527bbd77a4d8df66c938015c3c85f75da488cfd4d3d9366f6563b090b32895`); only LICENSE, README and the BDF files were extracted. Both games convert the glyphs they use at build time.
- **夜鳴き鐘 title lettering**: `assets/yonaki/logo/*_mask.png` are renderings of Noto Serif CJK JP Regular (SIL Open Font License 1.1); see `assets/yonaki/logo/README`. The font itself is not included.

Everything else in the ROMs — stories, characters, text, engine code, music, sound effects and waveforms — was written for these games. Backgrounds, portraits and silhouettes were newly generated with image-generation tools; prompts and sources are recorded in `assets/adv/ART.json`, `assets/adv/PREPARED.json`, `assets/yonaki/ART.json`, `assets/yonaki/prompts.json` and `assets/yonaki/stage.json`. No material from an existing game is used.

## Build and verification tools (fetched by `tools/bootstrap.py`, not in this repository or the ROMs)

- cc65 V2.19 (zlib license): assembler and linker.
- Pillow 13.0.0 and numpy 2.5.4: 夜鳴き鐘's picture tools and tests.
- Snes9x 1.63 libretro core: local tests only. Snes9x has its own license with non-commercial terms; see `tools/vendor/snes9x-1.63/LICENSE` after bootstrap.
- bsnes 115 (libretro/bsnes `63ee22f7af8f`, GPLv3) with libco (ISC): built unmodified and used only to replay the tests read-only.
