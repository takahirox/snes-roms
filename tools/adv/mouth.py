"""Mouth frames of 潮鳴りの密室 (data/adv/mouths.txt): parser, checks, and the patched portraits.

Frame 0 (closed) is the original portrait.  Frames 1 (half open) and 2 (open) replace the pixels of a
small patch around the mouth: "." keeps the original pixel, "1"/"2" take the original pixel one/two
rows up (the lower lip moves down), a letter is one of the mouth's own colours.

usage: python3 -I tools/adv/mouth.py preview OUTDIR   -- unquantized closed/half/open, 1x and 8x
"""
import re, sys, json, pathlib, hashlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import png_codec

MOUTHS = ROOT / 'data/adv/mouths.txt'
FRAMES = ('half', 'open')
MAX_TILES = 4
OPAQUE = 200            # patch pixels must be at least this opaque in the portrait (the art uses 252-254)


class MouthError(Exception):
    pass


def parse(text=None):
    """-> {portrait path: dict(x, y, w, h, colors, frames=[rows(half), rows(open)], line)}"""
    text = MOUTHS.read_text(encoding='utf-8') if text is None else text
    out, cur, sect = {}, None, None
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if line.startswith('@mouth'):
            p = line.split()
            if len(p) != 6:
                raise MouthError(f'mouths.txt:{no}: "@mouth PNG X Y W H"')
            path = p[1]
            if path in out:
                raise MouthError(f'mouths.txt:{no}: {path} twice')
            x, y, w, h = map(int, p[2:])
            cur = out[path] = dict(path=path, x=x, y=y, w=w, h=h, colors={}, rows={}, line=no)
            sect = None
            continue
        if cur is None:
            raise MouthError(f'mouths.txt:{no}: text outside @mouth')
        m = re.match(r'^colors:\s*(.*)$', line)
        if m:
            for item in m.group(1).split():
                k, _, v = item.partition('=')
                if not (len(k) == 1 and k.isalpha() and re.fullmatch(r'[0-9a-fA-F]{6}', v)):
                    raise MouthError(f'mouths.txt:{no}: colour "{item}" (L=RRGGBB)')
                cur['colors'][k] = tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
            continue
        m = re.match(r'^(half|open):\s*$', line)
        if m:
            sect = m.group(1)
            if sect in cur['rows']:
                raise MouthError(f'mouths.txt:{no}: {sect} twice')
            cur['rows'][sect] = []
            continue
        if sect is None:
            raise MouthError(f'mouths.txt:{no}: frame rows before "half:" / "open:"')
        if len(line) != cur['w']:
            raise MouthError(f'mouths.txt:{no}: row "{line}" is {len(line)} wide, the patch is {cur["w"]}')
        for ch in line:
            if ch not in '.12' and ch not in cur['colors']:
                raise MouthError(f'mouths.txt:{no}: "{ch}" is not ".", "1", "2" or a colour')
        cur['rows'][sect].append(line)
    for path, m in out.items():
        for f in FRAMES:
            if len(m['rows'].get(f, [])) != m['h']:
                raise MouthError(f'mouths.txt:{m["line"]}: {path} {f} needs {m["h"]} rows')
        m['frames'] = [m['rows'][f] for f in FRAMES]
    return out


def apply(portrait, m, frame):
    """portrait: RGBA rows (72x104).  frame 0 = original, 1 half, 2 open.  Returns new RGBA rows."""
    out = [list(r) for r in portrait]
    if frame == 0:
        return out
    rows = m['frames'][frame - 1]
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch == '.':
                continue
            x, y = m['x'] + dx, m['y'] + dy
            if ch in '12':
                src = portrait[y - int(ch)][x]
                out[y][x] = tuple(src[:3]) + (portrait[y][x][3],)
            else:
                out[y][x] = m['colors'][ch] + (portrait[y][x][3],)
    return out


