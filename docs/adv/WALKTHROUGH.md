# 潮鳴りの密室 (Shionari no Misshitsu) — Walkthrough (spoilers, for QA)

A prose version of the test routes `routes.standard` and `routes.deduce` (`tests/adv/routes.py`). Each step is written as "place: command → item". Place names, commands and item labels are the in-game Japanese text.

1. 第三倉庫 事務所 (Warehouse No. 3, office): しらべる (examine) → 柱時計 (pendulum clock), 振り子の窓 (pendulum window), 金庫 (safe), 鍵束 (key ring), メモ (memo), 荷揚げ口 (loading hatch), 鉄梯子 (iron ladder) / はなす (talk) (波多野 (Hatano)) → 検視 (autopsy), 辰巳とは (about Tatsumi)
2. 汐見署 (Shiomi police station): はなす (修一 (Shuichi)) → ゆうべのこと (last night), 父の戸じまり (father's locking-up habit), 時計のこと (about the clock)
3. 汐見港 信号所 (Shiomi Harbor signal station): しらべる → 掲示板 (notice board), 潮見表 (tide table), 回覧板 (circular) / はなす (古賀 (Koga)) → ゆうべのこと, 港内電話 (harbor phone), 梯子のこと (about the ladder), 灯台 (lighthouse) (unlocks 汐見灯台 (Shiomi Lighthouse))
4. 第二桟橋 詰所 (Pier No. 2, watch hut): はなす (辰巳 (Tatsumi)) → ゆうべのこと / みせる (show) → 保守のおしらせ (maintenance notice) (Tatsumi revises his story) / しらべる → 詰所の電話 (hut phone), 鍵帳 (key log), 作業艇 (work boat) / みせる → 詰所の電話 (Tatsumi breaks down)
5. 汐見灯台: しらべる → 当直日誌 (watch log)
6. 第二桟橋: みせる → 灯台の当直日誌 (lighthouse watch log) (he admits taking the boat out)
7. 信号所: はなす → 物入れの鍵 (locker key) (borrow the spare key)
8. 第二桟橋: しらべる → 物入れ (locker) (black ledger)
9. 喫茶「浮標」 (café "Buoy"): みせる → 黒い帳簿 (black ledger) (the half-past-nine appointment)
10. てちょう (notebook) → すいりする (deduce)
   1. 荷揚げ口
   2. 外れたかんぬき (unbarred bolt) (鉄梯子の錆あと (rust marks on the iron ladder) is also correct)
   3. 潮見表 (古賀「梯子と潮」 (Koga: "ladder and tide") is also correct)
   4. 九時半ごろ (around half past nine)
   5. 修一「九時二十五分」 (Shuichi: "9:25")
   6. 灯台の当直日誌
   7. 時計の赤い粉 (red powder on the clock)
   8. 辰巳
   9. 保守のおしらせ (古賀「電話は鳴らん」 (Koga: "the phone couldn't ring"), 詰所の電話, and 回覧板 are also correct)
   10. 作業艇の鍵帳 (work-boat key log) (辰巳「舟を出した」 (Tatsumi: "I took the boat out") is also correct)
   11. ママ「九時半の約束」 (the proprietress: "the half-past-nine appointment") (黒い帳簿 is also correct)

The conditions for starting the deduction are in DESIGN.md §2.3. If something is missing, the game states what is missing for the first unmet condition and returns to the notebook. The notebook's 「ヒント」 (hint) and Hatano's 「相談する」 (consult) point to the first stage that is not yet satisfied (the first time only the direction; choosing it again gives the concrete action).
