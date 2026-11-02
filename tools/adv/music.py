"""Music of 潮鳴りの密室 (original): instruments and the score compiler for the SPC700 driver (tools/adv/spc.py).

Instruments are computed here (sine partials, detuned copies for an ensemble, decaying attacks, filtered
noise for the drums) and BRR-encoded with the searching encoder of tools/adv/voice.py.  Nothing is
recorded or taken from another game.  The scores are in tools/adv/songs.py.

Score events (per channel, a list): ('inst', name), ('vol', v, pan), ('gate', ticks), ('vib', cents),
('note', midi, ticks), ('rest', ticks), ('loop',).  48 ticks to the quarter note.

Driver sequence bytes (per channel):
  $01 Plo Phi d   note: DSP pitch, d ticks (1-255); key on
  $02 d           rest: release, d ticks
  $03 d           tie: d more ticks of the sounding note
  $04 i           instrument i (instrument table: sample, ADSR1, ADSR2, release GAIN)
  $05 L R         volume
  $06 g           gate: release g ticks before the end of a note (not before a tie)
  $07 d           vibrato depth in pitch units (0 off)
  $08 lo hi       jump
  $09             end of the channel
Song header: T1 divisor (8 kHz / divisor = ticks per second), then 6 channel addresses (0 = unused).
"""
import math, pathlib, random, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import voice as voicemod

TPQ = 48                      # ticks per quarter note
MUSIC_GAIN = 0.75             # every song under the effects and the speech blips
CHANNELS = 6                  # music voices (DSP voices 2-7)
DSP_RATE = 32000


class MusicError(Exception):
    pass


# ------------------------------------------------------------------ BRR
def brr_loop(samples, loop_at):
    """Looped BRR: loop_at and len are multiples of 16; the first block and the loop block use filter 0
    (the decoder state differs between the first pass and the loop)."""
    assert len(samples) % 16 == 0 and loop_at % 16 == 0
    nblk = len(samples) // 16
    out = bytearray()
    p1 = p2 = 0
    for i in range(nblk):
        target = samples[i * 16:(i + 1) * 16]
        best = None
        for flt in ((0,) if i == 0 or i * 16 == loop_at else (0, 1, 2, 3)):
            for shift in range(13):
                err, nibs, q1, q2 = voicemod._block(target, flt, shift, p1, p2)
                if best is None or err < best[0]:
                    best = (err, flt, shift, nibs, q1, q2)
        err, flt, shift, nibs, p1, p2 = best
        out.append(shift << 4 | flt << 2 | 0x02 | (1 if i == nblk - 1 else 0))
        for j in range(0, 16, 2):
            out.append((nibs[j] & 15) << 4 | (nibs[j + 1] & 15))
    return bytes(out)


# ------------------------------------------------------------------ waveforms
def _norm(x, peak):
    m = max(abs(v) for v in x) or 1
    return [round(v * peak / m) for v in x]


def partials(parts, n, cycles=1, detune=(0,)):
    """n samples holding `cycles` periods of the partials [(harmonic, amp)], one copy per detune step
    (extra whole cycles over the n samples, so the loop stays seamless)."""
    out = [0.0] * n
    for d in detune:
        c = cycles + d
        for k, a in parts:
            ph = (k * 0.37 + d * 1.3) % 1.0            # fixed phases: no big peak at the loop start
            w = 2 * math.pi * k * c / n
            for i in range(n):
                out[i] += a * math.sin(w * i + 2 * math.pi * ph)
    return out


LOOP_PERIODS = 8


def struck(parts_attack, parts_loop, period, attack_periods, decay):
    """An attack of attack_periods periods where extra partials die away (exp decay per partial
    index * decay), then one looped period.  Returns samples and the loop start."""
    n = period * attack_periods
    att = [0.0] * n
    for k, a in parts_attack:
        rate = decay * k
        for i in range(n):
            t = i / n
            att[i] += a * math.exp(-rate * t) * math.sin(2 * math.pi * k * i / period + k * 0.37)
    loop = [0.0] * (period * LOOP_PERIODS)       # several periods: room for the better BRR filters
    for k, a in parts_loop:
        for i in range(len(loop)):
            loop[i] += a * math.sin(2 * math.pi * k * i / period + k * 0.37)
    # cross-fade the end of the attack into the loop shape
    fade = min(n, period * 4)
    for i in range(fade):
        w = i / fade
        j = n - fade + i
        att[j] = att[j] * (1 - w) + loop[j % period] * w
    return att + loop, n


def noise(n, seed, lp=1.0, hp=0.0):
    r = random.Random(seed)
    out, y, lo = [], 0.0, 0.0
    for _ in range(n):
        x = r.uniform(-1, 1)
        y += lp * (x - y)                 # one-pole low-pass
        lo += hp * (y - lo)               # subtract a low-passed copy: high-pass
        out.append(y - lo if hp else y)
    return out


