"""Pad-only tests of 潮鳴りの密室 on the unmodified Snes9x 1.63 libretro core.

Every game action reaches the ROM through joypad bits only; checks read WRAM by label (read only),
VRAM and the video output.  The battery SRAM is carried between cores like a frontend's .srm file.
Results: build/adv/tests.json (with the ROM SHA-256); pad traces in host_libretro_replay.py format
under build/adv/traces/<test>.json; screens under build/adv/tests/<test>/.

usage: python3 -I tests/adv/run.py [test ...]
"""
import sys, json, pathlib, traceback, hashlib, random
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from drive import Driver, Stuck, ROOT, M_CMD, M_LIST, M_MSG, M_FADE, M_END, M_OPEN, OP_TITLE
sys.path.insert(0, str(ROOT / 'tools/adv'))
from songs import SONG_IDS as SONG
import routes

B = ROOT / 'build/adv'
SHOTS = B / 'tests'
TRACES = B / 'traces'
results = {}


class Monitor:
    """Per-frame: worst NMI end line, overruns, text clipping, lag streaks."""
    def __init__(self):
        self.max_lag_streak = 0
        self.streak = 0
        self.last_lag = 0

    def __call__(self, g):
        if g.w('main_count') == 0:
            return                          # the boot (the sound driver upload, a fixed length)
        lag = g.w('lag_count')
        if lag != self.last_lag:
            self.streak += 1
            self.max_lag_streak = max(self.max_lag_streak, self.streak)
        else:
            self.streak = 0
        self.last_lag = lag


def new(name, sram=None):
    g = Driver(sram=sram)
    g.name = name
    g.mon = Monitor()
    g.observers.append(g.mon)
    g.shots = SHOTS / name
    return g


def shot(g, label):
    g.quiet()
    g.shot(g.shots / f'{label}.png')


def hw(g):
    return dict(frames=g.frame, lag_count=g.w('lag_count'), max_lag_streak=g.mon.max_lag_streak,
                vblank_overrun_count=g.w('vblank_overrun_count'), nmi_end_line_max=g.w('nmi_end_line_max'),
                dma_bytes_max=g.w('dma_bytes_max'), dma_deferred=g.w('dma_deferred'), text_clip=g.w('text_clip'),
                messages=g.w('msg_count'), pages=g.pages_seen)


def check_hw(g):
    assert g.w('vblank_overrun_count') == 0, 'NMI work ran past the V-blank'
    assert 225 <= g.w('nmi_end_line_max') <= 258, ('NMI end line too late', g.w('nmi_end_line_max'))
    assert g.w('text_clip') == 0, 'a glyph crossed its box'
    assert g.w('dma_deferred') == 0, 'a DMA job had to wait for the next V-blank'


def start_new(g):
    g.boot_menu()
    assert g.w('list_kind') == 9, 'not on the title'
    g.tap('A')
    g.settle()
    assert g.mode() == M_CMD and g.w('scene') == 0, ('intro did not end in the warehouse', g.mode(), g.w('scene'))


def finish(g, record):
    check_hw(g)
    record.update(hw(g))
    final = g.save_battery(g.shots)
    record['input_sram_sha256'] = g.sram_files['initial.srm']['sha256']
    record['output_sram_sha256'] = g.sram_files['final.srm']['sha256']
    g.trace(TRACES / f'{g.name}.json')
    g.close()
    return final


def have(g, *names):
    missing = [n for n in names if not g.flag(n)]
    assert not missing, f'missing {missing}'


REQUIRED = ['K_BAR', 'K_LADDER', 'T_HABIT', 'K_TIDE', 'T_LADDER', 'T_SHUICHI', 'K_LOG', 'K_RUST', 'T_TATSUMI',
            'K_PHONE', 'K_BOATLOG', 'K_LEDGER', 'T_APPOINT']


def end_and_title(g, rec):
    assert g.mode() == M_END, ('no ending', g.mode())
    rec['actions'] = g.w('actions')
    rec['wrong'] = g.w('wrong_count')
    shot(g, 'ending')
    g.ending_to_title()
    shot(g, 'title_after')


