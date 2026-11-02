# SFC アドベンチャー 2 作

スーパーファミコン用に作った、オリジナルのアドベンチャーゲーム 2 本です。65816 アセンブリのエンジン、SPC700 の音源ドライバ、データを作るツール、エミュレータでの自動テストがそろっています。

| | 潮鳴りの密室 | 夜鳴き鐘 |
|---|---|---|
| ジャンル | コマンド選択式の推理アドベンチャー | サウンドノベル |
| ROM | [`dist/shionari.sfc`](dist/shionari.sfc) (512 KiB) | [`dist/yonaki.sfc`](dist/yonaki.sfc) (4 MiB) |
| 内容 | 昭和 62 年の架空の漁港「汐見港」で、内側から鍵のかかった倉庫の事務所の死を、夜明けまでに調べる短編。調べる場所 6 か所、人物 6 人、手がかり 33、推理 11 問 | 山奥の一軒宿「水明館」の最後の夜、台風で孤立した宿で伝説をなぞるように人が死ぬ。約 6.5 万字、選択肢 49 か所、結末 20 種 |
| 資料 | [docs/adv/README.md](docs/adv/README.md) | [docs/yonaki/README.md](docs/yonaki/README.md) |

どちらも LoROM、コピアヘッダなし、8 KiB バッテリー SRAM で、特殊チップは使いません。ROM の SHA-256 は `dist/*.sha256` にあります。確認はエミュレータ (Snes9x 1.63 と bsnes 115) だけで、実機では確かめていません。

## 作る

```
python3 tools/bootstrap.py                  # cc65 2.19 と Pillow / numpy を tools/vendor/ に取得
make                                        # build/adv/shionari.sfc と build/yonaki/yonaki.sfc
```

テストには、エミュレータのコアも取得します (C/C++ コンパイラが必要です)。

```
python3 tools/bootstrap.py --with-emulator  # Snes9x 1.63 と bsnes 115 の libretro コアをソースからビルド
make test                                   # 両作のテスト (パッド入力だけで遊び、bsnes で同じ操作を再生して比べる)
make adv-release yonaki-release             # テストに合格した ROM を dist/ へ
```

外部ツールは `tools/dependencies.json` に版と SHA-256 を固定しています。システムには何も入れません。Python 3.13 で使っています。

## ディレクトリ

| 場所 | 潮鳴りの密室 | 夜鳴き鐘 |
|---|---|---|
| エンジン (65816) | `src/adv/` | `src/yonaki/` |
| シナリオ | `data/adv/` | `data/yonaki/` |
| 絵 | `assets/adv/` | `assets/yonaki/` |
| ビルドツール、作曲、音源ドライバ | `tools/adv/` | `tools/yonaki/` |
| テスト | `tests/adv/` | `tests/yonaki/` |
| 資料 | `docs/adv/` | `docs/yonaki/` |

共通: `assets/shinonome/` (本文のフォント)、`tools/png_codec.py`、`tools/host_libretro_replay.py` (bsnes での再生)、`tests/harness.py` (Snes9x での操作)。

素材の出所とライセンスは [THIRD_PARTY.md](THIRD_PARTY.md) にあります。
