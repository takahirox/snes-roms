"""Recordings and numeric review of the sound of 夜鳴き鐘 (tools/yonaki/audio.py) on a real emulator.

A tiny test ROM (assembled below, 65816) uploads the SPC image through the IPL exactly as a game does,
waits for the driver's $5A, then forwards commands from a WRAM mailbox to the APU ports once per frame
(the same port-0 command / port-1 toggle a game uses).  The unmodified Snes9x 1.63 libretro core runs it;
its audio output is recorded.  Mailbox: $7E0011 = command, $7E0010 = sequence (a change sends it);
$7E0014/15 = APU ports 2/3 copied every frame, $7E0016 = 1 once the driver answered.

Output (docs/yonaki/music/review/ or the folder given):
  songs/<n>_<name>.m4a each song from its start through one loop and 9 s more (non-looping: to the end)
  sfx/<n>_<name>.m4a   each effect, alone
  amb/<name>.m4a       the ambiences alone, and rain under the 'night' song
  RESULT.json          per recording: peak, clipped samples, RMS; songs: loop-seam continuity (the
                       recording at the loop point vs the same place one loop later), pitch / chord-tone
                       share against the score, port 2 / port 3 (song and beats); effects: length, onset,
                       peak; ambience: level vs the music, droplet transient rate, spectral flatness.

usage: python3 -I tests/yonaki/music_review.py [OUT_DIR] [--only song1,sfx:bell,...] [--no-audio-files]
"""
import sys, json, math, pathlib, struct, subprocess, hashlib, wave, array, cmath, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tools/yonaki'))
from harness import Emulator                     # noqa: E402
import audio                                     # noqa: E402

FPS = 60.0988
RATE = 32040                 # the core's output rate (real time)
POS = 32000                  # DSP samples per APU second: score time -> sample index
ROMPATH = 'build/yonaki-audio/review.sfc'
MB_SEQ, MB_CMD, MB_P2, MB_P3, MB_READY = 0x10, 0x11, 0x14, 0x15, 0x16


# ------------------------------------------------------------------ the test ROM
class A65:
    def __init__(self):
        self.code = bytearray()
        self.labels = {}
        self.fix = []

    def b(self, *v):
        self.code += bytes(v)

    def label(self, n):
        self.labels[n] = len(self.code)

    def br(self, op, n):
        self.b(op, 0)
        self.fix.append((len(self.code) - 1, n))

    def link(self):
        for at, n in self.fix:
            d = self.labels[n] - (at + 1)
            assert -128 <= d <= 127
            self.code[at] = d & 0xFF
        return bytes(self.code)


