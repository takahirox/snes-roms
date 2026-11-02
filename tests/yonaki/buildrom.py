"""Build a 夜鳴き鐘 ROM from a scenario directory into an output directory (build.py + ca65 + ld65 + romfix).

usage (module): build(out, scenario=None, extra=()) -> path of the .sfc
"""
import subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
CC = ROOT / 'tools/vendor/cc65-2.19/bin'
FIXTURE = ROOT / 'tests/yonaki/fixture'


def build(out, scenario=None, extra=(), quiet=True):
    out = pathlib.Path(out)
    cmd = [sys.executable, '-I', str(ROOT / 'tools/yonaki/build.py'), '--out', str(out), '--quiet', *extra]
    if scenario:
        cmd += ['--scenario', str(scenario)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stdout + r.stderr)
    rel = out.relative_to(ROOT)
    for c in ([str(CC / 'ca65'), '-g', '-I', '.', '-I', str(rel), 'src/yonaki/yonaki.s', '-o', f'{rel}/yonaki.o',
               '-l', f'{rel}/yonaki.lst'],
              [str(CC / 'ld65'), '-C', f'{rel}/yonaki.cfg', f'{rel}/yonaki.o', '-o', f'{rel}/yonaki.sfc', '-m',
               f'{rel}/yonaki.map', '-Ln', f'{rel}/labels.txt'],
              [sys.executable, '-I', 'tools/yonaki/romfix.py', f'{rel}/yonaki.sfc']):
        r = subprocess.run(c, cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(' '.join(c) + '\n' + r.stdout + r.stderr)
    return out / 'yonaki.sfc'


def build_fixture():
    return build(ROOT / 'build/yonaki-test', FIXTURE / 'scenario', ['--omake-endings', '3'])
