"""Music of 夜鳴き鐘 (original): samples, BRR encoder and the score compiler for tools/yonaki/spc.py.

Every sample is computed here from formulas (sine partials, detuned copies, decaying attacks, filtered
noise, resonators).  Nothing is recorded or taken from another game.  Scores: tools/yonaki/songs.py,
effects: tools/yonaki/sfx.py.

Sample tuning: a sample plays its "natural" frequency f_nat at DSP pitch $1000.  The driver turns a
note into a pitch with one table (2^(k/12), 96 entries, $1000 at 72) and a per-instrument base note B (the lowest
MIDI note with f(B) >= f_nat) and fine tune TUNE (pitch += pitch * TUNE / 1024).

Score events (per channel, a list):
  ('inst', name) ('vol', v 0-127, pan 0-128) ('gate', ticks) ('vib', depth) ('bend', d, n, arrive)
  ('note', midi, ticks) ('rest', ticks) ('tie', ticks) ('loop',) ('bar',) ('rep', n, [events])
48 ticks to the quarter note.

Driver sequence bytes (per channel):
  $00            end of the channel
  $01-$7F        length L (ticks) for the following notes / rests / ties
  $80-$DB        note (MIDI = byte - $80 + 12), current length; key on
  $DC            tie (current length)     $DD  rest (release; current length)
  $E0 L          length L (1-255)
  $E1 i          instrument i (table: sample, ADSR1, ADSR2, release GAIN, transpose, tune)
  $E2 l r        volume
  $E3 g          gate: release g ticks before the end of a note (not before a tie)
  $E4 d          vibrato depth (pitch * d / 4096 peak; 0 off)
  $E5 lo hi      jump                     $E6  end
  $E7 lo hi      call                     $E8  return (one level)
  $E9 n          repeat start (n times)   $EA  repeat end (one level)
  $EB d n        bend: d signed (pitch * d / 4096 per tick), n ticks (bit 7: arrive at the note = scoop)
Song header: T1 divisor, echo feedback, echo volume, echo-on mask (DSP voices), 6 channel addresses.
"""
import math, pathlib, random, sys, hashlib, json

TPQ = 48
CHANNELS = 6
DSP_RATE = 32000
MUSIC_GAIN = 0.80
ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / 'build/yonaki-audio/brr-cache'


class MusicError(Exception):
    pass


# ------------------------------------------------------------------ BRR (exact S-DSP decoder, searching encoder)
def _clamp16(s):
    return max(-32768, min(32767, s))


def brr_step(nib, shift, flt, p1, p2):
    s = (nib << shift) >> 1
    if shift >= 0xD:
        s = -2048 if nib < 0 else 0
    q2 = p2 >> 1
    if flt == 1:
        s += p1 >> 1
        s += (-p1) >> 5
    elif flt == 2:
        s += p1 - q2
        s += q2 >> 4
        s += (p1 * -3) >> 6
    elif flt == 3:
        s += p1 - q2
        s += (p1 * -13) >> 7
        s += (q2 * 3) >> 4
    s = _clamp16(s)
    s = (s * 2) & 0xFFFF
    return s - 0x10000 if s >= 0x8000 else s


def _block(target, flt, shift, p1, p2, limit):
    nibs, err = [], 0
    for t in target:
        best = None
        est = (t - brr_step(0, shift, flt, p1, p2)) / (1 << shift)
        for nib in {max(-8, min(7, math.floor(est) + k)) for k in (-1, 0, 1)}:
            s = brr_step(nib, shift, flt, p1, p2)
            e = (s - t) ** 2
            if best is None or e < best[0]:
                best = (e, nib, s)
        err += best[0]
        if err > limit:
            return err, None, 0, 0
        nibs.append(best[1])
        p2, p1 = p1, best[2]
    return err, nibs, p1, p2


def _encode(samples, loop_at, end_flags):
    """loop_at: sample index of the loop start (None: one-shot).  end_flags: header bits of the last block."""
    nblk = len(samples) // 16
    out = bytearray()
    p1 = p2 = 0
    for i in range(nblk):
        target = samples[i * 16:(i + 1) * 16]
        best = None
        filters = (0,) if i == 0 or (loop_at is not None and i * 16 == loop_at) else (0, 1, 2, 3)
        for flt in filters:
            for shift in range(13):
                err, nibs, q1, q2 = _block(target, flt, shift, p1, p2, best[0] if best else 1e30)
                if nibs is not None and (best is None or err < best[0]):
                    best = (err, flt, shift, nibs, q1, q2)
        err, flt, shift, nibs, p1, p2 = best
        hdr = shift << 4 | flt << 2
        if i == nblk - 1:
            hdr |= end_flags
        out.append(hdr)
        for j in range(0, 16, 2):
            out.append((nibs[j] & 15) << 4 | (nibs[j + 1] & 15))
    return bytes(out)


def _cached(kind, samples, loop_at, flags):
    key = hashlib.sha256(json.dumps([kind, samples, loop_at, flags]).encode()).hexdigest()[:24]
    path = CACHE / f'{key}.brr'
    if path.exists():
        return path.read_bytes()
    data = _encode(samples, loop_at, flags)
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def brr_oneshot(samples):
    """One-shot: the samples, 1 silent block, then the silent end block (no loop)."""
    s = [_clamp16(round(v)) for v in samples] + [0] * ((-len(samples)) % 16 + 32)
    return _cached('one', s, None, 0x01)


