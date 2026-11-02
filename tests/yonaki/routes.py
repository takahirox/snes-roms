"""Choice routes of a 夜鳴き鐘 build, from its layout.json (no ROM needed).

plan(layout) -> list of dict(ending, start, gflags, path) in an order that can be played one after the other
with the battery kept: every ending first with no global flags, then with the flags (and seen endings) that
the endings already found give, and so on.  path = [(choice id, visible index, target label, text), ...].
The VM's rules are simulated exactly (local flags, @if / @ifnot on local and global flags, gated options).

usage: python3 -I tests/yonaki/routes.py [build/yonaki]   prints the plan
"""
import sys, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/yonaki'))
import script as sc          # noqa: E402


def _choice_ids(layout):
    return {v['op']: int(k) for k, v in layout['choices'].items()}


def plan(layout):
    ops = [tuple(o) for o in layout['ops']]
    labels = layout['label_op']
    cid_of = _choice_ids(layout)
    sets = {e['id']: e['sets'] for e in layout['endings']}
    known = {}
    g = set()
    order = []
    while True:
        starts = ['start']
        if 'omake' in labels and sum(1 for e in g if e in sets) >= layout['omake_endings']:
            starts.append('omake')
        new = []
        for st in starts:
            found = sc.routes(ops, labels, frozenset(g), start=st)
            for e, path in sorted(found.items(), key=lambda kv: len(kv[1])):
                if e not in known and e not in [n['ending'] for n in new]:
                    new.append(dict(ending=e, start=st, gflags=sorted(g),
                                    path=[(cid_of[i], k, lab, ''.join(text)) for i, k, lab, text in path]))
        if not new:
            break
        for n in new:
            known[n['ending']] = n
            order.append(n)
        for n in new:
            g |= {n['ending'], *sets[n['ending']]}
    missing = [e['id'] for e in layout['endings'] if e['id'] not in known]
    return order, missing


if __name__ == '__main__':
    b = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'build/yonaki')
    lay = json.loads((b / 'layout.json').read_text())
    order, missing = plan(lay)
    for n in order:
        print(f"{n['ending']} from *{n['start']} with {n['gflags'] or 'no global flags'}: "
              + ' / '.join(t for _, _, _, t in n['path']))
    if missing:
        print('not reachable:', missing)
