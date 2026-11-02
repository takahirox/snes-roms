"""Pad-only tests of 夜鳴き鐘 on the unmodified Snes9x 1.63 libretro core.

The fixture scenario (tests/yonaki/fixture: every op, gated choices, six endings, おまけ after 3 endings) is
built into build/yonaki-test/ first.  Every action reaches the ROM through joypad bits only; checks read WRAM
by label and the battery RAM (carried between power cycles like a frontend's .srm file).
Results: build/yonaki-test/tests.json; screenshots: build/yonaki-test/shots/<test>/; pad traces:
build/yonaki-test/traces/<test>.json.

usage: python3 -I tests/yonaki/run.py [--real] [test ...]
  --real   also build the real scenario (data/yonaki/scenario -> build/yonaki) and play every ending of it
"""
import sys, json, pathlib, traceback, struct, random, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import buildrom                       # noqa: E402
import routes                         # noqa: E402
from drive import Driver, Stuck, ROOT  # noqa: E402

B = ROOT / 'build/yonaki-test'
results = {}
REAL = '--real' in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith('--')]


def new(name, sram=None, build=B):
    g = Driver(build=build, sram=sram)
    g.name = name
    g.shots = build / 'shots' / name
    return g


def shot(g, label, settle=True):
    if settle:
        for _ in range(120):
            if not (g.w('text_dirty') | g.w('text_dirty', 2) | g.w('photo_dirty') | g.w('photo_dirty', 2)):
                break
            g.run(1)
        g.run(2)
    g.shot(g.shots / f'{label}.png')


def hw(g):
    return dict(frames=g.frame, lag_count=g.w('lag_count'), vblank_overrun_count=g.w('vblank_overrun_count'),
                nmi_end_line_max=g.w('nmi_end_line_max'), dma_bytes_max=g.w('dma_bytes_max'),
                dma_deferred=g.w('dma_deferred'), text_clip=g.w('text_clip'), paragraphs=g.w('paragraphs'))


def finish(g, rec):
    h = hw(g)
    rec.update(h)
    assert h['vblank_overrun_count'] == 0, 'NMI work ran past the V-blank'
    assert 225 <= h['nmi_end_line_max'] <= 261 or h['nmi_end_line_max'] == 0, ('NMI end line', h['nmi_end_line_max'])
    assert h['text_clip'] == 0, 'a glyph was clipped'
    assert h['dma_deferred'] == 0, 'a DMA job had to wait'
    sram = g.sram_image()
    g.trace(B / 'traces' / f'{g.name}.json')
    g.close()
    return sram


# ------------------------------------------------------------------ SRAM decoding (tests only)
def words(b, a, n):
    return struct.unpack_from(f'<{n}H', b, a)


def global_block(sram):
    w = words(sram, 0, 128)
    ok = sum(w[:126]) & 0xFFFF == w[126] and w[126] ^ 0xFFFF == w[127] and sram[:4] == b'YNKG'
    return dict(valid=ok, speed=w[3], endings=w[4] | w[5] << 16, gflags=w[6] | w[7] << 16)