def one_shot(x):
    pad = (-len(x)) % 16
    return list(x) + [0] * pad


# ------------------------------------------------------------------ instruments
# sample: (samples, loop start or None, natural frequency at its rate, rate)
# adsr: (attack 0-15, decay 0-7, sustain level 0-7, sustain rate 0-31); release: GAIN exp-decrease rate
def _samples():
    S = {}
    P = 32
    # electric piano: a bright struck attack falling into a soft round tone
    x, lp = struck([(1, 1.0), (2, 0.5), (3, 0.25), (4, 0.18), (7, 0.12)], [(1, 1.0), (2, 0.16), (3, 0.05)], P, 48, 1.6)
    S['ep'] = (_norm(x, 20000), lp, 1000.0, DSP_RATE)
    # strings: a soft saw, three detuned copies over a 4096-sample loop (128 +-1 cycles)
    saw = [(k, (1 / k) * 0.92 ** k) for k in range(1, 13)]
    S['strings'] = (_norm(partials(saw, 4096, 128, (-1, 0, 1)), 20000), 0, 1000.0, DSP_RATE)
    # pad / choir: rounder, also detuned
    S['pad'] = (_norm(partials([(1, 1.0), (2, 0.32), (3, 0.16), (4, 0.06), (5, 0.03)], 4096, 128, (-1, 0, 1)), 20000),
                0, 1000.0, DSP_RATE)
    # flute: near-sine, a breath at the start
    x, lp = struck([(1, 1.0), (2, 0.10), (3, 0.08)], [(1, 1.0), (2, 0.10), (3, 0.07), (4, 0.02)], P, 32, 0.0)
    br = noise(len(x) - P, 7, lp=0.35)
    for i in range(len(br)):
        x[i] += 0.22 * br[i] * math.exp(-6 * i / len(br))
    S['flute'] = (_norm(x, 20000), lp, 1000.0, DSP_RATE)
    # clarinet: odd partials, hollow
    S['clarinet'] = (_norm(partials([(1, 1.0), (3, 0.55), (5, 0.28), (7, 0.14), (9, 0.06), (2, 0.05)], P * 8, 8), 20000),
                     0, 1000.0, DSP_RATE)
    # oboe: nasal, strong 2nd-4th partials
    S['oboe'] = (_norm(partials([(1, 0.55), (2, 1.0), (3, 0.75), (4, 0.42), (5, 0.25), (6, 0.12), (7, 0.06)], P * 8, 8), 20000),
                 0, 1000.0, DSP_RATE)
    # bass: a plucked bass, 128-sample period (250 Hz natural)
    x, lp = struck([(1, 1.0), (2, 0.6), (3, 0.35), (4, 0.2), (5, 0.12), (6, 0.08)],
                   [(1, 1.0), (2, 0.38), (3, 0.14), (4, 0.05)], 128, 16, 2.2)
    S['bass'] = (_norm(x, 22000), lp, 250.0, DSP_RATE)
    # harp / nylon pluck: 64-sample period (500 Hz)
    x, lp = struck([(k, 0.9 / k) for k in range(1, 11)], [(1, 1.0), (2, 0.12), (3, 0.03)], 64, 40, 1.5)
    S['harp'] = (_norm(x, 20000), lp, 500.0, DSP_RATE)
    # celesta / glockenspiel
    x, lp = struck([(1, 1.0), (2, 0.25), (4, 0.6), (6, 0.2)], [(1, 1.0), (4, 0.10)], P, 64, 1.2)
    S['bell'] = (_norm(x, 20000), lp, 1000.0, DSP_RATE)
    # drums (one-shots at 16 kHz)
    R = 16000
    RT = 8000                         # the timpani: low enough for 8 kHz
    n = int(RT * 0.9)
    timp = []
    nz = noise(n, 11, lp=0.35)
    for i in range(n):
        t = i / RT
        f0 = 87.307
        v = (math.sin(2 * math.pi * f0 * t) + 0.45 * math.sin(2 * math.pi * f0 * 1.504 * t) * math.exp(-t * 3)
             + 0.25 * math.sin(2 * math.pi * f0 * 1.742 * t) * math.exp(-t * 5))
        timp.append(v * math.exp(-t * 2.6) * min(1, i / 40) + 0.5 * nz[i] * math.exp(-t * 40))
    S['timp'] = (_norm(one_shot(timp), 22000), None, 87.307, RT)
    n = int(R * 0.05)
    hat = noise(n, 3, lp=1.0, hp=0.5)
    hat = [v * math.exp(-i / n * 5) for i, v in enumerate(hat)]
    S['shaker'] = (_norm(one_shot(hat), 12000), None, 261.6256, R)
    n = int(R * 0.045)
    # wood block: partials 4 and 6 times the note (the clock of the investigation: a3 = A5 + E6, e3 = E5 + B5)
    f = 261.6256
    wb = [(math.sin(2 * math.pi * 4 * f * i / R) + 0.45 * math.sin(2 * math.pi * 6 * f * i / R)) * math.exp(-i / R * 90)
          for i in range(n)]
    S['wood'] = (_norm(one_shot(wb), 20000), None, 261.6256, R)
    return S


