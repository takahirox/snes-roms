"""Replay every Snes9x test trace on the pinned bsnes 115 libretro core and compare.

For each build/adv/traces/<test>.json: the recorded pad masks only, the session's initial battery
image given to bsnes as <save dir>/shionari.srm (bsnes loads it at load_game and writes it back at
unload), captures at the same frames (no frame offset).  Compared with the Snes9x run: every capture (256x224, max RGB
difference per pixel, at most 2 = the cores' 5-bit to 8-bit expansion) and the final battery image.  Uses tools/host_libretro_replay.Frontend
read-only (no core patches, no memory writes).  Results: build/adv/bsnes/RESULTS.json.

usage: python3 -I tests/adv/bsnes.py [test ...]
"""
import sys, json, hashlib, pathlib, shutil
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import png_codec
from host_libretro_replay import Frontend

CORE = ROOT / 'tools/vendor/bsnes-63ee22f7af8f' / ('bsnes_libretro.' + ('dylib' if sys.platform == 'darwin' else 'so'))   # built from the pinned source by tools/bootstrap.py
CORE_SHA = hashlib.sha256(CORE.read_bytes()).hexdigest() if CORE.exists() else None   # this machine's build, recorded
ROM = ROOT / 'build/adv/shionari.sfc'
OUT = ROOT / 'build/adv/bsnes'
sha = lambda b: hashlib.sha256(b).hexdigest()


def compare(a_path, b_path):
    a = png_codec.read(a_path)
    b = png_codec.read(b_path)
    assert (len(a), len(a[0])) == (len(b), len(b[0])), 'size'
    worst = 0
    differing = 0
    for ra, rb in zip(a, b):
        for pa, pb in zip(ra, rb):
            d = max(abs(pa[k] - pb[k]) for k in range(3))
            worst = max(worst, d)
            differing += d > 2
    return worst, differing


def replay(name):
    trace = json.loads((ROOT / f'build/adv/traces/{name}.json').read_text())
    assert trace['rom_sha256'] == sha(ROM.read_bytes()), 'trace/ROM mismatch'
    out = OUT / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    initial = (ROOT / trace['input_sram']['path']).read_bytes()
    assert sha(initial) == trace['input_sram']['sha256']
    rom = out / 'shionari.sfc'
    shutil.copy2(ROM, rom)
    (out / 'shionari.srm').write_bytes(initial)
    e = Frontend(CORE, rom, out)
    caps = {}
    for c in trace['captures']:
        caps.setdefault(c['frame'], []).append(c['name'])
    shots = []
    try:
        for mask in trace['masks']:
            e.step(mask)
            for n in caps.get(e.frames, []):
                shots.append(e.capture(n))
    finally:
        e.close()
    final = (out / 'shionari.srm').read_bytes()
    want = (ROOT / trace['output_sram']['path']).read_bytes()
    res = dict(frames=len(trace['masks']), captures=[], input_sram_sha256=sha(initial),
               bsnes_final_sram_sha256=sha(final), snes9x_final_sram_sha256=sha(want),
               battery_equal=final == want)
    worst_all = 0
    for s in shots:
        a = ROOT / 'build/adv/tests' / name / f'{s["name"]}.png'
        b = out / f'{s["name"]}.png'
        worst, n = compare(a, b)
        worst_all = max(worst_all, worst)
        res['captures'].append(dict(name=s['name'], frame=s['frame'], max_rgb_difference=worst, pixels_over_2=n))
    res['max_rgb_difference'] = worst_all
    res['ok'] = res['battery_equal'] and worst_all <= 2      # 5-bit -> 8-bit expansion of the two cores
    return res


def main(names):
    names = names or sorted(p.stem for p in (ROOT / 'build/adv/traces').glob('*.json'))
    results = {}
    ok = True
    for n in names:
        try:
            r = replay(n)
        except Exception as exc:
            r = dict(ok=False, error=f'{type(exc).__name__}: {exc}')
        results[n] = r
        ok &= r['ok']
        print(('PASS' if r['ok'] else 'FAIL'), n, {k: r.get(k) for k in ('max_rgb_difference', 'battery_equal', 'error')})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'RESULTS.json').write_text(json.dumps(dict(
        rom_sha256=sha(ROM.read_bytes()), core_sha256=CORE_SHA, core='bsnes 115 libretro (pinned, unmodified)',
        scope='Replay of the Snes9x test traces (pad masks + battery image) on a second emulator; not physical hardware.',
        results=results), ensure_ascii=False, indent=1) + '\n')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main(sys.argv[1:])
