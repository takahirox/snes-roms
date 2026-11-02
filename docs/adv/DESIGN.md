# 潮鳴りの密室 (Shionari no Misshitsu) — Design (SFC command-selection adventure)

Target: `dist/shionari.sfc` (LoROM, no copier header, 512 KiB = 16 banks, 8 KiB battery-backed SRAM).
Sources: `src/adv/` (65816, ca65/ld65), `tools/adv/` (build), `data/adv/` (scenario), `tests/adv/`, `build/adv/`.

Status: this is a design document. The state of implementation and verification is in `docs/adv/STATUS.md`. Behavior has not been verified on real hardware (an SFC console).

---

## 1. Story

### 1.1 Setting
- From the night of Saturday, November 14, Showa 62 (1987), to the dawn of Sunday the 15th. The fictional fishing port 汐見港 (Shiomi Harbor, しおみこう).
- Stormy weather (時化, shike) since the previous day. At 3 p.m. on the 14th the fishermen's cooperative banned departures; every fishing boat was either hauled ashore or moored with its key left with the cooperative. The rain stopped at exactly 21:00. Wind and waves remained.
- **Harbor phone (港内電話)**: a private wired phone system linking the harbor facilities (signal station, each warehouse, the Pier No. 2 watch hut). The switchboard is in the signal station, and extensions cannot reach each other without going through it. It is separate from outside phones (Denden Kosha = NTT public lines). The Pier No. 2 watch hut has only the harbor phone. From 21:00 to 23:00 on the 14th the whole system was shut down for switchboard maintenance (a notice posted at the signal station, and a circular sent around to the parties concerned on the 13th).
- **Warehouse No. 3 (第三倉庫)**: an old warehouse of 浜崎海運 (Hamasaki Kaiun, Hamasaki Shipping). Upstairs is the chairman's office. The landward "front door" (表戸) locks with a knob on the inside. On the sea side is a "loading hatch" (荷揚げ口) for hoisting cargo up from boats, closed with a bolt (かんぬき) on the inside. The lower part of the iron ladder below the hatch has rotted away, so it can be reached from a boat only for about an hour either side of high tide (high tide on the 14th: 21:18).
- Consistency with reality: no unrealistic devices such as a power outage or NTT phones going dead. The time of death is never determined from the reading of the stopped clock (the clock only shows that it was "tampered with"). The autopsy estimate (21:00–23:00) is treated as a range.

### 1.2 People (appearance matched to the host's portraits)
| ID | Name | Age / position | Appearance | Location | Portrait |
|---|---|---|---|---|---|
| — | わたし ("I") | Detective, First Investigation Division, prefectural police HQ (name never shown; the player) | Not shown | — | none |
| hatano | 波多野 夏子 (はたの なつこ, Hatano Natsuko) | 35, criminal affairs section of 汐見署 (Shiomi police station). Partner | Short dark-brown hair, beige blazer | Crime scene | detective |
| shuichi | 浜崎 修一 (はまさき しゅういち, Hamasaki Shuichi) | 47, president of Hamasaki Shipping. The victim's eldest son. One of those who found the body | Black hair, charcoal suit, maroon tie | Police station | director |
| yukiko | 潮田 ゆき子 (しおた ゆきこ, Shiota Yukiko) | 52, proprietress ("mama") of the café 「浮標 (ブイ)」 ("Buoy") | Hair tied up, russet cardigan and apron | Café | owner |
| ookouchi | 大河内 正 (おおこうち ただし, Ookouchi Tadashi) | 63, lighthouse engineer at 汐見灯台 (Shiomi Lighthouse). On stormy nights he watches the harbor and keeps a watch log | Graying hair, mustache, navy work jacket | Lighthouse | keeper |
| koga | 古賀 勇 (こが いさむ, Koga Isamu) | 58, communications officer at the harbor signal station. Also in charge of the harbor phone switchboard | (requested from the host) Short white crew cut, tanned, gray work clothes | Signal station | not yet |
| tatsumi | 辰巳 透 (たつみ とおる, Tatsumi Tooru) | 38, accountant at Hamasaki Shipping. **The culprit** | (requested from the host) Thin, black hair parted 7:3, silver-rimmed glasses, white shirt under a navy padded jacket | Pier No. 2 watch hut | not yet |
| (victim) | 浜崎 剛造 (はまさき ごうぞう, Hamasaki Gouzou) | 71, chairman and founder of Hamasaki Shipping | Does not appear | — | — |

