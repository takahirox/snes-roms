"""Speech blips of 潮鳴りの密室: data/adv/voices.txt -> original BRR samples and tables for the driver.

Each voice is one short one-shot sample computed here: sine partials (the timbre) on a fundamental that
glides over the blip, shaped by a raised-cosine attack and decay to silence.  Nothing is recorded.  The
samples are made for playback at 16 kHz (DSP pitch $0800), then BRR-encoded with a search over the four
filters and the ranges against the exact decoder below (the first block uses filter 0 and starts at 0,
two silent blocks and the silent end block close the sample: the DSP silences a one-shot voice as soon
as it reaches the end block).

usage: python3 -I tools/adv/voice.py [--preview OUT.wav]   (offline preview: decoded BRR, linear
       resampling, NOT the DSP's Gaussian interpolation -- the real sound is recorded from the ROM)
"""
import math, pathlib, struct, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VOICES = ROOT / 'data/adv/voices.txt'
RATE = 16000                 # sample rate of the blips
BASE_PITCH = 0x0800          # DSP pitch for RATE (32 kHz = $1000)
PEAK = 12000                 # sample peak (16-bit scale; leaves headroom for the Gaussian interpolation)
SPEAKER_ME_NAME = 'わたし'


class VoiceError(Exception):
    pass


def parse(text=None):
    text = VOICES.read_text(encoding='utf-8') if text is None else text
    timbres, voices, silent, contour = {}, {}, None, None
    cur = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('@'):
            kind, _, name = line[1:].partition(' ')
            name = name.strip()
            if kind == 'timbre':
                cur = timbres.setdefault(name, {})
            elif kind == 'voice':
                if name in voices:
                    raise VoiceError(f'line {n}: voice {name} twice')
                cur = voices[name] = {}
            else:
                raise VoiceError(f'line {n}: unknown block @{kind}')
            continue
        key, _, val = line.partition(':')
        key, val = key.strip(), val.strip()
        if key == 'silent':
            silent = set(val.replace(' ', '')) | {'　'}
        elif key == 'contour':
            contour = [float(v) for v in val.split()]
        elif cur is None:
            raise VoiceError(f'line {n}: "{key}" outside a block')
        elif key == 'harmonics':
            cur[key] = [float(v) for v in val.split()]
        elif key == 'timbre':
            cur[key] = val
        elif key in ('pitch', 'glide', 'length', 'attack'):
            cur[key] = float(val)
        elif key in ('volume', 'gap'):
            cur[key] = int(val)
        else:
            raise VoiceError(f'line {n}: unknown key {key}')
    if silent is None or not contour or len(contour) != 8:
        raise VoiceError('silent: and contour: (8 values) are required')
    for name, v in voices.items():
        miss = {'timbre', 'pitch', 'glide', 'length', 'attack', 'volume', 'gap'} - set(v)
        if miss:
            raise VoiceError(f'voice {name}: missing {sorted(miss)}')
        if v['timbre'] not in timbres:
            raise VoiceError(f'voice {name}: no timbre {v["timbre"]}')
        if not 15 <= v['length'] <= 40 or not 1 <= v['attack'] < v['length'] / 2:
            raise VoiceError(f'voice {name}: length 15-40 ms, attack under half of it')
        if not 0 < v['volume'] < 128 or not 2 <= v['gap'] <= 30:
            raise VoiceError(f'voice {name}: volume 1-127, gap 2-30 frames')
        if v['pitch'] * len(timbres[v['timbre']]['harmonics']) >= RATE / 2 * 0.8:
            raise VoiceError(f'voice {name}: partials too high for {RATE} Hz')
    return dict(timbres=timbres, voices=voices, silent=silent, contour=contour)


def synth(v, harmonics):
    """One blip, 16-bit samples at RATE, peak PEAK, starting and ending at 0."""
    n = round(v['length'] * RATE / 1000)
    att = v['attack'] * RATE / 1000
    out, phase = [], 0.0
    for i in range(n):
        x = i / n
        f = v['pitch'] * (1 + v['glide'] / 100 * x)
        if i < att:
            env = 0.5 - 0.5 * math.cos(math.pi * i / att)
        else:
            env = 0.5 + 0.5 * math.cos(math.pi * (i - att) / (n - att))
        env *= 1 - 0.35 * x                     # a little more decay towards the end
        out.append(env * sum(a * math.sin((k + 1) * phase) for k, a in enumerate(harmonics)))
        phase += 2 * math.pi * f / RATE
    peak = max(abs(s) for s in out)
    return [round(s / peak * PEAK) for s in out]


# ------------------------------------------------------------------ BRR (exact decoder, searching encoder)
def _clamp16(s):
    return max(-32768, min(32767, s))


def brr_step(nib, shift, flt, p1, p2):
    """Decode one nibble (-8..7) like the S-DSP: returns the stored 16-bit sample."""
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
    s = ((s * 2) & 0xFFFF)
    return s - 0x10000 if s >= 0x8000 else s


def brr_decode(data):
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


