"""Speech-blip tests of 潮鳴りの密室 on the unmodified Snes9x 1.63 libretro core (pad input only).

The blips are checked in the core's own audio output (native PCM), not only by counters.  Every session
keeps its pad trace (build/adv/traces/<name>.json, also replayed on bsnes by tests/adv/bsnes.py), the
8 KiB battery before and after, the whole session's PCM as a WAV, and a per-frame log (PCM sample
offset, mode, page state, text, speaker, sound, music, blip counters) under build/adv/speech/<name>/.

The expected blips come from a model of the rules (src/adv/voice.inc) run over the ROM's text bytes
consumed in each main-loop iteration (msg_ptr before / after), the speakers' voices of
data/adv/voices.txt and the glyph pauses of the build: a blip when the page body of a speaker draws
a voiced glyph, gap frames after the previous one, not in a pause after punctuation, not in waits,
not with the sound off.  Checked against
  - WRAM: the blips sent (voice_sent, voice_mail = voice and phrase bit) in every modelled iteration;
  - the PCM: every expected blip is found in the audio by correlation with its waveform (the voice's
    BRR sample decoded, at the expected pitch) near its time, over the songs (tools/adv/songs.py: one
    plays under every scene since the music was added) and under effects, separated from negative
    controls; each blip is measured in the twin residual below (length, peak, RMS, DC, largest sample
    step, clipping, the true silence before and after, fundamental and the 2nd/1st partial ratio);
    with the sound off the whole time is exactly 0 (music and echo included).
Screens, battery images, session.wav and frames.json of a session: build/adv/tests/<name>/; results:
build/adv/speech/RESULTS.json; bsnes output: build/adv/speech/speech_cores/; review reel: build/adv/speech/review/.
The null-volume twin ROMs (build/adv-speechtwin/, build/adv-speechfixture-twin/): the same sources with the 7-byte
speech volume table of the driver image at 0 (the ROMs differ in those bytes and the checksum only): played with
the same pad trace, the release ROM's PCM minus the twin's is voice 1 alone -- every expected blip must be in
it (correlation with its waveform, level), and it must be exactly 0 everywhere else (so the effects, the songs and
the timing are the same with the blips).
Sessions:
  speech_main     new game to the ending: the intro (narration, 波多野 without a portrait), the seven
                  speakers at normal speed, A and B fast-forward, menus, every song, the sound off,
                  わたし in the deduction, ending and title; the songs go on under the blips
  speech_d_save   candidate D's battery images continue the same on D and on this ROM; blips after
                  continuing; a record written here is read the same by D
  speech_cores    speech_main's pad trace replayed on a fresh Snes9x (PCM byte-identical) and on bsnes
                  115 (blips at the same frames, pitch / level / length within measured tolerances)
  speech_fixture  NOT the release ROM: build/adv-speechfixture/ (own sources, story diff, SHA-256,
                  labels, layout, trace): a clue chime alone and the same chime under 波多野's blips
                  (in front of 修一's portrait, then わたし): the chime is intact (aligned residual), the
                  blips are the speakers' own voices
  review          a short reel of the seven speakers for listening / viewing (WAV + MP4 with sound)
WRAM, VRAM and the video output are read, never written.

usage: python3 -I tests/adv/speech.py [speech_main] [speech_d_save] [speech_cores] [speech_fixture] [review]
"""
import sys, json, pathlib, hashlib, subprocess, wave, traceback, shutil, math, statistics
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools/adv'))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))
from drive import Driver, ROOT, M_CMD, M_LIST, M_MSG, M_FADE, M_END, fw
from emu import labels as read_labels
import routes
import pcm as P
import voice as voicemod

B = ROOT / 'build/adv'
OUT = B / 'speech'
TRACES = B / 'traces'
D_DIR = ROOT / 'tests/adv/compat/D'
D_SHA = '3cb02d07e3bf2bc3bf470311b4046ffb061ee7f8aa7b844e551b4144f0826b42'
FIX = ROOT / 'build/adv-speechfixture'
TWIN = ROOT / 'build/adv-speechtwin'
BSNES = ROOT / 'tools/vendor/bsnes-63ee22f7af8f' / ('bsnes_libretro.' + ('dylib' if sys.platform == 'darwin' else 'so'))   # built from the pinned source by tools/bootstrap.py
BSNES_SHA = hashlib.sha256(BSNES.read_bytes()).hexdigest() if BSNES.exists() else None   # this machine's build, recorded
sha = lambda b: hashlib.sha256(b).hexdigest()
FPS = 60.0988
QUIET_AFTER_COMMAND = 50          # frames after any driver command (effect, song, mute) not required silent
CORR_MIN = 0.80                   # correlation of an expected blip with its waveform (indoors, clean)
TWIN_CORR_MIN = 0.95              # correlation of every expected blip in the residual release - twin ROM


# ------------------------------------------------------------------ ROM text
class RomText:
    def __init__(self, rom_path, label_path):
        self.data = pathlib.Path(rom_path).read_bytes()
        self.L = read_labels(label_path)

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