INSTRUMENTS = {
    # name: (sample, adsr, release rate, volume gain, vibrato delay irrelevant)
    'ep':       ('ep',       (15, 3, 2, 14), 21, 1.0),
    'strings':  ('strings',  (9, 2, 6, 6),   19, 0.9),
    'slowstr':  ('strings',  (6, 1, 6, 4),   17, 0.9),
    'pad':      ('pad',      (6, 2, 6, 4),   17, 0.9),
    'flute':    ('flute',    (12, 4, 6, 7),  22, 1.0),
    'clarinet': ('clarinet', (12, 4, 6, 8),  22, 0.85),
    'oboe':     ('oboe',     (12, 4, 6, 8),  22, 0.8),
    'bass':     ('bass',     (15, 4, 3, 15), 24, 1.0),
    'harp':     ('harp',     (15, 4, 1, 16), 20, 1.0),
    'bell':     ('bell',     (15, 4, 1, 15), 18, 0.9),
    'timp':     ('timp',     (15, 7, 7, 0),  20, 1.0),
    'shaker':   ('shaker',   (15, 7, 7, 0),  26, 1.0),
    'wood':     ('wood',     (15, 7, 7, 0),  26, 1.0),
}


def build_samples():
    """-> ordered sample names, BRR blobs (with the loop offset in bytes) and an info report."""
    S = _samples()
    names = list(S)
    blobs, info = [], {}
    for name in names:
        x, loop, f0, rate = S[name]
        if loop is None:
            blob = voicemod.brr_encode(x)
            loop_ofs = 0
        else:
            blob = brr_loop(x, loop)
            loop_ofs = loop // 16 * 9
        dec = voicemod.brr_decode(blob) if loop is None else None
        blobs.append((blob, loop_ofs))
        info[name] = dict(samples=len(x), brr_bytes=len(blob), looped=loop is not None, natural_hz=f0, rate=rate,
                          peak=max(abs(v) for v in x))
    return names, blobs, S, info


# ------------------------------------------------------------------ melody notation
NOTE = dict(c=0, d=2, e=4, f=5, g=7, a=9, b=11)


def mml(s, length=4):
    """A small MML for hand-written lines: o4 = the octave of middle C, > <, notes a-g with + / -,
    length 1/2/4/8/16/32 with dots, ^ ties, r rests, '|' bar lines (checked by the compiler).
    Returns ('note' / 'rest' / 'tie' / 'bar') events."""
    ev, i, octave = [], 0, 4

    def num():
        nonlocal i
        j = i
        while i < len(s) and s[i].isdigit():
            i += 1
        return int(s[j:i]) if i > j else None

    def dur():
        nonlocal i
        n = num()
        t = TPQ * 4 // (n or length)
        add = t
        while i < len(s) and s[i] == '.':
            add //= 2
            t += add
            i += 1
        while i < len(s) and s[i] == '^':
            i += 1
            n2 = num()
            t2 = TPQ * 4 // (n2 or length)
            a2 = t2
            while i < len(s) and s[i] == '.':
                a2 //= 2
                t2 += a2
                i += 1
            t += t2
        return t
    while i < len(s):
        c = s[i]
        i += 1
        if c.isspace():
            continue
        if c == 'o':
            octave = num()
        elif c == '>':
            octave += 1
        elif c == '<':
            octave -= 1
        elif c == 'l':
            length = num()
        elif c == '|':
            ev.append(('bar',))
        elif c in NOTE:
            n = NOTE[c]
            while i < len(s) and s[i] in '+-':
                n += 1 if s[i] == '+' else -1
                i += 1
            ev.append(('note', 12 * (octave + 1) + n, dur()))
        elif c == 'r':
            ev.append(('rest', dur()))
        else:
            raise MusicError(f'mml: unexpected {c!r} at {i - 1} in {s[:60]!r}')
    return ev


# ------------------------------------------------------------------ compiler
def pitch_of(inst, midi, S):
    smp = S[INSTRUMENTS[inst][0]]
    f = 440.0 * 2 ** ((midi - 69) / 12)
    p = round(4096 * f / smp[2] * smp[3] / DSP_RATE)
    if not 1 <= p <= 0x3FFF:
        raise MusicError(f'{inst}: note {midi} out of the DSP pitch range ({p})')
    return p


