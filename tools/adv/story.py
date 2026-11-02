"""Parser for data/adv/story.txt (the scenario of 潮鳴りの密室).

Returns plain Python structures; tools/adv/build.py lays out the text and emits the ROM tables.
Blocks start with "@kind args"; see the header of story.txt for the script lines.
"""
import re


class StoryError(Exception):
    pass


class Block:
    def __init__(self, kind, args, line):
        self.kind, self.args, self.line = kind, args, line
        self.keys = {}
        self.lines = []          # (lineno, text) script lines, in order


def read_blocks(text):
    blocks = []
    cur = None
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if line.startswith('@'):
            head = line[1:].split()
            cur = Block(head[0], head[1:], no)
            blocks.append(cur)
            continue
        if cur is None:
            raise StoryError(f'line {no}: text outside a block')
        m = re.match(r'^(name|image|person|portrait|music|if):\s*(.*)$', line)
        if m and not cur.lines and cur.kind in ('scene', 'person', 'look', 'topic', 'clue', 'hint'):
            cur.keys[m.group(1)] = m.group(2).strip()
            continue
        cur.lines.append((no, line))
    return blocks


def split_sections(block, names):
    """For @deduce: split the lines into sections that start with 'name:' or 'name ARG:' headers."""
    out = []
    for no, line in block.lines:
        m = re.match(r'^(%s)(\*?)(?:\s+([^:]+?))?:\s*(.*)$' % '|'.join(names), line)
        if m and not line.startswith(('>',)) and '>' not in line.split(':', 1)[0]:
            out.append(dict(name=m.group(1), star=bool(m.group(2)), arg=(m.group(3) or '').strip(),
                            rest=m.group(4).strip(), line=no, lines=[]))
        else:
            if not out:
                raise StoryError(f'line {no}: deduce text before a section header')
            out[-1]['lines'].append((no, line))
    return out


def parse(text):
    blocks = read_blocks(text)
    st = dict(images={}, image_order=[], persons={}, person_order=[], scenes={}, scene_order=[],
              groups={}, clues={}, clue_order=[], looks=[], topics=[], shows=[], scripts={},
              hints=[], requires=[], deduce=[], time=[])
    for b in blocks:
        k = b.kind
        if k == 'image':
            name, path = b.args
            st['images'][name] = path
            st['image_order'].append(name)
        elif k == 'person':
            pid = b.args[0]
            st['persons'][pid] = dict(id=pid, name=b.keys['name'])
            st['person_order'].append(pid)
        elif k == 'scene':
            sid = b.args[0]
            sc = dict(id=sid, name=b.keys['name'], image=b.keys['image'], person=b.keys.get('person'),
                      cond=b.keys.get('if', ''), music=b.keys.get('music', 'investigate'), portrait=None)
            if 'portrait' in b.keys:
                path, x, y = b.keys['portrait'].split()
                sc['portrait'] = (path, int(x), int(y))
            st['scenes'][sid] = sc
            st['scene_order'].append(sid)
        elif k == 'group':
            m = re.match(r'^(\w+)\s*=\s*(.+)$', ' '.join(b.args))
            st['groups'][m.group(1)] = [t.strip() for t in m.group(2).split('|')]
        elif k == 'clue':
            cid, kind = b.args
            assert kind in ('item', 'testimony'), (b.line, kind)
            st['clues'][cid] = dict(id=cid, kind=kind, name=b.keys['name'], desc=b.lines, line=b.line)
            st['clue_order'].append(cid)
        elif k == 'look':
            st['looks'].append(dict(scene=b.args[0], label=' '.join(b.args[1:]), cond=b.keys.get('if', ''),
                                    lines=b.lines, line=b.line))
        elif k == 'topic':
            st['topics'].append(dict(person=b.args[0], label=' '.join(b.args[1:]), cond=b.keys.get('if', ''),
                                     lines=b.lines, line=b.line))
        elif k == 'show':
            st['shows'].append(dict(person=b.args[0], clues=b.args[1:], lines=b.lines, line=b.line))
        elif k == 'script':
            st['scripts'][b.args[0]] = b.lines
        elif k == 'hint':
            texts = {}
            for no, line in b.lines:
                m = re.match(r'^([12])>\s*(.*)$', line)
                if not m:
                    raise StoryError(f'line {no}: hint lines are "1> ..." and "2> ..."')
                texts[int(m.group(1))] = m.group(2)
            st['hints'].append(dict(cond=b.keys.get('if', ''), t1=texts[1], t2=texts[2], line=b.line))
        elif k == 'require':
            st['requires'].append(dict(terms=b.args, lines=b.lines, line=b.line))
        elif k == 'deduce':
            kind = b.args[0]
            q = dict(kind=kind, accept=b.args[1:], line=b.line, prompt=None, ok=None, wrong=None,
                     opts=[], wrong_for={})
            q['ask'] = None
            for sec in split_sections(b, ['ask', 'prompt', 'opt', 'ok', 'wrong']):
                if sec['name'] == 'ask':
                    q['ask'] = sec['rest']
                elif sec['name'] == 'prompt':
                    q['prompt'] = sec['lines']
                elif sec['name'] == 'ok':
                    q['ok'] = sec['lines']
                elif sec['name'] == 'wrong':
                    if sec['arg']:
                        q['wrong_for'][sec['arg']] = sec['lines']
                    else:
                        q['wrong'] = sec['lines']
                elif sec['name'] == 'opt':
                    q['opts'].append(dict(label=sec['arg'] or sec['rest'], correct=sec['star'], lines=sec['lines']))
            st['deduce'].append(q)
        elif k == 'time':
            for no, line in b.lines:
                cond, _, t = line.partition(':')
                st['time'].append((cond.strip(), t.strip()))
        else:
            raise StoryError(f'line {b.line}: unknown block @{k}')
    return st