def make_rom(image):
    a = A65()
    a.b(0x78, 0x18, 0xFB)                        # sei, clc, xce
    a.b(0xC2, 0x30)                              # rep #$30
    a.b(0xA2, 0xFF, 0x1F, 0x9A)                  # ldx #$1FFF, txs
    a.b(0xE2, 0x20)                              # sep #$20
    a.b(0x9C, 0x00, 0x42)                        # stz $4200
    a.b(0xA9, 0x80, 0x8D, 0x00, 0x21)            # force blank
    for z in range(0x10, 0x18):
        a.b(0x64, z)                             # stz dp
    a.label('ipl')
    a.b(0xAD, 0x40, 0x21, 0xC9, 0xAA)
    a.br(0xD0, 'ipl')
    a.b(0xAD, 0x41, 0x21, 0xC9, 0xBB)
    a.br(0xD0, 'ipl')
    a.b(0xA9, 0x00, 0x8D, 0x42, 0x21, 0xA9, 0x02, 0x8D, 0x43, 0x21)   # destination $0200
    a.b(0xA9, 0x01, 0x8D, 0x41, 0x21, 0xA9, 0xCC, 0x8D, 0x40, 0x21)
    a.label('w1')
    a.b(0xCD, 0x40, 0x21)
    a.br(0xD0, 'w1')
    a.b(0x64, 0x00)                              # counter
    chunks = [image[i:i + 0x8000] for i in range(0, len(image), 0x8000)]
    for k, ch in enumerate(chunks):
        a.b(0xA2, 0x00, 0x00)                    # ldx #0
        a.label(f'c{k}')
        a.b(0xBF, 0x00, 0x80, 1 + k)             # lda $bb8000,x
        a.b(0x8D, 0x41, 0x21)
        a.b(0xA5, 0x00, 0x8D, 0x40, 0x21)
        a.label(f'w{k}x')
        a.b(0xCD, 0x40, 0x21)
        a.br(0xD0, f'w{k}x')
        a.b(0x1A, 0x85, 0x00)                    # inc a, sta $00
        a.b(0xE8, 0xE0, len(ch) & 0xFF, len(ch) >> 8)   # inx, cpx #len
        a.br(0xD0, f'c{k}')
    a.b(0xA9, 0x00, 0x8D, 0x42, 0x21, 0xA9, 0x02, 0x8D, 0x43, 0x21)   # entry $0200
    a.b(0x9C, 0x41, 0x21)                        # stz $2141: execute
    a.b(0xA5, 0x00, 0x1A, 0x1A)
    a.br(0xD0, 'nz')
    a.b(0x1A)
    a.label('nz')
    a.b(0x8D, 0x40, 0x21)
    a.label('w2')
    a.b(0xCD, 0x40, 0x21)
    a.br(0xD0, 'w2')
    a.label('rdy')
    a.b(0xAD, 0x40, 0x21, 0xC9, 0x5A)
    a.br(0xD0, 'rdy')
    a.b(0xA9, 0x01, 0x85, MB_READY)
    a.b(0xAD, 0x41, 0x21, 0x85, 0x13)            # the port-1 value the driver has seen
    a.label('main')
    a.label('vb1')
    a.b(0xAD, 0x12, 0x42)
    a.br(0x30, 'vb1')
    a.label('vb2')
    a.b(0xAD, 0x12, 0x42)
    a.br(0x10, 'vb2')
    a.b(0xA5, MB_SEQ, 0xC5, 0x12)
    a.br(0xF0, 'skip')
    a.b(0x85, 0x12, 0xA5, MB_CMD, 0x8D, 0x40, 0x21, 0xE6, 0x13, 0xA5, 0x13, 0x8D, 0x41, 0x21)
    a.label('skip')
    a.b(0xAD, 0x42, 0x21, 0x85, MB_P2, 0xAD, 0x43, 0x21, 0x85, MB_P3)
    a.b(0x80)
    a.fix.append((len(a.code), 'main'))
    a.b(0)
    code = a.link()
    rom = bytearray(0x8000 * (1 + len(chunks)))
    rom[:len(code)] = code
    for k, ch in enumerate(chunks):
        rom[0x8000 * (1 + k):0x8000 * (1 + k) + len(ch)] = ch
    if len(rom) < 0x20000:
        rom += bytes(0x20000 - len(rom))
    hdr = 0x7FC0
    rom[hdr:hdr + 21] = b'YONAKI SOUND TEST    '
    rom[hdr + 0x15] = 0x20                       # LoROM
    rom[hdr + 0x16] = 0x00
    rom[hdr + 0x17] = 0x07                       # 128 KiB
    rom[hdr + 0x18] = 0x00
    rom[hdr + 0x19] = 0x01
    rom[hdr + 0x1A] = 0x00
    rom[0x7FFC:0x7FFE] = b'\x00\x80'             # reset
    rom[0x7FEA:0x7FEC] = b'\x00\x80'
    s = sum(rom) & 0xFFFF
    rom[0x7FDC:0x7FE0] = struct.pack('<HH', s ^ 0xFFFF, s)
    s = (sum(rom) - sum(rom[0x7FDC:0x7FE0]) + 0xFF * 2) & 0xFFFF
    rom[0x7FDC:0x7FE0] = struct.pack('<HH', s ^ 0xFFFF, s)
    return bytes(rom)


class Player:
    def __init__(self, image):
        p = ROOT / ROMPATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(make_rom(image))
        self.e = Emulator(ROMPATH)
        self.frame = 0
        self.seq = 0
        for _ in range(600):
            self.run(1)
            if self.e.ram[MB_READY] == 1:
                break
        assert self.e.ram[MB_READY] == 1, 'the driver never answered $5A'
        self.ready_frame = self.frame
        self.run(30)                              # echo writes start after 0.3 s

    def run(self, n=1):
        for _ in range(n):
            self.e.lib.retro_run()
            self.frame += 1

    def cmd(self, c):
        self.e.ram[MB_CMD] = c
        self.seq = (self.seq + 1) & 0xFF
        self.e.ram[MB_SEQ] = self.seq
        self.run(1)

    def record(self, seconds, cmd=None):
        """Record `seconds` of output; with cmd, the command is sent in the first recorded frame."""
        self.e.audio_pcm = bytearray()
        self.e.record_audio = True
        if cmd is not None:
            self.e.ram[MB_CMD] = cmd
            self.seq = (self.seq + 1) & 0xFF
            self.e.ram[MB_SEQ] = self.seq
        ports = []
        for _ in range(int(round(seconds * FPS))):
            self.run(1)
            ports.append((self.e.ram[MB_P2], self.e.ram[MB_P3]))
        self.e.record_audio = False
        return bytes(self.e.audio_pcm), ports

    def close(self):
        self.e.close()