### 1.3 The truth
- To cover his boat-racing debts, Tatsumi had embezzled about 3 million yen of the "mutual aid reserve" (共済積立金, the sailors' savings) held by the company. The chairman noticed it through a secret ledger (the reserve ledger with a black cover).
- At noon on the 14th, at the café 「浮標」, the chairman slapped the ledger and told Tatsumi, 「今夜九時半、裏から来い。月曜には署へ行く」 ("Tonight at half past nine, come round the back. On Monday I'm going to the police") (Yukiko overheard part of it). The chairman did not mean to turn Tatsumi in, but **to go to the police together so that Tatsumi could turn himself in, and to bow his own head as well** (the memo on the desk, 「月曜 署へ 辰巳と」 ("Monday, police, with Tatsumi"), whose meaning flips near the end). "Round the back" was to avoid being seen.
- Tatsumi was on a business trip to the prefectural office on the 12th–13th and did not see the circular about the harbor phone maintenance that went around on the 13th (only Tatsumi's box on the circular has no seal).
- The course of the night (established timeline):

| Time | Event | Who knows / clue |
|---|---|---|
| 20:30 | Tatsumi borrows the work boat's key from the watch hut "for patrol" | Key log |
| 21:00 | The rain stops. Koga shuts down the switchboard and starts working by the signal station window (from which Warehouse No. 3's front door is visible under the outdoor light) | Notice, circular, Koga, Ookouchi |
| 21:18 | High tide | Tide table |
| 21:25 | The chairman calls Shuichi at home on the outside phone to say he'll be late. On his end there is a knock-knock, he says 「来たか」 ("You came"), and hangs up | Shuichi |
| 21:30 | From the lighthouse, two figures in the office window | Watch log |
| about 21:35 | An argument. Tatsumi shoves the chairman, who hits the back of his head on the corner of the safe and dies (the time comes from the confession; the evidence supports only "21:25 visitor, 21:30 two people, 21:40 lights out") | Confession (+ the autopsy injury) |
| 21:35–21:40 | Tatsumi takes the ledger, and still wearing rust-stained work gloves, turns the clock hands to 10:15 and stops the pendulum, puts out the light at 21:40, and climbs down the ladder from the loading hatch to the work boat. The bolt cannot be set from outside | Red powder on the clock, unbarred bolt, rust marks on the ladder, watch log (21:40 lights out) |
| 21:50 | An unlit small boat goes from the direction of Warehouse No. 3 to Pier No. 2 | Watch log |
| to 22:00 | Moors the work boat, hides the ledger in the locker. Drops one glove on the deck | Work boat, glove, ledger |
| 22:12 | Comes to the café 「浮標」 and checks the time: 「ママ、今何時?」 ("Mama, what time is it?"). His jacket is wet with seawater (the rain stopped at 21:00) | Yukiko, Ookouchi (rain) |
| 23:00 | Switchboard maintenance ends. Tatsumi writes the return of the work boat key in the key log | Key log |
| 23:30 | His father not coming home, Shuichi calls Koga; they break the glass of the front door, go in, and find him | Shuichi, Koga, Hatano |
| 0:40 | わたし arrives. The station chief sees it as "locked from the inside, an accidental fall" | Introduction |

- Tatsumi's false alibi: he testifies, 「十時ごろ、詰所の港内電話に会長から『帳簿の件は明日話そう』と電話があった」 ("Around ten, the chairman called the hut's harbor phone and said, 'Let's talk about the ledger tomorrow'"). Combined with the clock stopped at 10:15, this makes a story in which the chairman was alive after 22:00 and Tatsumi himself was at the café from 22:12.
- **What the locked room really is**: (a) The chairman locked the front door himself from the inside (his habit at night). The office key ring is on the desk. The duplicate key is in the key box at the signal station, with no record of it being taken out. From 21:00 to 23:00, Koga was watching the front door under the outdoor light. (b) The loading hatch on the sea side is at the top of a ladder that can be reached from a boat only around high tide. At the time of discovery (23:30), more than two hours past high tide, the ladder was out of reach, and everyone assumed "no one could get in or out". In fact Tatsumi came and went by work boat just after high tide, and the bolt, which cannot be set from outside, was left unbarred.
- Independence of the evidence: the time of death is kept as the autopsy range (21:00–23:00) and not asserted in the deduction. What the deduction shows is that "at 21:25 a visitor came from the sea side (the knocking and 『来たか』 in the call to Shuichi), at 21:30 there were two people in the office, at 21:40 the lights went out and it stayed dark from then on (the lighthouse log; Ookouchi says the office window and Pier No. 2 are in plain view from the lighthouse window)". Therefore the only things that say "the chairman was alive after 22:00" are Tatsumi's testimony and the stopped clock, and both collapse. This evidence does not depend on the clock. The evidence that Tatsumi's phone testimony is a lie is the switchboard shutdown (notice, Koga's work), the fact that the hut has only the harbor phone, and the fact that Tatsumi did not see the circular. The evidence that he went out to sea is the key log, the watch log and the glove. The motive is the ledger and the noon appointment. The confession is for explaining the ending; the deduction does not rely on it.

### 1.4 People who look suspicious (misdirection)
- Shuichi: was quarrelling with his father over selling Warehouse No. 3 to a resort development company (around the time of the 1987 Resort Law, Showa 62). But at 21:25 he was at home taking his father's call, Koga was watching the front door, and he has no work boat key.
- Koga: manages the duplicate key and was working alone. But his testimony that no one came to the front door under the outdoor light does not contradict the lighthouse log, and traces of his shutting down the switchboard remain.
- The "accident" theory: the injury from the safe's corner could be explained by a fall. But it cannot explain the emptied shelf of the safe, the tampered clock, or the unbarred bolt.

---

## 2. Scenes (6) and what can be examined

`*` marks items that appear conditionally. `→` is the clue obtained. In-game labels are given in Japanese.

| ID | Scene | Background | Person |
|---|---|---|---|
| warehouse | 第三倉庫 二階事務所 (Warehouse No. 3, upstairs office) (crime scene) | warehouse | Hatano |
| signal | 汐見港 信号所 (Shiomi Harbor signal station) | signal | Koga |
| pier | 第二桟橋 詰所 (Pier No. 2 watch hut) | harbor (night version requested) | Tatsumi |
| cafe | 喫茶「浮標」 (café "Buoy") | cafe | Yukiko |
| lighthouse | 汐見灯台 (Shiomi Lighthouse) (not reachable at first) | lighthouse | Ookouchi |
| station | 汐見署 (Shiomi police station) | station | Shuichi |

- Crime scene, しらべる (examine): 柱時計 (pendulum clock) → K_CLOCK / *振り子の窓 (pendulum window) (after the clock) → K_RUST / 金庫 (safe) → K_SAFE / 鍵束 (key ring) → K_KEYS / 赤い帳面 (red account book) (an ordinary cash book; the figures add up) / 電話 (phone) (the black outside phone and the gray harbor-phone receiver side by side) / メモ (memo) → K_MEMO / 表戸 (front door) / 荷揚げ口 (loading hatch) → K_BAR / *鉄梯子 (iron ladder) (after the loading hatch) → K_LADDER
- Crime scene, はなす (talk) (Hatano): 検視 (autopsy) → T_AUTOPSY / 発見のようす (how he was found) / 署長の見立て (the station chief's view) / 鍵のこと (about the keys) / *相談 (consult) (tells what to do now, with the same content as the notebook hint)
- Signal station, しらべる: 掲示板 (notice board) → K_NOTICE / *潮見表 (tide table) (after the notice board) → K_TIDE / *回覧板 (circular) (after K_NOTICE) → K_CIRC / 交換盤 (switchboard) / 鍵箱 (key box) → K_SPARE / 窓 (window)
- Signal station, はなす (Koga): 事件のこと (about the case) / ゆうべのこと (last night) → T_KOGA / 港内電話 (harbor phone) → T_LINE / 会長のこと (about the chairman) / 灯台 (lighthouse) → makes the lighthouse reachable / *梯子 (ladder) (after K_BAR or K_LADDER) → T_LADDER / *舟 (boats) (after T_LADDER or K_LOG) → T_BOATS / *物入れの鍵 (locker key) (after examining the work boat) → spare key (flag)
- Pier No. 2, しらべる: 詰所の電話 (hut phone) → K_PHONE / 鍵帳 (key log) → K_BOATLOG / 作業艇 (work boat) → K_GLOVE (the locker is locked) / *物入れ (locker) (after the spare key) → K_LEDGER / 海 (sea)
- Pier No. 2, はなす (Tatsumi): 事件のこと / ゆうべのこと → T_TATSUMI / 会長のこと / *出張 (business trip) (after the circular) → T_TRIP / *帳簿 (ledger) (after K_SAFE)
- Café, しらべる: 壁の時計 (wall clock) (set every morning by the radio time signal) / 窓 / カウンター (counter)
- Café, はなす (Yukiko): ゆうべのこと → T_YUKIKO / *辰巳のようす (how Tatsumi seemed) (after T_YUKIKO) → T_WET / 会長のこと / *辰巳のこと (about Tatsumi) → T_BOATRACE / 修一のこと (about Shuichi) (misdirection) / 灯台 → makes the lighthouse reachable
- Lighthouse, しらべる: 当直日誌 (watch log) → K_LOG / 双眼鏡 (binoculars) / 灯 (the light)
- Lighthouse, はなす (Ookouchi): ゆうべのこと / 雨 (rain) → T_RAIN / *人影 (figures) (after K_LOG) / *小舟 (small boat) (after K_LOG)
- Police station, しらべる: 遺品の上着 (the deceased's jacket) / 署長の書類 (the station chief's papers) (「転倒による事故の見込み」, "probably an accidental fall") / 掲示 (notices) (wanted posters and the like, for atmosphere)
- Police station, はなす (Shuichi): ゆうべのこと → T_SHUICHI / 発見のこと (about the discovery) / 父の戸じまり (father's locking-up habit) → T_HABIT / *時計のこと (about the clock) (after K_CLOCK) → T_WIND / リゾートの話 (the resort deal) (misdirection)

### 2.1 Important reactions to みせる (show)
| Person | Shown | Reaction |
|---|---|---|
| Tatsumi | K_NOTICE / T_LINE / K_CIRC | Revises: 「外の電話だったかも」 ("Maybe it was the outside phone") → T_TATSUMI2 |
| Tatsumi | K_PHONE (after the revision) | 「……記憶ちがいでした」 ("……I misremembered") → F_TATSUMI_BROKE |
| Tatsumi | K_LOG | 「見回りで作業艇を出していた。灯りはつけ忘れた」 ("I had the work boat out on patrol. I forgot to turn on the light") → T_TATSUMI3 |
| Tatsumi | K_LEDGER | Shaken, falls silent |
| Koga | T_TATSUMI | 「十時に港内電話? ありえん、盤を止めとった」 ("The harbor phone at ten? Impossible, I had the board shut down") |
| Koga | K_LADDER | Talk about the ladder → T_LADDER |
| Koga | K_GLOVE | It's a glove kept on the work boat |
| Yukiko | K_LEDGER | 「この帳面よ! 今夜九時半、裏から来い、月曜には署へ…」 ("That's the book! Tonight at half past nine, come round the back, on Monday to the police…") → T_APPOINT |
| Yukiko | T_TATSUMI | 「電話? 店ではそんな話してなかったわ」 ("A phone call? He said nothing like that in the café") |
| Ookouchi | K_CLOCK | 「十時十五分? 二階は九時四十分から真っ暗だった」 ("Quarter past ten? The upstairs was pitch dark from 9:40") |
| Ookouchi | T_TATSUMI | 「真っ暗な部屋で電話をかけたのかね」 ("He made a phone call in a pitch-dark room, did he?") |
| Shuichi | K_CLOCK | T_WIND (he winds it on the 1st of every month; it shouldn't stop) |
| Shuichi | K_SAFE / K_LEDGER | 「父の積立金台帳です」 ("That's my father's reserve ledger") |
| Hatano | anything | A short opinion on that clue (to prevent getting stuck) |
Combinations not in the table above get each person's fixed default reply.

### 2.2 Clue dependency graph
```
intro ─┬─ scene: clock K_CLOCK ── pendulum window K_RUST ──────────────────────┐ (clock tampering)
       │        └─(show Shuichi)─ T_WIND ──────────────────────────────────────┘
       ├─ scene: loading hatch K_BAR ── iron ladder K_LADDER ─(Koga)─ T_LADDER ─┐ (way in and out)
       │                  signal station: notice board ─ tide table K_TIDE ─────┘
       ├─ pier: Tatsumi, last night T_TATSUMI ───────┐
       │  signal station: notice board K_NOTICE ─────┼─(show Tatsumi)─ T_TATSUMI2 ─ hut phone K_PHONE ─(show)─ breaks down
       │  signal station: Koga, harbor phone T_LINE ─┘   circular K_CIRC ─ Tatsumi: business trip T_TRIP
       ├─ café: Yukiko / signal station: Koga ─ lighthouse opens ─ watch log K_LOG ─(show Tatsumi)─ T_TATSUMI3
       │                                                           └─ Koga: boats T_BOATS
       ├─ station: Shuichi, last night T_SHUICHI (the 21:25 call)
       └─ pier: work boat K_GLOVE ─ Koga: locker key ─ locker K_LEDGER ─(show Yukiko)─ T_APPOINT
          pier: key log K_BOATLOG
```
Five places are reachable from the start. They can be examined in any order, and every conditional item is unlocked by actions at places reachable from the start.

### 2.3 Deduction (notebook → すいりする (deduce))
To start, every key combination in the chain of reasoning must be in hand (following the host's review, the deduction cannot start with only items that are weak on their own).
- From the sea: K_BAR (unbarred bolt) **and** T_HABIT (the chairman sets the bolt every night) **and** K_LADDER (broken ladder and fresh rust) **and** K_TIDE (high tide 21:18) **and** T_LADDER (reachable only around high tide)
- Time window: T_SHUICHI (the knocking at 21:25 and 『来たか』) **and** K_LOG (two people at 21:30, lights out at 21:40, an unlit boat at 21:50)
- Clock: K_RUST (rust powder on the handle of the pendulum window)
- Phone: T_TATSUMI **and** (K_NOTICE or T_LINE) **and** K_PHONE (the hut has only the harbor phone)
- Boat: K_BOATLOG (Tatsumi borrowed the key at 20:30) **and** K_LOG
- Motive and appointment: K_LEDGER **and** T_APPOINT
If something is missing, the game says concretely what is missing for the first unmet condition and returns to the investigation (in the same order as the hint table).

| # | Question | Form | Answer | Rebuttal to tempting wrong choices |
|---|---|---|---|---|
| 1 | Where did the culprit get in and out? | Choice (front door / loading hatch / window / attic) | Loading hatch | Koga was watching the front door and the key ring is on the desk; the window is fixed shut |
| 2 | Clues showing the loading hatch was used | Clues | K_BAR, K_LADDER | T_HABIT alone does not show the bolt was unbarred |
| 3 | Clues showing when the ladder was reachable from a boat | Clues | K_TIDE, T_LADDER | — |
| 4 | Around what time was the visitor with the chairman? | Choice (around half past nine / around ten / around quarter past ten / around half past eleven) | Around half past nine | The only basis for around ten is Tatsumi's word; for quarter past ten, only the clock |
| 5 | Clue showing when the visitor arrived | Clues | T_SHUICHI | — |
| 6 | Clue showing what happened in the room after that | Clues | K_LOG | T_AUTOPSY is too broad |
| 7 | Clue showing the pendulum clock at 10:15 cannot be trusted | Clues | K_RUST | T_WIND only says it rarely stops; it could still have stopped from being bumped |
| 8 | Who gave false testimony? | Choice (5 people) | Tatsumi | Each is rebutted with information already obtained |
| 9 | Clues that break that lie | Clues | K_NOTICE, T_LINE, K_PHONE, K_CIRC (after the correct answer, the partner ties the three together and explains) | — |
| 10 | Clues showing Tatsumi took the boat out | Clues | K_BOATLOG, T_TATSUMI3 | K_GLOVE is equipment of the work boat, so it does not show who used it |
| 11 | Clues showing why Tatsumi visited at half past nine | Clues | T_APPOINT, K_LEDGER | — |

The time of death is not asserted even in the deduction (it only says 「十時過ぎに生きていたと言えるものは何もない」, "nothing shows he was alive after ten").

On a wrong answer, the partner rebuts according to what was chosen and returns to the same question (no game over; wrong answers are counted). B quits the deduction and returns to the investigation. Answering all questions correctly leads to the confrontation, the confession, the meaning of the memo, the dawn epilogue, 「おわり」 ("The End") with the record display (number of actions and number of wrong answers in the deduction), and the title.

### 2.4 Hints (notebook → ヒント (hint))
From a table of conditions in order, the hint for the first unsatisfied stage is shown. The first time only the direction is given; choosing it again at the same stage gives the concrete action (where, what, with which command). The partner's 「相談」 (consult) uses the same table.

---

## 3. Controls and screen

### 3.1 Screen (256x224)
```
y   0- 15 heading (BG2 4bpp): place name on the left, status on the right (time, or "しらべる ▶ target")
y  16-143 background picture 256x128 (BG1 8bpp, 512 tiles)
y 144-223 lower window (BG2 4bpp): framed
   command mode: 5 commands vertically in the left box (x 8-68) (y 149,163,177,191,205), a 5-line target list in the right box (x 76-244)
   message mode: the whole window. Speaker name (yellow) + 3 lines of body text; narration has 4 lines. 18 characters per line (x 12-228). Line spacing 17px. Advance with ▼
```
- The font is Shinonome 12-dot (shnmk12, public domain); only the needed characters are extracted at build time. The ▶ cursor and the ▼ advance mark are original 12x12 glyphs (JIS X 0208 has no ▶).
- Colors (CGRAM 0-15, fixed for the UI): 0 black (backdrop), 1 window background (dark navy), 2 body text (white), 3 frame (light), 4 frame shadow, 5 already-read / unselectable items (gray), 6 speaker, cursor, selected command (yellow), 7 new clue (light blue).
- When a list exceeds 5 lines, ▲/▼ and a page indicator like "2/3" appear at the right edge. Up/Down scroll one line at a time; L/R (or Left/Right) move one page.
- Controls: D-pad Up/Down to select (held: repeats every 5 frames after 16 frames), A to confirm/advance, B to go back (during a message it advances, like A). A and B are accepted only at the moment of pressing, so holding them does not skip dialogue. Pressing A while a message is being typed shows the whole page at once.
- Topics already read and targets already examined are gray; those not yet chosen are white.
- During conversation and みせる (show), the scene person's portrait (72x104) is overlaid at a fixed position on the background picture (replacement tiles composited at build time are DMA-transferred during VBlank; forced blank is not used).

### 3.2 Commands
| Command | What is chosen next | Action |
|---|---|---|
| はなす (talk) | Topic (the partner is the one person in the scene) | Runs the script |
| しらべる (examine) | Target | Runs the script |
| みせる (show) | Clue (one list combining items and testimony) | Reaction for (person, clue); if none, the person's fixed default reply |
| いどう (move) | Place | Changes the picture |
| てちょう (notebook) | しょうこ (evidence) / しょうげん (testimony) / ヒント (hint) / すいりする (deduce) / きろくする (save) / おと (sound) | List → read description / deduction / save / sound on/off |

Title: 「はじめから / つづきから」 (new game / continue). When there is no save data or it is corrupted, 「つづきから」 is shown in gray, and choosing it displays the reason (the game does not start).

---

## 4. Hardware design

### 4.1 ROM and CPU
- LoROM `$20` (SlowROM), cartridge type `$02` (ROM+RAM+battery), ROM 512 KiB (`$09`), SRAM 8 KiB (`$03`), country code Japan. The checksum is written by `tools/adv/romfix.py`.
- Bank allocation (as actually built for candidate A): bank0 holds code, tables, the script, palettes, the logo, and the SPC700 driver. bank1 holds the font (588 glyphs × 24 bytes). bank2 holds the body text (416 texts, 32018 bytes; if it runs out, the build tool moves on to the next bank; no single text straddles a bank boundary). bank3-9 hold the 7 backgrounds (one bank each, 32768 bytes = 512 tiles; picture DMA is in chunks of at most 4 KiB and does not straddle a bank boundary). bank10-11 hold the portrait replacement tiles (6 portraits, 7488 bytes each; no portrait straddles a bank boundary). bank12 holds the text-layer template (22528 bytes). bank13-15 are free ($FF). 512 KiB in total. Each bank's capacity is set in ld65's `MEMORY`, and the build tool checks the boundaries.
- Run-time conventions: native mode, X/Y always 16-bit, A normally 16-bit (8-bit only when writing hardware registers). DB is `$00`, DP is `$0000`. Large buffers from `$7E:2000` on are accessed with long addressing (`f:`). The stack grows down from `$1FFF`.

### 4.2 PPU
- Mode 3 (`BGMODE=$03`). BG1 is the picture at 8bpp, BG2 is text and windows at 4bpp. OBJ and BG3/4 are not used (TM=`$03`). At startup all 544 bytes of OAM are placed off screen, and no OBJ is displayed.
- VRAM (word addresses):

| Range | Contents |
|---|---|
| `$0000-$3FFF` | BG1 8bpp tiles 0-511 (picture) |
| `$4000-$401F` | BG1 tile 512 = transparent (zeroed at startup) |
| `$4400-$47FF` | BG1 tilemap 32x32 (rows 2-17 = tiles 0-511, everything else 512) |
| `$4800-$4BFF` | BG2 tilemap 32x32 (rows 0-1 = tiles 1-64, rows 18-27 = tiles 65-384, everything else 0) |
| `$5000-$6FFF` | BG2 4bpp tiles 0-511 (0 is transparent, 1-384 in the same order as the WRAM bitmap) |

  BG12NBA=`$50`, BG1SC=`$44`, BG2SC=`$48`, scroll H=0, V=-1 (BG row 0 lands on the first displayed line).
- CGRAM: 0-15 are the UI (in Mode 3 these double as BG2 palette 0 and BG1 colors 0-15). 16-255 are the background picture. At build time the picture is quantized to 240 colors (median cut, 15-bit color). Tiles with a portrait overlaid are also expressed within the scene's 240 colors (picture and portrait are quantized together).
- Text: the CPU draws glyphs into a bitmap in WRAM from `$7E:2000`, 12 tile rows × 32 tiles × 32 bytes = 12288 bytes (2 heading rows and 10 lower-window rows). Frames and divider lines are in ROM templates (heading, message window, command window); erasing is done per tile by DMA from the template into WRAM (channel 1, `$2180`). Rewritten rows are remembered in "per-row dirty bits", and the NMI DMAs them one row (1024 bytes) at a time (up to 4 rows per VBlank; even rewriting the whole lower window shows up within 3 frames). DrawGlyph assumes it draws on the window background color (1), so when changing colors the area is always restored from the template before redrawing.
- Picture changes: the background palette (16-255) is darkened in 8 steps (every 2 frames), the tiles are transferred in chunks of up to 4 KiB over 8 or more VBlanks, and then the palette is brightened. The UI stays visible. Forced blank is used only for initialization right after power-on. Portraits are put on and taken off by transferring the 9x13 tile rows of that area from the replacement tiles in ROM, or from the original picture tiles.
- NMI: only in frames where things are ready, it processes the job queue (VRAM / CGRAM DMA, channel 0). The main loop queues no more than 4096 bytes per VBlank. Counted: `nmi_count`, `lag_count` (frames in which the main loop was late and the NMI did not transfer), `dma_bytes_max`, `dma_deferred`, `nmi_end_line_max`, `vblank_overrun_count` (the number of times the end of NMI processing went past VBlank and back into the next display period at V=0..224; the code checks whether the V counter at exit is below 225).
- Budget for one VBlank: NTSC has V=225..261, 37 lines × 1364 master cycles = 50468. DMA takes at least 8 cycles per byte, so 4096 bytes is at least 32768 cycles (a little over 24 lines). Refresh and channel setup are added to that. With the initial budget of 4608 bytes, the end line measured 260 (1 line to spare), so it was lowered to 4096 bytes. Across all of candidate A's tests, `nmi_end_line_max` is 256 and `vblank_overrun_count` is 0 (both measured on emulators).

### 4.3 SRAM (`$70:0000`, 512 of the 8 KiB used)
- Two slots, A (`$0000`) and B (`$0100`), 256 bytes each: `+0` "SHIO", `+4` version (=1), `+6` sequence number, `+8` scene, `+10` wrong answers in the deduction, `+12` action count, `+14` sound setting, `+16..+143` flags (1024 bits), `+252` sum (sum of the 16-bit words over 0-251), `+254` complement of the sum.
- Saving writes the body to the older (or corrupted) slot and writes the sum last. Loading uses whichever valid slot has the newer sequence number. Checked items: the signature, version, sum, scene number range, that the scene is not an unreachable one, and that unused flag bits are 0.
- When both are invalid: if there is no signature either, 「記録がありません」 ("No save data"); if there is a signature but the checks fail, 「記録が壊れています」 ("Save data is corrupted"); then it returns to the title. SRAM is undefined at power-on, so all such cases are rejected by these checks.

### 4.4 Sound
- An original SPC700 driver (`tools/adv/spc.py` assembles the machine code with a small assembler; 674 bytes). The BRR waveforms (a soft square wave and a sine wave, each with a 32-sample period) are also original. It is transferred to `$0200` via the IPL and started; when ready it returns `$5A` on port0. The CPU writes one command per frame to port0 and then changes port1 (queue of 8). The 8 sound effects (cursor, confirm, cancel, clue, wrong answer, page advance, correct deduction, move) use voice 0. The wave sound slowly varies the volume of DSP noise on voice 2 (noise clock `$11`) with a 64-step table, with the left and right channels out of phase. Timer 0 is 100 Hz. Scenes with the wave sound: title, Pier No. 2, lighthouse. With 「おと：なし」 (sound: off), only master volume 0 and a wave-sound stop are sent, and no sound effects are sent. The setting is stored in SRAM.

---

## 5. Data structure (`data/adv/story.txt` → `tools/adv/build.py`)
- One text file lists blocks (`@scene`, `@person`, `@look`, `@topic`, `@show`, `@clue`, `@hint`, `@deduce`, `@script`). Each block has conditions (`if: FLAG !FLAG`), actions (`get: CLUE`, `set: FLAG`, `goto: SCENE`) and text (`> 話者| 本文`, i.e. `> speaker| text`).
- The build tool's job: assigning flag numbers, automatically setting the group flags for clues, line and page breaking with kinsoku rules (18 characters per line; `、。」』）ー…` never start a line), checking the width of each label (12 characters for lists; the heading's place name and status must not overlap), detecting clues and flags that are used but not defined, and reachability checks: whether every clue can be obtained and whether each deduction question can be answered under the conditions for starting it.
- Output: `build/adv/data.inc` (ca65 tables and per-bank segment assignments), `build/adv/*.bin`, `build/adv/manifest.json` (source hashes, character count, usage per bank), `build/adv/layout.json` (for tests: label and flags per item).
- The script in ROM is a sequence of 16-bit instructions: `END, TEXT id, SET f, CLR f, IF f rel, IFN f rel, JMP rel, GET clue, GOTO scene, SFX n, DEDUCE, ENDING, PORTRAIT on/off`.
- List items: text ID of the label, 3 conditions (flag numbers; negated if the top bit is set), pointer to the script, read flag.
- Text: a sequence of 16-bit glyph numbers. Control codes: `$FFFF` end, `$FFFE` newline, `$FFFD` page break, `$FFFC c` color.

## 6. Verification
- `make adv` builds. `make adv-test` runs pad-input-only tests on the unmodified Snes9x 1.63 libretro core (WRAM is only read, via the labels). Test contents: start to ending (standard order), to the end in a different order, wrong answers in the deduction and recovery, save → recreate the core (carrying over only the SRAM contents, as with a battery) → つづきから (continue) → to the end, SRAM empty / all 0xFF / random / bad sum / only one slot corrupted, held buttons, checks that text does not spill out of the frame (the build-time width check and the run-time draw-position monitor label `text_clip`), VBlank overruns 0, lag.
- The same pad input is replayed on bsnes 115 (a fixed libretro core) and the screen is recorded.
- Not verified on real hardware.

## 7. Implementation stages
1. Skeleton: header, reset, NMI and job queue, Mode 3 initialization, provisional palette, pad.
2. Text bitmap drawing, windows, messages, lists and scrolling.
3. Script VM, commands, scene changes (darkening the palette), notebook.
4. Build tool, the full `story.txt`, background quantization.
5. Deduction, ending, save and load, SRAM checks.
6. Tests (Snes9x), replay on bsnes, screen checks and text-width adjustment.
7. Portrait overlays, sound effects and ambient sound.
8. Confirm a matching clean build with `make adv-release` and produce `dist/shionari.sfc`.

## 8. Requests to the host (images)
1. **warehouse**: please add a pendulum wall clock (with a glass door) on the wall, with its hands at **10:15**. The red book on the desk will be used as the 「出納帳」 (cash book) and the key ring as the 「事務所の鍵束」 (office key ring) (fine as is). The door on the right is treated as the 「表戸」 (front door) (its glass broken).
2. **signal**: the wall clock points to about 5 o'clock; please change it to **about 1:10** (the time of the investigation) or make the hands not clearly visible. A switchboard (a box like a distribution board with its cover off) on the wall would match the description (optional).
3. **harbor**: the current sunset picture will be used for the **ending (dawn)**. For Pier No. 2 a **late-night version** is wanted (no sunset light, a light on in a small watch hut, a small work boat moored, no people).
4. **cafe**: please change the wall clock to about 1:30 or make the hands not clearly visible (optional).
5. **Two more portraits** (72x104, alpha): 古賀 (Koga) (58-year-old man, short white crew cut, tanned, gray work clothes) and 辰巳 (Tatsumi) (38-year-old man, thin, black hair parted 7:3, silver-rimmed glasses, white shirt under a navy padded jacket, tired eyes). To avoid only the culprit having a portrait, or only the culprit lacking one, every person in the scenes should have a portrait.
6. Quantization (0-15 for the UI, 16-255 for the backgrounds) is done in `tools/adv/build.py` (it reads `*-256.png`; for reproducibility the SHA of `PREPARED.json` is recorded in the manifest).