# ------------------------------------------------------------------ the session log
class Log:
    """Per frame (after each retro_run): the state the blips depend on and the PCM sample offset."""
    FIELDS = ('mode', 'msg_state', 'msg_text', 'msg_count', 'mouth_actor', 'por_shown', 'scene', 'voice_sent',
              'voice_mail', 'voice_wait', 'voice_pause', 'voice_glyphs', 'sound_on', 'spc_ready', 'music_cur',
              'sfx_count', 'sfx_last', 'snd_sent', 'main_count', 'frame_ready', 'msg_fast')

    def __init__(self, g):
        self.g = g
        self.rows = []
        self.pcm = bytearray()
        g.e.audio_pcm = self.pcm
        g.e.record_audio = True
        self.ptr_addr = g.addr('msg_ptr')
        g.observers.append(self)

    def __call__(self, g):
        r = {k: g.w(k) for k in self.FIELDS}
        r['msg_ptr'] = g.w('msg_ptr') | g.e.ram[self.ptr_addr + 2] << 16
        r['frame'] = g.frame
        r['pcm'] = len(self.pcm) // 4
        r['music'] = 1 if r['sound_on'] and r['spc_ready'] == 0x5A else 0   # a song under everything
        self.rows.append(r)

    def save(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        with wave.open(str(folder / 'session.wav'), 'wb') as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(P.RATE)
            f.writeframes(bytes(self.pcm))
        cols = ['frame', 'pcm'] + list(self.FIELDS) + ['msg_ptr']
        (folder / 'frames.json').write_text(json.dumps(dict(
            columns=cols, pcm='samples per channel of the session WAV after the frame (16-bit stereo, 32040 Hz)',
            rows=[[r[c] for c in cols] for r in self.rows])) + '\n')
        return dict(wav=str((folder / 'session.wav').relative_to(ROOT)), wav_sha256=sha((folder / 'session.wav').read_bytes()),
                    pcm_sha256=sha(bytes(self.pcm)), frames_log=str((folder / 'frames.json').relative_to(ROOT)),
                    samples=len(self.pcm) // 4)


# ------------------------------------------------------------------ the model of the rules
class Voices:
    def __init__(self, layout):
        d = voicemod.parse()
        self.d = d
        self.names = list(d['voices'])
        self.by_speaker = {sid: self.names.index(n) for n, sid in layout['speaker_ids'].items()}
        self.gap = {sid: d['voices'][n]['gap'] for n, sid in layout['speaker_ids'].items()}
        chars = layout['glyph_chars']
        self.voiced = [0 if c in d['silent'] else 1 for c in chars]
        pause = layout['glyph_pause']
        self.pause = [pause.get(c, 0) for c in chars]
        self.chars = chars
        self.templates = {}

    def voice(self, v):
        return self.d['voices'][self.names[v]]

    def expected_f0(self, v, step):
        x = self.voice(v)
        return x['pitch'] * (1 + x['glide'] / 200) * (1 + self.d['contour'][step] / 100)

    def template(self, v, step, rate=P.RATE):
        """The blip as the DSP plays it (decoded BRR, linear resampling at the pitch; amplitude as output)."""
        key = (v, step, rate)
        if key not in self.templates:
            x = self.voice(v)
            dec = voicemod.brr_decode(voicemod.brr_encode(voicemod.synth(x, self.d['timbres'][x['timbre']]['harmonics'])))
            ratio = voicemod.BASE_PITCH * (1 + self.d['contour'][step] / 100) / 4096 * 32000 / rate
            n = int((len(dec) - 1) / ratio)
            out = []
            for i in range(n):
                p = i * ratio
                j = int(p)
                out.append((dec[j] + (dec[j + 1] - dec[j]) * (p - j)) * x['volume'] / 128 * 0.5)
            while out and abs(out[-1]) < 1:
                out.pop()
            self.templates[key] = out
        return self.templates[key]


def model(rows, rom, voices):
    """Run the rules over the iterations; returns (events, stats).  events: one per modelled iteration with
    a blip expected or sent: frame, speaker, voice, step, phrase, sent, mail."""
    st = dict(wait=0, pause=0, phrase=1, step=0)
    out, stats = [], dict(iterations=0, unmodelled=0, glyphs_voiced=0, glyphs_silent=0, punct_pause_frames=0,
                          blips=0, mismatches=[], fast_blips=0, actor_mismatch=0)
    prev = None
    for r in rows:
        if r['frame_ready'] != 1:
            continue
        if prev is None:
            prev = r
            continue
        if r['main_count'] == prev['main_count']:
            continue
        if (r['main_count'] - prev['main_count']) & 0xFFFF != 1:
            stats['unmodelled'] += 1
            st.update(wait=r['voice_wait'], pause=r['voice_pause'])
            prev = r
            continue
        stats['iterations'] += 1
        # glyphs of this iteration
        codes = []
        if r['mode'] == M_MSG or prev['mode'] == M_MSG:
            tid = r['msg_text']
            p1 = rom.off(r['msg_ptr'])
            same = tid == prev['msg_text'] and r['msg_count'] == prev['msg_count']
            p0 = rom.off(prev['msg_ptr']) if same else rom.text_start(tid)
            if p0 <= p1 <= p0 + 200:
                actor = rom.actor_at(tid, p0)
                o = p0
                while o < p1:
                    c = rom.word(o)
                    o += 2
                    if c == 0xFFFC:
                        o += 2
                    elif c == 0xFFFD:
                        actor = 0
                    elif c & 0xFFF0 == 0xFFE0:
                        actor = c & 0xF
                        st['pause'] = 0
                        codes.append(('speaker', actor))
                    elif c < 0xFFE0:
                        codes.append(('glyph', c, actor))
        glyphs = 0
        for c in codes:
            if c[0] != 'glyph':
                continue
            g, actor = c[1], c[2]
            st['pause'] = max(st['pause'], voices.pause[g])
            if g != 0 and actor and voices.voiced[g]:
                glyphs += 1
                stats['glyphs_voiced'] += 1
            elif actor:
                stats['glyphs_silent'] += 1
        exp = None
        if st['wait']:
            st['wait'] -= 1
        if r['mode'] != M_MSG or r['msg_state'] != 0 or r['mouth_actor'] == 0:
            st.update(pause=0, phrase=1)
        elif st['pause']:
            st['pause'] -= 1
            st['phrase'] = 1
            stats['punct_pause_frames'] += 1
        elif glyphs and st['wait'] == 0 and r['sound_on'] and r['spc_ready'] == 0x5A:
            sid = r['mouth_actor']
            v = voices.by_speaker[sid]
            if st['phrase']:
                st['step'] = 0
            exp = dict(speaker=sid, voice=v, step=st['step'], phrase=st['phrase'], mail=v | (0x80 if st['phrase'] else 0))
            st['step'] = st['step'] + 1 if st['step'] < 7 else 4
            st['wait'] = voices.gap[sid]
            st['phrase'] = 0
        sent = (r['voice_sent'] - prev['voice_sent']) & 0xFFFF
        if (1 if exp else 0) != sent or (exp and exp['mail'] != r['voice_mail']):
            stats['mismatches'].append(dict(frame=r['frame'], expected=exp, sent=sent, mail=r['voice_mail']))
        if exp:
            stats['blips'] += 1
            stats['fast_blips'] += 1 if r['msg_fast'] else 0
            exp.update(frame=r['frame'], fast=r['msg_fast'], music=r['music'], sound_on=r['sound_on'],
                       text=r['msg_text'], portrait=r['por_shown'])
            out.append(exp)
        prev = r
    return out, stats


# ------------------------------------------------------------------ PCM checks
def frame_index(rows):
    return {r['frame']: i for i, r in enumerate(rows)}


def ncorr(x, t, at):
    n = len(t)
    seg = x[at:at + n]
    if len(seg) < n:
        return 0.0
    num = sum(a * b for a, b in zip(seg, t))
    den = math.sqrt(sum(a * a for a in seg) * sum(b * b for b in t)) or 1
    return num / den


def best_corr(x, t, lo, hi, step=2):
    best = (-1.0, lo)
    for at in range(max(0, lo), hi, step):
        c = ncorr(x, t, at)
        if c > best[0]:
            best = (c, at)
    c, at = best
    for a2 in range(at - step + 1, at + step):
        if a2 >= 0:
            c2 = ncorr(x, t, a2)
            if c2 > c:
                c, at = c2, a2
    return c, at


def goertzel(x, a, b, f, rate=P.RATE):
    w = 2 * math.pi * f / rate
    cw = 2 * math.cos(w)
    s1 = s2 = 0.0
    for v in x[a:b]:
        s1, s2 = v + cw * s1 - s2, s1
    return math.sqrt(max(0.0, s1 * s1 + s2 * s2 - cw * s1 * s2)) / max(1, b - a)


def check_pcm(rows, x, events, voices):
    """The expected blips in the PCM; the silence; returns the measurements."""
    fi = frame_index(rows)
    start_of = lambda f: rows[fi[f] - 1]['pcm'] if fi.get(f, 0) > 0 else 0
    # the frames after a driver command (effect, song, mute / unmute) and under the music: not required to be silent
    noisy, last_cmd = set(), -10 ** 9
    for i, r in enumerate(rows):
        if i and r['snd_sent'] != rows[i - 1]['snd_sent']:
            last_cmd = r['frame']
        if r['frame'] - last_cmd <= QUIET_AFTER_COMMAND or r['music']:
            noisy.add(r['frame'])
    found, misses, clean, latency = [], [], [], []
    blip_frames = set()
    for e in events:
        t = voices.template(e['voice'], e['step'])
        lo = start_of(e['frame'] - 1)
        hi = rows[fi[e['frame']] + 1]['pcm'] if fi[e['frame']] + 1 < len(rows) else len(x)
        c, at = best_corr(x, t, lo - 200, hi)
        e['corr'] = round(c, 3)
        e['onset'] = at
        e['latency_samples'] = at - start_of(e['frame'])
        for k in range(e['frame'] - 1, e['frame'] + 4):
            blip_frames.add(k)
        env = 'music' if e['music'] else 'effect' if e['frame'] in noisy else 'clean'
        e['env'] = env
        if env == 'clean' and c < CORR_MIN:
            misses.append(dict(frame=e['frame'], corr=e['corr'], env=env, speaker=e['speaker']))
        found.append(e)
        latency.append(e['latency_samples'])
    # negative controls in the music: the same search (same width, the scene's voices) where no blip can sound
    control, far = [], set()
    for e in events:
        far.update(range(e['frame'] - 6, e['frame'] + 8))
    music_ev = [e for e in events if e['music']]
    music_frames = [r['frame'] for i, r in enumerate(rows) if i > 2 and r['music'] and r['frame'] not in far
                   and r['frame'] not in noisy_cmd(rows) and i + 1 < len(rows)]
    for k, f in enumerate(music_frames[::7][:len(music_ev)]):
        e = music_ev[k % len(music_ev)]
        t = voices.template(e['voice'], e['step'])
        c, _ = best_corr(x, t, start_of(f - 1) - 200, rows[fi[f] + 1]['pcm'])
        control.append(round(c, 3))
    # clean blips: the measurements in the raw PCM
    clean = measure(x, [e for e in found if e['env'] == 'clean' and e['corr'] >= CORR_MIN], 'onset', voices)
    # silence: frames where nothing may sound are exactly 0
    silent_frames, loud = 0, []
    cats = dict(name_or_narration=0, page_wait=0, menu=0, punctuation_pause=0, fast_after_blips=0, sound_off=0)
    for i, r in enumerate(rows):
        if i == 0 or r['frame'] in noisy or r['frame'] in blip_frames:
            continue
        if r['spc_ready'] != 0x5A:
            continue
        a, b = rows[i - 1]['pcm'], r['pcm']
        seg = x[a:b]
        silent_frames += 1
        if any(seg):
            loud.append(dict(frame=r['frame'], peak=max(abs(v) for v in seg), mode=r['mode'], state=r['msg_state'],
                             actor=r['mouth_actor']))
        if not r['sound_on']:
            cats['sound_off'] += 1
        elif r['mode'] == M_MSG and r['msg_state']:
            cats['page_wait'] += 1
        elif r['mode'] == M_MSG and not r['mouth_actor']:
            cats['name_or_narration'] += 1
        elif r['mode'] == M_MSG and r['voice_pause']:
            cats['punctuation_pause'] += 1
        elif r['mode'] == M_MSG and r['msg_fast']:
            cats['fast_after_blips'] += 1
        elif r['mode'] != M_MSG:
            cats['menu'] += 1
    return dict(found=found, misses=misses, control=control, clean=clean, latency=latency,
                silent_frames_checked=silent_frames, silent_by_kind=cats, loud=loud[:20], loud_count=len(loud))


def measure(x, events, key, voices, rate=P.RATE):
    """Each blip's run of non-zero samples around events[key] (an onset sample): length, peak, RMS, DC, the
    largest step, the first / last sample, the true silence before (160 samples of 0), pitch, 2nd/1st partial."""
    out = []
    segs = P.segments(x, thr=0)                     # runs of non-zero samples (gaps under 3 ms merged)
    starts = [a for a, _ in segs]
    import bisect
    for e in events:
        i = bisect.bisect_right(starts, e[key] + 40) - 1
        if i < 0 or not segs[i][0] <= e[key] + 40 < segs[i][1]:
            continue
        a, b = segs[i]
        pre = x[max(0, a - 160):a]
        d = P.describe(x, a, b, thr=0, rate=rate)
        f = d['f0'] or voices.expected_f0(e['voice'], e['step'])
        h1, h2 = goertzel(x, a, b, f, rate), goertzel(x, a, b, 2 * f, rate)
        d.update(frame=e['frame'], speaker=e['speaker'], voice=e['voice'], step=e['step'], env=e['env'],
                 expected_f0=round(voices.expected_f0(e['voice'], e['step']), 1),
                 silence_before=len(pre) == 160 and all(v == 0 for v in pre),
                 nonzero_ms=round((b - a) * 1000 / rate, 2), first_sample=abs(x[a]), last_sample=abs(x[b - 1]),
                 h2_h1=round(h2 / h1, 3) if h1 else None)
        out.append(d)
    return out


def assert_shape(meas, what):
    for d in meas:
        assert d['silence_before'], (what, 'no true silence before a blip', d)
        assert d['clipped'] == 0 and d['peak'] < 32767, (what, 'clipped', d)
        assert abs(d['dc']) < 0.02, (what, 'DC offset', d)
        assert d['max_step_ratio'] < 0.4, (what, 'a sample step too large for the blip', d)
        assert d['first_sample'] <= 0.03 * d['peak'], (what, 'the blip starts with a step', d)
        assert d['last_sample'] <= 0.03 * d['peak'], (what, 'the blip ends with a step', d)
        assert 15 <= d['nonzero_ms'] <= 40, (what, 'blip length', d)
        assert d['f0'] and abs(d['f0'] / d['expected_f0'] - 1) < 0.05, (what, 'pitch', d)


_NOISY = {}


def noisy_cmd(rows):
    """Frames within QUIET_AFTER_COMMAND frames after a driver command (effects included)."""
    key = id(rows)
    if key not in _NOISY:
        out, last = set(), -10 ** 9
        for i, r in enumerate(rows):
            if i and r['snd_sent'] != rows[i - 1]['snd_sent']:
                last = r['frame']
            if r['frame'] - last <= QUIET_AFTER_COMMAND:
                out.add(r['frame'])
        _NOISY[key] = out
    return _NOISY[key]


def summarize(events, meas, voices):
    out = {}
    for v, name in enumerate(voices.names):
        cl = [d for d in meas if d['voice'] == v]
        ev = [e for e in events if e['voice'] == v]
        if not ev:
            continue
        f0s = [d['f0'] / d['expected_f0'] for d in cl if d['f0']]
        out[name] = dict(blips=len(ev), clean_measured=len(cl), under_music=sum(1 for e in ev if e['music']),
                         under_effect=sum(1 for e in ev if e['env'] == 'effect'),
                         corr_min=min(e.get('twin_corr', e['corr']) for e in ev),
                         f0_median=round(statistics.median([d['f0'] for d in cl if d['f0']]), 1) if f0s else None,
                         f0_vs_expected=[round(min(f0s), 3), round(max(f0s), 3)] if f0s else None,
                         nonzero_ms=[min(d['nonzero_ms'] for d in cl), max(d['nonzero_ms'] for d in cl)] if cl else None,
                         peak=[min(d['peak'] for d in cl), max(d['peak'] for d in cl)] if cl else None,
                         rms_median=round(statistics.median([d['rms'] for d in cl]), 1) if cl else None,
                         h2_h1_median=round(statistics.median([d['h2_h1'] for d in cl if d['h2_h1'] is not None]), 3) if cl else None,
                         timbre=voices.voice(v)['timbre'])
    return out


def assert_pcm(pcm, per_voice, need_voices):
    """need_voices: speakers that must have blips measured in the raw PCM without music (none since the
    songs: every blip sounds over music, and is measured in the twin residual instead)."""
    assert not pcm['misses'], ('expected blips not found in the PCM', pcm['misses'][:5])
    assert pcm['loud_count'] == 0, ('sound where nothing may sound', pcm['loud'][:5])
    assert_shape(pcm['clean'], 'raw PCM')
    for n in need_voices:
        assert n in per_voice and per_voice[n]['clean_measured'] >= 3, ('too few measured blips of', n)


def assert_speakers(per_voice, voices):
    """Different speakers: the pitches keep the data's order and steps; the timbres' 2nd partial order."""
    meas = {n: v for n, v in per_voice.items() if v['f0_median']}
    names = sorted(meas, key=lambda n: voices.d['voices'][n]['pitch'])
    for a, b in zip(names, names[1:]):
        assert meas[b]['f0_median'] > meas[a]['f0_median'] * 1.03, ('pitches too close', a, b)
    by_timbre = {}
    for n, v in meas.items():
        by_timbre.setdefault(v['timbre'], []).append(v['h2_h1_median'])
    harm = {t: statistics.median(v) for t, v in by_timbre.items()}
    want = sorted(voices.d['timbres'], key=lambda t: (voices.d['timbres'][t]['harmonics'] + [0])[1])
    got = [t for t in want if t in harm]
    for a, b in zip(got, got[1:]):
        assert harm[b] > harm[a], ('timbres do not differ in the 2nd partial', harm)
    return dict(pitch_order=names, h2_h1_by_timbre={t: round(h, 3) for t, h in harm.items()})


# ------------------------------------------------------------------ driving
def new(name, rom=None, sram=None, label_file=None, layout=None):
    g = Driver(rom=rom or 'build/adv/shionari.sfc', sram=sram, label_file=label_file)
    if layout is not None:
        g.layout = layout
        g.text_ids = {}
        for i, t in enumerate(layout['texts']):
            if t['kind'] == 'label':
                g.text_ids.setdefault(t['text'], i)
    g.name = name
    g.shots = B / 'tests' / name                    # (tests/adv/bsnes.py compares the screens found here)
    if g.shots.exists():
        shutil.rmtree(g.shots)
    g.shots.mkdir(parents=True)
    return g


def check_hw(g):
    assert g.w('vblank_overrun_count') == 0, 'NMI work ran past the V-blank'
    assert 225 <= g.w('nmi_end_line_max') <= 258, ('NMI end line', g.w('nmi_end_line_max'))
    assert g.w('dma_deferred') == 0, 'a DMA job had to wait'
    assert g.w('text_clip') == 0, 'a glyph crossed its box'


def hw(g):
    return dict(frames=g.frame, lag_count=g.w('lag_count'), vblank_overrun_count=g.w('vblank_overrun_count'),
                nmi_end_line_max=g.w('nmi_end_line_max'), dma_bytes_max=g.w('dma_bytes_max'),
                dma_deferred=g.w('dma_deferred'), text_clip=g.w('text_clip'), voice_sent=g.w('voice_sent'),
                snd_sent=g.w('snd_sent'))


def finish(g, log, rec, trace_path):
    check_hw(g)
    rec.update(hw(g))
    rec['session'] = log.save(g.shots)
    g.save_battery(g.shots)
    rec['input_sram_sha256'] = g.sram_files['initial.srm']['sha256']
    rec['output_sram_sha256'] = g.sram_files['final.srm']['sha256']
    g.trace(trace_path)
    rec['trace'] = str(trace_path.relative_to(ROOT))
    g.close()


def wait_typing(g, limit=900):
    for _ in range(limit):
        if g.mode() == M_MSG and g.w('msg_state') == 0:
            return
        g.run(1)
    raise AssertionError('no message started')


def read_page(g, fast=None, fast_after=0, hold_wait=24):
    wait_typing(g)
    body, pressed = None, False
    while g.mode() == M_MSG and g.w('msg_state') == 0:
        btn = ()
        if body is not None and fast and not pressed and g.frame - body >= fast_after:
            btn, pressed = (fast,), True
        g.run(1, btn)
        if body is None and g.w('mouth_actor'):
            body = g.frame
    last = g.w('msg_state') == 2
    g.run(hold_wait)
    return last


def read_pages(g, n=99, shots=None, **kw):
    for i in range(n):
        last = read_page(g, **(kw if i == 0 else {}))
        if shots and i == 0:
            g.shot(g.shots / f'{shots}.png')
        g.run(2, ('A',))
        if last:
            break


def choose(g, cmd, label):
    if g.mode() != M_LIST or g.w('cmd_active') != ['はなす', 'しらべる', 'みせる', 'いどう', 'てちょう'].index(cmd):
        g.cmd(cmd)
    want = g.list_texts().index(g.text_ids[fw(label)])
    while g.w('list_sel') != want:
        g.tap('DOWN' if want > g.w('list_sel') else 'UP')
    g.quiet()                                 # (a key in a redraw's lag frame is not read)
    g.run(2, ('A',))


def topic(g, cmd, label, pages=99, shots=None, **kw):
    """はなす / みせる / しらべる -> label; pages at normal speed (kw: fast='A'/'B', fast_after on the 1st)."""
    choose(g, cmd, label)
    read_pages(g, pages, shots=shots, **kw)
    g.settle()
    g.quiet()


# ------------------------------------------------------------------ sessions
def session_main():
    g = new('speech_main')
    log = Log(g)
    voices = Voices(g.layout)
    rom = RomText(B / 'shionari.sfc', B / 'labels.txt')
    rec = {}
    g.boot_menu()
    assert g.w('spc_ready') == 0x5A
    g.run(2, ('A',))
    read_pages(g)                                       # intro: narration, 波多野 without a portrait
    g.settle()
    g.quiet()
    g.shot(g.shots / 'warehouse.png')
    topic(g, 'はなす', '検視', shots='hatano_page1', fast='A', fast_after=200)   # normal speed (no press)
    topic(g, 'はなす', '検視', fast='A', fast_after=6)                          # A fast-forward
    topic(g, 'はなす', '検視', fast='B', fast_after=1)                          # B fast-forward at once
    for k in ('DOWN', 'DOWN', 'UP', 'UP'):                                      # menu: cursor sounds only
        g.tap(k, 2, 20)
    g.to_cmd()
    g.look('柱時計', '振り子の窓', '金庫', 'メモ', '荷揚げ口', '鉄梯子')
    topic(g, 'しらべる', '鍵束')                                                  # 波多野 without a portrait
    g.to_cmd()
    g.move(routes.STATION)
    topic(g, 'はなす', 'ゆうべのこと', shots='shuichi_page1')
    g.to_cmd()
    g.move(routes.SIGNAL)
    g.look('掲示板', '潮見表', '回覧板')
    topic(g, 'はなす', 'ゆうべのこと', shots='koga_page1')
    topic(g, 'はなす', '灯台')
    g.to_cmd()
    g.move(routes.PIER)
    g.run(240)                                                                  # the sea song alone
    topic(g, 'はなす', 'ゆうべのこと', shots='tatsumi_page1')
    g.to_cmd()
    g.run(240)
    g.move(routes.LIGHTHOUSE)
    topic(g, 'はなす', 'ゆうべのこと', shots='ookouchi_page1')
    g.to_cmd()
    g.move(routes.CAFE)
    topic(g, 'はなす', 'ゆうべのこと', shots='yukiko_page1')
    g.to_cmd()
    g.note('おと：あり')                                                         # sound off
    g.to_cmd()
    assert g.w('sound_on') == 0
    g.run(60)
    off0 = g.w('voice_sent')
    topic(g, 'はなす', '辰巳のようす')
    g.to_cmd()
    rec['sound_off_blips_sent'] = (g.w('voice_sent') - off0) & 0xFFFF
    assert rec['sound_off_blips_sent'] == 0
    g.note('おと：なし')
    g.to_cmd()
    assert g.w('sound_on') == 1
    g.move(routes.WAREHOUSE)
    routes.standard(g)                                                          # the rest at test speed
    g.to_cmd()
    choose(g, 'てちょう', 'すいりする')
    read_pages(g, 4, shots='me_deduce')                                         # わたし and 波多野
    g.settle()
    for ans in routes.ANSWERS:
        g.pick(g.layout['clue_names'][ans] if ans in g.layout['clue_names'] else ans)
    assert g.mode() == M_END
    g.quiet()
    g.shot(g.shots / 'ending.png')
    g.ending_to_title()
    g.run(120)
    g.shot(g.shots / 'title_after.png')
    rows = log.rows
    x = P.mono(bytes(log.pcm))[0]
    events, mstats = model(rows, rom, voices)
    finish(g, log, rec, TRACES / 'speech_main.json')
    assert not mstats['mismatches'], ('WRAM blips differ from the model', mstats['mismatches'][:5])
    pcm = check_pcm(rows, x, events, voices)
    per_voice_raw = summarize(events, pcm['clean'], voices)
    rec['model'] = {k: v for k, v in mstats.items() if k != 'mismatches'}
    rec['per_voice_raw_pcm'] = per_voice_raw
    rec['silence'] = dict(frames_checked=pcm['silent_frames_checked'], by_kind=pcm['silent_by_kind'], loud=pcm['loud_count'])
    rec['latency_samples'] = [min(pcm['latency']), max(pcm['latency'])]
    under = [e for e in events if e['music']]
    ctl = sorted(pcm['control'])
    auc = sum(sum(1 for c in ctl if c < e['corr']) + 0.5 * sum(1 for c in ctl if c == e['corr']) for e in under) / max(1, len(under) * len(ctl))
    rec['music_blips_raw_pcm'] = dict(
        note='blips over the music correlated with their waveform in the raw PCM, against negative controls (the same '
             'search where no blip can sound): a statistical separation only; each blip is proven by the twin residual',
        count=len(under), corr_min=min(e['corr'] for e in under), corr_median=round(statistics.median(e['corr'] for e in under), 3),
        controls=len(ctl), control_median=round(statistics.median(ctl), 3) if ctl else None,
        control_max=max(ctl) if ctl else None, auc=round(auc, 3))
    # the twin control ROM with the same pad trace: release minus twin = voice 1
    build_twin()
    trows, tx, tpcm = twin_replay(TRACES / 'speech_main.json')
    with wave.open(str(TWIN / 'speech_main.wav'), 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(P.RATE)
        f.writeframes(tpcm)
    res, R = residual_check(rows, x, trows, tx, events, voices)
    res['twin_wav'] = 'build/adv-speechtwin/speech_main.wav'
    res['twin_wav_sha256'] = sha((TWIN / 'speech_main.wav').read_bytes())
    res['twin_rom_sha256'] = sha((TWIN / 'rom.sfc').read_bytes())
    rec['twin_residual'] = res
    resid = measure(R, events, 'twin_onset', voices)
    per_voice = summarize(events, resid, voices)
    rec['per_voice'] = per_voice
    rec['per_voice_note'] = ('measured in the residual (release - null-volume twin): voice 1 alone, also in the '
                             'music and under effects; per_voice_raw_pcm: blips without music or effects in the raw output '
                             '(none: a song plays under every talk)')
    rec['blip_frames'] = [dict(frame=e['frame'], speaker=e['speaker'], step=e['step'], phrase=e['phrase'],
                               corr=e['corr'], twin_corr=e['twin_corr'], env=e['env'], onset_sample=e['onset'],
                               twin_onset_sample=e['twin_onset']) for e in events]
    rec['clean_blips'] = pcm['clean']
    rec['residual_blips'] = resid
    (g.shots / 'blips.json').write_text(json.dumps(dict(events=events, clean=pcm['clean'], residual=resid,
                                                        misses=pcm['misses'], control=pcm['control'], loud=pcm['loud']),
                                                   ensure_ascii=False) + '\n')
    assert len(ctl) >= 30 and auc >= 0.6, rec['music_blips_raw_pcm']
    assert_pcm(pcm, per_voice_raw, [])                                         # (every blip is over a song)
    assert_shape(resid, 'residual')
    assert len(resid) >= 0.95 * len(events), ('blips not measurable in the residual', len(resid), len(events))
    for n in voices.names:
        assert per_voice[n]['clean_measured'] >= 5, ('too few blips of', n)
    rec['speakers'] = assert_speakers(per_voice, voices)
    assert res['corr_min'] >= TWIN_CORR_MIN, ('a blip is not in the residual', res)
    assert 0.85 <= res['peak_ratio'][0] and res['peak_ratio'][1] <= 1.15, ('blip level', res)
    assert res['nonzero_outside'] == 0, ('the release ROM differs from the twin outside the blips', res)
    assert res['blip_to_background_db_250hz']['p10'] >= 0.0, ('blips buried in the music', res['blip_to_background_db'],
                                                               res['blip_to_background_db_250hz'])
    rec['music_continuity'] = music_continuity(rows, x, events)
    rec['fast'] = fast_pages(events, rows)
    return rec


def music_continuity(rows, x, events):
    """The song goes on under the talks, 10 dB down (ducked while a message is open): 100 ms windows without
    blips (and 90 frames away from a change of song), during the talks and on the menus (no message for
    the 20 frames before: the duck has come back), in each stretch with the sound on."""
    blip_at = {e['frame'] for e in events}
    changed, last = set(), None
    for r in rows:
        if r['music_cur'] != last:
            changed.update(range(r['frame'], r['frame'] + 90))
            last = r['music_cur']
    out = []
    i = 0
    while i < len(rows):
        if not rows[i]['music']:
            i += 1
            continue
        j = i
        while j < len(rows) and rows[j]['music']:
            j += 1
        talk = [r for r in rows[i:j] if r['mode'] == M_MSG and r['mouth_actor'] and r['msg_state'] == 0]
        win = []
        for k in range(i + 30, j - 6, 6):
            fr = rows[k]['frame']
            if fr in changed or any(f in blip_at for f in range(fr - 3, fr + 7)):
                continue
            a, b = rows[k - 1]['pcm'], rows[k + 5]['pcm']
            seg = x[a:b]
            kind = 'talk' if rows[k]['mode'] == M_MSG and rows[k]['mouth_actor'] != 0 else \
                   'menu' if all(r['mode'] != M_MSG for r in rows[k - 20:k + 6]) else 'other'
            win.append((fr, math.sqrt(sum(v * v for v in seg) / max(1, len(seg))), kind))
        if win and talk:
            during = [w for _, w, t in win if t == 'talk']
            other = [w for _, w, t in win if t == 'menu']
            out.append(dict(first_frame=rows[i]['frame'], last_frame=rows[j - 1]['frame'], talk_frames=len(talk),
                            windows=len(win), rms_min=round(min(w for _, w, _ in win), 1),
                            rms_during_talk_median=round(statistics.median(during), 1) if during else None,
                            rms_menu_median=round(statistics.median(other), 1) if other else None))
            assert min(w for _, w, _ in win) > 60, ('the music stopped', out[-1])
            if during and other:
                ratio = statistics.median(during) / statistics.median(other)
                out[-1]['ratio'] = round(ratio, 2)
                assert 0.18 < ratio < 0.6, ('the music is not ducked (10 dB) under the talk', out[-1])
        i = j
    assert len(out) >= 2, 'no stretch of music with a talk'
    return out


def fast_pages(events, rows):
    """Fast-forwarded typing: blips at least gap frames apart, none after the typing ends."""
    fast = [e for e in events if e['fast']]
    gaps = []
    by_text = {}
    for e in fast:
        by_text.setdefault((e['text']), []).append(e['frame'])
    for fr in by_text.values():
        gaps += [b - a for a, b in zip(fr, fr[1:])]
    fast_frames = sum(1 for r in rows if r['mode'] == M_MSG and r['msg_state'] == 0 and r['msg_fast'] and r['mouth_actor'])
    assert all(gp >= 4 for gp in gaps), ('fast-forward blips too close', gaps)
    return dict(fast_blips=len(fast), min_gap_frames=min(gaps) if gaps else None, spoken_fast_frames=fast_frames)


def session_d_save():
    import lipsync
    rec = {}
    d_rom, d_labels = D_DIR / 'shionari.sfc', D_DIR / 'labels.txt'
    assert sha(d_rom.read_bytes()) == D_SHA
    for src in ('save_a', 'save_b'):
        sram = (D_DIR / 'tests' / src / 'final.srm').read_bytes()
        ga = lipsync.continue_on(d_rom, d_labels, sram, 'speech_tmp_d')
        sa = lipsync.state(ga)
        ga.close()
        gb = lipsync.continue_on(B / 'shionari.sfc', None, sram, 'speech_tmp_e')
        sb = lipsync.state(gb)
        gb.close()
        assert sa == sb, ('candidate D and this ROM continue differently', src, sa, sb)
        rec[src] = dict(sram_sha256=sha(sram), state=sa, same=True)
    sram = (D_DIR / 'tests' / 'save_a' / 'final.srm').read_bytes()
    g = new('speech_d_save', sram=sram)
    log = Log(g)
    voices = Voices(g.layout)
    rom = RomText(B / 'shionari.sfc', B / 'labels.txt')
    g.boot_menu()
    assert g.w('save_status') == 2 and g.w('list_sel') == 1
    g.tap('A')
    g.settle()
    assert g.mode() == M_CMD and g.w('scene') == 5
    g.quiet()
    topic(g, 'はなす', '発見のこと')
    g.to_cmd()
    g.note('きろくする')
    assert g.w('save_ok') == 1
    g.to_cmd()
    st = lipsync.state(g)
    rows = log.rows
    x = P.mono(bytes(log.pcm))[0]
    finish(g, log, rec, TRACES / 'speech_d_save.json')
    events, mstats = model(rows, rom, voices)
    assert not mstats['mismatches'], mstats['mismatches'][:5]
    pcm = check_pcm(rows, x, events, voices)
    assert not pcm['misses'] and pcm['loud_count'] == 0, (pcm['misses'][:3], pcm['loud'][:3])
    talk = [e for e in events if e['speaker'] == 6]
    assert len(talk) >= 5, 'no blips after continuing'
    rec['after_continue'] = dict(blips=len(talk), corr_min=min(e['corr'] for e in talk))
    new_sram = (g.shots / 'final.srm').read_bytes()
    ga = lipsync.continue_on(d_rom, d_labels, new_sram, 'speech_tmp_d')
    sa = lipsync.state(ga)
    ga.close()
    gb = lipsync.continue_on(B / 'shionari.sfc', None, new_sram, 'speech_tmp_e')
    sb = lipsync.state(gb)
    gb.close()
    assert sa == sb, ('candidate D and this ROM read this record differently', sa, sb)
    for k in ('scene', 'actions', 'wrong_count', 'sound_on', 'flags'):
        assert sa[k] == st[k], ('the record does not hold the state at saving', k)
    rec['e_record_on_d'] = dict(sram_sha256=sha(new_sram), same_on_d_and_e=True)
    for d in ('speech_tmp_d', 'speech_tmp_e'):
        shutil.rmtree(lipsync.SHOTS / d, ignore_errors=True)
    return rec


def replay_pcm_snes9x(trace):
    import emu
    g = emu.Game(sram=(ROOT / trace['input_sram']['path']).read_bytes())
    pcm = bytearray()
    g.e.audio_pcm = pcm
    g.e.record_audio = True
    for m in trace['masks']:
        g.e.mask = m
        g.e.lib.retro_run()
    g.close()
    return bytes(pcm)


def bsnes_run(rom, trace, out, tag):
    """The pad trace on bsnes 115 in a process of its own (a core loaded twice in one process keeps state):
    the PCM (stereo bytes), the PCM sample offset after each frame and the sample rate."""
    work = out / tag
    subprocess.run([sys.executable, '-I', str(pathlib.Path(__file__).resolve()), '_bsnes_run', str(rom),
                    json.dumps(trace['masks']), str(ROOT / trace['input_sram']['path']), str(work)], check=True)
    raw = (work / 'pcm.raw').read_bytes()
    meta = json.loads((work / 'meta.json').read_text())
    shutil.rmtree(work)
    return raw, meta['ends'], meta['rate']


def _bsnes_child(rom, masks, sram, work):
    from host_libretro_replay import Frontend
    work = pathlib.Path(work)
    work.mkdir(parents=True)
    trace = dict(masks=json.loads(masks), input_sram=dict(path=str(pathlib.Path(sram).relative_to(ROOT))))
    rom = pathlib.Path(rom)
    shutil.copy2(rom, work / 'shionari.sfc')
    (work / 'shionari.srm').write_bytes((ROOT / trace['input_sram']['path']).read_bytes())
    e = Frontend(BSNES, work / 'shionari.sfc', work)
    path = work / 'pcm.raw'
    f = path.open('wb')
    e.audio_file = f
    ends = []
    try:
        for m in trace['masks']:
            e.step(m)
            ends.append(e.audio_samples // 2)
    finally:
        e.close()
        f.close()
    (work / 'meta.json').write_text(json.dumps(dict(ends=ends, rate=e.av['sample_rate'])))
    (work / 'shionari.sfc').unlink()


def session_cores():
    """speech_main's trace on a fresh Snes9x (byte-identical PCM) and on bsnes 115: the release and the twin
    ROM, the residual = the expected blips and nothing else; clean blips compared with Snes9x."""
    trace = json.loads((TRACES / 'speech_main.json').read_text())
    assert trace['rom_sha256'] == sha((B / 'shionari.sfc').read_bytes())
    main = json.loads((B / 'tests' / 'speech_main' / 'blips.json').read_text())
    with wave.open(str(B / 'tests' / 'speech_main' / 'session.wav')) as f:
        orig = f.readframes(f.getnframes())
    rec = {}
    again = replay_pcm_snes9x(trace)
    rec['snes9x_replay'] = dict(bytes=len(again), identical=again == orig, sha256=sha(again))
    assert again == orig, 'the same trace gave different PCM on Snes9x'
    out = OUT / 'speech_cores'
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    ea, ends, rate = bsnes_run(B / 'shionari.sfc', trace, out, 'release')
    ta, tends, trate = bsnes_run(TWIN / 'rom.sfc', trace, out, 'twin')
    assert rate == trate and abs(len(ea) - len(ta)) <= 4096, (rate, trate, len(ea), len(ta))
    boundary_shift = max(abs(a - b) for a, b in zip(ends, tends))      # samples handed over per frame vary
    for tag, raw in (('release', ea), ('twin', ta)):
        with wave.open(str(out / f'bsnes-{tag}.wav'), 'wb') as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(round(rate))
            f.writeframes(raw)
    xb, tb = P.mono(ea)[0], P.mono(ta)[0]
    n = min(len(xb), len(tb))
    R = [a - b for a, b in zip(xb[:n], tb[:n])]
    voices = Voices(json.loads((B / 'layout.json').read_text()))
    mask = bytearray(len(R))
    clean = {d['frame']: d for d in main['clean']}
    worst = dict(corr=1.0, f0=0.0, peak=0.0, onset_ms=0.0)
    diffs = []
    for ev in main['events']:
        t = voices.template(ev['voice'], ev['step'], rate=rate)
        k = ev['frame'] - 1
        lo, hi = (ends[k - 2] if k >= 2 else 0) - 200, ends[k + 1] if k + 1 < len(ends) else len(R)
        c, at = best_corr(R, t, lo, hi)
        worst['corr'] = min(worst['corr'], c)
        for i in range(max(0, at - 32), min(len(R), at + len(t) + 96)):
            mask[i] = 1
        if ev['frame'] in clean:
            d = clean[ev['frame']]
            run = next(((a + at - 64, b + at - 64) for a, b in P.segments(xb[at - 64:at + 2000], thr=0)), None)
            if run is None:
                continue
            a, b = run
            db = P.describe(xb, a, b, thr=0, rate=rate)
            df = abs(db['f0'] / d['f0'] - 1) if db['f0'] and d['f0'] else 1
            dp = abs(db['peak'] / d['peak'] - 1)
            ob = (a - (ends[k - 1] if k >= 1 else 0)) * 1000 / rate
            os_ = (d['onset'] - frame_start_s9x(ev['frame'])) * 1000 / P.RATE
            worst.update(f0=max(worst['f0'], df), peak=max(worst['peak'], dp), onset_ms=max(worst['onset_ms'], abs(ob - os_)))
            diffs.append(dict(frame=ev['frame'], f0=[d['f0'], db['f0']], peak=[d['peak'], db['peak']],
                              nonzero_ms=[d['nonzero_ms'], round((b - a) * 1000 / rate, 2)],
                              onset_in_frame_ms=[round(os_, 2), round(ob, 2)]))
    outside = [v for v, m in zip(R, mask) if not m]
    rec['bsnes'] = dict(sample_rate=rate, frames=len(ends), samples=len(xb), compared_samples=n,
                        frame_boundary_shift_max_samples=boundary_shift,
                        release_wav_sha256=sha((out / 'bsnes-release.wav').read_bytes()),
                        twin_wav_sha256=sha((out / 'bsnes-twin.wav').read_bytes()),
                        blips=len(main['events']), clean_compared=len(diffs),
                        residual_corr_min=round(worst['corr'], 4),
                        residual_nonzero_outside=sum(1 for v in outside if v),
                        residual_max_abs_outside=max((abs(v) for v in outside), default=0),
                        worst_vs_snes9x={k: round(v, 4) for k, v in worst.items() if k != 'corr'},
                        tolerances=dict(f0=0.02, peak=0.10, onset_ms=17.0))
    (out / 'compare.json').write_text(json.dumps(diffs) + '\n')
    assert worst['corr'] >= TWIN_CORR_MIN, rec['bsnes']
    assert rec['bsnes']['residual_nonzero_outside'] == 0, rec['bsnes']
    assert worst['f0'] <= 0.02 and worst['peak'] <= 0.10 and worst['onset_ms'] <= 17.0, rec['bsnes']
    return rec


_S9X_ROWS = {}


def frame_start_s9x(frame):
    if not _S9X_ROWS:
        d = json.loads((B / 'tests' / 'speech_main' / 'frames.json').read_text())
        ci = d['columns'].index('frame'), d['columns'].index('pcm')
        prev = 0
        for row in d['rows']:
            _S9X_ROWS[row[ci[0]]] = prev
            prev = row[ci[1]]
    return _S9X_ROWS[frame]


# ------------------------------------------------------------------ fixture ROM (not the release)
FIX_ANCHOR = '\nget: T_SHUICHI\n'
FIX_LINES = ('sfx: clue\n> 遠くで、柱時計が鳴ったような気がした。\n'
             'sfx: clue\n波多野> 修一さんそのときのことをもう少しくわしく聞かせてくださいませんか時刻と電話の向こうの音のことです。\n'                                      # (no punctuation: fast-forwarded, the blips start under the chime)
             'わたし> 時刻は、確かですか。電話の向こうで何かを叩く音がしたのは、九時二十五分ごろで間違いありませんか。\n')   # (long: blips past the page sound)
FIXTWIN = ROOT / 'build/adv-speechfixture-twin'


def build_tree(dest, story=None, generated=None):
    """A copy of the sources in dest/tree, changed by story(text) / generated(tree) (the generated build
    files, before ca65), built there with the same tools.  Returns (tree, sources of the copy, the story)."""
    if dest.exists():
        shutil.rmtree(dest)
    tree = dest / 'tree'
    for d in ('src/adv', 'tools/adv', 'data/adv', 'assets/shinonome'):
        shutil.copytree(ROOT / d, tree / d, ignore=shutil.ignore_patterns('__pycache__'))
    (tree / 'assets/adv').mkdir(parents=True)
    for p in (ROOT / 'assets/adv').glob('*.png'):
        if p.name.endswith(('-256.png', '-72.png')):
            shutil.copy2(p, tree / 'assets/adv' / p.name)
    for n in ('ART.json', 'PREPARED.json'):
        shutil.copy2(ROOT / 'assets/adv' / n, tree / 'assets/adv' / n)
    shutil.copy2(ROOT / 'tools/png_codec.py', tree / 'tools/png_codec.py')
    text = (tree / 'data/adv/story.txt').read_text(encoding='utf-8')
    if story:
        text = story(text)
        (tree / 'data/adv/story.txt').write_text(text, encoding='utf-8')
    (tree / 'build/adv').mkdir(parents=True)
    run = lambda *a: subprocess.run(list(a), cwd=tree, check=True, capture_output=True, text=True)
    run(sys.executable, '-I', 'tools/adv/build.py')
    if generated:
        generated(tree)
    run(str(ROOT / 'tools/vendor/cc65-2.19/bin/ca65'), '-g', '-I', '.', 'src/adv/shionari.s', '-o', 'build/adv/shionari.o')
    run(str(ROOT / 'tools/vendor/cc65-2.19/bin/ld65'), '-C', 'src/adv/adv.cfg', 'build/adv/shionari.o', '-o',
        'build/adv/shionari.sfc', '-Ln', 'build/adv/labels.txt')
    run(sys.executable, '-I', 'tools/adv/romfix.py', 'build/adv/shionari.sfc')
    files = sorted(q for q in tree.rglob('*') if q.is_file() and 'build' not in q.relative_to(tree).parts
                   and '__pycache__' not in q.parts)
    for f in ('shionari.sfc', 'labels.txt', 'layout.json'):
        shutil.copy2(tree / 'build/adv' / f, dest / ('rom.sfc' if f == 'shionari.sfc' else f))
    return tree, {str(q.relative_to(tree)): sha(q.read_bytes()) for q in files}, text


COPY_STEPS = ('copy src/adv tools/adv data/adv assets/shinonome tools/png_codec.py and the assets/adv inputs from '
              'the repository into {dir}/tree')
BUILD_STEPS = ('in tree: python3 -I tools/adv/build.py; {patch}ca65 -g -I . src/adv/shionari.s; ld65 -C src/adv/adv.cfg; '
               'python3 -I tools/adv/romfix.py; ROM, labels and layout copied to {dir}/')


def _fixture_story(text):
    assert text.count(FIX_ANCHOR) == 1
    return text.replace(FIX_ANCHOR, '\n' + FIX_LINES + 'get: T_SHUICHI\n')


def build_fixture():
    import difflib
    tree, sources, story = build_tree(FIX, story=_fixture_story)
    diff = ''.join(difflib.unified_diff((ROOT / 'data/adv/story.txt').read_text(encoding='utf-8').splitlines(True),
                                        story.splitlines(True), 'data/adv/story.txt', 'fixture/data/adv/story.txt'))
    (FIX / 'story.diff').write_text(diff, encoding='utf-8')
    (FIX / 'FIXTURE.json').write_text(json.dumps(dict(
        purpose='test fixture for the speech blips: an effect under the blips, and other speakers in front of a '
                'portrait (never in the real story); not a release candidate',
        procedure=[COPY_STEPS.format(dir='build/adv-speechfixture'),
                   'insert added_lines before "get: T_SHUICHI" (topic 修一 ゆうべのこと) in tree/data/adv/story.txt',
                   BUILD_STEPS.format(dir='build/adv-speechfixture', patch='')],
        added_lines=FIX_LINES.splitlines(), story_diff='build/adv-speechfixture/story.diff', sources=sources,
        repository_story_sha256=sha((ROOT / 'data/adv/story.txt').read_bytes()),
        rom='build/adv-speechfixture/rom.sfc', rom_sha256=sha((FIX / 'rom.sfc').read_bytes()),
        labels='build/adv-speechfixture/labels.txt', layout='build/adv-speechfixture/layout.json'),
        ensure_ascii=False, indent=1) + '\n')
    return tree


# ------------------------------------------------------------------ twin control ROM (not the release)
def _null_volume(tree):
    """build/adv/spc.bin of the copy: the speech voices' volume table (7 bytes) set to 0."""
    info = json.loads((tree / 'build/adv/layout.json').read_text())['speech']['spc']
    path = tree / 'build/adv/spc.bin'
    img = bytearray(path.read_bytes())
    o, n = info['speech_volume_offset'], info['speech_voices']
    assert all(img[o:o + n]), 'not the volume table'
    img[o:o + n] = bytes(n)
    path.write_bytes(bytes(img))


def build_twin(dest=None, story=None, ref=None):
    """(dest, story: a fixture's twin; ref: the fixture's directory with rom.sfc / labels.txt / layout.json)
    The release sources built the same way, with the speech volume table of the driver image at 0: the same
    CPU and SPC700 programs, the same commands and key-ons; voice 1 sounds at volume 0.  Played with the same
    pad trace, the release ROM's PCM minus the twin's is voice 1 only."""
    dest = dest or TWIN
    rom_ref, lab_ref, lay_ref = ((ref / 'rom.sfc', ref / 'labels.txt', ref / 'layout.json') if ref else
                                 (B / 'shionari.sfc', B / 'labels.txt', B / 'layout.json'))
    tree, sources, _ = build_tree(dest, story=story, generated=_null_volume)
    rel, twin = rom_ref.read_bytes(), (dest / 'rom.sfc').read_bytes()
    info = json.loads(lay_ref.read_text())['speech']['spc']
    base = RomText.off(read_labels(lab_ref)['SpcImage']) + info['speech_volume_offset']
    allowed = set(range(base, base + info['speech_voices'])) | set(range(0x7FDC, 0x7FE0))
    diff = [i for i in range(len(rel)) if rel[i] != twin[i]]
    assert len(rel) == len(twin) and set(diff) <= allowed and set(range(base, base + info['speech_voices'])) <= set(diff), \
        ('the twin ROM differs elsewhere', [hex(i) for i in diff][:10])
    d = str(dest.relative_to(ROOT))
    (dest / 'TWIN.json').write_text(json.dumps(dict(
        purpose='control ROM for the speech blips (null volume): the same sources as ' + str(rom_ref.relative_to(ROOT)) +
                ', the speech volumes of the driver image at 0; its PCM with the same pad trace is subtracted; '
                'not a release candidate',
        procedure=[COPY_STEPS.format(dir=d)] + (['the fixture story change (see its FIXTURE.json)'] if story else []) +
                  [BUILD_STEPS.format(dir=d, patch='in build/adv/spc.bin the speech volume table (layout.json speech.spc.'
                                                  'speech_volume_offset, speech_voices bytes) set to 0; ')],
        sources=sources, rom=d + '/rom.sfc', rom_sha256=sha(twin), reference_rom=str(rom_ref.relative_to(ROOT)),
        reference_rom_sha256=sha(rel), rom_bytes_differing_from_reference=[hex(i) for i in diff],
        labels_equal_to_reference=(dest / 'labels.txt').read_bytes() == lab_ref.read_bytes()),
        ensure_ascii=False, indent=1) + '\n')
    assert (dest / 'labels.txt').read_bytes() == lab_ref.read_bytes()
    return dest / 'rom.sfc'


TRAJECTORY = ('mode', 'msg_state', 'msg_text', 'msg_count', 'msg_ptr', 'mouth_actor', 'por_shown', 'scene', 'sound_on',
              'music_cur', 'sfx_count', 'sfx_last', 'snd_sent', 'main_count', 'frame_ready', 'msg_fast',
              'voice_sent', 'voice_mail')
# (not the PCM offset after each frame: Snes9x runs the APU lazily, so the samples handed over per frame vary
# with the APU accesses; the sample stream itself is compared)


def twin_replay(trace_path, twin=None):
    """The trace on a twin ROM (directory with rom.sfc, labels.txt) -> (rows, mono PCM, stereo bytes)."""
    import emu
    twin = twin or TWIN
    trace = json.loads(trace_path.read_text())
    sram = (ROOT / trace['input_sram']['path']).read_bytes()
    g = emu.Game(rom=str((twin / 'rom.sfc').relative_to(ROOT)), sram=sram, label_file=twin / 'labels.txt')
    log = Log(g)
    for m in trace['masks']:
        g.e.mask = m
        g.e.lib.retro_run()
        g.frame += 1
        log(g)
    g.close()
    return log.rows, P.mono(bytes(log.pcm))[0], bytes(log.pcm)


def residual_check(rows, x, trows, tx, events, voices):
    """Release minus twin (null volume), same pad trace and the same blips sent: every expected blip is in the
    difference with its waveform and level, and the difference is exactly 0 everywhere else."""
    assert len(rows) == len(trows), 'traces of different length'
    diff = [(r['frame'], k) for r, t in zip(rows, trows) for k in TRAJECTORY if r[k] != t[k]]
    assert not diff, ('the twin ROM did not follow the same course', diff[:5])
    shift = max(abs(r['pcm'] - t['pcm']) for r, t in zip(rows, trows))
    assert abs(len(x) - len(tx)) <= 1024, ('PCM lengths', len(x), len(tx))
    n = min(len(x), len(tx))
    R = [a - b for a, b in zip(x[:n], tx[:n])]
    fi = frame_index(rows)
    start_of = lambda f: rows[fi[f] - 1]['pcm'] if fi.get(f, 0) > 0 else 0
    mask = bytearray(len(R))
    worst, amp = 1.0, []
    by_env = {}
    for e in events:
        t = voices.template(e['voice'], e['step'])
        lo = start_of(e['frame'] - 1) - 200
        hi = rows[fi[e['frame']] + 1]['pcm'] if fi[e['frame']] + 1 < len(rows) else len(R)
        c, at = best_corr(R, t, lo, hi)
        e['twin_corr'] = round(c, 4)
        e['twin_onset'] = at
        seg = R[at:at + len(t)]
        ratio = max(abs(v) for v in seg) / max(abs(v) for v in t)
        e['twin_peak_ratio'] = round(ratio, 3)
        # audibility: the blip (residual) against what else sounds in the same samples (raw - residual)
        bg = [a - b for a, b in zip(x[at:at + len(t)], seg)]
        rb = math.sqrt(sum(v * v for v in seg) / max(1, len(seg)))
        rg = math.sqrt(sum(v * v for v in bg) / max(1, len(bg)))
        e['blip_to_background_db'] = round(20 * math.log10(rb / rg), 1) if rg else None
        hb, hg = highpass(seg), highpass(bg)
        rb = math.sqrt(sum(v * v for v in hb) / max(1, len(hb)))
        rg = math.sqrt(sum(v * v for v in hg) / max(1, len(hg)))
        e['blip_to_background_db_250hz'] = round(20 * math.log10(rb / rg), 1) if rg else None
        amp.append(ratio)
        worst = min(worst, c)
        by_env.setdefault(e['env'], []).append(c)
        for i in range(max(0, at - 32), min(len(R), at + len(t) + 96)):
            mask[i] = 1
    outside = [v for v, m in zip(R, mask) if not m]
    nonzero = sum(1 for v in outside if v)
    res = dict(blips=len(events), corr_min=round(worst, 4),
               corr_min_by_env={k: round(min(v), 4) for k, v in by_env.items()},
               blips_by_env={k: len(v) for k, v in by_env.items()},
               peak_ratio=[round(min(amp), 3), round(max(amp), 3)] if amp else None,
               samples_outside_blips=len(outside), nonzero_outside=nonzero,
               max_abs_outside=max((abs(v) for v in outside), default=0),
               trajectory_frames=len(rows), frame_boundary_shift_max_samples=shift, compared_samples=n)
    for key, note in (('blip_to_background_db', 'RMS of each blip (residual) over the RMS of the rest of the output '
                                                 '(music, effects) in the same samples'),
                      ('blip_to_background_db_250hz', 'the same above 250 Hz (one-pole high-pass on both): the band '
                                                      'of the blips, without the bass of the songs')):
        db = sorted(e[key] for e in events if e.get(key) is not None)
        if db:
            res[key] = dict(min=db[0], p10=db[len(db) // 10], median=db[len(db) // 2], max=db[-1], note=note)
    return res, R


def highpass(v, fc=250.0, rate=P.RATE):
    a = 1 / (1 + 2 * math.pi * fc / rate)
    out, y, px = [], 0.0, v[0] if v else 0
    for s_ in v:
        y = a * (y + s_ - px)
        px = s_
        out.append(y)
    return out


def open_fast(g, limit=600):
    """A on the page / end wait; the next message opens: fast-forward it from its first frame (A until msg_fast)."""
    n0 = g.w('msg_count')
    g.run(2, ('A',))
    for _ in range(limit):
        if g.w('msg_count') != n0 and g.mode() == M_MSG:
            break
        g.run(1)
    for _ in range(20):
        if g.w('msg_fast') or g.w('msg_state'):
            break
        g.run(1, ('A',))
        g.run(1)
    assert g.w('msg_fast'), 'could not fast-forward the message'
    while g.w('msg_state') == 0:
        g.run(1)
    g.run(30)


def note_track(x, a, n, notes, hop=160, win=320):
    """Per note frequency: when it sounds (magnitude over half its largest, 5 ms hops) and how loud."""
    out = []
    for f in notes:
        mags = [goertzel(x, a + i, a + i + win, f) for i in range(0, n - win, hop)]
        top = max(mags)
        on = [i for i, m in enumerate(mags) if m > 0.5 * top]
        out.append(dict(hz=f, start_ms=round(on[0] * hop * 1000 / P.RATE, 1), end_ms=round(on[-1] * hop * 1000 / P.RATE, 1),
                        peak=round(top, 1)))
    return out


def session_fixture():
    build_fixture()
    rom_path = FIX / 'rom.sfc'
    layout = json.loads((FIX / 'layout.json').read_text())
    assert sha(rom_path.read_bytes()) != sha((B / 'shionari.sfc').read_bytes())
    g = new('speech_fixture', rom=str(rom_path.relative_to(ROOT)), label_file=FIX / 'labels.txt', layout=layout)
    shutil.rmtree(g.shots)
    g.shots = FIX / 'session'
    g.shots.mkdir(parents=True)
    log = Log(g)
    voices = Voices(layout)
    rom = RomText(rom_path, FIX / 'labels.txt')
    g.boot_menu()
    g.run(2, ('A',))
    g.settle()
    g.quiet()
    g.move(routes.STATION)
    choose(g, 'はなす', 'ゆうべのこと')
    for _ in range(2):                     # 修一 x2 at normal speed (stays in the end wait)
        read_page(g)
        if g.w('msg_state') == 2:
            break
        g.run(2, ('A',))
    open_fast(g)                           # chime + narration, fast-forwarded from the start
    open_fast(g)                           # chime + 波多野 (in front of 修一's portrait), fast: blips under the chime
    g.run(2, ('A',))
    read_pages(g, 1)                       # わたし at normal speed
    g.settle()
    g.quiet()
    g.run(60)
    rows = log.rows
    x = P.mono(bytes(log.pcm))[0]
    rec = dict(rom_sha256=sha(rom_path.read_bytes()), added_lines=FIX_LINES.splitlines(),
               note='fixture ROM (not the release): an effect under the blips; other speakers in front of a portrait')
    finish(g, log, rec, FIX / 'trace.json')
    events, mstats = model(rows, rom, voices)
    assert not mstats['mismatches'], mstats['mismatches'][:5]
    pcm_f = check_pcm(rows, x, events, voices)
    # the fixture's own null-volume twin, the same pad trace: the residual is the blips and nothing else
    build_twin(FIXTWIN, story=_fixture_story, ref=FIX)
    trows, tx, tpcm = twin_replay(FIX / 'trace.json', FIXTWIN)
    with wave.open(str(FIXTWIN / 'session.wav'), 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(P.RATE)
        f.writeframes(tpcm)
    res, R = residual_check(rows, x, trows, tx, events, voices)
    res['twin_rom_sha256'] = sha((FIXTWIN / 'rom.sfc').read_bytes())
    res['twin_wav_sha256'] = sha((FIXTWIN / 'session.wav').read_bytes())
    rec['twin_residual'] = res
    resid = measure(R, events, 'twin_onset', voices)
    # the chimes: X alone (narration), Y with the blips of 波多野; Y as the twin plays it (the same commands and
    # key-ons, voice 1 at volume 0) against X: the same notes (auxiliary: the 100 Hz timer phase may move a note
    # by one 10 ms tick, so the two chimes are compared by their notes, not sample by sample)
    chimes = [r['frame'] for i, r in enumerate(rows) if i and r['sfx_count'] != rows[i - 1]['sfx_count'] and r['sfx_last'] == 4]
    assert len(chimes) >= 2, chimes
    fi = frame_index(rows)
    n = round(0.45 * P.RATE)
    ax, ay = rows[fi[chimes[0]] - 1]['pcm'], rows[fi[chimes[1]] - 1]['pcm']
    notes = [703.1, 886.7, 1058.6, 1406.3]
    tr_x, tr_y = note_track(x, ax, n, notes), note_track(tx, ay, n, notes)
    chime_end = ay + round(tr_y[-1]['end_ms'] * P.RATE / 1000)
    under = [e for e in events if ay <= e['twin_onset'] < chime_end]
    rec['chime'] = dict(frames=chimes[:2], alone=tr_x, under_speech_twin=tr_y, blips_under_chime=len(under),
                        blip_residual_corr=[e['twin_corr'] for e in under],
                        raw_window_peak=max(abs(v) for v in x[ay:ay + n]))
    sp_ids = layout['speaker_ids']
    who = {}
    for d in resid:
        who.setdefault(d['speaker'], []).append(d)
    shuichi_portrait = 1 + layout['persons'].index('shuichi')
    rec['in_front_of_shuichi'] = {n_: dict(blips=len([e for e in events if e['speaker'] == sp_ids[n_]]),
                                           in_front_of_shuichi=len([e for e in events if e['speaker'] == sp_ids[n_]
                                                                    and e['portrait'] == shuichi_portrait]),
                                           f0=[d['f0'] for d in who.get(sp_ids[n_], [])][:8],
                                           expected_f0=sorted({d['expected_f0'] for d in who.get(sp_ids[n_], [])}))
                                  for n_ in ('波多野', 'わたし')}
    rec['raw_clean'] = pcm_f['clean']
    (FIX / 'RESULT.json').write_text(json.dumps(rec, ensure_ascii=False, indent=1) + '\n')
    assert res['corr_min'] >= TWIN_CORR_MIN and res['nonzero_outside'] == 0, res
    assert_shape(resid, 'fixture residual')
    assert len(under) >= 2, ('the blips did not overlap the chime', rec['chime'])
    for a_, b_ in zip(tr_x, tr_y):
        assert abs((b_['end_ms'] - b_['start_ms']) - (a_['end_ms'] - a_['start_ms'])) <= 15, ('a chime note length', a_, b_)
        assert abs(b_['start_ms'] - a_['start_ms']) <= 15 and abs(b_['peak'] / a_['peak'] - 1) < 0.1, ('a chime note', a_, b_)
    assert [t['start_ms'] for t in tr_y] == sorted(t['start_ms'] for t in tr_y)
    for name in ('波多野', 'わたし'):
        ev = [e for e in events if e['speaker'] == sp_ids[name]]
        front = [e for e in ev if e['portrait'] == shuichi_portrait]
        assert len(front) >= 2, (name, 'did not speak in front of the portrait', rec['in_front_of_shuichi'])
        assert all(abs(d['f0'] / d['expected_f0'] - 1) < 0.05 for d in who[sp_ids[name]]), (name, 'not the own voice')
        assert who.get(sp_ids[name]), (name, 'no blips measured')
    assert pcm_f['loud_count'] == 0 and not pcm_f['misses'], (pcm_f['loud'][:3], pcm_f['misses'][:3])
    assert_shape(pcm_f['clean'], 'fixture raw PCM')
    # (no raw-PCM blip without music since the songs: わたし is measured in the residual above)
    return rec


# ------------------------------------------------------------------ review reel (listening / viewing)
class Recorder:
    """Video frames of chosen spans; the audio of the same frames from the Log."""
    def __init__(self, g, log):
        self.g, self.log = g, log
        self.on = False
        self.frames = bytearray()
        self.spans = []
        self.audio = bytearray()
        g.observers.append(self)

    def start(self, label):
        self.on = True
        self.spans.append([label, self.g.frame + 1, None, len(self.log.pcm)])

    def stop(self):
        self.on = False
        sp = self.spans[-1]
        sp[2] = self.g.frame
        self.audio += self.log.pcm[sp[3]:]

    def __call__(self, g):
        if self.on:
            w, h, pitch, data = g.e.frame
            bpp = 2 if g.e.pixel_format != 1 else 4
            self.size = (w, h)
            self.fmt = {1: 'bgra', 2: 'rgb565le'}.get(g.e.pixel_format, 'rgb555le')
            self.frames += b''.join(data[y * pitch:y * pitch + w * bpp] for y in range(h))

    def write(self, folder, name):
        folder.mkdir(parents=True, exist_ok=True)
        wav_path = folder / f'{name}.wav'
        with wave.open(str(wav_path), 'wb') as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(P.RATE)
            f.writeframes(bytes(self.audio))
        raw = folder / f'{name}.video.raw'
        raw.write_bytes(bytes(self.frames))
        w, h = self.size
        mp4 = folder / f'{name}.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'rawvideo', '-pixel_format', self.fmt, '-video_size', f'{w}x{h}', '-framerate', str(FPS),
                        '-i', str(raw), '-i', str(wav_path),
                        '-vf', 'scale=768:672:flags=neighbor', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '12',
                        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart',
                        str(mp4)], check=True)
        raw.unlink()
        t, spans = 0.0, []
        for label, a, b, _ in self.spans:
            k = b - a + 1
            spans.append(dict(label=label, first_frame=a, last_frame=b, video_start_s=round(t, 2), seconds=round(k / FPS, 2)))
            t += k / FPS
        return dict(wav=str(wav_path.relative_to(ROOT)), mp4=str(mp4.relative_to(ROOT)),
                    wav_sha256=sha(wav_path.read_bytes()), mp4_sha256=sha(mp4.read_bytes()), spans=spans, seconds=round(t, 2))


def session_review():
    g = new('review')
    log = Log(g)
    rec = Recorder(g, log)
    g.boot_menu()

    def span(label, fn):
        g.quiet()
        rec.start(label)
        fn()
        g.run(20)
        rec.stop()
        g.settle()
        g.quiet()

    def talk(label, **kw):
        span(label, lambda: (choose(g, 'はなす', label.split('|')[1]), read_pages(g, 1, **kw)))

    rec.start('intro (narration silent, 波多野 without a portrait)')
    g.run(2, ('A',))
    read_pages(g)
    g.run(10)
    rec.stop()
    g.settle()
    g.quiet()
    talk('波多野 (portrait), A fast-forward from the 2nd page|検視')
    g.move(routes.STATION)
    talk('修一|ゆうべのこと')
    g.move(routes.SIGNAL)
    g.look('掲示板', '潮見表', '回覧板')
    talk('古賀|ゆうべのこと')
    g.talk('港内電話', '灯台')
    g.move(routes.PIER)
    talk('辰巳 (the pier: the sea song goes on)|ゆうべのこと')
    g.move(routes.LIGHTHOUSE)
    talk('大河内 (outdoors)|ゆうべのこと')
    g.move(routes.CAFE)
    talk('ゆき子|ゆうべのこと')
    g.note('おと：あり')
    g.to_cmd()
    talk('ゆき子 with the sound off (silent)|ゆうべのこと')
    g.note('おと：なし')
    g.to_cmd()
    g.move(routes.WAREHOUSE)
    routes.standard(g)
    g.to_cmd()
    span('わたし (deduction)', lambda: (choose(g, 'てちょう', 'すいりする'), read_pages(g, 3)))
    out = rec.write(OUT / 'review', 'speech-review')
    g.save_battery(g.shots)
    g.trace(OUT / 'review' / 'trace.json')
    out['trace'] = 'build/adv/speech/review/trace.json'
    import wavesheet
    xr = P.mono(bytes(rec.audio))[0]
    t, rows_, zooms, seen = 0, [], [], set()
    for sp in out['spans']:
        n = round((sp['last_frame'] - sp['first_frame'] + 1) / FPS * P.RATE)
        segs = [(a + t, b + t) for a, b in P.segments(xr[t:t + n])]
        rows_.append((sp['label'], t, t + n, [a for a, _ in segs]))
        for a, b in segs:
            d = P.describe(xr, a, b)
            if sp['label'] not in seen and 15 <= d['length_ms'] <= 35 and d['max_step_ratio'] < 0.4 and d['f0']:
                seen.add(sp['label'])
                zooms.append((sp['label'], a - 32, a + 1000))
        t += n
    wavesheet.sheet(xr, rows_, zooms, OUT / 'review' / 'waveforms.png')
    out['note'] = 'review reel for listening / viewing; the checks are in speech_main'
    g.close()
    return out


SESSIONS = dict(speech_main=session_main, speech_d_save=session_d_save, speech_cores=session_cores,
                speech_fixture=session_fixture, review=session_review)


def main(names):
    rom_sha = sha((B / 'shionari.sfc').read_bytes())
    if not names and OUT.exists():
        shutil.rmtree(OUT)                          # a full run: nothing left over from earlier runs
    ok, results = True, {}
    for name in names or SESSIONS:
        try:
            r = SESSIONS[name]()
            results[name] = dict(ok=True, **(r or {}))
            print(f'PASS {name}', json.dumps({k: v for k, v in (r or {}).items() if k not in ('blip_frames', 'clean_blips')},
                                            ensure_ascii=False)[:1500])
        except Exception as e:
            ok = False
            results[name] = dict(ok=False, error=f'{type(e).__name__}: {e}'[:4000], trace=traceback.format_exc())
            print(f'FAIL {name}: {type(e).__name__}: {str(e)[:2000]}')
            traceback.print_exc()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / ('RESULTS.json' if not names else 'RESULTS-partial.json')
    path.write_text(json.dumps(dict(
        rom_sha256=rom_sha, core='Snes9x 1.63 libretro (unmodified)', bsnes_core_sha256=BSNES_SHA,
        scope='Emulator only (not physical hardware); pad input only; WRAM read only; native PCM of the cores. '
              'Nothing here judges how the blips sound to a listener.',
        results=results), ensure_ascii=False, indent=1) + '\n')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    if sys.argv[1:2] == ['_bsnes_run']:
        _bsnes_child(*sys.argv[2:6])
    else:
        main(sys.argv[1:])
