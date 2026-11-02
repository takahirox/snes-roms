"""Reproduce 潮鳴りの密室 from a clean copy of its sources and publish it to dist/shionari.sfc.

1. the current ROM must be the one the Snes9x tests, the lip-sync tests, the speech-blip tests and the bsnes
   replays passed with,
2. copy the build inputs into build/adv-clean/ (fresh) and run `make adv` there with the same cc65 (no cache),
3. require the clean ROM to be byte-identical, 4. copy ROM + labels + map + manifest + SHA256 to dist/.

usage: python3 -I tools/adv/release.py [--check]
       --check: steps 1-3 only (nothing is written to dist/)
"""
import sys, pathlib, shutil, subprocess, hashlib, json

ROOT = pathlib.Path(__file__).resolve().parents[2]
B = ROOT / 'build/adv'
CLEAN = ROOT / 'build/adv-clean'
sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def source_files():
    files = []
    for d in ('src/adv', 'tools/adv', 'data/adv', 'tests/adv', 'assets/shinonome'):
        files += [p for p in (ROOT / d).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    man = json.loads((B / 'manifest.json').read_text())
    files += [ROOT / p for p in man['sources']]
    files += [ROOT / f for f in ('Makefile', 'tools/png_codec.py', 'tools/host_libretro_replay.py', 'tests/harness.py',
                                 'assets/adv/PREPARED.json', 'assets/adv/ART.json')]
    return sorted(set(p for p in files if p.exists()))


def main():
    check_only = '--check' in sys.argv
    rom = B / 'shionari.sfc'
    a = sha(rom)
    tests = json.loads((B / 'tests.json').read_text())
    assert tests['rom_sha256'] == a and all(v['ok'] for v in tests['results'].values()), 'Snes9x tests'
    bs = json.loads((B / 'bsnes/RESULTS.json').read_text())
    assert bs['rom_sha256'] == a and all(v['ok'] for v in bs['results'].values()), 'bsnes replays'
    lip = json.loads((B / 'lipsync/RESULTS.json').read_text())
    assert lip['rom_sha256'] == a and lip['results'] and all(v['ok'] for v in lip['results'].values()), 'lip-sync'
    sp = json.loads((B / 'speech/RESULTS.json').read_text())
    assert sp['rom_sha256'] == a and sp['results'] and all(v['ok'] for v in sp['results'].values()), 'speech blips'
    inputs = [str(p.relative_to(ROOT)) for p in source_files()]
    if CLEAN.exists():
        shutil.rmtree(CLEAN)
    for rel in inputs:
        (CLEAN / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, CLEAN / rel)
    vendor = ROOT / 'tools/vendor/cc65-2.19/bin'
    subprocess.run(['make', 'adv', f'CA65={vendor / "ca65"}', f'LD65={vendor / "ld65"}', f'PYTHON={sys.executable}'],
                   cwd=CLEAN, check=True, stdout=subprocess.DEVNULL)
    b = sha(CLEAN / 'build/adv/shionari.sfc')
    print('main ROM ', a)
    print('clean ROM', b)
    assert a == b, 'clean build differs'
    if check_only:
        print('check only: clean rebuild identical; dist/ not written')
        return
    dist = ROOT / 'dist'
    shutil.copy2(rom, dist / 'shionari.sfc')
    shutil.copy2(B / 'labels.txt', dist / 'shionari.labels.txt')
    shutil.copy2(B / 'shionari.map', dist / 'shionari.map')
    shutil.copy2(B / 'manifest.json', dist / 'shionari.manifest.json')
    (dist / 'shionari.sfc.sha256').write_text(f'{a}  shionari.sfc\n')
    (B / 'release.json').write_text(json.dumps(dict(rom_sha256=a, clean_rom_sha256=b, inputs=len(inputs)), indent=1) + '\n')
    print('published dist/shionari.sfc')


if __name__ == '__main__':
    main()
