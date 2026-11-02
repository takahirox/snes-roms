"""Lip-sync tests of 潮鳴りの密室 on the unmodified Snes9x 1.63 libretro core (pad input only).

WRAM, VRAM and the video output are read, never written.  A checker runs after every frame; where the
main loop has finished its frame (frame_ready = 1) it compares
  - mouth_actor with the speaker code of the page being typed, parsed from the ROM text at msg_ptr
    (the speaker comes from the ROM, not from the name's glyphs);
  - mouth_talk with the rule: message typing, the speaker is the person of the portrait on screen
    (MouthTable in the ROM), the portrait fully uploaded; mouth_want is closed otherwise;
  - the portrait area of VRAM with the ROM: the mouth tiles = the closed/half/open frame mouth_shown, every
    other portrait tile = the ROM portrait tile (nothing around the mouth is damaged), whenever no BG1
    upload is waiting in the job queue;
and in every frame: at most one mouth upload, and the frames from "stops talking" to a closed mouth in
VRAM.  Sessions (pad traces in build/adv/traces/ for tests/adv/bsnes.py):
  lip_main    new game to the ending: the six people at normal speed (screens of every frame of a page
              for the strips), A / B fast-forward, the same page twice (same mouth timeline), narration and
              Hatano without a portrait, a narration page in front of a portrait, わたし (deduction),
              portrait off, moves, sound off, ending and title
  lip_a_save  candidate A's battery images (tests/adv/compat/A/tests/save_*/final.srm): つづきから on
              candidate A's ROM and on this ROM give the same state, the mouth moves after continuing, and
              a record written by this ROM is read back the same by candidate A's ROM
  fixture     NOT the release ROM: a separate ROM built in its own directory (build/adv-lipfixture/, own
              SHA-256, own source list and procedure in FIXTURE.json, own trace) from a copy of the sources
              with three extra lines in one topic, where 波多野 and わたし speak in front of 修一's portrait
              (the real story never does): only 修一 moves.  The repository sources are not touched.
Results: build/adv/lipsync/RESULTS.json; strips, crops and videos (release ROM only) under build/adv/lipsync/.

usage: python3 -I tests/adv/lipsync.py [main] [a_save] [fixture]
"""
import sys, json, pathlib, hashlib, shutil, subprocess, traceback, ctypes as C
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from drive import Driver, ROOT, M_CMD, M_LIST, M_MSG, M_FADE, M_END, fw
from emu import labels as read_labels
import routes
import png_codec

B = ROOT / 'build/adv'
OUT = B / 'lipsync'
SHOTS = B / 'tests'
TRACES = B / 'traces'
A_DIR = ROOT / 'tests/adv/compat/A'
FIX = ROOT / 'build/adv-lipfixture'
sha = lambda b: hashlib.sha256(b).hexdigest()
PEOPLE = ['hatano', 'koga', 'tatsumi', 'yukiko', 'ookouchi', 'shuichi']
CLOSE_LATENCY_MAX = 2      # frames from "not talking" to the closed mouth in VRAM (lag frames excluded)


