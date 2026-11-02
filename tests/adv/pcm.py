"""PCM analysis of the emulator's audio output for the speech-blip tests (tests/adv/speech.py).

Input: 16-bit stereo PCM (the core's audio callback, 32040 Hz).  Blips are found as runs of samples
above a threshold (gaps under 3 ms merged); for each: onset, length, peak, RMS, DC (mean / peak), the
first and last sample above the threshold, the largest sample-to-sample step (clicks), clipped samples,
and the fundamental by autocorrelation over the blip's middle (150-900 Hz: the speech range only; a
higher tone such as an effect is reported as a sub-multiple, so f0 is not used for the effects).
"""
import struct, math

RATE = 32040


def mono(pcm):
    v = struct.unpack(f'<{len(pcm) // 2}h', pcm)
    return [(v[i] + v[i + 1]) // 2 for i in range(0, len(v) - 1, 2)], v


def segments(x, thr=40, merge=0.003, rate=RATE):
    gap = int(merge * rate)
    segs = []
    start = last = None
    for i, s in enumerate(x):
        if abs(s) > thr:
            if start is None:
                start = i
            elif i - last > gap:
                segs.append((start, last + 1))
                start = i
            last = i
    if start is not None:
        segs.append((start, last + 1))
    return segs


def f0(x, a, b, lo=150, hi=900, rate=RATE):
    """Fundamental (Hz) of x[a:b] by normalized autocorrelation, the first strong peak."""
    n = b - a
    seg = x[a + n // 6:a + n * 4 // 5]
    if len(seg) < rate // lo + 8:
        seg = x[a:b]
    m = sum(seg) / len(seg)
    seg = [s - m for s in seg]
    e0 = sum(s * s for s in seg) or 1
    best = (0, None)
    cands = []
    for lag in range(int(rate // hi), min(int(rate // lo), len(seg) - 4) + 1):
        c = sum(seg[i] * seg[i + lag] for i in range(len(seg) - lag)) / e0 * len(seg) / (len(seg) - lag)
        cands.append((lag, c))
        if c > best[0]:
            best = (c, lag)
    if best[1] is None:
        return None, 0
    # the first local maximum above 85 % of the best one (avoids the octave below)
    for i in range(1, len(cands) - 1):
        lag, c = cands[i]
        if c >= 0.85 * best[0] and c >= cands[i - 1][1] and c >= cands[i + 1][1]:
            l0, c0 = cands[i - 1]
            l2, c2 = cands[i + 1]
            den = c0 - 2 * c + c2
            shift = 0.5 * (c0 - c2) / den if den else 0
            return rate / (lag + shift), round(c, 3)
    return rate / best[1], round(best[0], 3)


def describe(x, a, b, thr=40, rate=RATE):
    seg = x[a:b]
    peak = max(abs(s) for s in seg)
    rms = math.sqrt(sum(s * s for s in seg) / len(seg))
    step = max(abs(seg[i + 1] - seg[i]) for i in range(len(seg) - 1)) if len(seg) > 1 else 0
    hz, corr = f0(x, a, b, rate=rate)
    return dict(onset=a, length_ms=round((b - a) * 1000 / rate, 1), peak=peak, rms=round(rms, 1),
                dc=round(sum(seg) / len(seg) / peak, 4) if peak else 0, max_step=step,
                max_step_ratio=round(step / peak, 3) if peak else 0,
                edge_in=abs(x[a]), edge_out=abs(x[b - 1]), clipped=sum(1 for s in seg if abs(s) >= 32767),
                f0=round(hz, 1) if hz else None, f0_corr=corr)
