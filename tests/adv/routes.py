"""Investigation routes for the tests (only menu choices a player can see; see drive.py)."""

WAREHOUSE, SIGNAL, PIER, CAFE, LIGHTHOUSE, STATION = ('第三倉庫　事務所', '汐見港　信号所', '第二桟橋　詰所',
                                                     '喫茶「浮標」', '汐見灯台', '汐見署')

# deduction answers (option labels or clue ids), in question order
ANSWERS = ['荷揚げ口', 'K_BAR', 'K_TIDE', '九時半ごろ', 'T_SHUICHI', 'K_LOG', 'K_RUST', '辰巳',
           'K_NOTICE', 'K_BOATLOG', 'T_APPOINT']


def standard(g, shots=None):
    """The order a player is guided to (scene by scene)."""
    shot = shots or (lambda name: None)
    g.look('柱時計', '振り子の窓', '金庫', '鍵束', 'メモ', '荷揚げ口', '鉄梯子')
    shot('warehouse_looked')
    g.talk('検視', '辰巳とは')
    g.move(STATION)
    g.talk('ゆうべのこと', '父の戸じまり', '時計のこと')
    g.move(SIGNAL)
    g.look('掲示板', '潮見表', '回覧板')
    g.talk('ゆうべのこと', '港内電話', '梯子のこと', '灯台')
    g.move(PIER)
    g.talk('ゆうべのこと')
    g.show('K_NOTICE')
    shot('pier_waver')
    g.look('詰所の電話', '鍵帳', '作業艇')
    g.show('K_PHONE')
    g.move(LIGHTHOUSE)
    g.look('当直日誌')
    shot('lighthouse_log')
    g.move(PIER)
    g.show('K_LOG')
    g.move(SIGNAL)
    g.talk('物入れの鍵')
    g.move(PIER)
    g.look('物入れ')
    g.move(CAFE)
    g.show('K_LEDGER')
    shot('cafe_appoint')


def other_order(g, shots=None):
    """A different order: café and pier first, the scene of the crime late, deduction hints read."""
    g.move(CAFE)
    g.talk('ゆうべのこと', '辰巳のようす', '辰巳のこと', '灯台')
    g.move(LIGHTHOUSE)
    g.talk('ゆうべのこと', '雨')
    g.look('当直日誌')
    g.talk('人影のこと', '小舟のこと')
    g.move(PIER)
    g.talk('ゆうべのこと')
    g.look('鍵帳', '作業艇', '詰所の電話')
    g.show('K_LOG', 'K_PHONE')
    g.move(SIGNAL)
    g.talk('港内電話', '物入れの鍵')
    g.look('掲示板', '潮見表')
    g.move(PIER)
    g.show('T_LINE', 'K_PHONE')
    g.look('物入れ')
    g.move(STATION)
    g.talk('ゆうべのこと', '父の戸じまり')
    g.show('K_LEDGER')
    g.move(CAFE)
    g.show('K_LEDGER')
    g.move(WAREHOUSE)
    g.look('荷揚げ口', '鉄梯子', '柱時計', '振り子の窓')
    g.move(SIGNAL)
    g.talk('梯子のこと')


def deduce(g, answers=ANSWERS, wrong=None, shots=None):
    """Answer the deduction.  wrong: {question index: [wrong answers to try first]}."""
    shot = shots or (lambda name: None)
    g.note('すいりする')
    for i, ans in enumerate(answers):
        assert g.w('mode') == 1 and g.w('list_kind') in (7, 8), (i, g.w('mode'), g.w('list_kind'))
        assert g.w('dq_index') == i, (i, g.w('dq_index'))
        for bad in (wrong or {}).get(i, []):
            before = g.w('wrong_count')
            g.pick(g.layout['clue_names'][bad] if bad in g.layout['clue_names'] else bad)
            assert g.w('wrong_count') == before + 1, ('wrong answer not counted', i, bad)
            assert g.w('dq_index') == i, ('a wrong answer moved on', i, bad)
        if i == 0:
            shot('deduce_q1')
        g.pick(g.layout['clue_names'][ans] if ans in g.layout['clue_names'] else ans)
