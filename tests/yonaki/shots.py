"""Screenshots of 夜鳴き鐘 pages for review (art + text), driven by the pad on the Snes9x core.

usage:
  python3 -I tests/yonaki/shots.py [options] LABEL [LABEL ...]
  python3 -I tests/yonaki/shots.py [options] --ending E01 [--ending E05 ...]
  python3 -I tests/yonaki/shots.py [options] --all-labels
options:
  --scenario DIR   (default data/yonaki/scenario)   --allow-missing-art   --pages N (per label, default 12)
  --follow         at a choice, take the first option and go on (default: stop at the choice)
  --scale N        PNG scale (default 2)             --no-build  (reuse build/yonaki-shots)

LABEL mode builds a review ROM (build.py --debug-start) into build/yonaki-shots/ and starts はじめから at the
label (local flags all clear, no global flags; the picture / silhouettes / music are whatever the script sets
from there -- a label in the middle of a scene starts on black until its next @bg).
--ending follows the route of tests/yonaki/routes.py to that ending from the title (exact flags).
Every page is captured when it is complete (the wait mark is the page mark, a choice, or the ending), plus
chapter cards.  Output: build/yonaki-shots/<label or ending>/NNN_<text id>.png and index.png (a contact sheet).
"""
import sys, json, pathlib, argparse, struct
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import buildrom                        # noqa: E402
import routes                          # noqa: E402
from drive import Driver, ROOT        # noqa: E402

OUT = ROOT / 'build/yonaki-shots'


def sram_with_start(addr):
    b = bytearray(8192)
    b[0x1FF0:0x1FF2] = b'DB'
    b[0x1FF2:0x1FF5] = struct.pack('<I', addr)[:3]
    return bytes(b)


def capture(g, folder, pages, follow, scale):
    folder.mkdir(parents=True, exist_ok=True)
    for f in folder.glob('*.png'):
        f.unlink()
    n = 0
    files = []
    page_glyph = None
    last_chapter = None
    for _ in range(200000):
        st = g.state()
        if st == 'CHAPTER' and g.w('bright') == 15 and g.w('reg_tm') == 2 and g.w('chapter_cur') != last_chapter:
            last_chapter = g.w('chapter_cur')
            g.run(20)
            files.append(g.shot(folder / f'{n:03d}_chapter.png', scale))
            n += 1
        if st == 'WAIT':
            if page_glyph is None:
                page_glyph = g.layout['glyphs'].index('')
            if g.w('mark_glyph') == page_glyph:
                g.run(12)
                files.append(g.shot(folder / f'{n:03d}_t{g.w("cur_text"):05d}.png', scale))
                n += 1
            g.tap('A', 1, 1)
        elif st == 'TYPE':
            g.tap('A', 1, 1)
        elif st == 'CHOICE':
            g.run(12)
            files.append(g.shot(folder / f'{n:03d}_choice{g.w("choice_id"):03d}.png', scale))
            n += 1
            if not follow:
                break
            g.choose(index=0)
        elif st == 'ENDING':
            g.run(260)
            files.append(g.shot(folder / f'{n:03d}_ending.png', scale))
            n += 1
            break
        elif st == 'TITLE':
            break
        else:
            g.run(1)
        if n >= pages:
            break
    if files:
        import subprocess
        subprocess.run([sys.executable, '-I', str(ROOT / 'tests/yonaki/sheet.py'), str(folder / 'index.png'), '4', '1',
                        *map(str, files)], check=True)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('labels', nargs='*')
    ap.add_argument('--scenario')
    ap.add_argument('--allow-missing-art', action='store_true')
    ap.add_argument('--pages', type=int, default=12)
    ap.add_argument('--follow', action='store_true')
    ap.add_argument('--scale', type=int, default=2)
    ap.add_argument('--ending', action='append', default=[])
    ap.add_argument('--all-labels', action='store_true')
    ap.add_argument('--no-build', action='store_true')
    a = ap.parse_args()
    if not a.no_build:
        extra = ['--debug-start'] + (['--allow-missing-art'] if a.allow_missing_art else [])
        buildrom.build(OUT, a.scenario, extra)
    lay = json.loads((OUT / 'layout.json').read_text())
    labels = list(lay['labels']) if a.all_labels else a.labels
    for lab in labels:
        if lab not in lay['labels']:
            sys.exit(f'no label *{lab}')
        g = Driver(build=OUT, sram=sram_with_start(lay['labels'][lab]))
        g.new_game()
        files = capture(g, OUT / lab, a.pages, a.follow, a.scale)
        g.close()
        print(f'*{lab}: {len(files)} shots -> {OUT / lab}')
    if a.ending:
        order, _ = routes.plan(lay)
        by = {n['ending']: n for n in order}
        sram = bytes(8192)
        for n in order:                       # endings that need earlier ones are played in order
            want = n['ending'] in a.ending
            needed = any(n['ending'] in by[e]['gflags'] for e in a.ending if e in by)
            if not (want or needed):
                continue
            g = Driver(build=OUT, sram=sram)
            g.title()
            g.title_pick(3 if n['start'] == 'omake' else 0)
            if want:
                files = capture_route(g, OUT / n['ending'], n['path'], a.scale)
                print(f'{n["ending"]}: {len(files)} shots -> {OUT / n["ending"]}')
            else:
                g.play(n['path'])
            if g.state() == 'ENDING':
                g.ending_to_title()
            sram = g.sram_image()
            g.close()


def capture_route(g, folder, path, scale):
    folder.mkdir(parents=True, exist_ok=True)
    for f in folder.glob('*.png'):
        f.unlink()
    files = []
    page_glyph = g.layout['glyphs'].index('')
    steps = list(path)
    n = 0
    for _ in range(400000):
        st = g.state()
        if st == 'WAIT':
            if g.w('mark_glyph') == page_glyph:
                g.run(12)
                files.append(g.shot(folder / f'{n:04d}_t{g.w("cur_text"):05d}.png', scale))
                n += 1
            g.tap('A', 1, 1)
        elif st == 'TYPE':
            g.tap('A', 1, 1)
        elif st == 'CHOICE':
            g.run(12)
            files.append(g.shot(folder / f'{n:04d}_choice{g.w("choice_id"):03d}.png', scale))
            n += 1
            cid, k, _, _ = steps.pop(0)
            assert g.w('choice_id') == cid
            g.choose(index=k)
        elif st == 'ENDING':
            g.run(260)
            files.append(g.shot(folder / f'{n:04d}_ending.png', scale))
            break
        else:
            g.run(1)
    return files


if __name__ == '__main__':
    main()