# ------------------------------------------------------------------ tests
def test_full():
    """Start to ending in the guided order, correct deduction, every screen type captured."""
    g = new('full')
    rec = {}
    g.boot_menu()
    shot(g, 'title')
    g.tap('A')
    g.settle()
    shot(g, 'start')
    routes.standard(g, lambda n: shot(g, n))
    have(g, *REQUIRED)
    g.cmd('てちょう')
    shot(g, 'note')
    g.pick('しょうこ')
    shot(g, 'items')
    for _ in range(12):
        g.tap('DOWN')
    shot(g, 'items_scrolled')
    g.to_cmd()
    g.note('ヒント')
    routes.deduce(g, shots=lambda n: shot(g, n))
    end_and_title(g, rec)
    rec['minutes_at_test_speed'] = round(g.frame / 60.1 / 60, 1)
    finish(g, rec)
    return rec


def test_order():
    """A different order of investigation reaches the same ending."""
    g = new('order')
    rec = {}
    start_new(g)
    routes.other_order(g)
    have(g, *REQUIRED)
    routes.deduce(g)
    end_and_title(g, rec)
    finish(g, rec)
    return rec


def test_wrong():
    """Deduction before the clues are in, wrong answers, quitting and resuming: no dead end."""
    g = new('wrong')
    rec = {}
    start_new(g)
    g.note('すいりする')                         # too early: told what is missing, back to the notebook
    assert g.mode() == M_LIST and g.w('list_kind') == 4 and g.w('dq_index') == 0
    shot(g, 'too_early')
    g.to_cmd()
    routes.standard(g)
    wrong = {0: ['表戸', '天井裏'], 1: ['T_HABIT', 'K_KEYS'], 3: ['十時十五分ごろ', '十時ごろ'], 5: ['T_AUTOPSY'],
             6: ['T_WIND'], 7: ['修一', '古賀'], 9: ['K_GLOVE']}
    # first attempt: two wrong answers in question 1, then quit with B and come back
    g.note('すいりする')
    g.pick('表戸')
    shot(g, 'wrong_reply_back_to_list')
    assert g.w('dq_index') == 0 and g.w('wrong_count') == 1
    g.tap('B')
    g.settle()
    assert g.mode() == M_CMD, 'B did not leave the deduction'
    g.cmd('はなす')                              # the investigation still works
    g.to_cmd()
    routes.deduce(g, wrong=wrong)
    rec['wrong_count'] = g.w('wrong_count')
    assert g.w('wrong_count') == 1 + sum(len(v) for v in wrong.values())
    end_and_title(g, rec)
    finish(g, rec)
    return rec


def play_to_save(g):
    start_new(g)
    g.look('柱時計', '振り子の窓', '荷揚げ口', '鉄梯子')
    g.move(routes.STATION)
    g.talk('ゆうべのこと', '父の戸じまり')
    g.note('きろくする')
    assert g.w('save_ok') == 1, 'save not verified'
    g.to_cmd()


def test_save():
    """Save, power off (new core, battery image only), continue, second save, and finish."""
    g = new('save_a')
    play_to_save(g)
    flags_before = g.b('flags', 128)
    scene_before = g.w('scene')
    slot1 = g.w('save_slot')
    shot(g, 'saved')
    rec = dict(first_slot=slot1)
    sram = finish(g, rec)
    # power cycle: a fresh core with only the battery image
    g = new('save_b', sram=sram)
    assert g.initial_sram == sram, 'save_b does not start from save_a.final'
    g.boot_menu()
    assert g.w('save_status') == 2, 'saved record not recognised'
    assert g.w('list_sel') == 1, 'cursor should start on つづきから'
    shot(g, 'title_with_record')
    g.tap('A')
    g.settle()
    assert g.mode() == M_CMD
    assert g.b('flags', 128) == flags_before and g.w('scene') == scene_before, 'restored state differs'
    assert g.w('load_count') == 1
    shot(g, 'continued')
    # second save goes to the other slot
    g.move(routes.SIGNAL)
    g.note('きろくする')
    assert g.w('save_ok') == 1 and g.w('save_slot') == 1 - slot1, 'second save did not alternate slots'
    g.to_cmd()
    rest_after_partial(g)
    end_and_title(g, rec)
    sram2 = finish(g, rec)
    # the newest record is the second one
    g = new('save_c', sram=sram2)
    assert g.initial_sram == sram2, 'save_c does not start from save_b.final'
    g.boot_menu()
    g.tap('A')
    g.settle()
    assert g.w('scene') == 1, 'newest record not chosen'
    finish(g, {})
    return rec


