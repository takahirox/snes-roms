"""Pictures for 潮鳴りの密室: 256x128 RGB -> 240 colours (CGRAM 16-255) -> 512 8bpp tiles (one LoROM bank).

Pure Python (no Pillow/numpy): median cut on 15-bit colours weighted by pixel count, refined by a few
k-means passes, then nearest-colour mapping (weighted RGB distance).  Portraits (72x104 RGBA) are
alpha-composited over the picture at build time; the picture and every composited portrait are
quantized together so the portrait tiles share the picture's 240 colours.  The mouth frames of a
portrait (data/adv/mouths.txt, applied by tools/adv/mouth.py) are composited the same way and their
patch pixels join the histogram, so the lip-sync tiles use the same palette.  Deterministic.
"""
import json, hashlib, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import png_codec

W, H = 256, 128
COLORS = 240
CACHE = ROOT / 'build/adv/cache'
WR, WG, WB = 3, 4, 2


def c5(v):
    return (v * 31 + 127) // 255


def load(path, size=None):
    rows = png_codec.read(path)
    if size and (len(rows[0]), len(rows)) != size:
        raise ValueError(f'{path}: {len(rows[0])}x{len(rows)}, expected {size[0]}x{size[1]}')
    return rows


def composite(base, portrait, x0, y0):
    out = [list(r) for r in base]
    for y, row in enumerate(portrait):
        for x, (r, g, b, a) in enumerate(row):
            if a == 0:
                continue
            br, bg, bb = out[y0 + y][x0 + x][:3]
            out[y0 + y][x0 + x] = ((r * a + br * (255 - a) + 127) // 255, (g * a + bg * (255 - a) + 127) // 255,
                                   (b * a + bb * (255 - a) + 127) // 255, 255)
    return out


def dist(a, b):
    return WR * (a[0] - b[0]) ** 2 + WG * (a[1] - b[1]) ** 2 + WB * (a[2] - b[2]) ** 2


def median_cut(hist, n):
    boxes = [sorted(hist.items())]
    while len(boxes) < n:
        best, score = None, -1
        for i, b in enumerate(boxes):
            if len(b) < 2:
                continue
            cnt = sum(c for _, c in b)
            rng = max(max(col[k] for col, _ in b) - min(col[k] for col, _ in b) for k in range(3))
            s = rng * rng * cnt
            if s > score:
                best, score = i, s
        if best is None:
            break
        b = boxes.pop(best)
        ranges = [max(col[k] for col, _ in b) - min(col[k] for col, _ in b) for k in range(3)]
        axis = max(range(3), key=lambda k: (ranges[k] * (WR, WG, WB)[k], -k))
        b.sort(key=lambda e: (e[0][axis], e[0]))
        total = sum(c for _, c in b)
        acc, cut = 0, 1
        for i, (_, c) in enumerate(b):
            acc += c
            if acc * 2 >= total:
                cut = min(max(i + 1, 1), len(b) - 1)
                break
        boxes.insert(best, b[:cut])
        boxes.insert(best + 1, b[cut:])
    pal = []
    for b in boxes:
        cnt = sum(c for _, c in b)
        pal.append(tuple((sum(col[k] * c for col, c in b) + cnt // 2) // cnt for k in range(3)))
    return pal


def nearest_map(colors, pal):
    out = {}
    for col in colors:
        bi, bd = 0, 1 << 30
        for i, p in enumerate(pal):
            d = WR * (col[0] - p[0]) ** 2 + WG * (col[1] - p[1]) ** 2 + WB * (col[2] - p[2]) ** 2
            if d < bd:
                bi, bd = i, d
                if d == 0:
                    break
        out[col] = bi
    return out


def quantize(hist):
    pal = median_cut(hist, COLORS)
    for _ in range(3):                       # k-means refinement
        m = nearest_map(hist, pal)
        acc = [[0, 0, 0, 0] for _ in pal]
        for col, c in hist.items():
            a = acc[m[col]]
            a[0] += col[0] * c; a[1] += col[1] * c; a[2] += col[2] * c; a[3] += c
        pal = [tuple((a[k] + a[3] // 2) // a[3] for k in range(3)) if a[3] else pal[i] for i, a in enumerate(acc)]
    pal = sorted(set(pal))
    return pal, nearest_map(hist, pal)


def tile8(idx, tx, ty):
    t = bytearray(64)
    for y in range(8):
        for x in range(8):
            v = idx[ty * 8 + y][tx * 8 + x] + 16
            bit = 0x80 >> x
            for p in range(8):
                if v >> p & 1:
                    t[(p >> 1) * 16 + y * 2 + (p & 1)] |= bit
    return bytes(t)


def convert(path, portraits):
    """portraits: list of (png path, x, y) or (png path, x, y, mouth) with x, y multiples of 8.  mouth =
    dict(key, patch=(x, y, w, h) in portrait pixels, rect=(tx, ty, tw, th) picture tiles, variants=[RGBA
    rows of the half-open and the open portrait]).  Returns tiles/palette/portrait tiles (+ mouth tiles:
    closed, half, open, each tw x th tiles row-major)."""
    key = hashlib.sha256(pathlib.Path(__file__).read_bytes() + pathlib.Path(path).read_bytes()
                         + b''.join(pathlib.Path(p[0]).read_bytes() + f'{p[1]},{p[2]}'.encode()
                                    + (p[3]['key'].encode() if len(p) > 3 and p[3] else b'') for p in portraits)).hexdigest()
    cache = CACHE / f'{key}.json'
    if cache.exists():
        d = json.loads(cache.read_text())
        return dict(tiles=bytes.fromhex(d['tiles']), palette=d['palette'], stats=d['stats'],
                    portraits=[dict(w=p['w'], h=p['h'], tiles=bytes.fromhex(p['tiles']),
                                    mouth=dict(p['mouth'], frames=[bytes.fromhex(f) for f in p['mouth']['frames']])
                                    if p.get('mouth') else None) for p in d['portraits']])
    base = load(path, (W, H))
    comps = []
    for p in portraits:
        p, x, y, mouth = (tuple(p) + (None,))[:4]
        pr = load(p)
        pw, ph = len(pr[0]), len(pr)
        if x % 8 or y % 8 or x + pw > W or y + ph > H or pw % 8 or ph % 8:
            raise ValueError(f'portrait {p} at {x},{y} ({pw}x{ph}) must be tile-aligned inside the picture')
        variants = [composite(base, v, x, y) for v in mouth['variants']] if mouth else []
        comps.append((composite(base, pr, x, y), x, y, pw, ph, mouth, variants))
    to5 = lambda px: (c5(px[0]), c5(px[1]), c5(px[2]))
    hist = {}
    for row in base:
        for px in row:
            k = to5(px)
            hist[k] = hist.get(k, 0) + 1
    for img, x, y, pw, ph, mouth, variants in comps:
        for yy in range(y, y + ph):
            for xx in range(x, x + pw):
                k = to5(img[yy][xx])
                hist[k] = hist.get(k, 0) + 1
        # the mouth frames: their patch pixels are counted too (the closed mouth is the portrait itself)
        if mouth:
            mx, my, mw, mh = mouth['patch']
            for v in variants:
                for yy in range(y + my, y + my + mh):
                    for xx in range(x + mx, x + mx + mw):
                        k = to5(v[yy][xx])
                        hist[k] = hist.get(k, 0) + 1
    pal, m = quantize(hist)
    err = 0
    idx = [[m[to5(px)] for px in row] for row in base]
    for row in base:
        for px in row:
            err += dist(to5(px), pal[m[to5(px)]])
    tiles = b''.join(tile8(idx, tx, ty) for ty in range(H // 8) for tx in range(W // 8))
    assert len(tiles) == 32768
    out_p = []
    for img, x, y, pw, ph, mouth, variants in comps:
        cidx = [[m[to5(px)] for px in row] for row in img]
        data = b''.join(tile8(cidx, tx, ty) for ty in range(y // 8, (y + ph) // 8) for tx in range(x // 8, (x + pw) // 8))
        mo = None
        if mouth:
            tx0, ty0, tw, th = mouth['rect']
            frames, errs = [], []
            for f, v in enumerate([img] + variants):
                vidx = cidx if f == 0 else [[m[to5(px)] for px in row] for row in v]
                frames.append(b''.join(tile8(vidx, tx, ty) for ty in range(ty0, ty0 + th) for tx in range(tx0, tx0 + tw)))
                mx, my, mw, mh = mouth['patch']
                e = [dist(to5(v[yy][xx]), pal[vidx[yy][xx]]) for yy in range(y + my, y + my + mh)
                     for xx in range(x + mx, x + mx + mw)]
                errs.append(dict(mean=round(sum(e) / len(e), 3), max=max(e)))
            mo = dict(rect=list(mouth['rect']), frames=frames, patch_error=errs)
        out_p.append(dict(w=pw // 8, h=ph // 8, tiles=data, mouth=mo))
    palette = [b << 10 | g << 5 | r for r, g, b in pal] + [0] * (COLORS - len(pal))
    stats = dict(unique_15bit=len(hist), palette_used=len(pal), mean_weighted_error=round(err / (W * H), 3))
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(dict(tiles=tiles.hex(), palette=palette, stats=stats,
                                     portraits=[dict(w=p['w'], h=p['h'], tiles=p['tiles'].hex(),
                                                     mouth=dict(p['mouth'], frames=[f.hex() for f in p['mouth']['frames']])
                                                     if p['mouth'] else None) for p in out_p])))
    return dict(tiles=tiles, palette=palette, stats=stats, portraits=out_p)


def logo_tiles(font, text):
    """Title logo: the 12-dot glyphs doubled to 24 px, white (2) with a dark shadow (4) on the panel (1).
    Returned as 3 tile rows x (len*3) tiles of 4bpp, row-major, for a copy into the text bitmap."""
    wpx = len(text) * 24
    tw = wpx // 8
    pix = [[1] * wpx for _ in range(24)]
    shadow = [[0] * wpx for _ in range(24)]
    for i, ch in enumerate(text):
        rows = font.rows(ch)
        for y in range(12):
            for x in range(12):
                if rows[y] >> (15 - x) & 1:
                    for dy in range(2):
                        for dx in range(2):
                            X, Y = i * 24 + x * 2 + dx, y * 2 + dy
                            pix[Y][X] = 2
                            if X + 1 < wpx and Y + 1 < 24:
                                shadow[Y + 1][X + 1] = 1
    for y in range(24):
        for x in range(wpx):
            if shadow[y][x] and pix[y][x] == 1:
                pix[y][x] = 4
    out = bytearray()
    for ty in range(3):
        for tx in range(tw):
            t = bytearray(32)
            for y in range(8):
                for x in range(8):
                    v = pix[ty * 8 + y][tx * 8 + x]
                    for p in range(4):
                        if v >> p & 1:
                            t[(p >> 1) * 16 + y * 2 + (p & 1)] |= 0x80 >> x
            out += t
    return bytes(out)


def tiles4(img, r0, r1):
    out = bytearray()
    for ty in range(r0, r1):
        for tx in range(32):
            t = bytearray(32)
            for y in range(8):
                for x in range(8):
                    v = img[ty * 8 + y][tx * 8 + x]
                    for p in range(4):
                        if v >> p & 1:
                            t[(p >> 1) * 16 + y * 2 + (p & 1)] |= 0x80 >> x
            out += t
    return bytes(out)


def panel_templates():
    """Text-layer templates (4bpp, bitmap order): header rows 0-1 (2 KiB), the panel rows 2-11 for
    messages (frame only, 10 KiB) and for commands (frame + divider, 10 KiB).  The engine restores
    whole-tile rectangles from these by DMA instead of clearing with the CPU.  The coordinates must
    match the layout constants of src/adv/shionari.s (bitmap y = screen y - 128 below the picture)."""
    b = [[1] * 256 for _ in range(96)]

    def hline(img, x0, x1, y, c):
        for x in range(x0, x1 + 1):
            img[y][x] = c

    def vline(img, x, y0, y1, c):
        for y in range(y0, y1 + 1):
            img[y][x] = c
    hline(b, 0, 255, 15, 4)                    # header rule
    hline(b, 5, 250, 18, 3)                    # panel frame
    hline(b, 5, 250, 93, 3)
    vline(b, 3, 20, 91, 3)
    vline(b, 252, 20, 91, 3)
    for x, y in ((4, 19), (251, 19), (4, 92), (251, 92)):
        b[y][x] = 3
    hline(b, 6, 249, 19, 4)                    # inner shade
    vline(b, 4, 21, 90, 4)
    c = [row[:] for row in b]
    vline(c, 76, 22, 22 + 4 * 14 + 11, 4)     # divider of the command layout
    data = tiles4(b, 0, 2) + tiles4(b, 2, 12) + tiles4(c, 2, 12)
    assert len(data) == 2048 + 2 * 10240
    return data
