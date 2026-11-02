"""The title logo 夜鳴き鐘, drawn from the Shinonome 12-dot glyphs (public domain) enlarged smoothly
(font.smooth_glyph), written vertically, with a cold pale fill, a dark outline and a soft shadow.
It is composited into the title photo before quantizing (pictures.titled), so it gets the photo's 240 colours.
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor/pylib'))
sys.path.insert(0, str(ROOT / 'tools/yonaki'))
import numpy as np                       # noqa: E402
from PIL import Image, ImageFilter       # noqa: E402
import font as fontmod                    # noqa: E402

TEXT = '夜鳴き鐘'
SIZE = 44            # px per character
GAP = -2             # extra px between characters (the glyph cells have their own margin)


MASK = ROOT / 'assets/yonaki/logo/yonakigane_mask.png'


def coverage(font, text=TEXT, size=SIZE, vertical=True, bold=1):
    """Vertical coverage of the logo text: the Noto Serif rendering (assets/yonaki/logo) when it is there and
    the text is the title, else the smoothed Shinonome glyphs."""
    if text == TEXT and MASK.exists() and vertical:
        m = Image.open(MASK).convert('L')
        cell = m.width
        n = m.height // cell
        # emboldened a little at the high resolution, then resampled per character (tight vertical pitch)
        m = m.filter(ImageFilter.MaxFilter(5))
        cells = []
        for i in range(n):
            c = np.asarray(m.crop((0, i * cell, cell, (i + 1) * cell)), float)
            ys = np.nonzero(c.max(1) > 0)[0]
            c = c[max(0, ys.min() - 8):ys.max() + 8]
            im = Image.fromarray(c.astype(np.uint8))
            cells.append(np.asarray(im.resize((size, max(1, round(im.height * size / cell))), Image.LANCZOS),
                                    float) / 255)
        h = sum(c.shape[0] for c in cells) + 2 * (len(cells) - 1)
        out = np.zeros((h, size))
        y = 0
        for c in cells:
            out[y:y + c.shape[0]] = np.maximum(out[y:y + c.shape[0]], c)
            y += c.shape[0] + 2
        return np.clip(out, 0, 1)
    cells = [fontmod.smooth_glyph(font, ch, size, bold=bold) for ch in text]
    ch, cw = cells[0].shape
    if vertical:
        h = sum(c.shape[0] for c in cells) + GAP * (len(cells) - 1)
        out = np.zeros((h, cw))
        y = 0
        for c in cells:
            out[y:y + c.shape[0], :c.shape[1]] = np.maximum(out[y:y + c.shape[0], :c.shape[1]], c)
            y += c.shape[0] + GAP
    else:
        w = sum(c.shape[1] for c in cells) + GAP * (len(cells) - 1)
        out = np.zeros((ch, w))
        x = 0
        for c in cells:
            out[:, x:x + c.shape[1]] = np.maximum(out[:, x:x + c.shape[1]], c)
            x += c.shape[1] + GAP
    return out


def logo_rgba(font, text=TEXT, size=SIZE, vertical=True):
    cov = coverage(font, text, size, vertical)
    pad = 6
    cov = np.pad(cov, pad)
    h, w = cov.shape
    # outline: the coverage grown by about 1.5 px
    im = Image.fromarray((cov * 255).astype(np.uint8))
    outline = np.asarray(im.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.7)), float) / 255
    shadow = np.asarray(im.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(2.5)), float) / 255
    shadow = np.roll(np.roll(shadow, 2, 0), 1, 1)
    # fill: pale silver-blue at the top of each stroke area to white-ish, slightly darker toward the bottom
    yy = np.linspace(0, 1, h)[:, None]
    fill = np.stack([np.full((h, w), 1.0) * (236 - 40 * yy), np.full((h, w), 1.0) * (240 - 30 * yy),
                     np.full((h, w), 1.0) * (250 - 6 * yy)], 2)
    dark = np.array([6, 8, 22], float)
    pre = np.zeros((h, w, 3))          # premultiplied colour
    alpha = np.zeros((h, w))
    for a, c in ((shadow * 0.8, dark), (outline, dark * 0.6), (cov, fill)):
        c = c if np.ndim(c) == 3 else np.broadcast_to(c, (h, w, 3))
        pre = pre * (1 - a[..., None]) + c * a[..., None]
        alpha = alpha * (1 - a) + a
    rgb = pre / np.maximum(alpha[..., None], 1e-6)
    return np.concatenate([np.clip(rgb, 0, 255), (alpha * 255)[..., None]], 2).astype(np.uint8)


if __name__ == '__main__':
    f = fontmod.Font()
    lg = logo_rgba(f)
    out = ROOT / 'build/yonaki/logo.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(lg).save(out)
    big = Image.fromarray(lg)
    bg = Image.new('RGBA', big.size, (60, 60, 70, 255))
    bg.alpha_composite(big)
    bg.resize((big.width * 3, big.height * 3), Image.NEAREST).save(ROOT / 'build/yonaki/logo_x3.png')
    print(lg.shape)