def rest_after_partial(g):
    """From the save point (warehouse clock/rust/bar/ladder + station talks done) to the deduction."""
    g.look('掲示板', '潮見表', '回覧板')
    g.talk('ゆうべのこと', '港内電話', '梯子のこと', '灯台')
    g.move(routes.PIER)
    g.talk('ゆうべのこと')
    g.look('詰所の電話', '鍵帳', '作業艇')
    g.move(routes.LIGHTHOUSE)
    g.look('当直日誌')
    g.move(routes.SIGNAL)
    g.talk('物入れの鍵')
    g.move(routes.PIER)
    g.look('物入れ')
    g.move(routes.CAFE)
    g.show('K_LEDGER')
    have(g, *REQUIRED)
    routes.deduce(g)


def sram_case(name, image, expect_status, expect_msg_text):
    g = new(name, sram=image)
    g.boot_menu()
    st = g.w('save_status')
    assert st == expect_status, (name, st)
    assert g.w('list_sel') == (1 if st == 2 else 0)
    shot(g, 'title')
    # choose つづきから
    if g.w('list_sel') == 0:
        g.tap('DOWN')
    g.tap('A')
    g.run(30)
    if expect_msg_text is not None:
        assert g.mode() == M_MSG, 'no message for the bad record'
        want = g.layout['system'][{'none': 'NORECORD', 'broken': 'BROKEN'}[expect_msg_text]]
        assert g.w('msg_text') == want, ('wrong message', g.w('msg_text'), want)
        shot(g, 'message')
        g.settle()
        assert g.w('list_kind') == 9 and g.mode() == M_LIST, 'did not stay on the title'
        assert g.w('load_count') == 0
    else:
        assert g.w('msg_text') == g.layout['system']['LOADED'] or g.mode() == M_FADE
        g.settle()
        assert g.mode() == M_CMD and g.w('load_count') == 1
        assert g.w('msg_text') == g.layout['system']['LOADED'], 'no 再開 message'
    rec = dict(status=st)
    finish(g, rec)
    return rec


def valid_image():
    g = new('sram_make')
    play_to_save(g)
    img = g.sram_image()
    slot = g.w('save_slot')
    g.close()
    return img, slot


def test_sram():
    """Empty / 0xFF / random / corrupt battery RAM: the title says so and nothing is loaded."""
    rec = {}
    rec['zero'] = sram_case('sram_zero', bytes(8192), 0, 'none')
    rec['ff'] = sram_case('sram_ff', b'\xff' * 8192, 0, 'none')
    rnd = random.Random(1987)
    rec['random'] = sram_case('sram_random', bytes(rnd.randrange(256) for _ in range(8192)), 0, 'none')
    img, slot = valid_image()
    base = slot * 256
    bad = bytearray(img)
    bad[base + 40] ^= 0x01                      # one flag bit: checksum fails
    rec['checksum'] = sram_case('sram_checksum', bytes(bad), 1, 'broken')
    bad = bytearray(img)
    bad[base + 8] = 0x40                        # scene out of range (checksum fixed up)
    s = sum(bad[base + i] | bad[base + i + 1] << 8 for i in range(0, 252, 2)) & 0xFFFF
    bad[base + 252:base + 256] = bytes([s & 255, s >> 8, ~s & 255, (~s >> 8) & 255])
    rec['range'] = sram_case('sram_range', bytes(bad), 1, 'broken')
    bad = bytearray(img)
    bad[base + 16 + 120] = 0x10                 # a flag that does not exist (checksum fixed up)
    s = sum(bad[base + i] | bad[base + i + 1] << 8 for i in range(0, 252, 2)) & 0xFFFF
    bad[base + 252:base + 256] = bytes([s & 255, s >> 8, ~s & 255, (~s >> 8) & 255])
    rec['unused_flag'] = sram_case('sram_unused_flag', bytes(bad), 1, 'broken')
    # one slot broken, the other valid: the valid one is used
    two = bytearray(img)
    two[(1 - slot) * 256:(1 - slot) * 256 + 256] = img[base:base + 256]
    two[base + 30] ^= 0xFF
    rec['one_slot_broken'] = sram_case('sram_one_slot', bytes(two), 2, None)
    return rec