# ------------------------------------------------------------------ analysis helpers
def to_lr(pcm):
    v = array.array('h')
    v.frombytes(pcm)
    return v[0::2], v[1::2]


def mono(pcm):
    l, r = to_lr(pcm)
    return [(a + b) * 0.5 for a, b in zip(l, r)]


def stats(pcm):
    l, r = to_lr(pcm)
    peak = max(max(map(abs, l), default=0), max(map(abs, r), default=0))
    clipped = sum(1 for x in l if abs(x) >= 32767) + sum(1 for x in r if abs(x) >= 32767)
    m = mono(pcm)
    rms = math.sqrt(sum(x * x for x in m) / max(1, len(m)))
    return dict(seconds=round(len(l) / RATE, 2), peak=peak, clipped=clipped, rms=round(rms, 1),
                rms_dbfs=round(20 * math.log10(max(rms, 1e-9) / 32768), 1))


def write_audio(pcm, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    wav = path.with_suffix('.wav')
    with wave.open(str(wav), 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(pcm)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(wav), '-c:a', 'aac', '-b:a', '192k',
                    str(path)], check=True)
    wav.unlink()


def fft(x):
    n = len(x)
    if n <= 1:
        return list(x)
    even = fft(x[0::2])
    odd = fft(x[1::2])
    out = [0j] * n
    for k in range(n // 2):
        t = cmath.exp(-2j * math.pi * k / n) * odd[k]
        out[k] = even[k] + t
        out[k + n // 2] = even[k] - t
    return out


def decimate(x, f):
    """Average groups of f samples (a crude low-pass + downsample)."""
    return [sum(x[i:i + f]) / f for i in range(0, len(x) - f + 1, f)]


def spectrum(seg, rate):
    """Magnitude^2 spectrum of seg (len power of 2), Hann window -> (bin Hz, powers)."""
    n = len(seg)
    w = [0.5 - 0.5 * math.cos(2 * math.pi * i / n) for i in range(n)]
    X = fft([s * ww for s, ww in zip(seg, w)])
    return rate / n, [abs(X[k]) ** 2 for k in range(n // 2)]


def pitch_class_energy(x, rate, t0, t1, lo=180, hi=2500):
    """Energy per pitch class (12) of x[t0:t1] seconds: FFT frames of 4096 at rate (decimated),
    peaks assigned to the nearest semitone; also the share of energy within +-30 cents of a semitone."""
    pcs = [0.0] * 12
    tuned = total = 0.0
    n = 4096
    a, b = int(t0 * rate), int(t1 * rate)
    for s in range(a, b - n + 1, n // 2):
        df, P = spectrum(x[s:s + n], rate)
        for k in range(2, len(P) - 1):
            if not (P[k] > P[k - 1] and P[k] >= P[k + 1]):
                continue
            f = k * df
            if f < lo or f > hi:
                continue
            # parabolic interpolation of the peak
            d = 0.5 * (P[k - 1] - P[k + 1]) / (P[k - 1] - 2 * P[k] + P[k + 1] or 1e-12)
            f = (k + d) * df
            midi = 69 + 12 * math.log2(f / 440)
            e = P[k]
            total += e
            cents = abs(midi - round(midi)) * 100
            if cents <= 30:
                tuned += e
            pcs[round(midi) % 12] += e
    return pcs, tuned, total


def score_pcs(notes, t0, t1, tick_rate):
    """Pitch classes the score sounds within [t0, t1) s (weight = duration overlap)."""
    w = [0.0] * 12
    for chan in notes:
        for tick, midi, dur, inst in chan:
            if inst in ('taiko', 'snare', 'shaker', 'wood', 'timp', 'stab', 'kane'):
                continue
            s, e = tick / tick_rate, (tick + dur) / tick_rate
            ov = min(e, t1) - max(s, t0)
            if ov > 0:
                w[midi % 12] += ov
    return w


def seam(x, rate, loop_start_s, loop_len_s):
    """Continuity at the loop seam: compare 0.5 s around the end of the first loop with the same window
    one loop earlier (the start of the loop body): RMS ratio and correlation of the envelopes, and the
    largest sample step around the seam vs the recording's typical step."""
    end = loop_start_s + loop_len_s
    w = 0.5
    def env(t):
        a, b = int((t - w) * rate), int((t + w) * rate)
        seg = x[max(0, a):b]
        blk = 256
        return [math.sqrt(sum(v * v for v in seg[i:i + blk]) / blk) for i in range(0, len(seg) - blk + 1, blk)]
    e1 = env(end)
    e0 = env(loop_start_s) if loop_start_s >= w else None
    a, b = int((end - 0.05) * rate), int((end + 0.05) * rate)
    seg = x[a:b]
    step = max(abs(seg[i + 1] - seg[i]) for i in range(len(seg) - 1)) if len(seg) > 1 else 0
    ref = x[int(rate):int((end - 1) * rate)][::3]
    steps = sorted(abs(ref[i + 1] - ref[i]) for i in range(len(ref) - 1))
    p999 = steps[int(len(steps) * 0.999)] * 1.0 if steps else 0
    out = dict(seam_s=round(end, 2), max_step_at_seam=round(step), p999_step_elsewhere=round(p999 / 3 * 1.0))
    if e0:
        m = min(len(e0), len(e1))
        r0 = math.sqrt(sum(v * v for v in e0[:m]) / m)
        r1 = math.sqrt(sum(v * v for v in e1[:m]) / m)
        out['rms_before_seam'] = round(r1)
        out['rms_at_loop_start'] = round(r0)
    return out


def transients(x, rate):
    """Droplet transients: onsets where the 2 ms high-passed energy jumps 2.5x over the last 20 ms."""
    hp = [x[i] - x[i - 1] for i in range(1, len(x))]
    blk = int(rate * 0.002)
    en = [sum(v * v for v in hp[i:i + blk]) / blk for i in range(0, len(hp) - blk, blk)]
    hist = 10
    cnt = 0
    last = -99
    for i in range(hist, len(en)):
        base = sum(en[i - hist:i]) / hist
        if en[i] > 2.5 * base + 1 and i - last > 3:
            cnt += 1
            last = i
    return cnt / (len(x) / rate)


def flatness(x, rate):
    """Spectral flatness (geometric / arithmetic mean of the power, 200 Hz-12 kHz), median of frames;
    white noise ~0.56 with a Hann window, a tone ~0."""
    n = 2048
    vals = []
    for s in range(0, len(x) - n, n * 4):
        df, P = spectrum(x[s:s + n], rate)
        ks = [k for k in range(len(P)) if 200 <= k * df <= 12000]
        p = [P[k] + 1e-9 for k in ks]
        g = math.exp(sum(math.log(v) for v in p) / len(p))
        vals.append(g / (sum(p) / len(p)))
    vals.sort()
    return round(vals[len(vals) // 2], 3) if vals else None


def env_modulation(x, rate):
    """Variation of the 10 ms RMS envelope (std / mean): flat noise ~0.1-0.2, droplets much higher."""
    blk = int(rate * 0.01)
    e = [math.sqrt(sum(v * v for v in x[i:i + blk]) / blk) for i in range(0, len(x) - blk, blk)]
    m = sum(e) / len(e)
    sd = math.sqrt(sum((v - m) ** 2 for v in e) / len(e))
    return round(sd / m, 3) if m else None


def onset_s(x, rate, thr=200):
    for i, v in enumerate(x):
        if abs(v) > thr:
            return round(i / rate, 3)
    return None


def decay_s(x, rate, drop_db=40):
    """Time from the peak until the 20 ms RMS stays below peak RMS - drop_db."""
    blk = int(rate * 0.02)
    e = [math.sqrt(sum(v * v for v in x[i:i + blk]) / blk) for i in range(0, len(x) - blk, blk)]
    if not e:
        return None
    k = max(range(len(e)), key=e.__getitem__)
    lim = e[k] * 10 ** (-drop_db / 20)
    last = k
    for i in range(k, len(e)):
        if e[i] > lim:
            last = i
    return round((last - k) * 0.02, 2)


# ------------------------------------------------------------------ reviews
NAMES = 'C C# D D# E F F# G G# A A# B'.split()
DRUMS = ('taiko', 'snare', 'shaker', 'wood', 'timp', 'stab', 'kane')


def chord_pcs(name):
    import songs as songsmod
    r, q = songsmod.chord(name)
    return {(r + i) % 12 for i in q}


def bar_windows(rep, beats):
    tps = rep['ticks_per_second']
    bar = 48 * beats / tps
    n = int(round(rep['total_ticks'] / (48 * beats)))
    return [(i * bar, (i + 1) * bar) for i in range(n)]


def review_song(name, rep, pcm, ports, song_index):
    x = mono(pcm)
    out = stats(pcm)
    # ports: song number + 1 while playing, beats counting
    p2 = [p for p, _ in ports]
    out['port2_values'] = sorted(set(p2))
    beats = [b for _, b in ports]
    out['port3_last_beat'] = beats[-1]
    tps = rep['ticks_per_second']
    exp_beats = int(len(ports) / FPS * tps / 48)
    out['port3_expected_about'] = exp_beats % 256
    # pitch analysis at 8 kHz
    y = decimate(x, 4)
    yr = POS / 4
    bars = bar_windows(rep, rep['beats'])
    chords = rep.get('chords') or []
    tuned = tot = on_score = on_chord = 0.0
    per_bar = []
    for bi, (t0, t1) in enumerate(bars):
        if t1 > len(y) / yr:
            break
        pcs, tu, to = pitch_class_energy(y, yr, t0 + 0.05, t1)
        tuned += tu
        tot += to
        sc = score_pcs(rep['notes'], t0, t1, tps)
        s = sum(pcs) or 1e-9
        want = {i for i in range(12) if sc[i] > 0}
        share = sum(pcs[i] for i in want) / s
        on_score += share * s
        cs = None
        if bi < len(chords):
            cp = set()
            for c in chords[bi].split():
                cp |= chord_pcs(c)
            cs = sum(pcs[i] for i in cp) / s
            on_chord += cs * s
        top = sorted(range(12), key=lambda i: -pcs[i])[:4]
        per_bar.append(dict(bar=bi + 1, score_share=round(share, 3), chord_share=None if cs is None else round(cs, 3),
                            top=[NAMES[i] for i in top]))
    s_all = sum(1 for _ in per_bar)
    energy = tot or 1e-9
    out['tuned_share'] = round(tuned / energy, 3)
    weights = 0.0
    for bi, (t0, t1) in enumerate(bars[:len(per_bar)]):
        pass
    tot_e = 0.0
    acc_s = acc_c = 0.0
    for pb, (t0, t1) in zip(per_bar, bars):
        acc_s += pb['score_share']
        acc_c += pb['chord_share'] or 0
    out['score_share_mean'] = round(acc_s / max(1, len(per_bar)), 3)
    out['chord_share_mean'] = round(acc_c / max(1, len(per_bar)), 3) if chords else None
    out['score_share_min_bar'] = min(per_bar, key=lambda b: b['score_share']) if per_bar else None
    out['bars'] = per_bar
    if rep['loop_tick'] is not None:
        ls = rep['loop_tick'] / tps
        ll = (rep['total_ticks'] - rep['loop_tick']) / tps
        out['loop'] = seam(x, POS, ls, ll)
        # the second pass must repeat the first once the tails of what came before have died away:
        # correlation of 1 s windows, 5 s (or 40 % of the loop) after the loop start, lag +-6 samples
        d = min(5.0, 0.4 * ll)
        a = int((ls + d) * POS)
        b = a + round(ll * POS)
        n = int(1 * POS)
        if b + n + 64 <= len(x):
            best = 0
            s1 = x[a:a + n]
            e1 = math.sqrt(sum(v * v for v in s1))
            for lag in range(-6, 7):
                s2 = x[b + lag:b + lag + n]
                e2 = math.sqrt(sum(v * v for v in s2))
                c = sum(p * q for p, q in zip(s1, s2)) / (e1 * e2 or 1)
                best = max(best, c)
            out['loop']['repeat_correlation'] = round(best, 4)
            # the same with 10 ms RMS envelopes over 4 s (insensitive to the phase of sustained tones:
            # key-ons may land a few DSP samples apart between passes)
            def envl(st):
                blk = int(POS * 0.01)
                return [math.sqrt(sum(v * v for v in x[i:i + blk]) / blk) for i in range(st, st + int(4 * POS), blk)]
            if b + int(4 * POS) <= len(x):
                e1, e2 = envl(a), envl(b)
                m1, m2 = sum(e1) / len(e1), sum(e2) / len(e2)
                num = sum((p - m1) * (q - m2) for p, q in zip(e1, e2))
                den = math.sqrt(sum((p - m1) ** 2 for p in e1) * sum((q - m2) ** 2 for q in e2)) or 1
                out['loop']['repeat_envelope_correlation'] = round(num / den, 4)
                out['loop']['repeat_rms_ratio'] = round(math.sqrt(sum(q * q for q in e2) / (sum(p * p for p in e1) or 1)), 3)
            out['loop']['repeat_checked_at_s'] = round(ls + d, 2)
        # the same step measure at the loop start of the first pass (an attack there is music, not a click)
        a0 = int(ls * POS)
        seg = x[max(0, a0 - int(0.05 * POS)):a0 + int(0.05 * POS)]
        if len(seg) > 1:
            out['loop']['max_step_at_first_loop_start'] = round(max(abs(seg[i + 1] - seg[i]) for i in range(len(seg) - 1)))
        # no silence at the seam (a 100 ms window just after the seam)
        a = int((ls + ll) * POS)
        seg = x[a:a + int(0.1 * POS)]
        out['loop']['rms_100ms_after_seam'] = round(math.sqrt(sum(v * v for v in seg) / max(1, len(seg))))
    return out


def review_effect(name, pcm):
    x = mono(pcm)
    out = stats(pcm)
    out['onset_s'] = onset_s(x, RATE)
    out['decay_to_-40dB_s'] = decay_s(x, RATE)
    if name.startswith('bell') or name.startswith('clock'):
        # the strongest partials over the first second after the onset
        o = int((out['onset_s'] or 0) * RATE)
        seg = x[o + 800:o + 800 + 16384]
        if len(seg) == 16384:
            df, P = spectrum(seg, RATE)
            peaks = [k for k in range(2, len(P) - 1) if P[k] > P[k - 1] and P[k] >= P[k + 1] and k * df > 150]
            peaks.sort(key=lambda k: -P[k])
            top = sorted(peaks[:8])
            if top:
                f0 = None
                strongest = max(top, key=lambda k: P[k])
                out['partials_hz'] = [round(k * df, 1) for k in top]
                out['partials_ratio_to_strongest'] = [round(k / strongest, 3) for k in top]
                out['partials_db'] = [round(10 * math.log10(P[k] / P[strongest]), 1) for k in top]
    if name in ('heart', 'knock', 'steps', 'tick', 'door'):
        blk = int(RATE * 0.01)
        e = [math.sqrt(sum(v * v for v in x[i:i + blk]) / blk) for i in range(0, len(x) - blk, blk)]
        thr = max(e) * 0.25
        hits, last = [], -99
        for i in range(len(e)):
            if e[i] > thr and (i == 0 or e[i - 1] <= thr) and i - last > 8:
                hits.append(round(i * 0.01, 2))
                last = i
        out['hits_s'] = hits
    return out


def review_amb(x):
    return dict(transients_per_s=round(transients(x, RATE), 1), spectral_flatness=flatness(x, RATE),
                envelope_variation=env_modulation(x, RATE))


def protocol_checks(p, r):
    """The CPU protocol on the real emulator: each check records what it measured and passes or fails."""
    out = {}

    def rms(pcm):
        return stats(pcm)['rms']
    song = r['songs']['title']
    # fade: port 2 drops to 0 within ~1 s and the output falls silent
    p.cmd(0x40 + song)
    p.run(240)
    p.cmd(0x60)
    pcm, ports = p.record(1.5)
    zero_at = next((i for i, (a, b) in enumerate(ports) if a == 0), None)
    tail = rms(pcm[-int(0.3 * RATE) * 4:])
    out['fade'] = dict(port2_zero_after_s=None if zero_at is None else round(zero_at / FPS, 2), tail_rms=tail,
                       ok=zero_at is not None and 0.6 <= zero_at / FPS <= 1.2 and tail < 30)
    # stop: immediate, port 2 = 0, silent after the release tails (0.5 s)
    p.cmd(0x40 + song)
    p.run(240)
    p.cmd(0x61)
    pcm, ports = p.record(1.0)
    out['stop'] = dict(port2=ports[2][0], rms_after_0_5s=rms(pcm[int(0.5 * RATE) * 4:]),
                       ok=ports[2][0] == 0 and rms(pcm[int(0.5 * RATE) * 4:]) < 30)
    # mute: exactly zero output with a song, an effect and the rain running; unmute brings them back
    p.cmd(0x40 + song)
    p.cmd(0x70)
    p.run(120)
    p.cmd(0x30)
    p.cmd(r['sfx']['bell'])                    # ignored while muted
    pcm, _ = p.record(1.0)
    st = stats(pcm)
    p.cmd(0x31)
    pcm2, _ = p.record(1.0)
    out['mute'] = dict(peak_while_muted=st['peak'], rms_after_unmute=rms(pcm2), ok=st['peak'] == 0 and rms(pcm2) > 300)
    p.cmd(0x7F)
    # duck: the music level falls by ~8 dB and comes back
    p.cmd(0x40 + r['songs']['dawn'])
    p.run(30)
    a, _ = p.record(4.0)
    p.cmd(0x40 + r['songs']['dawn'])
    p.run(29)
    p.cmd(0x62)
    b, _ = p.record(4.0)
    p.cmd(0x63)
    p.run(240)
    db = 20 * math.log10(max(1, rms(b)) / max(1, rms(a)))
    out['duck'] = dict(level_change_db=round(db, 1), ok=-11 < db < -6)
    p.cmd(0x61)
    p.run(200)
    # rapid song changes: one command per frame through every song, then the last one plays normally
    for n in r['songs'].values():
        p.cmd(0x40 + n)
    pcm, ports = p.record(2.0)
    last = max(r['songs'].values())
    out['rapid_switch'] = dict(port2=ports[-1][0], expected=last + 1, rms=rms(pcm), ok=ports[-1][0] == last + 1 and rms(pcm) > 200)
    p.cmd(0x61)
    p.run(100)
    # effects over music and the storm: both slots busy, a third effect replaces slot A; nothing clips
    p.cmd(0x40 + r['songs']['horror'])
    p.cmd(0x71)
    p.run(60)
    p.cmd(r['sfx']['thunder'])
    p.cmd(r['sfx']['bell'])
    p.cmd(r['sfx']['shock'])
    pcm, ports = p.record(6.0)
    st = stats(pcm)
    out['layered'] = dict(peak=st['peak'], clipped=st['clipped'], port2=ports[-1][0], ok=st['clipped'] == 0 and ports[-1][0] > 0)
    # effect stop: silent after 0.8 s (the echo tail of the effect dies in that time; the music stopped first)
    p.cmd(0x61)
    p.cmd(0x7F)
    p.run(200)
    p.cmd(r['sfx']['bell'])
    p.run(30)
    p.cmd(0x64)
    pcm, _ = p.record(1.0)
    out['sfx_stop'] = dict(rms_after_0_8s=rms(pcm[int(0.8 * RATE) * 4:]), ok=rms(pcm[int(0.8 * RATE) * 4:]) < 30)
    # ambience off: the rain fades out within ~1.5 s
    p.cmd(0x70)
    p.run(200)
    p.cmd(0x7F)
    pcm, _ = p.record(2.5)
    out['amb_off'] = dict(rms_first_0_3s=rms(pcm[:int(0.3 * RATE) * 4]), rms_after_1_5s=rms(pcm[int(1.5 * RATE) * 4:]),
                          ok=rms(pcm[int(1.5 * RATE) * 4:]) < 10)
    # a song that does not loop (badend) reports port 2 = 0 at its end
    rep = r['report']['badend']
    p.cmd(0x40 + r['songs']['badend'])
    pcm, ports = p.record(rep['seconds'] + 2)
    out['badend_end'] = dict(port2_end=ports[-1][0], ok=ports[-1][0] == 0)
    out['all_ok'] = all(v['ok'] for v in out.values())
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    only = None
    for a in sys.argv[1:]:
        if a.startswith('--only='):
            only = set(a[7:].split(','))
    files = '--no-audio-files' not in sys.argv
    out_dir = pathlib.Path(args[0]) if args else ROOT / 'docs/yonaki/music/review'
    t_start = time.time()
    r = audio.build()
    rec = dict(image_sha256=hashlib.sha256(r['image']).hexdigest(), core='Snes9x 1.63 libretro (unmodified)',
               rom=ROMPATH, info={k: v for k, v in r['info'].items() if k not in ('samples', 'instruments')},
               note='recordings of a test ROM that uploads the image through the IPL and sends the commands '
                    'through the APU ports; analysis in tests/yonaki/music_review.py',
               songs={}, sfx={}, amb={})
    p = Player(r['image'])
    rec['driver_ready_frame'] = p.ready_frame

    def want(key):
        return only is None or key in only

    # songs
    for name, n in r['songs'].items():
        if not want(name):
            continue
        rep = r['report'][name]
        if rep['loop_tick'] is None:
            secs = rep['seconds'] + 4
        else:
            secs = rep['intro_seconds'] + rep['loop_seconds'] + 9
        pcm, ports = p.record(secs, 0x40 + n)
        p.cmd(0x61)
        p.run(90)
        res = review_song(name, rep, pcm, ports, n)
        res['seconds_score'] = rep['seconds']
        res['loop_seconds'] = rep['loop_seconds']
        if files:
            write_audio(pcm, out_dir / 'songs' / f'{n:02d}_{name}.m4a')
            res['file'] = f'songs/{n:02d}_{name}.m4a'
        rec['songs'][name] = res
        print(name, {k: v for k, v in res.items() if k not in ('bars',)}, flush=True)
    # effects
    secs_fx = r['effect_seconds']
    for name, n in r['sfx'].items():
        if not want('sfx:' + name) and not (only and 'sfx' in only):
            continue
        pcm, _ = p.record(secs_fx[name] + 1.5, n)
        p.cmd(0x64)
        p.run(30)
        res = review_effect(name, pcm)
        res['number'] = n
        if files:
            write_audio(pcm, out_dir / 'sfx' / f'{n:02d}_{name}.m4a')
            res['file'] = f'sfx/{n:02d}_{name}.m4a'
        rec['sfx'][name] = res
        print(name, res, flush=True)
    # ambience
    if only is None or 'amb' in only:
        for name, k in r['amb'].items():
            pcm, _ = p.record(30 if name == 'storm' else 20, 0x70 + k)
            p.cmd(0x7F)
            p.run(200)
            x = mono(pcm)
            res = dict(stats(pcm), **review_amb(x[RATE * 2:]))
            if files:
                write_audio(pcm, out_dir / 'amb' / f'{name}.m4a')
                res['file'] = f'amb/{name}.m4a'
            rec['amb'][name] = res
            print(name, res, flush=True)
        # rain under the night music vs the night music alone (the same 20 s of the song)
        n = r['songs']['night']
        p.cmd(0x40 + n)
        pcm_m, _ = p.record(20)
        p.cmd(0x70)
        p.cmd(0x40 + n)
        p.run(130)                                # rain fades in (~0.7 s); restart the song after that
        p.cmd(0x40 + n)
        pcm_mr, _ = p.record(20)
        p.cmd(0x7F)
        p.cmd(0x61)
        p.run(200)
        pcm_r = rec_rain = None
        p.cmd(0x70)
        p.run(130)
        pcm_r, _ = p.record(20)
        p.cmd(0x7F)
        p.run(200)
        m, mr, rr = stats(pcm_m), stats(pcm_mr), stats(pcm_r)
        res = dict(music_rms=m['rms'], rain_rms=rr['rms'], mixed_rms=mr['rms'],
                   rain_below_music_db=round(20 * math.log10(rr['rms'] / m['rms']), 1), mixed_peak=mr['peak'],
                   mixed_clipped=mr['clipped'])
        if files:
            write_audio(pcm_mr, out_dir / 'amb' / 'rain_under_night.m4a')
            res['file'] = 'amb/rain_under_night.m4a'
        rec['amb']['rain_under_night'] = res
        print('rain_under_night', res, flush=True)
        # a white-noise reference for the ambience metrics (the same analysis on a computed signal)
        import random
        rnd = random.Random(1)
        wn = [rnd.uniform(-3000, 3000) for _ in range(RATE * 10)]
        rec['amb']['_white_noise_reference'] = review_amb(wn)
    if only is None or 'protocol' in only:
        rec['protocol'] = protocol_checks(p, r)
        print('protocol', rec['protocol'], flush=True)
    p.close()
    rec['seconds_to_run'] = round(time.time() - t_start, 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / 'RESULT.json'
    if only and path.exists():
        old = json.loads(path.read_text())
        for k in ('songs', 'sfx', 'amb'):
            old.setdefault(k, {}).update(rec[k])
        old.update({k: v for k, v in rec.items() if k not in ('songs', 'sfx', 'amb')})
        rec = old
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + '\n')


if __name__ == '__main__':
    main()
