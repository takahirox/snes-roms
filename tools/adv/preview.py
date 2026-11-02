"""Decode the built picture data back to PNG (what the PPU will show) for review.

usage: python3 -I tools/adv/preview.py      -> build/adv/preview/pic<N>.png, pic<N>-portrait.png (2x)
Reads build/adv/pic*.bin, portrait*.bin and the palettes in build/adv/data.inc.
"""
import sys, re, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import png_codec

B = ROOT / 'build/adv'
OUT = B / 'preview'


def palettes():
    pals, cur = {}, None
    for line in (B / 'data.inc').read_text().splitlines():
        m = re.match(r'^Palette(\d+):', line)
        if m:
            cur = int(m.group(1)); pals[cur] = []
            continue
        if cur is not None and line.strip().startswith('.word $'):
            pals[cur] += [int(v.strip()[1:], 16) for v in line.strip()[6:].split(',')]
            continue
        cur = None
    return pals


def rgb(w):
    return ((w & 31) * 255 // 31, (w >> 5 & 31) * 255 // 31, (w >> 10 & 31) * 255 // 31)


def decode_tile(t, x0, y0, img, pal):
    for y in range(8):
        for x in range(8):
            v = 0
            for p in range(8):
                if t[(p >> 1) * 16 + y * 2 + (p & 1)] & (0x80 >> x):
                    v |= 1 << p
            img[y0 + y][x0 + x] = rgb(pal[v - 16]) if v >= 16 else (0, 0, 0)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pals = palettes()
    man = json.loads((B / 'manifest.json').read_text())
    for i in range(len(man['pictures'])):
        tiles = (B / f'pic{i}.bin').read_bytes()
        img = [[(0, 0, 0)] * 256 for _ in range(128)]
        for n in range(512):
            decode_tile(tiles[n * 64:n * 64 + 64], n % 32 * 8, n // 32 * 8, img, pals[i])
        png_codec.write(OUT / f'pic{i}.png', [[p for p in row for _ in (0, 1)] for row in img for _ in (0, 1)])
    # portraits over their pictures
    data = (B / 'data.inc').read_text()
    rows = re.findall(r'\.word (\d+), (\d+), (\d+), (\d+), \$([0-9A-F]{4}), (\d+)   ; (\w+)', data)
    scenes = re.findall(r'\.word \d+, (\d+), \d+, Look_(\w+),', data)
    sc_img = {s: int(i) for i, s in scenes}
    blobs = {}
    for b in man['portrait_banks']:
        blobs[b] = (B / f'portrait{man["portrait_banks"].index(b)}.bin').read_bytes()
    for x, y, w, h, addr, bank, scene in rows:
        x, y, w, h, addr, bank = int(x), int(y), int(w), int(h), int(addr, 16), int(bank)
        i = sc_img[scene]
        tiles = (B / f'pic{i}.bin').read_bytes()
        img = [[(0, 0, 0)] * 256 for _ in range(128)]
        for n in range(512):
            decode_tile(tiles[n * 64:n * 64 + 64], n % 32 * 8, n // 32 * 8, img, pals[i])
        blob = blobs[bank][addr - 0x8000:]
        for k in range(w * h):
            decode_tile(blob[k * 64:k * 64 + 64], (x + k % w) * 8, (y + k // w) * 8, img, pals[i])
        png_codec.write(OUT / f'{scene}-portrait.png', [[p for p in row for _ in (0, 1)] for row in img for _ in (0, 1)])
    print('wrote', OUT)


if __name__ == '__main__':
    main()