def test_hold():
    """Held buttons: A does not skip pages, the d-pad repeats at the documented rate and stops at the ends."""
    g = new('hold')
    rec = {}
    g.boot_menu()
    g.tap('A')
    pages = 0
    g.run(200, ('A',))                          # held through the intro: at most the first page completes
    assert g.mode() == M_MSG, 'held A left the intro'
    msgs = g.w('msg_count')
    g.run(100)
    assert g.w('msg_count') == msgs and g.w('msg_state') == 1, 'held A advanced a page'
    g.settle()
    assert g.mode() == M_CMD
    # held DOWN in the command menu: wraps every 5 frames after 16
    sel = []
    for _ in range(60):
        g.run(1, ('DOWN',))
        sel.append(g.w('cmd_sel'))
    changes = sum(1 for a, b in zip(sel, sel[1:]) if a != b) + (sel[0] != 0)
    rec['cmd_moves_in_60_frames_held'] = changes
    assert 8 <= changes <= 12, changes
    g.run(10)
    g.to_cmd()
    g.cmd('しらべる')
    g.run(120, ('DOWN',))
    assert g.w('list_sel') == g.w('list_count') - 1, 'held DOWN did not stop at the last entry'
    g.run(120, ('UP',))
    assert g.w('list_sel') == 0 and g.w('list_top') == 0
    g.tap('R')
    assert g.w('list_sel') == 5
    g.tap('L')
    assert g.w('list_sel') == 0
    shot(g, 'list_after_paging')
    # held B in a list goes back once and stays in the command menu
    g.run(60, ('B',))
    assert g.mode() == M_CMD
    finish(g, rec)
    return rec