def brr_looped(samples, loop_at):
    """Looped: len and loop_at multiples of 16; the loop block uses filter 0."""
    assert len(samples) % 16 == 0 and loop_at % 16 == 0, (len(samples), loop_at)
    s = [_clamp16(round(v)) for v in samples]
    return _cached('loop', s, loop_at, 0x03)


def brr_into_loop(samples):
    """A one-shot head whose last block jumps to another blob's loop (END + LOOP flags)."""
    s = [_clamp16(round(v)) for v in samples] + [0] * ((-len(samples)) % 16)
    return _cached('head', s, None, 0x03)


def brr_decode(data, max_blocks=None):
    out, p1, p2 = [], 0, 0
    for b in range(0, len(data), 9):
        hdr = data[b]
        shift, flt = hdr >> 4, hdr >> 2 & 3
        for j in range(16):
            byte = data[b + 1 + j // 2]
            nib = (byte >> 4) if j % 2 == 0 else (byte & 15)
            nib = nib - 16 if nib >= 8 else nib
            s = brr_step(nib, shift, flt, p1, p2)
            p2, p1 = p1, s
            out.append(s)
        if hdr & 1:
            break
    return out


# ------------------------------------------------------------------ synthesis helpers
def norm(x, peak):
    m = max(abs(v) for v in x) or 1
    return [v * peak / m for v in x]


def loop_partials(parts, n, detune=(0,), seed=0):
    """n samples; parts = [(cycles in n, amp)] (integer cycles: seamless).  Each detune step d adds a copy
    with cycles*(1)+d*harmonic number (a chorus that stays periodic)."""
    out = [0.0] * n
    rnd = random.Random(seed)
    for d in detune:
        for c, a in parts:
            ph = rnd.random()
            w = 2 * math.pi * c / n
            for i in range(n):
                out[i] += a * math.sin(w * i + 2 * math.pi * ph)
    return out


def harmonic_loop(f_cycles, harmonics, n, detune=(0,), seed=0):
    """harmonics [(k, amp)] of a tone with f_cycles cycles in n samples, chorus copies (f_cycles + d) * k."""
    out = [0.0] * n
    rnd = random.Random(seed)
    for d in detune:
        for k, a in harmonics:
            c = (f_cycles + d) * k
            ph = rnd.random()
            w = 2 * math.pi * c / n
            for i in range(n):
                out[i] += a * math.sin(w * i + 2 * math.pi * ph)
    return out


def white(n, seed):
    r = random.Random(seed)
    return [r.uniform(-1, 1) for _ in range(n)]


def onepole_lp(x, a, circular=False):
    y, out = 0.0, []
    if circular:
        for v in x:
            y += a * (v - y)
    for v in x:
        y += a * (v - y)
        out.append(y)
    return out


def highpass(x, a, circular=False):
    lo = onepole_lp(x, a, circular)
    return [v - l for v, l in zip(x, lo)]


def resonator(x, f, q, rate, circular=False):
    """Two-pole band-pass at f (Hz), quality q."""
    w = 2 * math.pi * f / rate
    r = math.exp(-w / (2 * q))
    a1, a2 = 2 * r * math.cos(w), -r * r
    g = 1 - r
    y1 = y2 = 0.0
    if circular:
        for v in x:
            y = g * v + a1 * y1 + a2 * y2
            y2, y1 = y1, y
    out = []
    for v in x:
        y = g * v + a1 * y1 + a2 * y2
        y2, y1 = y1, y
        out.append(y)
    return out


def struck(f, rate, parts, attack_n, loop_cycles, loop_parts, seed=1, bend=0.0, bend_t=0.03, click=0.0):
    """A struck / plucked tone: the attack (attack_n samples) sums parts [(ratio, amp, decay per second)]
    (inharmonic ratios allowed: they must have died by the end of the attack), cross-faded into a loop
    of loop_cycles periods of loop_parts [(harmonic, amp)].  f: frequency at `rate`; the loop length is
    rounded to whole samples (multiple of 16) and f is re-derived from it so the loop is exact.
    Returns (samples, loop start, the exact f)."""
    L = max(16, round(loop_cycles * rate / f / 16) * 16)
    f = loop_cycles * rate / L
    attack_n = attack_n // 16 * 16
    rnd = random.Random(seed)
    att = [0.0] * attack_n
    for ratio, a, dec in parts:
        ph = rnd.random() * 2 * math.pi
        ph0 = ph
        for i in range(attack_n):
            t = i / rate
            fb = f * ratio * (1 + bend * math.exp(-t / bend_t))
            ph0 += 2 * math.pi * fb / rate
            att[i] += a * math.exp(-dec * t) * math.sin(ph0)
    if click:
        nz = onepole_lp(white(min(attack_n, int(rate * 0.004)), seed + 7), 0.6)
        for i, v in enumerate(nz):
            att[i] += click * v * (1 - i / len(nz))
    loop = [0.0] * L
    for k, a in loop_parts:
        ph = rnd.random() * 2 * math.pi
        for i in range(L):
            loop[i] += a * math.sin(2 * math.pi * k * loop_cycles * i / L + ph)
    # scale the loop to the level the attack reaches at its end, cross-fade over the last quarter
    tail = att[-L:] if attack_n >= L else att
    lvl_a = math.sqrt(sum(v * v for v in tail) / max(1, len(tail)))
    lvl_l = math.sqrt(sum(v * v for v in loop) / L)
    loop = [v * lvl_a / lvl_l for v in loop] if lvl_l else loop
    fade = attack_n // 3
    for i in range(fade):
        w = i / fade
        j = attack_n - fade + i
        att[j] = att[j] * (1 - w) + loop[(j - attack_n) % L] * w
    return att + loop, attack_n, f


def oneshot_pad(x):
    return list(x) + [0.0] * ((-len(x)) % 16)


def env_ar(n, a, rate):
    na = max(1, int(a * rate))
    return [min(1.0, i / na) for i in range(n)]


# ------------------------------------------------------------------ samples
# each: dict(x=samples, loop=start or None, f=natural frequency at pitch $1000 (Hz) or None, loopto=name)
def samples():
    S = {}
    R = 32000

    def put(name, x, loop, f_at_rate, rate, peak=20000, loopto=None):
        S[name] = dict(x=norm(x, peak), loop=loop, f=None if f_at_rate is None else f_at_rate * R / rate,
                       loopto=loopto)

    # --- music box: a comb tine (modes 1 and 5.4 / 15, quick), a clear sine tail
    x, lp, f = struck(1000, R, [(1, 1.0, 1.5), (2, 0.12, 6), (5.4, 0.35, 30), (15.1, 0.12, 60)], 1536, 8,
                      [(1, 1.0), (2, 0.06)], seed=2, click=0.25)
    put('mbox', x, lp, f, R)
    # --- koto: plucked silk string, the pitch settles a little after the pluck
    harm = []
    for k in range(1, 13):
        a = abs(math.sin(math.pi * k * 0.22)) / k ** 0.9
        harm.append((k, a, 2.0 + 2.2 * k))
    x, lp, f = struck(1000, R, harm, 2048, 8, [(1, 1.0), (2, 0.30), (3, 0.14), (4, 0.05)], seed=3, bend=0.012,
                      bend_t=0.02, click=0.15)
    put('koto', x, lp, f, R)
    # --- harp / nylon guitar
    x, lp, f = struck(500, R, [(k, 0.9 / k, 3 + 1.5 * k) for k in range(1, 11)], 1536, 4,
                      [(1, 1.0), (2, 0.14), (3, 0.04)], seed=4)
    put('harp', x, lp, f, R)
    # --- soft piano / electric piano
    x, lp, f = struck(1000, R, [(1, 1.0, 2), (2, 0.5, 6), (3, 0.25, 9), (4, 0.18, 12), (7, 0.1, 20)], 1536, 8,
                      [(1, 1.0), (2, 0.16), (3, 0.05)], seed=5)
    put('ep', x, lp, f, R)
    # --- bass (plucked)
    x, lp, f = struck(250, R, [(k, a, 3 + 2 * k) for k, a in ((1, 1.0), (2, 0.6), (3, 0.35), (4, 0.2), (5, 0.12), (6, 0.08))],
                      1024, 4, [(1, 1.0), (2, 0.38), (3, 0.14), (4, 0.05)], seed=6)
    put('bass', x, lp, f, R, 22000)
    # --- strings: soft saw, three detuned copies (128 +-1 cycles in 4096)
    saw = [(k, (1 / k) * 0.9 ** k) for k in range(1, 13)]
    put('strings', harmonic_loop(128, saw, 4096, (-1, 0, 1), seed=7), 0, 128 * R / 4096, R)
    # --- choir "oo": low formants, one period (the driver vibrato gives life)
    ch = [(1, 1.0), (2, 0.55), (3, 0.22), (4, 0.10), (5, 0.06), (6, 0.04), (8, 0.03)]
    put('choir', harmonic_loop(8, ch, 256, (0,), seed=8), 0, 8 * R / 256, R)
    # --- organ / sho reed (odd and even partials, bright)
    put('organ', harmonic_loop(8, [(1, 1.0), (2, 0.7), (3, 0.5), (4, 0.35), (6, 0.2), (8, 0.15)], 256, (0,), seed=9),
        0, 1000, R)
    put('reed', harmonic_loop(8, [(1, 0.6), (2, 0.8), (3, 1.0), (4, 0.7), (5, 0.55), (6, 0.4), (7, 0.3), (9, 0.15),
                                  (11, 0.08)], 256, (0,), seed=10), 0, 1000, R)
    # --- clarinet / oboe
    put('clarinet', harmonic_loop(8, [(1, 1.0), (3, 0.55), (5, 0.28), (7, 0.14), (9, 0.06), (2, 0.05)], 256, (0,), seed=11),
        0, 1000, R)
    put('oboe', harmonic_loop(8, [(1, 0.55), (2, 1.0), (3, 0.75), (4, 0.42), (5, 0.25), (6, 0.12), (7, 0.06)], 256, (0,),
                              seed=12), 0, 1000, R)
    # --- flute: near-sine, a breath at the start
    x, lp, f = struck(1000, R, [(1, 1.0, 0), (2, 0.10, 0), (3, 0.08, 0)], 1024, 8, [(1, 1.0), (2, 0.10), (3, 0.07)],
                      seed=13)
    br = onepole_lp(white(len(x) - lp // 2, 14), 0.35)
    for i in range(min(lp, len(br))):
        x[i] += 0.25 * br[i] * math.exp(-5 * i / lp)
    put('flute', x, lp, f, R)
    # --- shakuhachi: a hollow tone with breath noise inside the loop and a strong chiff
    n = 2048
    cyc = 32                      # 500 Hz
    tone = harmonic_loop(cyc, [(1, 1.0), (2, 0.22), (3, 0.10), (4, 0.03)], n, (0,), seed=15)
    nz = resonator(white(n, 16), 1400, 0.9, R, circular=True)
    nz = norm(nz, 1.0)
    breath = [0.20 * nz[i] * (0.6 + 0.4 * math.sin(2 * math.pi * cyc * i / n)) for i in range(n)]
    loop = [t + b for t, b in zip(norm(tone, 1.0), breath)]
    att_n = 1024
    chiff = resonator(white(att_n, 17), 2000, 0.8, R)
    chiff = norm(chiff, 1.0)
    att = []
    for i in range(att_n):
        e = min(1.0, i / 700)
        att.append(loop[i % n] * e + 0.7 * chiff[i] * math.exp(-i / 220))
    put('shaku', att + loop, att_n, cyc * R / n, R)
    # --- celesta / glockenspiel (the bell motif's high double)
    x, lp, f = struck(1000, R, [(1, 1.0, 1.2), (2, 0.25, 3), (4, 0.6, 5), (6, 0.2, 10), (9.2, 0.1, 30)], 1536, 8,
                      [(1, 1.0), (4, 0.06)], seed=18)
    put('celesta', x, lp, f, R)
    # --- the small bronze bell (夜鳴き鐘): 16 kHz, prime 880 Hz at 16 kHz (pitch $0800 plays it as cast)
    RB = 16000
    prime = 880.0
    att_n = 3200
    loop_n = 6400                 # 0.4 s: partials on a 2.5 Hz grid
    grid = RB / loop_n
    # (ratio to the prime, amplitude, decay per second in the attack)
    bell_parts = [(0.5, 0.55, 0.7), (1.0, 1.0, 0.9), (1.003, 0.45, 0.9), (1.19, 0.55, 2.0), (1.505, 0.30, 3.5),
                  (2.0, 0.65, 2.2), (2.003, 0.25, 2.2), (2.54, 0.30, 6), (2.67, 0.35, 7), (3.27, 0.22, 10),
                  (4.21, 0.18, 16), (5.38, 0.12, 24), (6.7, 0.08, 35)]
    rnd = random.Random(19)
    att = [0.0] * att_n
    for ratio, a, dec in bell_parts:
        fr = prime * ratio
        ph = rnd.random() * 2 * math.pi
        for i in range(att_n):
            att[i] += a * math.exp(-dec * i / RB) * math.sin(2 * math.pi * fr * i / RB + ph)
    strike = resonator(white(240, 20), 3200, 1.5, RB)
    for i, v in enumerate(norm(strike, 1.0)):
        att[i] += 0.5 * v * (1 - i / 240)
    tail = [(0.5, 0.55), (1.0, 1.0), (1.003, 0.45), (1.19, 0.40), (1.505, 0.12), (2.0, 0.40), (2.003, 0.14),
            (2.67, 0.05)]
    loop = [0.0] * loop_n
    decs = {r: d for r, _, d in bell_parts}
    for ratio, a in tail:
        dec = decs[ratio]
        fr = round(prime * ratio / grid) * grid
        lvl = a * math.exp(-dec * att_n / RB)
        ph = rnd.random() * 2 * math.pi
        for i in range(loop_n):
            loop[i] += lvl * math.sin(2 * math.pi * fr * i / RB + ph)
    # match the attack's end into the loop
    fade = 1200
    for i in range(fade):
        w = i / fade
        j = att_n - fade + i
        att[j] = att[j] * (1 - w) + loop[(j - att_n) % loop_n] * w
    put('kane', att + loop, att_n, prime, RB, 22000)
    # --- stab: a dissonant cluster of soft saws (m2 clashes in three octaves) with a noisy head; looped.
    #     2048-sample loop: tones on a 15.625 Hz grid; nominal pitch = the lowest tone (cycles 9)
    n = 2048
    cl = [0.0] * n
    rnd = random.Random(25)
    for c in (9, 12, 13, 18, 19, 25, 26, 37):
        for k in range(1, 9):
            if c * k * 15.625 > 6000:
                break
            ph = rnd.random() * 6.283
            amp = 0.9 ** k / k
            for i in range(n):
                cl[i] += amp * math.sin(2 * math.pi * c * k * i / n + ph)
    cl = norm(cl, 1.0)
    head_n = 1024
    hn = highpass(white(head_n, 26), 0.2)
    head = [cl[i] * min(1.0, i / 40) + 0.8 * hn[i] * math.exp(-i / 260) for i in range(head_n)]
    put('stab', head + cl, head_n, 9 * R / n, R)
    # --- timpani (8 kHz)
    RT = 8000
    n = int(RT * 0.6) // 16 * 16
    nz = onepole_lp(white(n, 21), 0.35)
    timp = []
    f0 = 87.307
    for i in range(n):
        t = i / RT
        v = (math.sin(2 * math.pi * f0 * t) + 0.45 * math.sin(2 * math.pi * f0 * 1.504 * t) * math.exp(-t * 3)
             + 0.25 * math.sin(2 * math.pi * f0 * 1.742 * t) * math.exp(-t * 5))
        timp.append(v * math.exp(-t * 3.2) * min(1, i / 30) + 0.5 * nz[i] * math.exp(-t * 40))
    put('timp', timp, None, f0, RT, 22000)
    # --- taiko / low drum / heartbeat body (6 kHz): a pitch drop, a skin slap
    RK = 6000
    n = int(RK * 0.45) // 16 * 16
    nz = onepole_lp(white(n, 22), 0.5)
    tk, ph = [], 0.0
    for i in range(n):
        t = i / RK
        fr = 65 * (1 + 0.6 * math.exp(-t / 0.03))
        ph += 2 * math.pi * fr / RK
        tk.append(math.sin(ph) * math.exp(-t * 7) * min(1, i / 12) + 0.35 * nz[i] * math.exp(-t * 60))
    put('taiko', tk, None, 65.406, RK, 24000)          # nominally C2
    # --- snare (16 kHz)
    RS = 16000
    n = int(RS * 0.16) // 16 * 16
    nz = highpass(white(n, 23), 0.08)
    sn = [0.8 * nz[i] * math.exp(-i / RS * 22) + 0.6 * math.sin(2 * math.pi * 185 * i / RS) * math.exp(-i / RS * 35)
          for i in range(n)]
    put('snare', sn, None, 261.6256, RS, 16000)
    # --- shaker / hat (16 kHz)
    n = int(RS * 0.05) // 16 * 16
    hat = highpass(white(n, 24), 0.5)
    put('shaker', [v * math.exp(-i / n * 5) for i, v in enumerate(hat)], None, 261.6256, RS, 11000)
    # --- wood block (16 kHz): partials 4 and 6 times the note
    n = int(RS * 0.045) // 16 * 16
    fw = 261.6256
    wb = [(math.sin(2 * math.pi * 4 * fw * i / RS) + 0.45 * math.sin(2 * math.pi * 6 * fw * i / RS)) * math.exp(-i / RS * 90)
          for i in range(n)]
    put('wood', wb, None, fw, RS, 20000)
    return S


def effect_samples():
    """Samples used only by the effects and the ambience (tools/yonaki/sfx.py)."""
    S = {}
    R = 16000

    def put(name, x, loop=None, rate=R, peak=20000, loopto=None):
        S[name] = dict(x=norm(x, peak), loop=loop, f=rate / 8, loopto=loopto)   # pitch $0800 = as recorded

    # --- wooden knock: two body modes and a hard contact
    n = 1440
    nz = white(n, 30)
    kn = []
    for i in range(n):
        t = i / R
        kn.append(0.9 * math.sin(2 * math.pi * 410 * t) * math.exp(-t * 55) + 0.55 * math.sin(2 * math.pi * 1180 * t) *
                  math.exp(-t * 90) + 0.4 * math.sin(2 * math.pi * 2350 * t) * math.exp(-t * 160) +
                  0.6 * nz[i] * math.exp(-t * 400))
    put('knock', kn)
    # --- floor creak: one stick-slip pulse ringing at two wood modes (looped: the pitch slide plays it)
    n = 256
    pulse = [0.0] * n
    pulse[0] = 1.0
    cr = resonator(pulse, 900, 6, R, circular=True)
    cr2 = resonator(pulse, 2300, 8, R, circular=True)
    put('creak', [a + 0.6 * b for a, b in zip(norm(cr, 1), norm(cr2, 1))], loop=0)
    # --- rain: a soft band-limited bed (looped) under the droplet heads
    nb = 1024
    bed = onepole_lp(white(nb, 31), 0.45, circular=True)
    bed = highpass(bed, 0.08, circular=True)
    put('rainbed', bed, loop=0, peak=4200)
    # droplet heads: two short broadband ticks (drops on leaves / gravel), a "plip" into a puddle,
    # a dull tap on the wooden eaves; each settles into the bed (the shared loop)
    def head(n, seed, parts):
        nz = white(n, seed)
        x = [0.0] * n
        for kind, f, q, dec, amp in parts:
            if kind == 'noise':
                r = resonator(nz, f, q, R)
                r = norm(r, 1.0)
                for i in range(n):
                    x[i] += amp * r[i] * math.exp(-i / R / dec)
            elif kind == 'chirp':
                ph = 0.0
                for i in range(n):
                    t = i / R
                    ph += 2 * math.pi * f * (1 + 0.4 * min(1, t / dec)) / R
                    x[i] += amp * math.sin(ph) * math.exp(-t / dec) * min(1, i / 4)
            elif kind == 'tone':
                for i in range(n):
                    t = i / R
                    x[i] += amp * math.sin(2 * math.pi * f * t) * math.exp(-t / dec) * min(1, i / 3)
        return x
    shapes = [[('noise', 4200, 1.2, 0.0025, 1.0)],
              [('noise', 2600, 1.5, 0.0040, 1.0), ('noise', 6000, 1.0, 0.0015, 0.5)],
              [('chirp', 1900, 0, 0.007, 1.0), ('noise', 3500, 1.0, 0.002, 0.6)],
              [('tone', 480, 0, 0.012, 1.0), ('tone', 1150, 0, 0.006, 0.5), ('noise', 1800, 1.0, 0.003, 0.7)]]
    for k, parts in enumerate(shapes):
        n = 400
        x = norm(head(n, 40 + k, parts), 20000)
        for i in range(n - 96, n):
            w = (i - (n - 96)) / 96
            x[i] = x[i] * (1 - w) + S['rainbed']['x'][i - (n - 96)] * w
        S[f'drop{k}'] = dict(x=x, loop=None, f=R / 8, loopto='rainbed')
    # --- a water drip ("pichon"): a clean rising chirp, a little ring
    n = 640
    x, ph = [], 0.0
    for i in range(n):
        t = i / R
        fr = 1150 * (1 + 0.9 * (1 - math.exp(-t / 0.006)))
        ph += 2 * math.pi * fr / R
        x.append(math.sin(ph) * math.exp(-t / 0.010) * min(1, i / 5))
    put('plink', x)
    # --- glass shards: inharmonic tinkle
    n = 1920
    rnd = random.Random(50)
    gl = [0.0] * n
    for ratio, a, dec in ((1, 1.0, 25), (2.32, 0.7, 35), (3.85, 0.5, 50), (5.1, 0.35, 70), (6.9, 0.25, 90)):
        ph = rnd.random() * 6.28
        for i in range(n):
            gl[i] += a * math.exp(-dec * i / R) * math.sin(2 * math.pi * 1450 * ratio * i / R + ph)
    put('tink', gl)
    # --- low rumble: brown noise loop (the pitch value sets how low; looped, seamless)
    nr = 2048
    rb = onepole_lp(white(nr, 51), 0.04, circular=True)
    rb = highpass(rb, 0.004, circular=True)
    put('rumble', rb, loop=0, peak=20000)
    # --- scrape (sliding door runner): resonant band noise, looped
    ns = 1024
    sc = [a + 0.6 * b for a, b in zip(norm(resonator(white(ns, 52), 700, 3, R, circular=True), 1),
                                      norm(resonator(white(ns, 53), 1900, 4, R, circular=True), 1))]
    put('scrape', sc, loop=0)
    # --- wind: two resonances an octave and a fifth apart, looped (a pitch slide makes it moan)
    nw = 2048
    wd = [a + 0.5 * b for a, b in zip(norm(resonator(white(nw, 54), 500, 9, R, circular=True), 1),
                                      norm(resonator(white(nw, 55), 1250, 12, R, circular=True), 1))]
    put('gust', wd, loop=0)
    # --- a square and a sine (motor whirr, radio squelch)
    put('square', [1.0 if (i // 16) % 2 == 0 else -1.0 for i in range(32)], loop=0, peak=7000)
    put('sine', [math.sin(2 * math.pi * i / 32) for i in range(32)], loop=0, peak=10000)
    return S


def encode_sample(s):
    """-> (blob, loop offset in bytes or None, loopto)."""
    x = s['x']
    if s.get('loopto'):
        return brr_into_loop(x), None
    if s['loop'] is None:
        return brr_oneshot(x), None
    pad = (-len(x)) % 16
    assert pad == 0 and s['loop'] % 16 == 0, (len(x), s['loop'])
    return brr_looped(x, s['loop']), s['loop'] // 16 * 9


# ------------------------------------------------------------------ instruments
# name: (sample, (attack 0-15, decay 0-7, sustain level 0-7, sustain rate 0-31), release GAIN rate, gain)
INSTRUMENTS = {
    'mbox':     ('mbox',     (15, 4, 3, 13), 16, 1.0),
    'koto':     ('koto',     (15, 3, 3, 15), 20, 1.0),
    'koto_l':   ('koto',     (15, 4, 4, 11), 14, 1.0),     # let ring
    'harp':     ('harp',     (15, 4, 2, 15), 18, 1.0),
    'guitar':   ('harp',     (15, 5, 3, 16), 22, 1.0),
    'ep':       ('ep',       (15, 3, 2, 14), 20, 1.0),
    'bass':     ('bass',     (15, 4, 3, 15), 24, 1.0),
    'pizz':     ('bass',     (15, 6, 1, 20), 26, 1.0),
    'strings':  ('strings',  (9, 2, 6, 6),   19, 0.9),
    'slowstr':  ('strings',  (5, 1, 6, 3),   16, 0.9),
    'trem':     ('strings',  (14, 5, 4, 12), 26, 0.9),     # short bows (tremolo by repeated notes)
    'choir':    ('choir',    (5, 2, 6, 4),   15, 1.0),
    'organ':    ('organ',    (13, 2, 7, 2),  24, 0.7),
    'sho':      ('reed',     (6, 1, 7, 1),   14, 0.55),
    'reed':     ('reed',     (11, 3, 6, 6),  22, 0.6),
    'clarinet': ('clarinet', (12, 4, 6, 8),  22, 0.85),
    'oboe':     ('oboe',     (12, 4, 6, 8),  22, 0.8),
    'flute':    ('flute',    (12, 4, 6, 7),  22, 1.0),
    'shaku':    ('shaku',    (10, 3, 6, 6),  18, 1.0),
    'stab':     ('stab',     (15, 3, 4, 11), 16, 1.0),
    'celesta':  ('celesta',  (15, 4, 1, 14), 17, 0.9),
    'kane':     ('kane',     (15, 7, 7, 9),  12, 1.0),
    'timp':     ('timp',     (15, 7, 7, 0),  20, 1.0),
    'taiko':    ('taiko',    (15, 7, 7, 0),  20, 1.0),
    'snare':    ('snare',    (15, 7, 7, 0),  26, 1.0),
    'shaker':   ('shaker',   (15, 7, 7, 0),  26, 1.0),
    'wood':     ('wood',     (15, 7, 7, 0),  26, 1.0),
}


def adsr_bytes(a, d, sl, sr):
    return 0x80 | d << 4 | a, sl << 5 | sr


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def base_tune(f_nat):
    """-> (B, TUNE): the lowest MIDI note with f(B) >= f_nat, and pitch += pitch * TUNE / 1024."""
    B = math.ceil(69 + 12 * math.log2(f_nat / 440.0) - 1e-9)
    q = midi_hz(B) / f_nat
    tune = round((q - 1) * 1024)
    assert 0 <= tune < 64, (f_nat, B, q)
    return B, tune


def pitch_table():
    return [round(0x1000 * 2 ** ((j - 72) / 12)) for j in range(96)]


PTAB = pitch_table()


def driver_pitch(table_index, tune):
    """The pitch the driver computes (mirrors the SPC700 code)."""
    p = PTAB[table_index]
    pl, ph = p & 0xFF, p >> 8
    t = ph * tune + ((pl * tune) >> 8)
    return p + (t >> 2)


# ------------------------------------------------------------------ melody notation
NOTE = dict(c=0, d=2, e=4, f=5, g=7, a=9, b=11)


def mml(s, length=4):
    """o4 = the octave of middle C, > <, notes a-g with + / -, lengths 1 2 4 8 16 32 (dots, ^ ties),
    r rests, '|' bar lines, l default length, t3 = triplet prefix not supported (use explicit ticks: n96)."""
    ev, i, octave = [], 0, 4

    def num():
        nonlocal i
        j = i
        while i < len(s) and s[i].isdigit():
            i += 1
        return int(s[j:i]) if i > j else None

    def one():
        nonlocal i
        if i < len(s) and s[i] == '#':          # #ticks: an explicit length in ticks
            i += 1
            return num()
        n = num()
        t = TPQ * 4 // (n or length)
        add = t
        while i < len(s) and s[i] == '.':
            add //= 2
            t += add
            i += 1
        return t

    def dur():
        nonlocal i
        t = one()
        while i < len(s) and s[i] == '^':
            i += 1
            t += one()
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
        elif c == '&':                          # tie to the previous note
            ev.append(('tie', dur()))
        else:
            raise MusicError(f'mml: unexpected {c!r} at {i - 1} in {s[:60]!r}')
    return ev


# ------------------------------------------------------------------ compiler
class Inst:
    def __init__(self, names, S, sample_index):
        self.names = list(names)
        self.index = {n: i for i, n in enumerate(self.names)}
        self.table = []
        self.base = {}
        for n in self.names:
            smp, adsr, rel, _ = INSTRUMENTS[n]
            B, tune = base_tune(S[smp]['f'])
            self.base[n] = (B, tune)
            a1, a2 = adsr_bytes(*adsr)
            self.table.append([sample_index[smp], a1, a2, 0xA0 | rel, (84 - B) & 0xFF, tune, 0, 0])

    def note_index(self, inst, midi, where):
        B, tune = self.base[inst]
        j = midi - B + 72
        if not (12 <= midi <= 103 and 0 <= j < 96) or driver_pitch(j, tune) > 0x3FFF:
            raise MusicError(f'{where}: {inst} note {midi} out of range')
        return j


def _split_bars(events):
    bars, cur = [], []
    for e in events:
        cur.append(e)
        if e[0] == 'bar':
            bars.append(cur)
            cur = []
    if cur:
        bars.append(cur)
    return bars


def auto_repeat(events):
    """Consecutive identical groups of 1-4 bars become ('rep', n, group); only where no loop marker."""
    out = []
    for seg_i, seg in enumerate(_split_on_loop(events)):
        if seg_i:
            out.append(('loop',))
        bars = _split_bars(seg)
        i = 0
        while i < len(bars):
            best = (1, 1)
            for unit in (1, 2, 3, 4):
                if i + unit > len(bars):
                    break
                g = bars[i:i + unit]
                if any(e[0] == 'rep' for b in g for e in b):
                    continue
                k = 1
                while bars[i + k * unit:i + (k + 1) * unit] == g:
                    k += 1
                if k > 1 and k * unit > best[0] * best[1] - (0 if best[1] > 1 else 0):
                    best = (unit, k)
            unit, k = best
            if k > 1:
                body = [e for b in bars[i:i + unit] for e in b]
                out.append(('rep', k, body))
                i += unit * k
            else:
                out += bars[i]
                i += 1
    return out


def _split_on_loop(events):
    segs, cur = [], []
    for e in events:
        if e[0] == 'loop':
            segs.append(cur)
            cur = []
        else:
            cur.append(e)
    segs.append(cur)
    return segs


def compile_channel(events, inst, base, bar_ticks, where):
    """events -> (bytes for address `base`, total ticks, loop tick, loop byte offset, notes [(tick, midi, ticks, inst)])."""
    out = bytearray()
    st = dict(inst=None, vol=None, gate=None, vib=0, bend=None, len=None, tick=0)
    loop = [None, None]
    notes = []

    def set_len(d):
        if st['len'] != d:
            if d < 0x80:
                out.append(d)
            else:
                out.extend((0xE0, d))
            st['len'] = d

    def pieces(d):
        ps = []
        while d > 255:
            ps.append(192)
            d -= 192
        ps.append(d)
        return ps

    def emit_state():
        if st['inst'] is not None:
            out.extend((0xE1, inst.index[st['inst']]))
        if st['vol'] is not None:
            out.extend((0xE2, *st['vol']))
        if st['gate'] is not None:
            out.extend((0xE3, st['gate']))
        out.extend((0xE4, st['vib']))
        b = st['bend'] or (0, 0)
        out.extend((0xEB, b[0] & 0xFF, b[1]))
        st['len'] = None

    def run(evs, in_rep):
        for e in evs:
            k = e[0]
            if k == 'inst':
                st['inst'] = e[1]
                out.extend((0xE1, inst.index[e[1]]))
            elif k == 'vol':
                v, pan = e[1], e[2]
                g = INSTRUMENTS[st['inst']][3] if st['inst'] else 1.0
                v = v * g * MUSIC_GAIN
                L = round(min(127, v * min(1.0, (128 - pan) / 64)))
                R = round(min(127, v * min(1.0, pan / 64)))
                st['vol'] = (L, R)
                out.extend((0xE2, L, R))
            elif k == 'gate':
                st['gate'] = e[1]
                out.extend((0xE3, e[1]))
            elif k == 'vib':
                st['vib'] = min(120, e[1])
                out.extend((0xE4, st['vib']))
            elif k == 'bend':
                d, n, arrive = e[1], e[2], e[3] if len(e) > 3 else False
                assert -128 <= d <= 127 and 0 <= n < 128
                st['bend'] = (d, n | (0x80 if arrive else 0))
                out.extend((0xEB, d & 0xFF, st['bend'][1]))
            elif k == 'loop':
                if in_rep:
                    raise MusicError(f'{where}: loop inside a repeat')
                loop[0], loop[1] = st['tick'], len(out)
                emit_state()
            elif k == 'bar':
                if st['tick'] % bar_ticks:
                    raise MusicError(f'{where}: bar line at tick {st["tick"]} (bar = {bar_ticks})')
            elif k == 'note':
                if st['inst'] is None:
                    raise MusicError(f'{where}: note before an instrument')
                inst.note_index(st['inst'], e[1], where)
                ps = pieces(e[2])
                notes.append((st['tick'], e[1], e[2], st['inst']))
                set_len(ps[0])
                out.append(0x80 + e[1] - 12)
                for d in ps[1:]:
                    set_len(d)
                    out.append(0xDC)
                st['tick'] += e[2]
            elif k in ('rest', 'tie'):
                for d in pieces(e[1]):
                    set_len(d)
                    out.append(0xDD if k == 'rest' else 0xDC)
                st['tick'] += e[1]
            elif k == 'rep':
                if in_rep:
                    raise MusicError(f'{where}: nested repeat')
                n, body = e[1], e[2]
                out.extend((0xE9, n))
                st['len'] = None
                t0 = st['tick']
                run(body, True)
                one = st['tick'] - t0
                # the notes of the repeats (for the report / analysis)
                first = [x for x in notes if x[0] >= t0]
                for r in range(1, n):
                    notes.extend((t + r * one, m, d, i) for t, m, d, i in first)
                st['tick'] += one * (n - 1)
                out.append(0xEA)
                st['len'] = None
            else:
                raise MusicError(f'{where}: unknown event {e}')
    run(auto_repeat(events), False)
    if loop[1] is not None:
        a = base + loop[1]
        out.extend((0xE5, a & 0xFF, a >> 8))
    else:
        out.append(0xE6)
    return bytes(out), st['tick'], loop[0], loop[1], notes


def compile_songs(songs, inst, base):
    """songs: [dict(name, bpm, beats, chans=[6 event lists or None], echo=(feedback, volume), chords=[...])].
    -> sequence blob for address `base`, header entries [(name, header bytes without the addresses,
    [addresses])] and a report."""
    blob = bytearray()
    entries, report = [], {}
    for sg in songs:
        name, bpm, beats = sg['name'], sg['bpm'], sg['beats']
        div = round(8000 / (bpm * TPQ / 60))
        if not 1 <= div <= 255:
            raise MusicError(f'{name}: tempo out of range')
        addrs, ticks, loop_ticks, chan_notes = [], set(), set(), []
        eon = 0
        for ci, ev in enumerate(sg['chans']):
            if ev is None:
                addrs.append(0)
                chan_notes.append([])
                continue
            data, t, lt, lo, notes = compile_channel(ev, inst, base + len(blob), TPQ * beats, f'{name} ch{ci}')
            addrs.append(base + len(blob))
            blob += data
            ticks.add(t)
            loop_ticks.add(lt)
            chan_notes.append(notes)
            if ci not in sg.get('dry', ()):
                eon |= 1 << (ci + 2)
        if len(ticks) != 1:
            raise MusicError(f'{name}: channel lengths differ {sorted(ticks)}')
        if len(loop_ticks) != 1:
            raise MusicError(f'{name}: loop points differ {sorted(loop_ticks)}')
        efb, evol = sg.get('echo', (0x38, 0x1C))
        vspeed = max(4, min(60, round(256 * sg.get('vib_hz', 5.0) / (8000 / div))))
        entries.append((name, bytes((div, efb & 0xFF, evol & 0xFF, eon, vspeed)), addrs))
        t = ticks.pop()
        lt = loop_ticks.pop()
        tps = 8000 / div
        report[name] = dict(bpm=round(tps / TPQ * 60, 2), beats=beats, bars=t / (TPQ * beats), seconds=round(t / tps, 2),
                            loop_bar=None if lt is None else lt / (TPQ * beats) + 1,
                            loop_seconds=None if lt is None else round((t - lt) / tps, 2),
                            intro_seconds=None if lt is None else round(lt / tps, 2), ticks_per_second=tps,
                            total_ticks=t, loop_tick=lt, notes=chan_notes, chords=sg.get('chords'))
    return bytes(blob), entries, report