def compile_channel(events, S, inst_index, base, bar_ticks, where):
    """events -> (bytes for address `base`, total ticks, loop tick, loop byte offset)."""
    out = bytearray()
    tick = 0
    loop_tick = loop_ofs = None
    st = dict(inst=None, vol=None, gate=None, vib=0)
    cur_vib_units = 0

    def emit_state():
        if st['inst'] is not None:
            out.extend((0x04, inst_index[st['inst']]))
        if st['vol'] is not None:
            out.extend((0x05, *st['vol']))
        if st['gate'] is not None:
            out.extend((0x06, st['gate']))
        out.extend((0x07, 0))

    def dur_bytes(op, d, first_op=None):
        nonlocal tick
        tick += d
        while d > 255:
            yield 255
            d -= 255
        yield d
    for e in events:
        k = e[0]
        if k == 'inst':
            st['inst'] = e[1]
            out.extend((0x04, inst_index[e[1]]))
        elif k == 'vol':
            v, pan = e[1], e[2]
            g = INSTRUMENTS[st['inst']][3] if st['inst'] else 1.0
            v = v * g * MUSIC_GAIN
            L = round(min(127, v * min(1.0, (128 - pan) / 64)))
            R = round(min(127, v * min(1.0, pan / 64)))
            st['vol'] = (L, R)
            out.extend((0x05, L, R))
        elif k == 'gate':
            st['gate'] = e[1]
            out.extend((0x06, e[1]))
        elif k == 'vib':
            st['vib'] = e[1]
        elif k == 'loop':
            loop_tick, loop_ofs = tick, len(out)
            emit_state()
            cur_vib_units = 0
        elif k == 'bar':
            if tick % bar_ticks:
                raise MusicError(f'{where}: bar line at tick {tick} (bar = {bar_ticks})')
        elif k == 'note':
            if st['inst'] is None:
                raise MusicError(f'{where}: note before an instrument')
            p = pitch_of(st['inst'], e[1], S)
            units = min(255, round(p * (2 ** (st['vib'] / 1200) - 1))) if st['vib'] else 0
            if units != cur_vib_units:
                out.extend((0x07, units))
                cur_vib_units = units
            parts = list(dur_bytes(None, e[2]))
            out.extend((0x01, p & 0xFF, p >> 8, parts[0]))
            for d in parts[1:]:
                out.extend((0x03, d))
        elif k == 'rest':
            parts = list(dur_bytes(None, e[1]))
            for d in parts:
                out.extend((0x02, d))
        elif k == 'tie':
            for d in dur_bytes(None, e[1]):
                out.extend((0x03, d))
        else:
            raise MusicError(f'{where}: unknown event {e}')
    if loop_ofs is not None:
        a = base + loop_ofs
        out.extend((0x08, a & 0xFF, a >> 8))
    else:
        out.append(0x09)
    return bytes(out), tick, loop_tick, loop_ofs


def compile_songs(songs, S, inst_index, base):
    """songs: [(name, bpm, beats per bar, [6 event lists or None], extra entries {name: 'loop'})].
    Returns the sequence blob for address `base`, the header entries [(name, divisor, [addresses])]
    and a report."""
    blob = bytearray()
    entries, report = [], {}
    for name, bpm, beats, chans, extra in songs:
        div = round(8000 / (bpm * TPQ / 60))
        if not 1 <= div <= 255:
            raise MusicError(f'{name}: tempo out of range')
        addrs, loops, ticks, loop_ticks = [], [], set(), set()
        for ci, ev in enumerate(chans):
            if ev is None:
                addrs.append(0)
                loops.append(0)
                continue
            data, t, lt, lo = compile_channel(ev, S, inst_index, base + len(blob), TPQ * beats, f'{name} ch{ci}')
            addrs.append(base + len(blob))
            loops.append(base + len(blob) + lo if lo is not None else 0)
            blob += data
            ticks.add(t)
            loop_ticks.add(lt)
        if len(ticks) != 1:
            raise MusicError(f'{name}: channel lengths differ {sorted(ticks)}')
        if len(loop_ticks) != 1:
            raise MusicError(f'{name}: loop points differ {sorted(loop_ticks)}')
        entries.append((name, div, addrs))
        for xname, what in extra.items():
            assert what == 'loop'
            entries.append((xname, div, loops))
        t = ticks.pop()
        lt = loop_ticks.pop()
        report[name] = dict(bpm=round(8000 / div / TPQ * 60, 2), bars=t / (TPQ * beats),
                            seconds=round(t / (8000 / div), 2), loop_bar=None if lt is None else lt / (TPQ * beats) + 1)
    return bytes(blob), entries, report
