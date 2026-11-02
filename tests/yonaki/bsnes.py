"""Replay the Snes9x test traces of 夜鳴き鐘 (build/yonaki-test/traces) on the pinned bsnes 115 libretro core.

For each trace: the recorded pad masks only, the session's initial battery image as <dir>/yonaki.srm (bsnes loads
it at load_game and writes it back at unload), captures at the same frames.  Compared with the Snes9x run: the
final battery image (byte-equal) and every capture (max RGB difference per pixel; at most 2 = the cores' 5-bit to
8-bit expansion).  tools/host_libretro_replay.Frontend, read-only.  Results: build/yonaki-test/bsnes/RESULTS.json.

usage: python3 -I tests/yonaki/bsnes.py [--real] [test ...]   (--real: also the real scenario's traces, slow)
"""
import sys, json, hashlib, pathlib, shutil
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/vendor/pylib'))
from host_libretro_replay import Frontend     # noqa: E402
import numpy as np                             # noqa: E402
from PIL import Image                          # noqa: E402

CORE = ROOT / 'tools/vendor/bsnes-63ee22f7af8f' / ('bsnes_libretro.' + ('dylib' if sys.platform == 'darwin' else 'so'))   # built from the pinned source by tools/bootstrap.py
TR = ROOT / 'build/yonaki-test/traces'
OUT = ROOT / 'build/yonaki-test/bsnes'
sha = lambda b: hashlib.sha256(b).hexdigest()


def replay(name):
    t = json.loads((TR / f'{name}.json').read_text())
    rom_src = ROOT / t['rom']
    assert sha(rom_src.read_bytes()) == t['rom_sha256'], 'trace / ROM mismatch'
    out = OUT / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    rom = out / 'yonaki.sfc'
    shutil.copy2(rom_src, rom)
    shutil.copy2(TR / f'{name}.in.srm', out / 'yonaki.srm')
    e = Frontend(CORE, rom, out)
    caps = {}
    for c in t['captures']:
        caps.setdefault(c['frame'], []).append(c)
    got = []
    try:
        for mask in t['masks']:
            e.step(mask)
            for c in caps.get(e.frames, []):
                got.append((c, e.capture(pathlib.Path(c['path']).stem)))
    finally:
        e.close()
    final = (out / 'yonaki.srm').read_bytes()[:8192]
    want = (TR / f'{name}.out.srm').read_bytes()
    worst = 0
    for c, s in got:
        a = Image.open(ROOT / c['path']).convert('RGB')
        b = Image.open(out / f'{s["name"]}.png').convert('RGB')
        if c['scale'] != 1:
            b = b.resize(a.size, Image.NEAREST)
        if a.size != b.size:
            b = b.resize(a.size, Image.NEAREST)
        d = np.abs(np.asarray(a, int) - np.asarray(b, int)).max()
        worst = max(worst, int(d))
    res = dict(frames=len(t['masks']), captures=len(got), battery_equal=final == want, max_rgb_difference=worst)
    res['ok'] = res['battery_equal'] and worst <= 2
    return res


def main(names):
    real = '--real' in names
    names = [n for n in names if not n.startswith('--')]
    names = names or sorted(p.stem for p in TR.glob('*.json') if real or not p.stem.startswith('real_'))
    results, ok = {}, True
    for n in names:
        try:
            r = replay(n)
        except Exception as exc:
            r = dict(ok=False, error=f'{type(exc).__name__}: {exc}')
        results[n] = r
        ok &= r['ok']
        print('PASS' if r['ok'] else 'FAIL', n, r, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'RESULTS.json').write_text(json.dumps(dict(core='bsnes 115 libretro (pinned, unmodified)', results=results),
                                                 indent=1) + '\n')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main(sys.argv[1:])