def _block(target, flt, shift, p1, p2):
    nibs, err = [], 0
    for t in target:
        best = None
        est = (t - brr_step(0, shift, flt, p1, p2)) / (1 << shift)
        for nib in {max(-8, min(7, math.floor(est) + k)) for k in (-1, 0, 1, 2)}:
            s = brr_step(nib, shift, flt, p1, p2)
            e = (s - t) ** 2
            if best is None or e < best[0]:
                best = (e, nib, s)
        err += best[0]
        nibs.append(best[1])
        p2, p1 = p1, best[2]
    return err, nibs, p1, p2


def brr_encode(samples):
    """One-shot BRR: samples (16-bit) + 2 silent blocks + the silent end block (loop flag clear)."""
    pad = (-len(samples)) % 16
    samples = list(samples) + [0] * (pad + 32)
    nblk = len(samples) // 16 + 1
    out = bytearray()
    p1 = p2 = 0
    for i in range(nblk):
        target = samples[i * 16:(i + 1) * 16] if i < nblk - 1 else [0] * 16
        best = None
        for flt in ((0,) if i == 0 or i == nblk - 1 else (0, 1, 2, 3)):
            for shift in range(13):
                err, nibs, q1, q2 = _block(target, flt, shift, p1, p2)
                if best is None or err < best[0]:
                    best = (err, flt, shift, nibs, q1, q2)
        err, flt, shift, nibs, p1, p2 = best
        out.append(shift << 4 | flt << 2 | (1 if i == nblk - 1 else 0))
        for j in range(0, 16, 2):
            out.append((nibs[j] & 15) << 4 | (nibs[j + 1] & 15))
    return bytes(out)


# ------------------------------------------------------------------ tables
def build(speaker_ids, glyph_chars):
    """speaker_ids: name -> speaker id of the script (1.., 14 for わたし); glyph_chars: the font's chars.
    Returns the SPC data (samples, per-voice source/volume/pitch tables), the CPU tables and a report."""
    d = parse()
    names = list(d['voices'])
    missing = sorted(set(speaker_ids) - set(names))
    if missing:
        raise VoiceError(f'no voice for {missing}')
    extra = sorted(set(names) - set(speaker_ids))
    if extra:
        raise VoiceError(f'voices for unknown speakers {extra}')
    if len(names) > 15:
        raise VoiceError('at most 15 voices')
    contour = d['contour']
    samples, src, vol, pitch, report = [], [], [], [], []
    for name in names:
        v = d['voices'][name]
        pcm = synth(v, d['timbres'][v['timbre']]['harmonics'])
        blob = brr_encode(pcm)
        dec = brr_decode(blob)
        err = max(abs(a - b) for a, b in zip(pcm, dec))
        samples.append(blob)
        src.append(len(samples) - 1)
        vol.append(v['volume'])
        steps = [round(BASE_PITCH * (1 + c / 100)) for c in contour]
        pitch.append(steps)
        report.append(dict(name=name, speaker_id=speaker_ids[name], voice=len(report), timbre=v['timbre'],
                           pitch_hz=v['pitch'], glide_pct=v['glide'], length_ms=v['length'],
                           samples=len(pcm), brr_bytes=len(blob), brr_max_error=err, volume=v['volume'], gap=v['gap'],
                           contour_pitch=[f'${p:04X}' for p in steps]))
    speaker_voice = [0xFF] * 16
    speaker_gap = [0] * 16
    for i, name in enumerate(names):
        speaker_voice[speaker_ids[name]] = i
        speaker_gap[speaker_ids[name]] = d['voices'][name]['gap']
    glyph_voice = [0 if c in d['silent'] else 1 for c in glyph_chars]
    return dict(samples=samples, src=src, vol=vol, pitch=pitch,
                speaker_voice=speaker_voice, speaker_gap=speaker_gap, glyph_voice=glyph_voice,
                silent=''.join(sorted(d['silent'])), contour=d['contour'], report=report)


def preview(path):
    """Offline preview (NOT the ROM's sound): each voice's decoded BRR, 6 blips 4 frames apart."""
    import wave
    d = parse()
    out = []
    frame = 32000 / 60.0988
    for name, v in d['voices'].items():
        dec = brr_decode(brr_encode(synth(v, d['timbres'][v['timbre']]['harmonics'])))
        start = len(out)
        for k in range(6):
            pos = start + round(k * 4 * frame)
            step = (1 + d['contour'][k % len(d['contour'])] / 100) * 0.5     # 16 kHz -> 32 kHz
            m = int(len(dec) / step)
            while len(out) < pos + m:
                out.append(0)
            for i in range(m):
                x = i * step
                j = int(x)
                a = dec[j] if j < len(dec) else 0
                b = dec[j + 1] if j + 1 < len(dec) else 0
                out[pos + i] += round((a + (b - a) * (x - j)) * v['volume'] / 128 * 0.5)
        out += [0] * round(30 * frame)
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(32000)
        f.writeframes(struct.pack(f'<{len(out)}h', *[_clamp16(s) for s in out]))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--preview':
        preview(sys.argv[2])
    d = parse()
    for name, v in d['voices'].items():
        pcm = synth(v, d['timbres'][v['timbre']]['harmonics'])
        blob = brr_encode(pcm)
        dec = brr_decode(blob)
        print(name, len(pcm), 'samples', len(blob), 'BRR bytes', 'max error', max(abs(a - b) for a, b in zip(pcm, dec)))
