# snes-roms

Two original adventure games for the Super Famicom (SNES). The games are in Japanese. The repository holds their 65816 engines, SPC700 sound drivers, data tools and emulator tests.

| | 潮鳴りの密室 (Shionari no Misshitsu) | 夜鳴き鐘 (Yonaki Kane) |
|---|---|---|
| Genre | Command-menu mystery adventure | Sound novel |
| ROM | [`dist/shionari.sfc`](dist/shionari.sfc) (512 KiB) | [`dist/yonaki.sfc`](dist/yonaki.sfc) (4 MiB) |
| Story | A short case set in Shiomi, a fictional fishing port, in 1987: a death in a warehouse office locked from the inside, to be solved before dawn. 6 places, 6 people, 33 clues, 11 deduction questions | The last night of 水明館, a remote mountain inn cut off by a typhoon, where people die the way a local legend says. About 65,000 characters, 49 choice points, 20 endings |
| Docs | [docs/adv/README.md](docs/adv/README.md) | [docs/yonaki/README.md](docs/yonaki/README.md) |

Both are headerless LoROM images with 8 KiB of battery SRAM and no special chips. The ROMs' SHA-256 hashes are in `dist/*.sha256`. They have been tested on emulators only (Snes9x 1.63 and bsnes 115), not on real hardware.

## Build

```
python3 tools/bootstrap.py                  # fetch cc65 2.19 and Pillow / numpy into tools/vendor/
make                                        # build/adv/shionari.sfc and build/yonaki/yonaki.sfc
```

The tests also need the emulator cores, which are built from source (a C/C++ compiler is required).

```
python3 tools/bootstrap.py --with-emulator  # build the Snes9x 1.63 and bsnes 115 libretro cores
make test                                   # both games: play with pad input only, then replay the same input on bsnes and compare
make adv-release yonaki-release             # copy the tested ROMs to dist/
```

External tools are pinned by version and SHA-256 in `tools/dependencies.json`; nothing is installed system-wide. Developed with Python 3.13.

## Layout

| | 潮鳴りの密室 | 夜鳴き鐘 |
|---|---|---|
| Engine (65816) | `src/adv/` | `src/yonaki/` |
| Scenario | `data/adv/` | `data/yonaki/` |
| Art | `assets/adv/` | `assets/yonaki/` |
| Build tools, music, sound driver | `tools/adv/` | `tools/yonaki/` |
| Tests | `tests/adv/` | `tests/yonaki/` |
| Docs | `docs/adv/` | `docs/yonaki/` |

Shared: `assets/shinonome/` (text font), `tools/png_codec.py`, `tools/host_libretro_replay.py` (bsnes replay), `tests/harness.py` (Snes9x driver).

Sources and licenses of third-party material are listed in [THIRD_PARTY.md](THIRD_PARTY.md).