def test_screens():
    """Every place with and without the portrait, with the list cursor moved around (no ghost)."""
    g = new('screens')
    rec = {}
    start_new(g)
    g.cmd('はなす')
    for i in range(4):
        g.tap('DOWN')
    for i in range(4):
        g.tap('UP')
    rows = g.shot(g.shots / 'cursor_round_trip.png') if g.quiet() is None else None
    yellow = (31 * 255 // 31, 26 * 255 // 31, 12 * 255 // 31)       # UI colour 6 ($335F)
    is_y = lambda p: all(abs(p[k] - yellow[k]) <= 3 for k in range(3))
    in_cursor_col = sum(1 for y in range(144, 224) for x in range(80, 88) if is_y(rows[y][x]))
    in_cmd_col = sum(1 for y in range(144, 224) for x in range(8, 16) if is_y(rows[y][x]))
    assert in_cursor_col == 25, ('list cursor column should hold exactly one ▶ (25 px)', in_cursor_col)
    assert in_cmd_col == 0, ('no command cursor while a list is open', in_cmd_col)
    rec['cursor_pixels'] = in_cursor_col
    g.to_cmd()
    shot(g, 'cmd_after_talk')
    for name in ('汐見港　信号所', '第二桟橋　詰所', '喫茶「浮標」', '汐見署', '第三倉庫　事務所'):
        g.move(name)
        shot(g, f'scene{g.w("scene")}')
        g.cmd('はなす')
        shot(g, f'scene{g.w("scene")}_talk')
        g.to_cmd()
    finish(g, rec)
    return rec


def pcm_window(g, frames, buttons=()):
    """Run frames while recording; returns (peak, mean absolute, pcm) of the stereo PCM of that window."""
    import struct
    g.e.audio_pcm = bytearray()
    g.e.record_audio = True
    g.run(frames, buttons)
    g.e.record_audio = False
    pcm = bytes(g.e.audio_pcm)
    v = struct.unpack(f'<{len(pcm) // 2}h', pcm)
    return (max(abs(x) for x in v) if v else 0), (sum(abs(x) for x in v) / len(v) if v else 0), pcm


def wav(path, pcm):
    import wave
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(32040)
        f.writeframes(pcm)


def test_audio():
    """SPC700 driver: the songs of the opening, the title and each place, effects on input, silence with
    おと：なし, the song kept under it and back with おと：あり."""
    g = new('audio')
    rec = {}
    g.boot_menu()
    assert g.w('spc_ready') == 0x5A, 'sound driver did not answer'
    assert g.w('music_cur') == SONG['title'], ('title song', g.w('music_cur'))
    peak, mean, pcm = pcm_window(g, 400)
    wav(g.shots / 'title_music.wav', pcm)
    rec['title_music'] = dict(peak=peak, mean=round(mean, 1))
    assert peak > 1000 and mean > 100, 'no music on the title'
    g.tap('A')                                  # はじめから
    g.settle()
    assert g.w('music_cur') == SONG['investigate'], ('warehouse song', g.w('music_cur'))
    peak, mean, pcm = pcm_window(g, 400)
    wav(g.shots / 'warehouse_music.wav', pcm)
    rec['warehouse_music'] = dict(peak=peak, mean=round(mean, 1))
    assert peak > 1000 and mean > 100, 'no music in the warehouse'
    g.e.audio_pcm = bytearray()
    g.e.record_audio = True
    for k in ('DOWN', 'DOWN', 'UP', 'A', 'B', 'A'):
        g.tap(k, 2, 20)
    g.e.record_audio = False
    pcm = bytes(g.e.audio_pcm)
    wav(g.shots / 'effects.wav', pcm)
    rec['effects_peak'] = max(abs(int.from_bytes(pcm[i:i + 2], 'little', signed=True)) for i in range(0, len(pcm), 2))
    assert rec['effects_peak'] > 1000, 'no effects heard'
    g.to_cmd()
    g.look('柱時計')                             # a clue chime
    songs = {}
    for place, want in ((routes.SIGNAL, 'investigate'), (routes.PIER, 'sea'), (routes.CAFE, 'cafe'),
                        (routes.STATION, 'investigate')):
        g.move(place)
        g.quiet()
        assert g.w('music_cur') == SONG[want], (place, g.w('music_cur'))
        peak, mean, pcm = pcm_window(g, 300)
        wav(g.shots / f'{want}_{len(songs)}.wav', pcm)
        songs[place] = dict(song=want, peak=peak, mean=round(mean, 1))
        assert peak > 1000 and mean > 100, ('no music', place)
        assert peak < 30000, ('music too loud', place, peak)
    rec['places'] = songs
    g.note('おと：あり')                          # -> おと：なし
    assert g.w('sound_on') == 0
    g.to_cmd()
    g.run(30)
    peak, mean, _ = pcm_window(g, 300)
    rec['sound_off'] = dict(peak=peak, mean=round(mean, 1))
    assert peak == 0, 'sound still audible after おと：なし (music and echo included)'
    g.cmd('しらべる')                            # effects are not sent either
    peak2, _, _ = pcm_window(g, 60)
    assert peak2 == 0
    g.to_cmd()
    assert g.w('music_cur') == SONG['investigate']
    g.note('おと：なし')                          # back on
    assert g.w('sound_on') == 1
    g.to_cmd()
    peak, mean, _ = pcm_window(g, 400)
    rec['sound_on_again'] = dict(peak=peak, mean=round(mean, 1))
    assert peak > 1000
    rec['commands_sent'] = g.w('snd_sent')
    finish(g, rec)
    return rec


def test_opening():
    """Power-on without input: the notice, four pictures with their lines on the beats of the opening song,
    black, the title on beat 48; PUSH START BUTTON blinks; START opens the menu and B closes it; left alone
    the opening starts again.  Then START during the prologue skips to the title with the song's theme."""
    g = new('opening')
    rec = {}
    steps, beats, pics = [], {}, []
    last_step = -1
    for f in range(60 * 46):
        g.run(1)
        st = g.w('op_step')
        if st != last_step:
            steps.append(dict(frame=g.frame, step=st, beat=g.w('op_beat'), image=g.w('image_cur')))
            last_step = st
        if g.w('mode') == M_OPEN and g.w('op_state') == OP_TITLE:
            break
        for name, at in (('notice', 4), ('harbour', 12), ('lighthouse', 20), ('signal', 28), ('warehouse', 36)):
            if g.w('op_beat') == at and name not in beats:
                beats[name] = g.frame
                g.quiet()
                shot(g, name)
    assert g.w('mode') == M_OPEN and g.w('op_state') == OP_TITLE, 'the title did not come'
    title_frame = g.frame
    g.title_screen(skip=False)
    shot(g, 'title')
    rec['title_frame'] = title_frame
    rec['beats_at'] = beats
    # one picture every 8 beats, about 45 frames a beat (80 bpm)
    frames = [beats[k] for k in ('harbour', 'lighthouse', 'signal', 'warehouse')]
    gaps = [b - a for a, b in zip(frames, frames[1:])]
    rec['picture_gaps_frames'] = gaps
    assert all(abs(gp - 360) <= 4 for gp in gaps), ('the pictures do not follow the beat', gaps)
    rec['steps'] = steps
    img = g.layout['images']
    shown = []
    for s_ in steps:
        if s_['image'] not in shown:
            shown.append(s_['image'])
    assert shown[:4] == [img['title'], img['lighthouse'], img['signal'], img['warehouse']], ('pictures', shown)
    assert g.w('music_cur') == SONG['opening']
    assert g.w('image_cur') == img['title'] and g.w('fade_level') == 16
    # the title: PUSH START BUTTON blinks (colour 8 on, then off)
    on = off = 0
    for _ in range(140):
        g.run(1)
        if g.w('ui_pal', 16):
            on += 1
        else:
            off += 1
    rec['blink_frames_on_off'] = [on, off]
    assert on > 40 and off > 20, ('no blink', on, off)
    g.tap('START', 2, 4)
    assert g.mode() == M_LIST and g.w('list_kind') == 9, 'START did not open the menu'
    g.quiet()
    shot(g, 'menu')
    g.tap('B', 2, 4)
    assert g.mode() == M_OPEN and g.w('op_state') == OP_TITLE, 'B did not close the menu'
    # left alone on the title: everything fades and the opening starts again
    for _ in range(3200):
        g.run(1)
        if g.w('op_state') == 0:
            break
    assert g.w('op_state') == 0 and g.w('op_step') <= 1, 'the opening did not start again'
    rec['restart_after_frames'] = g.frame - title_frame
    for _ in range(120):
        g.run(1)
    assert g.w('music_cur') == SONG['opening'] and g.w('op_step') >= 1
    # skip: START during the prologue -> the title, the song from its theme
    g.run(200)
    g.tap('START', 2, 2)
    t0 = g.frame
    g.title_screen(skip=False)
    rec['skip_to_title_frames'] = g.frame - t0
    assert g.w('music_cur') == SONG['title']
    assert g.frame - t0 < 150, 'the skip is slow'
    shot(g, 'title_skipped')
    finish(g, rec)
    return rec


def vram_words(g, word_addr, n):
    v = g.e.vram
    return [v[(word_addr + i) * 2] | v[(word_addr + i) * 2 + 1] << 8 for i in range(n)]


def check_vram(g, picture):
    """The PPU memory the game set up: maps, blank tiles, picture tiles, text layer = WRAM bitmap."""
    m1 = vram_words(g, 0x4400, 1024)
    for r in range(32):
        for c in range(32):
            want = (r - 2) * 32 + c if 2 <= r < 18 else 512
            assert m1[r * 32 + c] == want, ('BG1 map', r, c, m1[r * 32 + c])
    m2 = vram_words(g, 0x4800, 1024)
    for r in range(32):
        for c in range(32):
            want = 1 + r * 32 + c if r < 2 else 1 + (r - 16) * 32 + c if 18 <= r < 28 else 0
            assert m2[r * 32 + c] == want, ('BG2 map', r, c, m2[r * 32 + c])
    v = bytes(g.e.vram)
    assert v[0x8000:0x8040] == bytes(64), 'BG1 blank tile 512 is not empty'
    assert v[0xA000:0xA020] == bytes(32), 'BG2 tile 0 is not transparent'
    pic = (B / f'pic{picture}.bin').read_bytes()
    assert v[0:0x8000] == pic, 'BG1 tiles differ from the built picture'
    bmp = g.b('bmp', 12288)
    assert v[0xA020:0xA020 + 12288] == bmp, 'text layer in VRAM differs from the WRAM bitmap'
    oam = g.b('oam_buf', 544)
    assert all(oam[i * 4 + 1] == 240 for i in range(128)) and oam[512:] == bytes(32), 'OAM image not off-screen'


def test_vram():
    """VRAM after boot, after a picture change, with a portrait, and after it is removed."""
    g = new('vram')
    rec = {}
    g.boot_menu()
    g.quiet()
    check_vram(g, g.w('image_cur'))
    start_new(g)
    g.quiet()
    check_vram(g, g.w('image_cur'))
    g.cmd('はなす')
    g.quiet()
    v = bytes(g.e.vram)
    pic = (B / f'pic{g.w("image_cur")}.bin').read_bytes()
    changed = sum(1 for t in range(512) if v[t * 64:t * 64 + 64] != pic[t * 64:t * 64 + 64])
    rec['portrait_tiles_changed'] = changed
    assert 0 < changed <= 9 * 13, changed
    g.to_cmd()
    g.quiet()
    check_vram(g, g.w('image_cur'))              # the portrait tiles are restored
    g.move('汐見署')
    g.quiet()
    check_vram(g, g.w('image_cur'))
    rec['labels'] = {k: hex(g.L[k]) for k in ('bmp', 'pal_buf', 'oam_buf', 'flags', 'mode', 'scene')}
    finish(g, rec)
    return rec


TESTS = dict(full=test_full, order=test_order, wrong=test_wrong, save=test_save, sram=test_sram,
             hold=test_hold, screens=test_screens, audio=test_audio, vram=test_vram, opening=test_opening)


def main(names):
    rom = B / 'shionari.sfc'
    rom_sha = hashlib.sha256(rom.read_bytes()).hexdigest()
    ok = True
    for name in names or TESTS:
        try:
            r = TESTS[name]()
            results[name] = dict(ok=True, **(r or {}))
            print(f'PASS {name} {json.dumps(r, ensure_ascii=False)}')
        except Exception as e:
            ok = False
            results[name] = dict(ok=False, error=f'{type(e).__name__}: {e}', trace=traceback.format_exc())
            print(f'FAIL {name}: {type(e).__name__}: {e}')
            traceback.print_exc()
    out = dict(rom_sha256=rom_sha, core='Snes9x 1.63 libretro (unmodified)',
               core_sha256=hashlib.sha256((ROOT / 'tools/vendor/snes9x-1.63/libretro/snes9x_libretro.dylib').read_bytes()).hexdigest(),
               scope='Emulator only (not physical hardware); pad input only; WRAM read only; SRAM handed over as a battery image.',
               results=results)
    path = B / ('tests.json' if not names else 'tests-partial.json')
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main(sys.argv[1:])