def read_block(sram):
    w = words(sram, 0x400, (0x2000 - 0x400) // 2)
    n = (0x1FFC - 0x400) // 2
    return dict(valid=sram[0x400:0x404] == b'YNKR' and sum(w[:n]) & 0xFFFF == w[n] and w[n] ^ 0xFFFF == w[n + 1],
                marks=sram[0x408:0x1FFC])


def slot_block(sram, k):
    a = 0x100 * (k + 1)
    w = words(sram, a, 128)
    return dict(valid=sram[a:a + 4] == b'YNKS' and sum(w[:126]) & 0xFFFF == w[126], kind=w[5], id=w[6])


def is_read(sram, tid):
    return bool(read_block(sram)['marks'][tid >> 3] >> (tid & 7) & 1)


# ------------------------------------------------------------------ tests
def test_boot():
    """Empty battery: both blocks are reset; the title has はじめから / しおりから (grey) / 結末の一覧."""
    g = new('boot', sram=bytes(8192))
    rec = {}
    g.title()
    rec['title_frame'] = g.frame
    assert g.frame < 400, g.frame
    assert g.w('sram_resets') == 3, g.w('sram_resets')
    assert g.title_items() == [0, 1, 2], g.title_items()
    assert g.w('slot_any') == 0
    assert g.w('spc_ready') == 1, 'the sound driver did not answer'
    shot(g, 'title')
    sram = finish(g, rec)
    gb = global_block(sram)
    assert gb['valid'] and gb['endings'] == 0 and gb['speed'] == 1, gb
    assert read_block(sram)['valid']
    return rec


def test_corrupt():
    """Random battery contents: everything is reset, nothing crashes, no bookmark is offered."""
    rnd = random.Random(7)
    g = new('corrupt', sram=bytes(rnd.randrange(256) for _ in range(8192)))
    rec = {}
    g.title()
    assert g.w('sram_resets') == 3, g.w('sram_resets')
    assert g.w('slot_any') == 0
    sram = finish(g, rec)
    assert global_block(sram)['valid'] and read_block(sram)['valid']
    # a valid battery with one bookmark broken by a flipped bit: that slot is empty, the others stay
    return rec


ROUND = {}


def test_endings():
    """Every ending of the fixture in the order of tests/yonaki/routes.py, the battery carried between power
    cycles: the ending is recorded in SRAM, its global flag set (cleared_main only by the true ending), the
    gated option appears only after the unlock, おまけ appears after 3 endings."""
    lay = json.loads((B / 'layout.json').read_text())
    order, missing = routes.plan(lay)
    assert not missing, missing
    eidx = {e['id']: i for i, e in enumerate(lay['endings'])}
    gidx = {n: i for i, n in enumerate(lay['gflags'])}
    sram = bytes(8192)
    rec = dict(order=[])
    gated_seen = {}
    for n in order:
        g = new(f'ending_{n["ending"]}', sram=sram)
        g.title()
        items = g.title_items()
        seen = global_block(sram)['endings']
        assert (3 in items) == (bin(seen).count('1') >= 3), (items, seen)
        g.title_pick(3 if n['start'] == 'omake' else 0)
        if n['start'] == 'start':
            st = g.advance()
            assert st == 'CHOICE'
            texts = [o['text'] for _, _, o in g.options()]
            gated_seen[n['ending']] = '古い写真のことを聞く' in texts
            unlocked = bool(global_block(sram)['gflags'] >> gidx['cleared_main'] & 1)
            assert gated_seen[n['ending']] == unlocked, (texts, unlocked)
        g.play(n['path'])
        assert g.w('endings_reached') == eidx[n['ending']] + 1
        g.run(240)
        shot(g, 'ending')
        g.ending_to_title()
        r = {}
        sram = finish(g, r)
        gb = global_block(sram)
        assert gb['valid']
        assert gb['endings'] >> eidx[n['ending']] & 1, 'ending not recorded'
        for f in lay['endings'][eidx[n['ending']]]['sets']:
            assert gb['gflags'] >> gidx[f] & 1, f'{f} not set'
        if n['ending'] in ('F02', 'F03'):
            assert not gb['gflags'] >> gidx['cleared_main'] & 1 or 'F01' in rec['order'], 'cleared_main too early'
        rec['order'].append(n['ending'])
        rec[n['ending']] = dict(choices=len(n['path']), **r)
    assert global_block(sram)['endings'] == (1 << len(lay['endings'])) - 1
    rec['gated_option_visible'] = gated_seen
    ROUND['sram'] = sram
    return rec


def test_endings_list():
    """結末の一覧: n/N and the seen titles; B back to the title."""
    sram = ROUND.get('sram')
    rec = {}
    for name, img in (('list_empty', bytes(8192)), ('list_full', sram)):
        if img is None:
            continue
        g = new(name, sram=img)
        g.title()
        g.title_pick(2)
        g.until(lambda: g.state() == 'ENDLIST', 200, 'endings list')
        shot(g, 'list')
        g.tap('B', 2, 4)
        g.title()
        rec[name] = {}
        finish(g, rec[name])
    return rec


def to_wait(g, text_id):
    while True:
        st = g.advance(limit=4000)
        raise Stuck(st)


def test_save_load():
    """START menu bookmark at a paragraph (slot 2) and at a choice (slot 3), タイトルへ, then しおりから after a
    power cycle resumes at the same paragraph / choice."""
    rec = {}
    g = new('save', sram=bytes(8192))
    g.new_game()
    # stop at the 6th paragraph
    g.until(lambda: g.state() == 'WAIT', 2000, 'first wait')
    while g.w('cur_text') < 5:
        g.tap('A', 1, 2)
        g.until(lambda: g.state() in ('WAIT', 'CHOICE'), 2000, 'wait')
    tid = g.w('cur_text')
    shot(g, 'wait')
    g.press('START', 'MENU')
    shot(g, 'menu')
    g.menu_to(0)
    g.press('A', 'SLOTS')
    shot(g, 'slots_save')
    g.menu_to(1)
    g.press('A', 'WAIT')
    assert g.w('save_ok') == 1
    shot(g, 'after_save')
    # on to the first choice; bookmark it in slot 3
    st = g.advance()
    assert st == 'CHOICE'
    cid = g.w('choice_id')
    shot(g, 'choice')
    g.press('START', 'MENU')
    g.menu_to(0)
    g.press('A', 'SLOTS')
    g.menu_to(2)
    g.press('A', 'CHOICE')
    # タイトルへ
    g.press('START', 'MENU')
    g.menu_to(2)
    g.press('A', 'CONFIRM')
    shot(g, 'confirm')
    g.menu_to(0)
    g.tap('A', 2, 4)
    g.title()
    sram = finish(g, rec.setdefault('first', {}))
    s1, s2 = slot_block(sram, 1), slot_block(sram, 2)
    assert s1['valid'] and s1['kind'] == 1 and s1['id'] == tid, s1
    assert s2['valid'] and s2['kind'] == 2 and s2['id'] == cid, s2
    assert not slot_block(sram, 0)['valid']
    # power cycle: load slot 2 -> the same paragraph
    g = new('load_text', sram=sram)
    g.title()
    assert g.w('slot_any') == 1
    g.title_pick(1)
    g.until(lambda: g.state() == 'SLOTS', 300, 'slots')
    g.run(40)
    shot(g, 'slots_load')
    g.menu_to(0)
    g.tap('A', 2, 30)
    assert g.state() == 'SLOTS', 'an empty slot must not load'
    g.menu_to(1)
    g.tap('A', 2, 4)
    g.until(lambda: g.state() == 'WAIT', 1200, 'resumed paragraph')
    assert g.w('cur_text') == tid, (g.w('cur_text'), tid)
    assert g.w('loads_done') == 1
    shot(g, 'loaded_text')
    finish(g, rec.setdefault('load_text', {}))
    # load slot 3 -> the same choice, the paragraph before it redrawn
    g = new('load_choice', sram=sram)
    g.title()
    g.title_pick(1)
    g.until(lambda: g.state() == 'SLOTS', 300, 'slots')
    g.run(40)
    g.menu_to(2)
    g.tap('A', 2, 4)
    g.until(lambda: g.state() == 'CHOICE', 1200, 'resumed choice')
    assert g.w('choice_id') == cid
    assert g.w('last_text') != 0xFFFF and g.w('text_on') == 1, 'the paragraph before the choice was not redrawn'
    shot(g, 'loaded_choice')
    g.choose(index=0)
    assert g.advance() in ('CHOICE', 'ENDING')
    finish(g, rec.setdefault('load_choice', {}))
    rec['text_id'] = tid
    rec['choice_id'] = cid
    return rec


def test_names():
    """はじめから asks for the two names: B deletes, the pages and the cursor type new ones, START decides; the
    names are kept in the battery RAM and drawn in the story in place of 結城 / 千尋."""
    rec = {}
    lay = json.loads((B / 'layout.json').read_text())
    gi = {c: i for i, c in enumerate(lay['glyphs'])}
    g = new('names', sram=bytes(8192))
    g.title()
    items = g.title_items()
    g.menu_to(items.index(0))
    g.tap('A', 2, 4)
    g.until(lambda: g.state() == 'NAME', 600, 'name entry')
    assert g.name_glyphs(0) == [gi['結'], gi['城']] and g.name_glyphs(1) == [gi['千'], gi['尋']], 'default names'
    shot(g, 'entry')
    g.tap('B', 2, 6)
    g.tap('B', 2, 6)
    assert g.name_glyphs(0) == []
    g.tap('R', 2, 30)
    g.tap('R', 2, 30)                         # the first kanji page: 結城千尋早瀬佐藤...
    assert g.w('ne_page') == 2
    g.name_pick(0, 6)
    g.name_pick(0, 7)
    assert g.name_glyphs(0) == [gi['佐'], gi['藤']], g.name_glyphs(0)
    g.tap('START', 2, 6)
    assert g.w('ne_field') == 1
    g.tap('B', 2, 6)
    g.tap('B', 2, 6)
    g.name_pick(8, 0)                         # かな
    g.until(lambda: g.state() == 'NAME', 600, 'page')
    g.name_pick(3, 0)                         # ま
    g.name_pick(4, 1)                         # り
    assert g.name_glyphs(1) == [gi['ま'], gi['り']], g.name_glyphs(1)
    shot(g, 'typed')
    g.tap('START', 2, 6)
    g.until(lambda: g.state() in ('WAIT', 'TYPE'), 2000, 'story')
    for _ in range(3):                        # the bus: 早瀬千尋さんは…
        g.until(lambda: g.state() == 'WAIT', 2000, 'wait')
        g.tap('A', 1, 2)
    g.until(lambda: g.state() == 'WAIT', 2000, 'wait')
    shot(g, 'story')
    g.press('START', 'MENU')
    g.menu_to(2)
    g.press('A', 'CONFIRM')
    g.menu_to(0)
    g.tap('A', 2, 4)
    g.title()
    sram = finish(g, rec.setdefault('typed', {}))
    w = lambda o: sram[o] | sram[o + 1] << 8
    assert [w(16), w(18), w(20)] == [2, gi['佐'], gi['藤']] and [w(26), w(28), w(30)] == [2, gi['ま'], gi['り']]
    g = new('names2', sram=sram)              # kept after a power cycle
    g.title()
    g.menu_to(g.title_items().index(0))
    g.tap('A', 2, 4)
    g.until(lambda: g.state() == 'NAME', 600, 'name entry')
    assert g.name_glyphs(0) == [gi['佐'], gi['藤']] and g.name_glyphs(1) == [gi['ま'], gi['り']]
    g.tap('B', 2, 6)
    g.tap('B', 2, 6)
    g.tap('B', 2, 6)                          # empty first name: back to the title
    g.title()
    finish(g, rec.setdefault('kept', {}))
    return rec


def test_fastforward():
    """B held skips read paragraphs only: it stops at the first unread one and waits there."""
    rec = {}
    g = new('ff', sram=bytes(8192))
    g.new_game()
    g.until(lambda: g.state() == 'WAIT', 2000, 'first wait')
    while g.w('cur_text') < 8:
        g.tap('A', 1, 2)
        g.until(lambda: g.state() in ('WAIT', 'CHOICE'), 2000, 'wait')
    last = g.w('cur_text')         # waiting on it: not read yet
    g.press('START', 'MENU')
    g.menu_to(2)
    g.press('A', 'CONFIRM')
    g.menu_to(0)
    g.tap('A', 2, 4)
    g.title()
    sram = finish(g, rec.setdefault('read', {}))
    assert is_read(sram, last - 1) and not is_read(sram, last), 'read marks'
    g = new('ff2', sram=sram)
    g.new_game()
    t0 = g.frame
    g.until(lambda: g.state() in ('TYPE', 'WAIT'), 2000, 'first text')
    for _ in range(3000):
        g.run(1, ('B',))
        if g.state() == 'WAIT' and g.w('cur_text') == last and g.w('cur_read') == 0:
            break
    assert g.w('cur_text') == last, (g.w('cur_text'), last)
    rec['frames_to_unread'] = g.frame - t0
    g.run(90, ('B',))
    assert g.state() == 'WAIT' and g.w('cur_text') == last, 'B went past unread text'
    shot(g, 'stopped_at_unread')
    finish(g, rec.setdefault('skip', {}))
    return rec


def test_speed():
    """文字の速さ cycles 遅い→普通→速い→瞬間 and is kept in the battery."""
    rec = {}
    g = new('speed', sram=bytes(8192))
    g.new_game()
    g.until(lambda: g.state() == 'WAIT', 2000, 'first wait')
    g.press('START', 'MENU')
    g.menu_to(1)
    speeds = [g.w('speed')]
    for _ in range(3):
        g.tap('A', 2, 2)
        g.until(lambda: g.state() == 'MENU' and g.w('speed') != speeds[-1], 300, 'speed')
        g.run(30)
        speeds.append(g.w('speed'))
    shot(g, 'menu_speed')
    assert speeds == [1, 2, 3, 0], speeds
    g.press('B', 'WAIT')
    # slow: a glyph every other frame
    g.tap('A', 1, 1)
    sram = finish(g, rec)
    assert global_block(sram)['speed'] == 0
    g = new('speed2', sram=sram)
    g.title()
    assert g.w('speed') == 0
    finish(g, {})
    rec['speeds'] = speeds
    return rec


def test_effects():
    """The route through every effect of the fixture with screenshots of the moments (dim, silhouettes,
    ripple, dark, mosaic, flash); the colour math and HDMA states are read from the shadows."""
    rec = {}
    g = new('effects', sram=bytes(8192))
    g.new_game()
    seen = {}
    for _ in range(40000):
        st = g.state()
        if st in ('CHOICE', 'ENDING'):
            if st == 'CHOICE':
                shot(g, f'choice_{g.w("choice_id")}')
                opts = g.options()
                g.choose(index=0)
                if g.w('choice_id') == 2:
                    break
                continue
            break
        if st == 'WAIT':
            t = g.w('cur_text')
            if t not in seen:
                seen[t] = dict(cgadsub=g.w('reg_cgadsub'), hdma=g.w('reg_hdma'), dim=g.w('dim_cur'),
                               sils=sum(1 for k in range(4) if g.w('sil_key', 2 * k) != 0xFFFF))
                shot(g, f'text_{t:03d}')
            g.tap('A', 1, 1)
        elif st == 'TYPE':
            g.tap('A', 1, 1)
        else:
            if g.w('reg_mosaic') & 0xF0 and 'mosaic' not in rec:
                rec['mosaic'] = g.frame
                g.shot(g.shots / 'mosaic.png')
            if g.w('add_level') > 20 and 'flash' not in rec:
                rec['flash'] = g.frame
                g.shot(g.shots / 'flash.png')
            g.run(1)
    rec['texts'] = seen
    assert any(v['hdma'] for v in seen.values()), 'ripple never on'
    assert any(v['dim'] == 31 for v in seen.values()), 'dark never reached'
    assert any(v['sils'] == 3 for v in seen.values()), 'three silhouettes never shown together'
    assert 'mosaic' in rec and 'flash' in rec
    finish(g, rec)
    return rec


def test_real():
    """The real scenario: build, boot, and play every ending of tests/yonaki/routes.py's plan."""
    buildrom.build(ROOT / 'build/yonaki', None, ['--quiet'])
    lay = json.loads((ROOT / 'build/yonaki/layout.json').read_text())
    order, missing = routes.plan(lay)
    rec = dict(missing=missing, order=[])
    sram = bytes(8192)
    for n in order:
        g = new(f'real_{n["ending"]}', sram=sram, build=ROOT / 'build/yonaki')
        g.title()
        g.title_pick(3 if n['start'] == 'omake' else 0)
        t = time.time()
        g.play(n['path'])
        g.run(240)
        shot(g, 'ending')
        g.ending_to_title()
        r = {}
        sram = finish(g, r)
        r['seconds'] = round(time.time() - t, 1)
        rec[n['ending']] = r
        rec['order'].append(n['ending'])
    assert not missing, missing
    g = new('real_list', sram=sram, build=ROOT / 'build/yonaki')
    g.title()
    assert 3 in g.title_items(), 'おまけ not on the title'
    g.title_pick(2)
    g.until(lambda: g.state() == 'ENDLIST', 300, 'list')
    shot(g, 'page1')
    g.tap('RIGHT', 2, 2)
    g.until(lambda: g.w('list_page') == 1 and g.state() == 'ENDLIST', 300, 'page 2')
    shot(g, 'page2')
    g.tap('B', 2, 4)
    g.title()
    finish(g, rec.setdefault('list', {}))
    return rec


def test_coverage():
    """The fixture uses every op, transition, effect, silhouette position / colour and condition kind."""
    lay = json.loads((B / 'layout.json').read_text())
    ops = lay['ops']
    kinds = {o[0] for o in ops}
    want = {'text', 'blank', 'page', 'bg', 'sil', 'silclear', 'bgm', 'se', 'amb', 'fx', 'set', 'clr', 'setg', 'clrg',
            'if', 'goto', 'choice', 'end', 'chapter'}
    assert want <= kinds, want - kinds
    assert {o[2] for o in ops if o[0] == 'bg'} >= {'cut', 'fade', 'white', 'mosaic'}
    assert {o[1] for o in ops if o[0] == 'fx'} >= {'shake', 'flash', 'redflash', 'ripple_on', 'ripple_off', 'dark',
                                                   'light', 'wait'}
    assert {o[1][:1] for o in ops if o[0] == 'sil'} >= {'l', 'c', 'r', 'x'}
    assert {o[3] for o in ops if o[0] == 'sil'} >= {'blue', 'white', 'red'}
    assert any(o[0] == 'sil' and o[2] is None for o in ops)
    conds = [c for o in ops if o[0] == 'choice' for opt in o[2] for c in opt[0]]
    assert any(c[2] for c in conds) and any(c[1] for c in conds) and any(not c[2] for c in conds)
    assert any(o[0] == 'if' and o[1][1] for o in ops) and any(o[0] == 'if' and o[1][2] for o in ops)
    assert any(len(o[2][k][1]) == 2 for o in ops if o[0] == 'choice' for k in range(len(o[2])))
    assert any(len(t['pages']) > 1 for t in lay['texts'].values()), 'no paragraph longer than a page'
    return dict(ops=sorted(kinds))


TESTS = [test_coverage, test_boot, test_corrupt, test_endings, test_endings_list, test_save_load, test_names, test_fastforward, test_speed,
         test_effects]


def main():
    buildrom.build_fixture()
    tests = TESTS + ([test_real] if REAL else [])
    if args:
        tests = [t for t in tests if t.__name__ in args or t.__name__[5:] in args]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            r = t()
            results[t.__name__] = dict(ok=True, seconds=round(time.time() - t0, 1), **(r or {}))
            print(f'ok    {t.__name__} ({time.time() - t0:.1f} s)')
        except Exception as e:
            failed += 1
            results[t.__name__] = dict(ok=False, error=f'{type(e).__name__}: {e}', trace=traceback.format_exc())
            print(f'FAIL  {t.__name__}: {type(e).__name__}: {e}')
            traceback.print_exc()
    rom = (B / 'yonaki.sfc').read_bytes()
    import hashlib
    (B / 'tests.json').write_text(json.dumps(dict(rom_sha256=hashlib.sha256(rom).hexdigest(), results=results),
                                             ensure_ascii=False, indent=1, default=str) + '\n')
    print(f'{len(tests) - failed}/{len(tests)} passed; build/yonaki-test/tests.json')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