# ------------------------------------------------------------------ ROM reading
class Rom:
    def __init__(self, rom_path, label_path, layout):
        self.data = pathlib.Path(rom_path).read_bytes()
        self.L = read_labels(label_path)
        self.layout = layout

    @staticmethod
    def off(long):
        bank, addr = long >> 16 & 0xFF, long & 0xFFFF
        assert addr >= 0x8000, hex(long)
        return (bank & 0x7F) * 0x8000 + addr - 0x8000

    def word(self, o):
        return self.data[o] | self.data[o + 1] << 8

    def text_start(self, tid):
        o = self.off(self.L['TextTable']) + tid * 3
        return self.off(self.data[o] | self.data[o + 1] << 8 | self.data[o + 2] << 16)

    def actor_at(self, tid, ptr):
        """Speaker code of the page at ROM offset ptr of text tid (0 before the code / no code)."""
        o, actor = self.text_start(tid), 0
        while o < ptr:
            c = self.word(o)
            o += 2
            if c == 0xFFFF:
                break
            if c == 0xFFFD:
                actor = 0
            elif c == 0xFFFC:
                o += 2
            elif c & 0xFFF0 == 0xFFE0:
                actor = c & 0xF
        return actor

    def page_speakers(self, tid):
        o, pages, cur = self.text_start(tid), [], 0
        while True:
            c = self.word(o)
            o += 2
            if c in (0xFFFD, 0xFFFF):
                pages.append(cur)
                cur = 0
                if c == 0xFFFF:
                    return pages
            elif c == 0xFFFC:
                o += 2
            elif c & 0xFFF0 == 0xFFE0:
                cur = c & 0xF

    def mouth_table(self):
        out = []
        base = self.off(self.L['MouthTable'])
        for k in range(len(self.layout['mouths'])):
            w = [self.word(base + k * 16 + i * 2) for i in range(8)]
            person, vram, rowb, rows, s0, s1, s2, bank = w
            frames = [self.data[self.off(bank << 16 | s):][:rowb * rows] for s in (s0, s1, s2)]
            out.append(dict(person=person, vram=vram, rowbytes=rowb, rows=rows, frames=frames,
                            tiles=[(vram // 32 + r * 32 + c) for r in range(rows) for c in range(rowb // 64)]))
        return out

    def portrait_table(self):
        out = []
        base = self.off(self.L['PortraitTable'])
        for k in range(len(self.layout['mouths'])):
            x, y, w, h, a, bank = [self.word(base + k * 12 + i * 2) for i in range(6)]
            data = self.data[self.off(bank << 16 | a):][:w * h * 64]
            out.append(dict(x=x, y=y, w=w, h=h, data=data))
        return out


# ------------------------------------------------------------------ the per-frame checker
class LipCheck:
    def __init__(self, g, rom):
        self.rom = rom
        self.mt = rom.mouth_table()
        self.pt = rom.portrait_table()
        mb = (B / 'mouth.bin').read_bytes() if rom.data == (B / 'shionari.sfc').read_bytes() else None
        for k, (m, info) in enumerate(zip(self.mt, rom.layout['mouths'])):
            for f in range(3):
                assert sha(m['frames'][f]) == info['frame_sha256'][f], ('ROM mouth frame != build', k, f)
                if mb is not None:
                    assert mb[info['frame_offset'][f]:][:len(m['frames'][f])] == m['frames'][f]
            assert m['frames'][0] == b''.join(self.portrait_tile(k, t) for t in m['tiles']), ('closed != portrait', k)
        self.ram = g.e.ram
        self.vaddr = C.addressof(g.e.vram)
        self.A = {n: g.addr(n) for n in ('frame_ready', 'mode', 'msg_state', 'msg_text', 'msg_ptr', 'mouth_actor',
                                          'mouth_want', 'mouth_shown', 'mouth_talk', 'mouth_pause', 'mouth_timer',
                                          'mouth_uploads', 'mouth_other', 'por_shown', 'por_rows', 'job_head',
                                          'job_tail', 'jobs', 'lag_count', 'nmi_count')}
        self.timeline = []
        self.errors = []
        self.last_up = self.r('mouth_uploads')
        self.stats = dict(frames=0, ready_frames=0, vram_checks=0, msg_frames=0, talk_frames=0, uploads=0,
                          max_uploads_per_frame=0, other_frames=0, actor_frames={}, close_latency_max=0,
                          close_events=0, shown_counts=[0, 0, 0])
        self.closing = None          # frame count since talk stopped, while the VRAM mouth is not closed
        self.prev_talk = 0

    def r(self, n, i=0):
        a = self.A[n] + i
        return self.ram[a] | self.ram[a + 1] << 8

    def vram(self, byte_addr, n):
        return C.string_at(self.vaddr + byte_addr, n)

    def portrait_tile(self, k, tile):
        p = self.pt[k]
        r, c = tile // 32 - p['y'], tile % 32 - p['x']
        return p['data'][(r * p['w'] + c) * 64:][:64]

    def vram_mouth(self, k):
        """0/1/2 = the mouth frame now in VRAM for portrait k, -1 = none of them."""
        m = self.mt[k]
        now = b''.join(self.vram(t * 64, 64) for t in m['tiles'])
        return m['frames'].index(now) if now in m['frames'] else -1

    def pending_bg1(self):
        h, t = self.r('job_head'), self.r('job_tail')
        for j in range(h, t, 8):
            dest, typ = self.r('jobs', j), self.r('jobs', j + 2) & 0xFF
            if typ == 0 and dest < 0x4000:
                return True
        return False

    def fail(self, g, msg):
        self.errors.append(dict(frame=g.frame, error=msg))
        raise AssertionError(f'frame {g.frame}: {msg}')

    def __call__(self, g):
        st = self.stats
        st['frames'] += 1
        if self.r('nmi_count') == 0:         # power-on: the reset code has not cleared WRAM / started the loop
            self.last_up = 0
            st['before_main_loop'] = st.get('before_main_loop', 0) + 1
            return
        up = self.r('mouth_uploads')
        d = (up - self.last_up) & 0xFFFF
        self.last_up = up
        st['uploads'] += d
        st['max_uploads_per_frame'] = max(st['max_uploads_per_frame'], d)
        if d > 1:
            self.fail(g, f'{d} mouth uploads in one frame')
        pshow, prows = self.r('por_shown'), self.r('por_rows')
        vm = self.vram_mouth(pshow - 1) if pshow else None
        # closing latency: from the frame where talking stops to a closed mouth in VRAM
        talk_now = self.r('mouth_talk')
        if self.prev_talk and not talk_now:
            self.closing = 0
        if self.closing is not None:
            if vm in (0, None) or prows:
                st['close_events'] += 1
                st['close_latency_max'] = max(st['close_latency_max'], self.closing)
                self.closing = None
            else:
                self.closing += 1
                if self.closing > CLOSE_LATENCY_MAX + 8:
                    self.fail(g, 'the mouth did not close')
        self.prev_talk = talk_now
        ready = self.r('frame_ready') == 1
        row = [g.frame, int(ready), self.r('mode'), self.r('msg_state'), self.r('msg_text'), self.r('mouth_actor'),
               talk_now, self.r('mouth_want'), self.r('mouth_shown'), self.r('mouth_pause'), up, pshow, prows,
               vm if vm is not None else -2]
        self.timeline.append(row)
        if not ready:
            return
        st['ready_frames'] += 1
        mode, mst, actor, want, shown = row[2], row[3], row[5], row[7], row[8]
        if mode == M_MSG:
            st['msg_frames'] += 1
            ptr = self.r('msg_ptr') | self.ram[self.A['msg_ptr'] + 2] << 16
            # at a page / end wait msg_ptr is already past the $FFFD / $FFFF of the page just typed
            exp = self.rom.actor_at(row[4], Rom.off(ptr) - (2 if mst else 0))
            if actor != exp:
                self.fail(g, f'mouth_actor {actor} but the ROM page speaker is {exp} (text {row[4]})')
            st['actor_frames'][str(actor)] = st['actor_frames'].get(str(actor), 0) + 1
        exp_talk = int(mode == M_MSG and mst == 0 and 1 <= actor <= len(PEOPLE) and pshow != 0 and prows == 0
                       and self.mt[pshow - 1]['person'] == actor)
        if talk_now != exp_talk:
            self.fail(g, f'mouth_talk {talk_now}, expected {exp_talk}')
        if (mode == M_MSG and mst == 0 and 1 <= actor <= len(PEOPLE) and pshow and prows == 0
                and self.mt[pshow - 1]['person'] != actor):
            st['other_frames'] += 1
        st['talk_frames'] += talk_now
        if want not in (0, 1, 2) or shown not in (0, 1, 2):
            self.fail(g, f'mouth state {want} {shown}')
        if not talk_now and want != 0:
            self.fail(g, 'mouth wanted open while not talking')
        if not pshow and shown != 0:
            self.fail(g, 'mouth_shown without a portrait')
        if pshow and prows == 0 and not self.pending_bg1():
            k = pshow - 1
            m, p = self.mt[k], self.pt[k]
            for r in range(p['h']):
                t0 = (p['y'] + r) * 32 + p['x']
                now = self.vram(t0 * 64, p['w'] * 64)
                for c in range(p['w']):
                    t = t0 + c
                    want_tile = (m['frames'][shown][m['tiles'].index(t) * 64:][:64] if t in m['tiles']
                                 else self.portrait_tile(k, t))
                    if now[c * 64:c * 64 + 64] != want_tile:
                        self.fail(g, f'VRAM tile {t} of portrait {k} differs (mouth_shown {shown})')
            st['vram_checks'] += 1
            st['shown_counts'][shown] += 1


def make_driver(name, rom=None, label_file=None, layout=None, sram=None, shots=SHOTS):
    g = Driver(rom=rom or 'build/adv/shionari.sfc', sram=sram, label_file=label_file)
    if layout is not None:
        g.layout = layout
        g.text_ids = {}
        for i, t in enumerate(layout['texts']):
            if t['kind'] == 'label':
                g.text_ids.setdefault(t['text'], i)
    g.name = name
    g.shots = shots / name
    if g.shots.exists():
        shutil.rmtree(g.shots)
    return g


def hw(g):
    return dict(frames=g.frame, lag_count=g.w('lag_count'), vblank_overrun_count=g.w('vblank_overrun_count'),
                nmi_end_line_max=g.w('nmi_end_line_max'), dma_bytes_max=g.w('dma_bytes_max'),
                dma_deferred=g.w('dma_deferred'), text_clip=g.w('text_clip'), mouth_uploads=g.w('mouth_uploads'),
                mouth_other=g.w('mouth_other'))


def check_hw(g):
    assert g.w('vblank_overrun_count') == 0, 'NMI work ran past the V-blank'
    assert 225 <= g.w('nmi_end_line_max') <= 258, ('NMI end line', g.w('nmi_end_line_max'))
    assert g.w('dma_bytes_max') <= 4096, ('DMA over the budget', g.w('dma_bytes_max'))
    assert g.w('dma_deferred') == 0, 'a DMA job had to wait'
    assert g.w('text_clip') == 0, 'a glyph crossed its box'


def finish(g, rec, trace=True):
    check_hw(g)
    rec.update(hw(g))
    g.save_battery(g.shots)
    rec['input_sram_sha256'] = g.sram_files['initial.srm']['sha256']
    rec['output_sram_sha256'] = g.sram_files['final.srm']['sha256']
    if trace:
        g.trace(TRACES / f'{g.name}.json')
    g.close()


# ------------------------------------------------------------------ reading pages
class Reader:
    """Pages read at normal speed with the frames recorded (and captured as screens if asked)."""
    def __init__(self, g, chk):
        self.g, self.chk = g, chk
        self.pages = []
        self.captures = {}           # tag -> list of (frame, png path)
        self.palettes = {}

    def wait_typing(self, limit=600):
        g = self.g
        for _ in range(limit):
            if g.mode() == M_MSG and g.w('msg_state') == 0:
                return
            g.run(1)
        raise AssertionError('no message started')

    def page(self, tag, capture=0, fast=None, fast_after=0):
        """Type the current page; fast = 'A'/'B' pressed once fast_after frames after the body starts."""
        g = self.g
        self.wait_typing()
        tid, start, up0 = g.w('msg_text'), g.frame, g.w('mouth_uploads')
        seq, n, body_at, pressed = [], 0, None, False
        if capture:
            self.palettes[tag] = g.b('pal_buf', 480).hex()
            assert g.w('pal_level') == 16
            self.captures.setdefault(tag, [])
        while g.mode() == M_MSG and g.w('msg_state') == 0:
            btn = ()
            if body_at is not None and fast and not pressed and g.frame - body_at >= fast_after:
                btn, pressed = (fast,), True
            g.run(1, btn)
            if body_at is None and (g.w('mouth_actor') or g.w('msg_x') > 12 and g.w('msg_y') > 21):
                body_at = g.frame
            seq.append(self.chk.timeline[-1])
            if n < capture:
                p = g.shots / f'{tag}_{n:03d}.png'
                g.shot(p)
                self.captures[tag].append((g.frame, p))
                n += 1
        for i in range(3):                       # the page / end wait
            g.run(1)
            seq.append(self.chk.timeline[-1])
            if capture:
                p = g.shots / f'{tag}_{n:03d}.png'
                g.shot(p)
                self.captures[tag].append((g.frame, p))
                n += 1
        speakers = self.chk.rom.page_speakers(tid)
        rec = dict(tag=tag, text=tid, what=g.layout['texts'][tid]['what'], speaker_codes=speakers,
                   actor=max((r[5] for r in seq), default=0), frames=g.frame - start, fast=fast,
                   uploads=(g.w('mouth_uploads') - up0) & 0xFFFF,
                   talk_frames=sum(r[6] for r in seq), sequence=[r[8] for r in seq if r[1]],
                   vram_sequence=[r[13] for r in seq], timeline=seq, first_frame=start)
        self.pages.append(rec)
        return rec

    def next(self):
        self.g.run(1, ('A',))
        self.g.run(1)

    def topic(self, cmd, label, tags, **kw):
        """はなす / みせる -> label, then read every page at normal speed (tags: one per page; options per
        tag in kw: capture=n screens, fast='A'/'B').  Pages past the tags are passed with A."""
        g = self.g
        if g.mode() != M_LIST or g.w('cmd_active') != ['はなす', 'しらべる', 'みせる'].index(cmd):
            g.cmd(cmd)
        label = fw(label)
        items = g.list_texts()
        want = items.index(g.text_ids[label])
        while g.w('list_sel') != want:
            g.tap('DOWN' if want > g.w('list_sel') else 'UP')
        g.run(1, ('A',))
        out = []
        for i, tag in enumerate(tags):
            opt = kw.get(tag, {}) if tag else {}
            r = self.page(tag or f'p{len(self.pages)}', **opt)
            out.append(r)
            last = g.w('msg_state') == 2
            self.next()
            if last:
                break
        g.settle()
        g.quiet()                    # the redraw after a message takes frames: let it finish before the next key
        return out


# ------------------------------------------------------------------ strips and video
def classify(rows, k, chk, palette_hex, mt_frames):
    """Which mouth frame the screen shows: render each candidate with the scene palette, nearest wins."""
    pal = bytes.fromhex(palette_hex)
    rgb = lambda i: tuple(((pal[(i - 16) * 2] | pal[(i - 16) * 2 + 1] << 8) >> s & 31) * 255 // 31 for s in (0, 5, 10))
    m = chk.mt[k]
    scores = []
    for f in range(3):
        worst = 0
        for ti, t in enumerate(m['tiles']):
            tile = m['frames'][f][ti * 64:ti * 64 + 64]
            x0, y0 = (t % 32) * 8, (t // 32) * 8 + 16
            for y in range(8):
                for x in range(8):
                    bit = 0x80 >> x
                    v = sum(((tile[(p >> 1) * 16 + y * 2 + (p & 1)] & bit) != 0) << p for p in range(8))
                    want = rgb(v)
                    got = rows[y0 + y][x0 + x]
                    worst = max(worst, max(abs(want[c] - got[c]) for c in range(3)))
        scores.append(worst)
    best = min(range(3), key=lambda f: scores[f])
    return best, scores


def crop(rows, x0, y0, w, h, scale):
    out = []
    for y in range(h * scale):
        out.append([rows[y0 + y // scale][x0 + x // scale] for x in range(w * scale)])
    return out


def strips(reader, chk, info):
    """Per person: every captured frame classified; a closed -> half -> open -> half -> closed strip at 1x
    and 6x; the whole capture window as crops; an MP4 of the captured screens (3x, nearest)."""
    res = {}
    sdir = OUT / 'strips'
    sdir.mkdir(parents=True, exist_ok=True)
    for tag, caps in reader.captures.items():
        k = next(i for i, m in enumerate(info['mouths']) if m['person'] == tag)
        m = chk.mt[k]
        tiles = m['tiles']
        tx0, ty0 = min(t % 32 for t in tiles), min(t // 32 for t in tiles)
        tx1, ty1 = max(t % 32 for t in tiles), max(t // 32 for t in tiles)
        cx, cy = tx0 * 8 - 12, ty0 * 8 + 16 - 14
        cw, ch = (tx1 - tx0 + 1) * 8 + 24, (ty1 - ty0 + 1) * 8 + 24
        frames = []
        for frame, path in caps:
            rows = png_codec.read(path)
            rows = [[px[:3] for px in r] for r in rows]
            f, scores = classify(rows, k, chk, reader.palettes[tag], m['frames'])
            tl = next(r for r in chk.timeline if r[0] == frame)
            frames.append(dict(frame=frame, png=str(path.relative_to(ROOT)), screen_mouth=f, scores=scores,
                               ram_mouth_want_requested=tl[7], ram_mouth_shown_last_submitted=tl[8],
                               vram_mouth_after_frame=tl[13], mouth_talk=tl[6], msg_state=tl[3],
                               mouth_actor=tl[5], text=tl[4], rows=rows))
        seq = [x['screen_mouth'] for x in frames]
        # first closed -> half -> open -> ... -> closed run on screen
        pick = None
        for i in range(len(seq)):
            if seq[i] != 0:
                continue
            j = i + 1
            path = [i]
            seen = set()
            while j < len(seq) and seq[j] != 0:
                if seq[j] != seq[path[-1]]:
                    path.append(j)
                seen.add(seq[j])
                j += 1
            if j < len(seq) and {1, 2} <= seen:
                path.append(j)
                pick = path
                break
        out = dict(crop_screen=[cx, cy, cw, ch], screen_sequence=seq,
                   phase_rule='screen_mouth = the closed/half/open frame (ROM MouthTable tiles drawn with the scene '
                              'palette from WRAM pal_buf) nearest to the video-callback pixels of the mouth tiles; '
                              'scores = max RGB difference per candidate.  ram_mouth_* are what the game requested '
                              '/ last queued, and vram_mouth_after_frame is VRAM read after the frame: the picture '
                              'of a frame shows the VRAM of the V-blank before it, so they can lead the pixels.',
                   frames=[{k2: v for k2, v in x.items() if k2 != 'rows'}
                                                                            for x in frames])
        if pick:
            out['strip_frames'] = [frames[i]['frame'] for i in pick]
            out['strip_states'] = [seq[i] for i in pick]
            for scale in (1, 6):
                gap = 2 * scale
                img = [[(0, 0, 0)] * (len(pick) * (cw * scale + gap) - gap) for _ in range(ch * scale)]
                for n, i in enumerate(pick):
                    c = crop(frames[i]['rows'], cx, cy, cw, ch, scale)
                    for y in range(ch * scale):
                        img[y][n * (cw * scale + gap):n * (cw * scale + gap) + cw * scale] = c[y]
                png_codec.write(sdir / f'{tag}-strip-{scale}x.png', img)
            out['strip_png'] = [f'build/adv/lipsync/strips/{tag}-strip-{s}x.png' for s in (1, 6)]
        # every captured frame as a 4x crop, in order
        cols = len(frames)
        img = [[(0, 0, 0)] * (cols * (cw * 4 + 4)) for _ in range(ch * 4)]
        for n, x in enumerate(frames):
            c = crop(x['rows'], cx, cy, cw, ch, 4)
            for y in range(ch * 4):
                img[y][n * (cw * 4 + 4):n * (cw * 4 + 4) + cw * 4] = c[y]
        png_codec.write(sdir / f'{tag}-window-4x.png', img)
        out['window_png'] = f'build/adv/lipsync/strips/{tag}-window-4x.png'
        # video: the captured screens at 60 fps, 3x
        vid = OUT / 'video' / f'{tag}.mp4'
        vid.parent.mkdir(parents=True, exist_ok=True)
        pattern = str(caps[0][1].parent / f'{tag}_%03d.png')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-framerate', '60.0988', '-i', pattern,
                        '-vf', 'scale=768:672:flags=neighbor', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '12',
                        '-pix_fmt', 'yuv420p', str(vid)], check=True)
        # the mouth area only, 8x, slowed to 15 fps so each frame is visible
        vid2 = OUT / 'video' / f'{tag}-mouth-8x-quarter-speed.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-framerate', '15', '-i', pattern,
                        '-vf', f'crop={cw}:{ch}:{cx}:{cy},scale={cw * 8}:{ch * 8}:flags=neighbor', '-c:v', 'libx264',
                        '-preset', 'veryfast', '-crf', '12', '-pix_fmt', 'yuv420p', str(vid2)], check=True)
        out['video'] = [str(vid.relative_to(ROOT)), str(vid2.relative_to(ROOT))]
        res[tag] = out
    return res


# ------------------------------------------------------------------ sessions
def page_checks(r, talking):
    """A page by a person in front of their own portrait (talking) or not."""
    seq = r['sequence']
    if talking:
        assert r['talk_frames'] > 0, (r['tag'], 'never talked')
        assert 1 in seq and 2 in seq, (r['tag'], 'half and open not both shown', seq)
        assert seq[-1] == 0 and r['vram_sequence'][-1] == 0, (r['tag'], 'not closed at the page wait')
    else:
        assert r['talk_frames'] == 0 and r['uploads'] == 0, (r['tag'], 'moved', r['talk_frames'], r['uploads'])


def session_main():
    g = make_driver('lip_main')
    rom = Rom(B / 'shionari.sfc', B / 'labels.txt', g.layout)
    chk = LipCheck(g, rom)
    g.observers.append(chk)
    rd = Reader(g, chk)
    rec = dict(pages=[])
    info = g.layout
    g.boot_menu()
    g.run(1, ('A',))
    # intro: narration and 波多野 without a portrait, at normal speed
    while True:
        r = rd.page(f'intro{len(rd.pages)}')
        page_checks(r, False)
        last = g.w('msg_state') == 2
        rd.next()
        if last:
            break
    g.settle()
    g.quiet()
    assert g.mode() == M_CMD and g.w('scene') == 0
    # 波多野 with her portrait: page 1 normal speed (captured), page 2 B fast-forward
    pages = rd.topic('はなす', '検視', ['hatano', 'hatano_b_fast'],
                     hatano=dict(capture=72), hatano_b_fast=dict(fast='B', fast_after=4))
    page_checks(pages[0], True)
    assert pages[1]['talk_frames'] > 0 and pages[1]['vram_sequence'][-1] == 0
    first_timeline = [(r[7], r[8]) for r in pages[0]['timeline']]
    # the same page again: the same mouth timeline (deterministic)
    again = rd.topic('はなす', '検視', ['hatano_again', 'hatano_again_a_fast'], hatano_again_a_fast=dict(fast='A'))
    assert [(r[7], r[8]) for r in again[0]['timeline']] == first_timeline, 'the same page moved differently'
    rec['same_page_twice'] = dict(frames=len(first_timeline), identical=True)
    g.to_cmd()
    g.quiet()
    v = bytes(g.e.vram[0:0x8000])
    assert v == (B / f'pic{g.w("image_cur")}.bin').read_bytes(), 'portrait off: BG1 is not the picture'
    rec['portrait_off_bg1_equals_picture'] = True
    # しらべる: the portrait is taken off; 波多野 speaks without it (鍵束)
    g.look('柱時計', '振り子の窓', '金庫', 'メモ', '荷揚げ口', '鉄梯子')
    g.cmd('しらべる')
    want = g.list_texts().index(g.text_ids[fw('鍵束')])
    while g.w('list_sel') != want:
        g.tap('DOWN' if want > g.w('list_sel') else 'UP')
    g.run(1, ('A',))
    for tag in ('look_keys0', 'look_keys1'):
        r = rd.page(tag)
        page_checks(r, False)
        last = g.w('msg_state') == 2
        rd.next()
        if last:
            break
    g.settle()
    g.quiet()
    g.to_cmd()
    rd.topic('はなす', '辰巳とは', [None])
    g.to_cmd()
    # 修一
    g.move(routes.STATION)
    pages = rd.topic('はなす', 'ゆうべのこと', ['shuichi', None], shuichi=dict(capture=72))
    page_checks(pages[0], True)
    rd.topic('はなす', '父の戸じまり', [None, None])
    rd.topic('はなす', '時計のこと', [None])
    g.to_cmd()
    # 古賀
    g.move(routes.SIGNAL)
    g.look('掲示板', '潮見表', '回覧板')
    pages = rd.topic('はなす', 'ゆうべのこと', ['koga', None], koga=dict(capture=72))
    page_checks(pages[0], True)
    rd.topic('はなす', '港内電話', [None, None])
    rd.topic('はなす', '梯子のこと', [None, None])
    rd.topic('はなす', '灯台', [None, None, None])
    g.to_cmd()
    # 辰巳, and a narration page in front of his portrait (K_NOTICE)
    g.move(routes.PIER)
    pages = rd.topic('はなす', 'ゆうべのこと', ['tatsumi', None, None], tatsumi=dict(capture=72))
    page_checks(pages[0], True)
    g.to_cmd()
    pages = rd.topic('みせる', g.layout['clue_names']['K_NOTICE'], ['notice_narration', 'notice_tatsumi', None])
    assert pages[0]['speaker_codes'][0] == 0
    page_checks(pages[0], False)
    page_checks(pages[1], True)
    rec['narration_in_front_of_portrait'] = dict(text=pages[0]['text'], talk_frames=pages[0]['talk_frames'])
    g.to_cmd()
    g.look('詰所の電話', '鍵帳', '作業艇')
    g.show('K_PHONE')
    # sound off, then 大河内
    g.note('おと：あり')
    g.to_cmd()
    assert g.w('sound_on') == 0
    g.move(routes.LIGHTHOUSE)
    g.look('当直日誌')
    pages = rd.topic('はなす', 'ゆうべのこと', ['ookouchi', None], ookouchi=dict(capture=72))
    page_checks(pages[0], True)
    assert g.w('sound_on') == 0
    rec['sound_off_talk'] = dict(sound_on=0, talk_frames=pages[0]['talk_frames'], uploads=pages[0]['uploads'])
    g.to_cmd()
    g.note('おと：なし')
    g.to_cmd()
    assert g.w('sound_on') == 1
    g.move(routes.PIER)
    g.show('K_LOG')
    g.move(routes.SIGNAL)
    g.talk('物入れの鍵')
    g.move(routes.PIER)
    g.look('物入れ')
    # ゆき子
    g.move(routes.CAFE)
    pages = rd.topic('はなす', 'ゆうべのこと', ['yukiko', None], yukiko=dict(capture=72))
    page_checks(pages[0], True)
    g.to_cmd()
    g.show('K_LEDGER')
    # deduction (わたし and 波多野 without a portrait), finale, ending, title
    g.note('ヒント')
    routes.deduce(g)
    assert g.mode() == M_END
    assert g.w('mouth_shown') == 0 and g.w('por_shown') == 0
    g.quiet()
    g.shot(g.shots / 'ending.png')
    g.ending_to_title()
    g.quiet()
    g.shot(g.shots / 'title_after.png')
    assert g.w('mouth_want') == 0 and g.w('mouth_shown') == 0
    st = chk.stats
    assert st['close_latency_max'] <= CLOSE_LATENCY_MAX, ('slow closing', st['close_latency_max'])
    for p in PEOPLE:
        assert p in rd.captures, p
    rec['checker'] = st
    rec['pages'] = [{k: v for k, v in p.items() if k != 'timeline'} for p in rd.pages]
    rec['strips'] = strips(rd, chk, g.layout)
    for tag, s in rec['strips'].items():
        assert s.get('strip_frames'), (tag, 'no closed-half-open-closed run on screen', s['screen_sequence'])
        bad = [x for x in s['frames'] if x['scores'][x['screen_mouth']] > 8]
        assert not bad, (tag, 'screen does not match any mouth frame', bad[:1])
    finish(g, rec)
    (OUT / 'timeline-lip_main.json').write_text(json.dumps(dict(
        columns=['frame', 'frame_ready', 'mode', 'msg_state', 'msg_text', 'mouth_actor', 'mouth_talk', 'mouth_want',
                 'mouth_shown', 'mouth_pause', 'mouth_uploads', 'por_shown', 'por_rows', 'vram_mouth'],
        rows=chk.timeline)) + '\n')
    return rec


STATE = ('scene', 'actions', 'wrong_count', 'sound_on', 'save_seq', 'save_slot', 'save_status', 'load_count',
         'mode', 'image_cur', 'dq_index', 'cmd_sel')


def state(g):
    return dict({k: g.w(k) for k in STATE}, flags=g.b('flags', 128).hex())


def continue_on(rom, labels, sram, name=None, layout=None, trace_name=None):
    g = make_driver(name or 'lip_tmp', rom=rom, label_file=labels, layout=layout, sram=sram)
    g.boot_menu()
    assert g.w('save_status') == 2 and g.w('list_sel') == 1, ('record not recognised', g.w('save_status'))
    g.tap('A')
    g.settle()
    assert g.mode() == M_CMD
    g.quiet()
    return g


def session_a_save():
    rec = {}
    a_rom, a_labels = A_DIR / 'shionari.sfc', A_DIR / 'labels.txt'
    assert sha(a_rom.read_bytes()) == 'cf3f89b9338f5c9b7d9482e9e9172bc343a0465704ede7028d47681a3feb30d3'
    for src in ('save_a', 'save_b'):
        sram = (A_DIR / 'tests' / src / 'final.srm').read_bytes()
        ga = continue_on(a_rom, a_labels, sram, 'lip_tmp_a')
        sa = state(ga)
        ga.close()
        gb = continue_on(B / 'shionari.sfc', None, sram, 'lip_tmp_b')
        sb = state(gb)
        gb.close()
        assert sa == sb, ('candidate A and this ROM continue differently', src, sa, sb)
        rec[src] = dict(sram_sha256=sha(sram), state=sa, same=True)
    # this ROM: continue from A's first record (汐見署), 修一 talks, a new record; candidate A reads it back
    sram = (A_DIR / 'tests' / 'save_a' / 'final.srm').read_bytes()
    g = make_driver('lip_a_save', sram=sram)
    rom = Rom(B / 'shionari.sfc', B / 'labels.txt', g.layout)
    chk = LipCheck(g, rom)
    g.observers.append(chk)
    rd = Reader(g, chk)
    g.boot_menu()
    assert g.w('save_status') == 2 and g.w('list_sel') == 1
    g.tap('A')
    g.settle()
    assert g.mode() == M_CMD and g.w('scene') == 5, ('continued elsewhere', g.w('scene'))
    pages = rd.topic('はなす', '発見のこと', ['shuichi_after_continue', None])
    page_checks(pages[0], True)
    g.to_cmd()
    g.note('きろくする')
    assert g.w('save_ok') == 1
    g.to_cmd()
    sb = state(g)
    rec['continued_talk'] = {k: v for k, v in pages[0].items() if k != 'timeline'}
    rec['checker'] = chk.stats
    finish(g, rec)
    new_sram = (g.shots / 'final.srm').read_bytes()
    ga = continue_on(a_rom, a_labels, new_sram, 'lip_tmp_a')
    sa = state(ga)
    ga.close()
    gb = continue_on(B / 'shionari.sfc', None, new_sram, 'lip_tmp_b')
    sb2 = state(gb)
    gb.close()
    assert sa == sb2, ('candidate A and this ROM read this ROM\'s record differently', sa, sb2)
    for k in ('scene', 'actions', 'wrong_count', 'sound_on', 'flags'):
        assert sa[k] == sb[k], ('the record does not hold the state at saving', k, sa[k], sb[k])
    rec['b_record_on_a'] = dict(sram_sha256=sha(new_sram), state_on_a=sa, same_as_on_this_rom=True,
                                game_fields_equal_to_the_state_at_saving=True)
    for d in ('lip_tmp_a', 'lip_tmp_b'):
        shutil.rmtree(SHOTS / d, ignore_errors=True)
    return rec


# ------------------------------------------------------------------ fixture ROM (not the release)
FIX_LINES = '波多野> 修一さん、そのときのことを、もう少し。\nわたし> 時刻は、確かですか。\n修一> ……はい。九時二十五分ごろです。\n'


def build_fixture():
    """A copy of the sources in build/adv-lipfixture/tree with the extra lines; build there."""
    if FIX.exists():
        shutil.rmtree(FIX)
    tree = FIX / 'tree'
    for d in ('src/adv', 'tools/adv', 'data/adv', 'assets/shinonome'):
        shutil.copytree(ROOT / d, tree / d, ignore=shutil.ignore_patterns('__pycache__'))
    (tree / 'assets/adv').mkdir(parents=True)
    for p in (ROOT / 'assets/adv').glob('*.png'):
        if p.name.endswith(('-256.png', '-72.png')):
            shutil.copy2(p, tree / 'assets/adv' / p.name)
    for n in ('ART.json', 'PREPARED.json'):
        shutil.copy2(ROOT / 'assets/adv' / n, tree / 'assets/adv' / n)
    shutil.copy2(ROOT / 'tools/png_codec.py', tree / 'tools/png_codec.py')
    story = (tree / 'data/adv/story.txt').read_text(encoding='utf-8')
    anchor = '\nget: T_SHUICHI\n'
    assert story.count(anchor) == 1
    story = story.replace(anchor, '\n' + FIX_LINES + 'get: T_SHUICHI\n')
    (tree / 'data/adv/story.txt').write_text(story, encoding='utf-8')
    (tree / 'build/adv').mkdir(parents=True)
    run = lambda *a: subprocess.run(list(a), cwd=tree, check=True, capture_output=True, text=True)
    run(sys.executable, '-I', 'tools/adv/build.py')
    run(str(ROOT / 'tools/vendor/cc65-2.19/bin/ca65'), '-g', '-I', '.', 'src/adv/shionari.s', '-o', 'build/adv/shionari.o')
    run(str(ROOT / 'tools/vendor/cc65-2.19/bin/ld65'), '-C', 'src/adv/adv.cfg', 'build/adv/shionari.o', '-o',
        'build/adv/shionari.sfc', '-Ln', 'build/adv/labels.txt')
    run(sys.executable, '-I', 'tools/adv/romfix.py', 'build/adv/shionari.sfc')
    files = sorted(q for q in tree.rglob('*') if q.is_file() and 'build' not in q.relative_to(tree).parts
                   and '__pycache__' not in q.parts)
    (FIX / 'FIXTURE.json').write_text(json.dumps(dict(
        purpose='test fixture for the lip-sync rule "another speaker in front of a portrait"; not a release candidate',
        procedure=['copy src/adv tools/adv data/adv assets/shinonome tools/png_codec.py and the assets/adv inputs '
                   'from the repository into build/adv-lipfixture/tree',
                   'insert added_lines before "get: T_SHUICHI" (topic 修一 ゆうべのこと) in tree/data/adv/story.txt',
                   'in tree: python3 -I tools/adv/build.py; ca65 -g -I . src/adv/shionari.s; ld65 -C src/adv/adv.cfg; '
                   'python3 -I tools/adv/romfix.py'],
        added_lines=FIX_LINES.splitlines(),
        sources={str(q.relative_to(tree)): sha(q.read_bytes()) for q in files},
        repository_story_sha256=sha((ROOT / 'data/adv/story.txt').read_bytes()),
        rom='build/adv-lipfixture/tree/build/adv/shionari.sfc',
        rom_sha256=sha((tree / 'build/adv/shionari.sfc').read_bytes())), ensure_ascii=False, indent=1) + '\n')
    return tree


def session_fixture():
    tree = build_fixture()
    rom_path = tree / 'build/adv/shionari.sfc'
    layout = json.loads((tree / 'build/adv/layout.json').read_text())
    g = make_driver('lip_fixture', rom=str(rom_path.relative_to(ROOT)), label_file=tree / 'build/adv/labels.txt',
                    layout=layout, shots=FIX / 'tests')
    assert sha(rom_path.read_bytes()) != sha((B / 'shionari.sfc').read_bytes())
    rom = Rom(rom_path, tree / 'build/adv/labels.txt', layout)
    chk = LipCheck(g, rom)
    g.observers.append(chk)
    rd = Reader(g, chk)
    g.boot_menu()
    g.tap('A')
    g.settle()
    g.move(routes.STATION)
    pages = rd.topic('はなす', 'ゆうべのこと', ['f_shuichi1', 'f_shuichi2', 'f_hatano', 'f_me', 'f_shuichi3'])
    codes = [p['speaker_codes'] for p in pages][0]
    assert codes == [6, 6, 1, 14, 6], codes
    page_checks(pages[0], True)
    page_checks(pages[4], True)
    for p in (pages[2], pages[3]):
        page_checks(p, False)
        assert all(r[11] != 0 for r in p['timeline']), 'the portrait was not on'
    assert pages[2]['actor'] == 1 and pages[3]['actor'] == 14
    other = g.w('mouth_other')
    assert other > 0 and chk.stats['other_frames'] > 0
    rec = dict(rom_sha256=sha(rom_path.read_bytes()), added_lines=FIX_LINES.splitlines(), speaker_codes=codes,
               pages=[{k: v for k, v in p.items() if k != 'timeline'} for p in pages], mouth_other=other,
               note='fixture ROM for the "someone else speaks in front of a portrait" rule; not a release candidate')
    rec['checker'] = chk.stats
    finish(g, rec, trace=False)
    g.trace(FIX / 'trace.json')
    rec['trace'] = 'build/adv-lipfixture/trace.json'
    rec['fixture_record'] = 'build/adv-lipfixture/FIXTURE.json'
    (FIX / 'RESULT.json').write_text(json.dumps(rec, ensure_ascii=False, indent=1) + '\n')
    return rec


SESSIONS = dict(main=session_main, a_save=session_a_save, fixture=session_fixture)


def main(names):
    OUT.mkdir(parents=True, exist_ok=True)
    rom = (B / 'shionari.sfc').read_bytes()
    results, ok = {}, True
    for n in names or SESSIONS:
        try:
            results[n] = dict(ok=True, **SESSIONS[n]())
            print(f'PASS lipsync {n}')
        except Exception as e:
            ok = False
            results[n] = dict(ok=False, error=f'{type(e).__name__}: {e}', trace=traceback.format_exc())
            print(f'FAIL lipsync {n}: {type(e).__name__}: {e}')
            traceback.print_exc()
    out = dict(rom_sha256=sha(rom), core='Snes9x 1.63 libretro (unmodified)',
               scope='Emulator only; pad input only; WRAM/VRAM read only; batteries handed over as images.',
               results=results)
    (OUT / ('RESULTS.json' if not names else 'RESULTS-partial.json')).write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main(sys.argv[1:])
