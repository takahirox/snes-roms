"""Glyphs of 夜鳴き鐘: Shinonome 12-dot Gothic (public domain, assets/shinonome), 12 px full width, 6 px ASCII.

Also the title logo: the 12-dot glyphs enlarged with Scale2x three times (8x), smoothed and resampled, so the
strokes keep the font's shapes but lose the stair steps; the style (fill gradient, outline, glow) is drawn here.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
FONT_K = ROOT / 'assets/shinonome/shnmk12.bdf'
FONT_A = ROOT / 'assets/shinonome/shnm6x12r.bdf'

# characters that the scenario may use but JIS X 0208 spells differently
MAP = {'—': '―', '–': '―', '～': '〜', '－': '−', '〰': '〜', '･': '・', '･': '・', '　': '　'}

# glyphs drawn here (not in JIS X 0208), 12 x 12, '#' = ink
CUSTOM = {
    '▸': ['............', '............', '...#........', '...##.......', '...###......', '...####.....',
               '...#####....', '...####.....', '...###......', '...##.......', '...#........', '............'],
}


def load_bdf(path, rowbytes):
    glyphs = {}
    enc = bits = None
    for line in path.read_text(encoding='latin-1').splitlines():
        if line.startswith('ENCODING'):
            enc = int(line.split()[1])
        elif line == 'BITMAP':
            bits = []
        elif line == 'ENDCHAR':
            glyphs[enc] = bits
            bits = None
        elif bits is not None:
            bits.append(int(line, 16) << (16 - 8 * rowbytes))
    return glyphs


class FontError(Exception):
    pass


class Font:
    def __init__(self):
        self.k = load_bdf(FONT_K, 2)
        self.a = load_bdf(FONT_A, 1)

    @staticmethod
    def norm(ch):
        return MAP.get(ch, ch)

    @staticmethod
    def width(ch):
        return 6 if ord(ch) < 0x80 else 12

    def has(self, ch):
        try:
            self.rows(ch)
            return True
        except FontError:
            return False

    def rows(self, ch):
        """12 rows of 16-bit masks, bit 15 = leftmost pixel."""
        if ch in CUSTOM:
            return [int(r.replace('#', '1').replace('.', '0') + '0000', 2) for r in CUSTOM[ch]]
        if ch == '　':
            return [0] * 12
        o = ord(ch)
        if o < 0x80:
            if o < 0x20 or o not in self.a:
                raise FontError(f'no half-width glyph for {ch!r}')
            return list(self.a[o])
        try:
            jis = ch.encode('iso2022_jp')
        except UnicodeEncodeError:
            raise FontError(f'character {ch!r} (U+{o:04X}) is not in JIS X 0208')
        if not (jis[:3] == b'\x1b$B' and len(jis) == 8):
            raise FontError(f'character {ch!r} (U+{o:04X}) is not a full-width JIS X 0208 glyph')
        code = jis[3] << 8 | jis[4]
        if code not in self.k:
            raise FontError(f'no glyph for {ch!r} (JIS {code:04X})')
        return list(self.k[code])


# ------------------------------------------------------------------ smooth large glyphs
def _scale2x(g):
    h, w = len(g), len(g[0])
    out = [[0] * (w * 2) for _ in range(h * 2)]
    for y in range(h):
        for x in range(w):
            p = g[y][x]
            a = g[y - 1][x] if y > 0 else 0
            b = g[y][x + 1] if x + 1 < w else 0
            c = g[y][x - 1] if x > 0 else 0
            d = g[y + 1][x] if y + 1 < h else 0
            e0 = e1 = e2 = e3 = p
            if c == a and c != d and a != b:
                e0 = a
            if a == b and a != c and b != d:
                e1 = b
            if d == c and d != b and c != a:
                e2 = c
            if b == d and b != a and d != c:
                e3 = d
            out[2 * y][2 * x], out[2 * y][2 * x + 1], out[2 * y + 1][2 * x], out[2 * y + 1][2 * x + 1] = e0, e1, e2, e3
    return out


def smooth_glyph(font, ch, size, bold=0):
    """Coverage (numpy float array size x size, 0..1) of ch enlarged smoothly to size px."""
    import sys
    sys.path.insert(0, str(ROOT / 'tools/vendor/pylib'))
    import numpy as np
    from PIL import Image, ImageFilter
    rows = font.rows(ch)
    w = font.width(ch)
    g = [[1 if rows[y] >> (15 - x) & 1 else 0 for x in range(w)] for y in range(12)]
    # one empty pixel of margin so the scaler sees the edges
    g = [[0] * (w + 2)] + [[0] + r + [0] for r in g] + [[0] * (w + 2)]
    for _ in range(3):
        g = _scale2x(g)
    a = np.array(g, np.uint8) * 255
    im = Image.fromarray(a)
    if bold:
        im = im.filter(ImageFilter.MaxFilter(bold * 2 + 1))
    im = im.filter(ImageFilter.GaussianBlur(2.2))
    # sharpen the edge again (a soft threshold), then resample
    arr = np.asarray(im, float) / 255
    arr = np.clip((arr - 0.5) * 3 + 0.5, 0, 1)
    # the 12 px cell + 1 px margin each side -> (cell + 2) * size / 12 px, margins included
    ow, oh = round((w + 2) * size / 12), round(14 * size / 12)
    im = Image.fromarray((arr * 255).astype(np.uint8)).resize((ow, oh), Image.LANCZOS)
    return np.clip(np.asarray(im, float) / 255, 0, 1)
