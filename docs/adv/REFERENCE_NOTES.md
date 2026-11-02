# コマンド選択型ADVの参照メモ

原作のシナリオ・素材を使うためではなく、捜査の操作と見せ方を確認する資料。以下の操作資料はファミコン原作のVC説明書であり、SFCリメイクのフレーム計測ではない。

- [任天堂公式説明書：探偵倶楽部PART II](https://www.nintendo.co.jp/data/software/manual/man_tb8j.pdf)：p6で上下選択/A決定・送り/B取消、p16–18でメッセージ/コマンド/対象サブコマンド、指定箇所をカーソルで調べる仕組み、推理、ゲーム内セーブを確認。
- [任天堂公式紹介](https://www.nintendo.com/jp/switch/aw3ca/index.html)：現代版も移動・聞く・呼ぶ・見る/調べるといった操作で進む。これは操作の系統を確認する資料で、SFC版の画面を示すものではない。
- [PVSnesLib Backgrounds](https://github.com/alekmaul/pvsneslib/wiki/Backgrounds)：Mode3はBG1 8bppとBG2 4bpp。背景の一枚絵とUI文字をPPUの別レイヤーで表示する設計の参照。

本作の設計では、場所・相手・対象を選んで情報を集め、手帳に蓄積し、証拠の提示と推理で進める。無意味な反復や、詰み状態を作る誤選択は避ける。事件の前提や真相はオリジナルで、UIや絵はそのまま複製しない。

背景はimagegenスキルのbuiltin image_genによる新規生成。原寸生成画像と生成指示はassets/adv/ART.json、実機向けサイズへの変換はassets/adv/PREPARED.json、ツールはtools/prepare_art.py（このファイルからの相対）に記録した。生成絵の時計や物の形は推理の正しさを保証しないため、ゲーム上の手がかりとして使う部分は別途整合を確認する。
