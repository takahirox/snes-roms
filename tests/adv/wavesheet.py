"""Waveform pictures of recorded PCM for the speech-blip review (no audio is judged here).

sheet(x, spans, blips, path): one row per span (min/max envelope, 1 px = 4 ms) with tick marks at the
detected blip onsets, and one zoomed blip per speaker (1 px = 2 samples) under it.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))
import png_codec

BG, AXIS, WAVE, TICK, TEXT = (16, 20, 32), (60, 66, 90), (120, 200, 255), (255, 210, 80), (200, 200, 200)


def _canvas(w, h):
    return [[BG] * w for _ in range(h)]


def _wave(img, x, a, b, x0, y0, w, h, per_px, scale):
    mid = y0 + h // 2
    for px in range(w):
        img[mid][x0 + px] = AXIS
    for px in range(w):
        s0 = a + px * per_px
        if s0 >= b:
            break
        seg = x[s0:min(b, s0 + per_px)]
        lo, hi = min(seg), max(seg)
        y_hi = max(y0, mid - round(hi / scale * (h // 2)))
        y_lo = min(y0 + h - 1, mid - round(lo / scale * (h // 2)))
        for y in range(y_hi, y_lo + 1):
            img[y][x0 + px] = WAVE


def sheet(x, spans, zooms, path, rate=32040, scale=4000):
    """spans: [(label, first sample, last sample, [onset samples])]; zooms: [(label, a, b)]."""
    per_px = rate // 250
    width = max(max((b - a) // per_px for _, a, b, _ in spans) + 8, 8 + len(zooms) * 260)
    rows_h = 64
    height = len(spans) * (rows_h + 6) + 140
    img = _canvas(width, height)
    y = 2
    for label, a, b, onsets in spans:
        _wave(img, x, a, b, 4, y, width - 8, rows_h, per_px, scale)
        for o in onsets:
            px = 4 + (o - a) // per_px
            if 4 <= px < width - 4:
                for k in range(4):
                    img[y + k][px] = TICK
        y += rows_h + 6
    for i, (label, a, b) in enumerate(zooms):
        _wave(img, x, a, b, 4 + i * 260, y + 4, 250, 128, 2, scale / 2)
    png_codec.write(pathlib.Path(path), img)