def check(portrait, m, px, py):
    """The patch is on opaque pixels and inside the portrait; px, py = portrait position in the picture
    (tile-aligned).  Returns the picture tile rectangle (tx, ty, tw, th) of the changed pixels."""
    ph, pw = len(portrait), len(portrait[0])
    if m['x'] < 0 or m['y'] < 0 or m['x'] + m['w'] > pw or m['y'] + m['h'] > ph:
        raise MouthError(f'{m["path"]}: patch outside the portrait')
    xs, ys = [], []
    for f, rows in enumerate(m['frames'], 1):
        changed = 0
        for dy, row in enumerate(rows):
            for dx, ch in enumerate(row):
                if ch == '.':
                    continue
                x, y = m['x'] + dx, m['y'] + dy
                if portrait[y][x][3] < OPAQUE:
                    raise MouthError(f'{m["path"]}: {FRAMES[f - 1]} touches the transparent pixel {x},{y}')
                if ch in '12' and portrait[y - int(ch)][x][3] < OPAQUE:
                    raise MouthError(f'{m["path"]}: {FRAMES[f - 1]} copies a transparent pixel into {x},{y}')
                xs.append(x)
                ys.append(y)
                changed += 1
        if not changed:
            raise MouthError(f'{m["path"]}: {FRAMES[f - 1]} is the same as closed')
    if m['frames'][0] == m['frames'][1]:
        raise MouthError(f'{m["path"]}: half and open are the same')
    tx0, tx1 = (px + min(xs)) // 8, (px + max(xs)) // 8
    ty0, ty1 = (py + min(ys)) // 8, (py + max(ys)) // 8
    tw, th = tx1 - tx0 + 1, ty1 - ty0 + 1
    if tw * th > MAX_TILES:
        raise MouthError(f'{m["path"]}: the mouth touches {tw}x{th} tiles (max {MAX_TILES})')
    return tx0, ty0, tw, th


def digest(m):
    return hashlib.sha256(json.dumps([m['x'], m['y'], m['w'], m['h'], sorted(m['colors'].items()), m['frames']])
                          .encode()).hexdigest()


def preview(outdir):
    """closed | half | open of each portrait on a neutral grey: the face crop at 1x and 8x, unquantized."""
    outdir = pathlib.Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    mouths = parse()
    rec = {}
    for path, m in mouths.items():
        por = png_codec.read(ROOT / path)
        check(por, m, 0, 0)
        name = pathlib.Path(path).stem
        # crop: the patch with a margin of 12 px, clamped
        cx0, cy0 = max(0, m['x'] - 12), max(0, m['y'] - 14)
        cx1, cy1 = min(len(por[0]), m['x'] + m['w'] + 12), min(len(por), m['y'] + m['h'] + 10)
        frames = [apply(por, m, f) for f in range(3)]
        for scale in (1, 8):
            gap = 2 * scale
            cw, ch = (cx1 - cx0) * scale, (cy1 - cy0) * scale
            img = [[(64, 64, 72)] * (3 * cw + 2 * gap) for _ in range(ch)]
            for f, fr in enumerate(frames):
                for y in range(ch):
                    for x in range(cw):
                        r, g, b, a = fr[cy0 + y // scale][cx0 + x // scale]
                        img[y][f * (cw + gap) + x] = tuple((c * a + 64 * (255 - a)) // 255 for c in (r, g, b))
            png_codec.write(outdir / f'{name}-{scale}x.png', img)
        # whole portrait, 1x, closed | half | open
        full = [[(64, 64, 72)] * (3 * 72 + 4) for _ in range(104)]
        for f, fr in enumerate(frames):
            for y in range(104):
                for x in range(72):
                    r, g, b, a = fr[y][x]
                    full[y][f * 74 + x] = tuple((c * a + 64 * (255 - a)) // 255 for c in (r, g, b))
        png_codec.write(outdir / f'{name}-full-1x.png', full)
        rec[name] = dict(portrait=path, portrait_sha256=hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                         patch=[m['x'], m['y'], m['w'], m['h']], crop=[cx0, cy0, cx1 - cx0, cy1 - cy0],
                         order='closed (original) | half | open', mouth_digest=digest(m))
    (outdir / 'PREVIEW.json').write_text(json.dumps(dict(
        source='data/adv/mouths.txt', source_sha256=hashlib.sha256(MOUTHS.read_bytes()).hexdigest(),
        note='unquantized RGBA composited on grey (64,64,72); the ROM tiles are the quantized ones',
        portraits=rec), ensure_ascii=False, indent=1) + '\n')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'preview':
        preview(sys.argv[2])
    else:
        sys.exit(__doc__)
