"""Pictures of 夜鳴き鐘: photos -> 256x192 8bpp tiles (240 colours, CGRAM 16-255), silhouettes -> 2-bit masks.

Backgrounds (assets/yonaki/src/bg/<id>.png, 4:3, any size): Lanczos resize to 256x192, a mild unsharp mask,
palette by median cut refined with weighted k-means on the 15-bit colours, snapped to the SNES 5-bit grid, then
dithered (default: serpentine Floyd-Steinberg with damped error, see DITHER) and cut into 768 8bpp tiles (32 per
row, row-major), pixel value = palette index + 16.

Silhouettes (assets/yonaki/src/sil/<id>.png, solid black figure on white): threshold, crop to the figure,
area-resample so the figure is SIL_HEIGHT pixels tall, re-threshold, pad to a whole number of tiles (figure
centred, feet on the last row) and mark a 1-pixel rim on the outer edge of the figure.  Mask format: per tile
(row-major, w x h tiles) 8 rows x 2 bytes (cover, rim) with bit 7 = left pixel.

Staged silhouettes (assets/yonaki/src/stage/<bg>__<name>__<key>.png, the background with the person painted flat
magenta, tools/yonaki/gen_stage.py): the magenta coverage through the background's crop and resize, specks
dropped, small holes filled, cut to the tiles it covers; the mask keeps its place (x, top in tiles).

Requires Pillow and numpy (tools/vendor/pylib, installed with `pip install --target tools/vendor/pylib pillow
numpy`, or the interpreter's own site-packages).  Results are cached by content hash in build/yonaki/cache.
"""
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor/pylib'))
import numpy as np                                   # noqa: E402
from PIL import Image, ImageFilter                   # noqa: E402

W, H = 256, 192
COLORS = 240
SIL_HEIGHT = 160
CACHE = ROOT / 'build/yonaki/cache'
WEIGHT = np.array([0.299, 0.587, 0.114]) * 3        # distance weights (gamma-encoded RGB)
DITHER = 'fs'                                       # 'fs' (damped error diffusion), 'bayer', 'none'
FS_DAMP = 0.75
VERSION = b'pictures-v3'


def _key(*parts):
    h = hashlib.sha256(VERSION + pathlib.Path(__file__).read_bytes())
    for p in parts:
        h.update(p if isinstance(p, bytes) else repr(p).encode())
    return h.hexdigest()


def to_snes(c):
    """8-bit -> 5-bit -> the colour the SNES shows (8-bit)."""
    c5 = np.clip(np.round(np.asarray(c, float) * 31 / 255), 0, 31).astype(int)
    return c5, (c5 << 3) | (c5 >> 2)


def resize_photo(img):
    img = img.convert('RGB')
    if img.size != (W, H):
        # crop to 4:3 first if needed
        w, h = img.size
        if w * 3 != h * 4:
            if w * 3 > h * 4:
                nw = h * 4 // 3
                img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
            else:
                nh = w * 3 // 4
                img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
        img = img.resize((W, H), Image.LANCZOS, reducing_gap=3.0)
    return img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=45, threshold=2))


def _kmeans(pix, pal, iters=8):
    """pix: (N,3) float, counts folded in by using unique colours with weights."""
    cols, counts = np.unique((pix / 4).round().astype(int), axis=0, return_counts=True)
    cols = cols * 4.0
    wts = counts.astype(float)
    for _ in range(iters):
        idx = _nearest(cols, pal)
        new = pal.copy()
        for k in range(len(pal)):
            m = idx == k
            if m.any():
                new[k] = (cols[m] * wts[m, None]).sum(0) / wts[m].sum()
        if np.allclose(new, pal, atol=0.25):
            pal = new
            break
        pal = new
    return pal


def _nearest(cols, pal, chunk=16384):
    out = np.empty(len(cols), int)
    pw = pal * np.sqrt(WEIGHT)
    for i in range(0, len(cols), chunk):
        c = cols[i:i + chunk] * np.sqrt(WEIGHT)
        d = ((c[:, None, :] - pw[None, :, :]) ** 2).sum(2)
        out[i:i + chunk] = d.argmin(1)
    return out


def make_palette(arr, n=COLORS):
    """Median cut + k-means, then on the SNES grid: centres that snap onto the same 15-bit colour are moved to
    the colours with the largest error and the k-means runs again, so the 240 entries stay distinct."""
    _, shown = to_snes(arr.reshape(-1, 3))
    cols, counts = np.unique(shown, axis=0, return_counts=True)
    cols = cols.astype(float)
    if len(cols) <= n:
        return cols
    img = Image.fromarray(arr.astype(np.uint8))
    q = img.quantize(colors=n, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = np.array(q.getpalette()[:n * 3], float).reshape(-1, 3)
    wts = counts.astype(float)
    for rnd in range(6):
        for _ in range(6):
            idx = _nearest(cols, pal)
            sums = np.zeros_like(pal)
            np.add.at(sums, idx, cols * wts[:, None])
            tot = np.bincount(idx, wts, minlength=len(pal))
            m = tot > 0
            pal[m] = sums[m] / tot[m, None]
        _, snapped = to_snes(pal)
        uniq = np.unique(snapped, axis=0).astype(float)
        if len(uniq) >= n or rnd == 5:
            pal = uniq
            break
        # refill: the colours worst served by the snapped palette
        idx = _nearest(cols, uniq)
        err = (((cols - uniq[idx]) ** 2) * WEIGHT).sum(1) * wts
        worst = cols[np.argsort(-err)[:n - len(uniq)]]
        pal = np.concatenate([uniq, worst])
    return pal[:n]


def _lut(pal):
    """Nearest palette index for every colour of a 64-level grid (index r*4096+g*64+b)."""
    g = np.arange(64) * 255 / 63
    r, gg, b = np.meshgrid(g, g, g, indexing='ij')
    cols = np.stack([r.ravel(), gg.ravel(), b.ravel()], 1)
    return _nearest(cols, pal)


BAYER8 = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
                   [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
                   [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                   [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]]) / 64.0 - 0.5


def dither(arr, pal, method=DITHER):
    a = arr.astype(float)
    if method == 'none':
        return _nearest(a.reshape(-1, 3), pal).reshape(H, W)
    if method == 'bayer':
        t = np.tile(BAYER8, (H // 8, W // 8))[..., None] * 8.0
        return _nearest(np.clip(a + t, 0, 255).reshape(-1, 3), pal).reshape(H, W)
    lut = _lut(pal)
    palf = pal.tolist()
    err = [[0.0, 0.0, 0.0] for _ in range(W + 2)]
    out = np.zeros((H, W), int)
    rows = a.tolist()
    for y in range(H):
        nxt = [[0.0, 0.0, 0.0] for _ in range(W + 2)]
        row = rows[y]
        xs = range(W) if y % 2 == 0 else range(W - 1, -1, -1)
        d = 1 if y % 2 == 0 else -1
        for x in xs:
            e = err[x + 1]
            r = min(255.0, max(0.0, row[x][0] + e[0]))
            g = min(255.0, max(0.0, row[x][1] + e[1]))
            b = min(255.0, max(0.0, row[x][2] + e[2]))
            k = lut[int(r * 63 / 255 + 0.5) * 4096 + int(g * 63 / 255 + 0.5) * 64 + int(b * 63 / 255 + 0.5)]
            out[y, x] = k
            p = palf[k]
            er, eg, eb = (r - p[0]) * FS_DAMP, (g - p[1]) * FS_DAMP, (b - p[2]) * FS_DAMP
            for (dx, tgt, f) in ((d, err, 7 / 16), (-d, nxt, 3 / 16), (0, nxt, 5 / 16), (d, nxt, 1 / 16)):
                c = tgt[x + 1 + dx]
                c[0] += er * f
                c[1] += eg * f
                c[2] += eb * f
        err = nxt
    return out


def tiles8(idx, base=16):
    """(H, W) palette indices -> 8bpp tiles, 32 per row, row-major."""
    v = (np.asarray(idx) + base).astype(np.uint8)
    th, tw = v.shape[0] // 8, v.shape[1] // 8
    t = v.reshape(th, 8, tw, 8).transpose(0, 2, 1, 3)        # ty, tx, y, x
    out = np.zeros((th, tw, 4, 8, 2), np.uint8)              # plane pair, row, (lo, hi)
    for p in range(8):
        bits = (t >> p) & 1
        byte = np.zeros(bits.shape[:3], np.uint8)
        for x in range(8):
            byte |= (bits[..., x] << (7 - x)).astype(np.uint8)
        out[:, :, p >> 1, :, p & 1] = byte
    return out.tobytes()


def palette_words(pal):
    c5, _ = to_snes(pal)
    words = [int(b) << 10 | int(g) << 5 | int(r) for r, g, b in c5]
    return words + [0] * (COLORS - len(words))


def convert_photo(arr, method=DITHER):
    pal = make_palette(arr)
    idx = dither(arr, pal, method)
    rgb = pal[idx]
    err = float((((rgb - arr) ** 2) * WEIGHT).sum(2).mean())
    return dict(tiles=tiles8(idx), palette=palette_words(pal), preview=rgb.astype(np.uint8),
                stats=dict(palette_used=len(pal), mean_weighted_error=round(err, 2), dither=method))


def _cached(key, make):
    path = CACHE / f'{key}.npz'
    if path.exists():
        d = np.load(path, allow_pickle=False)
        meta = json.loads(str(d['meta']))
        return dict(meta, tiles=d['tiles'].tobytes(), preview=d['preview'], **(
            dict(mask=d['mask'].tobytes()) if 'mask' in d else {}), **(
            dict(scene=d['scene']) if 'scene' in d else {}))
    r = make()
    CACHE.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in r.items() if k not in ('tiles', 'preview', 'mask', 'scene')}
    extra = dict(mask=np.frombuffer(r['mask'], np.uint8)) if 'mask' in r else {}
    if 'scene' in r:
        extra['scene'] = r['scene']
    np.savez_compressed(path, tiles=np.frombuffer(r['tiles'], np.uint8), preview=r['preview'],
                        meta=json.dumps(meta), **extra)
    return r


def background(path, method=DITHER):
    """Photo file -> dict(tiles 49152 bytes, palette 240 words, preview (192,256,3), stats)."""
    data = pathlib.Path(path).read_bytes()

    def make():
        arr = np.asarray(resize_photo(Image.open(path)), float)
        return convert_photo(arr, method)
    return _cached(_key(data, method), make)


def solid(rgb):
    """A solid background: every pixel index 239 (value 255: every bitplane set), that colour."""
    pal = np.array([rgb] * 1, float)
    _, snapped = to_snes(pal)
    words = [0] * (COLORS - 1) + palette_words(snapped)[:1]
    return dict(tiles=b'\xff' * (W * H), palette=words, preview=np.tile(snapped[0].astype(np.uint8), (H, W, 1)),
                stats=dict(solid=list(map(int, snapped[0]))))


def titled(path, logo_rgba, pos, method=DITHER):
    """Title picture: the photo with the logo (RGBA numpy array) alpha-composited at pos before quantizing."""
    data = pathlib.Path(path).read_bytes()

    def make():
        arr = np.asarray(resize_photo(Image.open(path)), float)
        lh, lw = logo_rgba.shape[:2]
        x, y = pos
        a = logo_rgba[..., 3:4] / 255.0
        arr[y:y + lh, x:x + lw] = arr[y:y + lh, x:x + lw] * (1 - a) + logo_rgba[..., :3] * a
        return convert_photo(arr, method)
    return _cached(_key(data, logo_rgba.tobytes(), pos, method), make)


# ------------------------------------------------------------------ silhouettes
def silhouette(path, height=SIL_HEIGHT):
    data = pathlib.Path(path).read_bytes()

    def make():
        # background = the light pixels connected to the border (flood fill through a 1-px white frame);
        # enclosed light regions (an apron, a gap under an arm that does not reach the edge) are body
        g = Image.open(path).convert('L').point(lambda v: 255 if v >= 128 else 0)
        fr = Image.new('L', (g.width + 2, g.height + 2), 255)
        fr.paste(g, (1, 1))
        from PIL import ImageDraw
        ImageDraw.floodfill(fr, (0, 0), 128)
        fig = np.asarray(fr, np.uint8)[1:-1, 1:-1] != 128
        ys, xs = np.nonzero(fig)
        if not len(ys):
            raise ValueError(f'{path}: no figure (no dark pixels)')
        crop = fig[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        ch, cw = crop.shape
        nh = height
        nw = max(1, round(cw * nh / ch))
        small = np.asarray(Image.fromarray((crop * 255).astype(np.uint8)).resize((nw, nh), Image.BOX), float) / 255
        mask = small >= 0.5
        return _sil_from_mask(mask)
    return _cached(_key(data, height), make)


def placeholder_silhouette(height=SIL_HEIGHT):
    """A plain standing figure for a missing silhouette (--allow-missing-art)."""
    w = 48
    yy, xx = np.mgrid[0:height, 0:w]
    head = ((xx - w / 2) / 9) ** 2 + ((yy - 14) / 12) ** 2 <= 1
    body = (yy >= 26) & (np.abs(xx - w / 2) <= 9 + (yy - 26) * 0.12) & (yy < height)
    return _sil_from_mask(head | body)


def staged_silhouette(path, bg_path):
    """A person painted flat magenta into the background photo (tools/yonaki/gen_stage.py) -> a mask placed where
    the picture has them: x / top in tiles of the 256x192 picture.  stats.bg_diff = mean difference of the rest
    of the picture from the background (large when the edit redrew the scene)."""
    data = pathlib.Path(path).read_bytes() + pathlib.Path(bg_path).read_bytes()

    def make():
        im = Image.open(path).convert('RGB')
        a = np.asarray(im, float)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        mag = (r > 150) & (b > 150) & (g < np.minimum(r, b) - 90)
        # the same crop and resize as the background, by coverage
        cov = Image.fromarray((mag * 255).astype(np.uint8))
        cov = np.asarray(_fit(cov, Image.BOX), float) / 255
        mask = cov >= 0.5
        mask = _keep_figure(mask)
        if not mask.any():
            raise ValueError(f'{path}: no magenta figure')
        # holes (the background between an arm and the body stays; enclosed specks of the edit are filled)
        mask |= _small_holes(mask, 6)
        photo = np.asarray(resize_photo(im), float)
        bg = np.asarray(resize_photo(Image.open(bg_path)), float)
        diff = float(np.abs(photo - bg).mean(2)[~_grow(mask, 3)].mean())
        ys, xs = np.nonzero(mask)
        tx0, tx1, ty0, ty1 = xs.min() // 8, xs.max() // 8, ys.min() // 8, ys.max() // 8
        # the rim: figure pixels next to the photo (not next to the picture's edge)
        pad = np.pad(mask, 1, mode='edge')
        inner = pad[1:-1, 1:-1] & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
        crop = (slice(ty0 * 8, ty1 * 8 + 8), slice(tx0 * 8, tx1 * 8 + 8))
        r = _sil_tiles(mask[crop], (mask & ~inner)[crop])
        r.update(x=int(tx0), top=int(ty0), stats=dict(px_w=int(xs.max() - xs.min() + 1),
                                                       px_h=int(ys.max() - ys.min() + 1), bg_diff=diff))
        prev = (np.asarray(bg, np.uint8) * 0.55).astype(np.uint8)
        prev[mask] = (24, 40, 112)
        prev[mask & ~inner] = (72, 112, 208)
        r['scene'] = prev
        return r
    return _cached(_key(data, 'staged'), make)


def _fit(img, method):
    w, h = img.size
    if w * 3 > h * 4:
        nw = h * 4 // 3
        img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    elif w * 3 < h * 4:
        nh = w * 3 // 4
        img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return img.resize((W, H), method)


def _components(mask):
    """4-connected components of a small bool array -> list of index arrays (largest first)."""
    seen = np.zeros_like(mask)
    out = []
    hh, ww = mask.shape
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack, comp = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            comp.append((y, x))
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < hh and 0 <= nx < ww and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        out.append(tuple(np.array(comp).T))
    return sorted(out, key=lambda c: -len(c[0]))


def _keep_figure(mask):
    """Drop specks: keep the components of at least 4% of the largest one."""
    comps = _components(mask)
    out = np.zeros_like(mask)
    for c in comps:
        if len(c[0]) >= max(6, len(comps[0][0]) * 0.04):
            out[c] = True
    return out


def _small_holes(mask, limit):
    comps = _components(~mask)
    out = np.zeros_like(mask)
    hh, ww = mask.shape
    for c in comps:
        ys, xs = c
        if len(ys) <= limit and ys.min() > 0 and xs.min() > 0 and ys.max() < hh - 1 and xs.max() < ww - 1:
            out[c] = True
    return out


def _grow(mask, n):
    m = mask.copy()
    for _ in range(n):
        p = np.pad(m, 1)
        m = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return m


def _sil_from_mask(mask):
    h, w = mask.shape
    tw = (w + 2 + 7) // 8
    th = (h + 7) // 8
    full = np.zeros((th * 8, tw * 8), bool)
    x0 = (tw * 8 - w) // 2
    full[th * 8 - h:, x0:x0 + w] = mask
    pad = np.pad(full, 1)
    inner = pad[1:-1, 1:-1] & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    rim = full & ~inner
    r = _sil_tiles(full, rim)
    r['stats'] = dict(px_w=w, px_h=h)
    return r


def _sil_tiles(full, rim):
    th, tw = full.shape[0] // 8, full.shape[1] // 8
    out = bytearray()
    for ty in range(th):
        for tx in range(tw):
            for y in range(8):
                c = r = 0
                for x in range(8):
                    if full[ty * 8 + y, tx * 8 + x]:
                        c |= 0x80 >> x
                    if rim[ty * 8 + y, tx * 8 + x]:
                        r |= 0x80 >> x
                out += bytes([c, r])
    prev = np.zeros((th * 8, tw * 8, 3), np.uint8) + 255
    prev[full] = (24, 40, 112)
    prev[rim] = (72, 112, 208)
    return dict(w=tw, h=th, mask=bytes(out), tiles=b'', preview=prev)


def preview_png(arr, path, scale=1):
    im = Image.fromarray(np.asarray(arr, np.uint8))
    if scale != 1:
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


if __name__ == '__main__':
    # compare dithers: python3 -I tools/yonaki/pictures.py bell [bus ...] -> build/yonaki/dither/<id>_<method>.png
    out = ROOT / 'build/yonaki/dither'
    for name in sys.argv[1:]:
        p = ROOT / f'assets/yonaki/src/bg/{name}.png'
        for m in ('fs', 'bayer', 'none'):
            r = background(p, m)
            preview_png(r['preview'], out / f'{name}_{m}.png', 1)
            preview_png(r['preview'], out / f'{name}_{m}_x3.png', 3)
            print(name, m, r['stats'])
