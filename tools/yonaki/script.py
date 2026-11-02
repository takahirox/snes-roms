"""Scenario parser, text layout and static checks of 夜鳴き鐘 (docs/yonaki/DESIGN.md §7, docs/yonaki/ENGINE.md).

parse() reads every *.txt of a scenario directory (sorted by name) into one program: a list of ops (tuples) and
a label -> op index map.  Paragraph text is normalized, wrapped (18 full-width characters, kinsoku) and split
into page-sized chunks here; pagination across paragraphs happens at run time (a paragraph that does not fit
the rest of the page starts a new page).

Ops (the VM of src/yonaki/vm.inc runs the same list, encoded by tools/yonaki/build.py):
  ('text', tid, chunks)         chunks: list of pages, each a list of lines (str)
  ('blank',) ('page',)
  ('bg', name, mode)            mode: cut fade white mosaic
  ('sil', key, name|None, colour)   key: 'l' 'c' 'r' or 'x=NN'; name None removes
  ('silclear',)
  ('bgm', name|'stop'|'fade') ('se', name) ('amb', name|'off')
  ('fx', kind, arg)             kind: shake flash redflash ripple_on ripple_off dark light wait
  ('set', flag) ('clr', flag) ('setg', g) ('clrg', g)
  ('if', cond, label)           cond = (name, negated, is_global); jumps when the condition holds
  ('goto', label)
  ('choice', cid, [(conds, lines, label), ...])   lines: the option text wrapped (1 or 2 lines)
  ('end', ending_id)
  ('chapter', chid, title)
"""
import pathlib, re

NO_START = set('、。，．・：；？！ー…‥」』）］｝〕〉》】ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々〜゛゜ヽヾゝゞ'
               ',.:;?!)]}')
NO_END = set('「『（［｛〔〈《【([{')
NO_SPLIT = set('…‥―')          # never break between two of these
LINE_PX = 216                    # 18 full-width characters
PAGE_LINES = 12
CHOICE_PX = 188                  # after the cursor and the option letter (src/yonaki/vm.inc OPT_TEXT_X)
MAX_CHOICES = 8
# the names the player sets (はじめから): in the script they are written as the default names, which become
# the control codes $03 / $04; the engine draws the name in their place, so a line is laid out for the longest
NAME_VARS = {'結城': '\x03', '千尋': '\x04'}     # 主人公の名字, ヒロインの名前
NAME_MAX = 4
MAX_CONDS = 4
SIL_KEYS = ('l', 'c', 'r')
BG_MODES = ('cut', 'fade', 'white', 'mosaic')
FX = ('shake', 'flash', 'redflash', 'ripple', 'dark', 'light', 'wait')
BUILTIN_BG = ('black', 'white')
COLOURS = ('blue', 'white', 'red')


class ScriptError(Exception):
    pass


class Diag:
    def __init__(self, strict=False):
        self.errors, self.warnings, self.notes = [], [], []
        self.strict = strict

    def err(self, where, msg):
        self.errors.append(f'{where}: {msg}')

    def warn(self, where, msg):
        (self.errors if self.strict else self.warnings).append(f'{where}: {msg}')

    def note(self, where, msg):
        self.notes.append(f'{where}: {msg}')


def width(s):
    return sum(NAME_MAX * 12 if c in '\x03\x04' else 6 if ord(c) < 0x80 else 12 for c in s)


def name_vars(s):
    for name, code in NAME_VARS.items():
        s = s.replace(name, code)
    return s


def normalize(s, font):
    """Characters the font spells differently (— -> ―, ～ -> 〜 ...); in Japanese text ! and ? are full width
    (！？) and the space after them a full-width space.  Other ASCII stays half width (6 px)."""
    out = []
    for i, c in enumerate(s):
        if c in '!?' and (any(ord(x) > 0x7F for x in s[max(0, i - 1):i + 2]) or not s[:i].isascii()):
            c = chr(ord(c) + 0xFEE0)
        elif c == ' ' and out and out[-1] in '！？':
            c = '　'
        out.append(font.norm(c))
    return ''.join(out)


def wrap(s, maxpx=LINE_PX):
    """Greedy line breaking with kinsoku (push-out): no line starts with NO_START, none ends with NO_END,
    no break inside '……' / '――' or inside a run of ASCII letters/digits."""
    def breakable(a, b):
        if b in NO_START or a in NO_END:
            return False
        if a in NO_SPLIT and b in NO_SPLIT:
            return False
        if a.isascii() and b.isascii() and (a.isalnum() and b.isalnum()):
            return False
        return True

    lines = []
    cur = ''
    for ch in s:
        if width(cur + ch) <= maxpx:
            cur += ch
            continue
        # find the last allowed break inside cur + ch (between cur[i-1] and cur[i])
        t = cur + ch
        cut = None
        for i in range(len(t) - 1, 0, -1):
            if width(t[:i]) <= maxpx and breakable(t[i - 1], t[i]):
                cut = i
                break
        if cut is None:
            raise ScriptError(f'cannot break the line "{s}"')
        lines.append(t[:cut])
        cur = t[cut:]
    if cur:
        lines.append(cur)
    for ln in lines:
        assert width(ln) <= maxpx
    return lines


def check_kinsoku(lines):
    for i, ln in enumerate(lines):
        if i and ln and ln[0] in NO_START:
            return f'line starts with {ln[0]}'
        if i < len(lines) - 1 and ln and ln[-1] in NO_END:
            return f'line ends with {ln[-1]}'
    return None


# ------------------------------------------------------------------ endings
def parse_endings(path):
    out = []
    seen = set()
    for no, line in enumerate(pathlib.Path(path).read_text(encoding='utf-8').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        p = line.split(None, 3)
        if len(p) != 4 or p[1] not in ('true', 'normal', 'bad'):
            raise ScriptError(f'{path}:{no}: expected "ID KIND SCENARIO TITLE" (KIND true|normal|bad): {line}')
        if p[0] in seen:
            raise ScriptError(f'{path}:{no}: ending {p[0]} twice')
        seen.add(p[0])
        out.append(dict(id=p[0], kind=p[1], scenario=p[2], title=p[3], line=no))
    if not out:
        raise ScriptError(f'{path}: no endings')
    if len(out) > 32:
        raise ScriptError(f'{path}: {len(out)} endings (at most 32)')
    return out


def global_names(endings):
    """Global flags (SRAM): cleared_<scenario> for every scenario of endings.txt (set by its endings: main only
    by a true ending, the others by any ending), then extra names used by @setg.  Ending ids are global
    conditions too (that ending was seen)."""
    names = []
    for e in endings:
        n = f'cleared_{e["scenario"]}'
        if n not in names:
            names.append(n)
    return names


def ending_sets(endings):
    """ending id -> global flags it sets."""
    out = {}
    for e in endings:
        if e['scenario'] == 'main':
            out[e['id']] = ['cleared_main'] if e['kind'] == 'true' else []
        else:
            out[e['id']] = [f'cleared_{e["scenario"]}']
    return out


# ------------------------------------------------------------------ parse
class Program:
    def __init__(self):
        self.ops = []            # (op tuple, where)
        self.labels = {}         # name -> op index
        self.label_where = {}
        self.files = []
        self.text_count = 0
        self.choice_count = 0
        self.chapters = []       # titles
        self.gnames = []


def parse(scn_dir, endings, font, diag):
    prog = Program()
    gnames = global_names(endings)
    ending_ids = {e['id'] for e in endings}
    files = sorted(pathlib.Path(scn_dir).glob('*.txt'))
    if not files:
        raise ScriptError(f'{scn_dir}: no *.txt scenario files')
    pending_choice = None
    local_flags = set()

    def is_global(name):
        return name in gnames or name in ending_ids

    def cond(name, where):
        neg = name.startswith('!')
        n = name[1:] if neg else name
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', n):
            diag.err(where, f'bad flag name "{name}"')
        return (n, neg, is_global(n))

    def emit(op, where):
        prog.ops.append((op, where))

    def close_choice():
        nonlocal pending_choice
        if pending_choice is not None:
            op, where = pending_choice
            if not op[2]:
                diag.err(where, '@choice without "> text -> label" lines')
            emit(op, where)
            pending_choice = None

    last_blank = True
    for f in files:
        prog.files.append(f.name)
        lines = f.read_text(encoding='utf-8').splitlines()
        for no, raw in enumerate(lines, 1):
            where = f'{f.name}:{no}'
            line = raw.rstrip()
            s = line.strip()
            if s.startswith('>'):
                if pending_choice is None:
                    diag.err(where, '"> ..." outside a @choice')
                    continue
                m = re.fullmatch(r'>\s*((?:\{[^}]*\}\s*)*)(.*?)\s*->\s*([A-Za-z0-9_]+)\s*', s)
                if not m:
                    diag.err(where, f'bad choice line (expected "> [{{flag}}] text -> label"): {s}')
                    continue
                conds = [cond(c.strip(), where) for c in re.findall(r'\{([^}]*)\}', m.group(1))]
                if len(conds) > MAX_CONDS:
                    diag.err(where, f'more than {MAX_CONDS} conditions on a choice')
                text = name_vars(normalize(m.group(2).strip(), font))
                if not text:
                    diag.err(where, 'empty choice text')
                try:
                    cl = wrap(text, CHOICE_PX)
                except ScriptError as e:
                    diag.err(where, str(e))
                    cl = [text]
                if len(cl) > 2:
                    diag.err(where, f'choice "{text}" needs {len(cl)} lines (at most 2 lines of 15 full-width characters)')
                pending_choice[0][2].append((conds, cl, m.group(3)))
                continue
            close_choice()
            if not s:
                if not last_blank:
                    emit(('blank',), where)
                last_blank = True
                continue
            if s.startswith('#'):
                continue
            last_blank = False
            if s.startswith('*'):
                name = s[1:].strip()
                if not re.fullmatch(r'[A-Za-z0-9_]+', name):
                    diag.err(where, f'bad label name "{name}"')
                elif name in prog.labels:
                    diag.err(where, f'label *{name} defined twice (first at {prog.label_where[name]})')
                else:
                    prog.labels[name] = len(prog.ops)
                    prog.label_where[name] = where
                last_blank = True
                continue
            if s.startswith('@'):
                parts = s[1:].split()
                cmd, args = parts[0], parts[1:]
                if cmd == 'choice':
                    if args:
                        diag.err(where, '@choice takes no arguments')
                    pending_choice = (['choice', prog.choice_count, []], where)
                    prog.choice_count += 1
                elif cmd == 'chapter':
                    title = normalize(s[len('@chapter'):].strip(), font)
                    if not title:
                        diag.err(where, '@chapter without a title')
                    if width(title) > LINE_PX:
                        diag.err(where, f'chapter title too wide ({width(title)} px)')
                    if title not in prog.chapters:
                        prog.chapters.append(title)
                    emit(('chapter', prog.chapters.index(title), title), where)
                elif cmd == 'bg':
                    if not args or len(args) > 2:
                        diag.err(where, 'usage: @bg name [cut|fade|white|mosaic]')
                        continue
                    mode = args[1] if len(args) > 1 else 'fade'
                    if mode not in BG_MODES:
                        diag.err(where, f'unknown @bg transition "{mode}"')
                        mode = 'fade'
                    emit(('bg', args[0], mode), where)
                elif cmd == 'sil':
                    if len(args) < 2 or len(args) > 3:
                        diag.err(where, 'usage: @sil name l|c|r|x=NN [blue|white|red] / @sil - l|c|r|x=NN')
                        continue
                    key = args[1]
                    if key not in SIL_KEYS:
                        m = re.fullmatch(r'x=(\d+)', key)
                        if not m or int(m.group(1)) > 31:
                            diag.err(where, f'bad silhouette position "{key}" (l, c, r or x=0..31)')
                            continue
                        key = f'x={int(m.group(1))}'
                    col = args[2] if len(args) > 2 else 'blue'
                    if col not in COLOURS:
                        diag.err(where, f'unknown silhouette colour "{col}" (blue, white, red)')
                        col = 'blue'
                    emit(('sil', key, None if args[0] == '-' else args[0], col), where)
                elif cmd == 'silclear':
                    emit(('silclear',), where)
                elif cmd == 'bgm':
                    if len(args) != 1:
                        diag.err(where, 'usage: @bgm name|stop|fade')
                        continue
                    emit(('bgm', args[0]), where)
                elif cmd == 'se':
                    if len(args) != 1:
                        diag.err(where, 'usage: @se name')
                        continue
                    emit(('se', args[0]), where)
                elif cmd == 'amb':
                    if len(args) != 1:
                        diag.err(where, 'usage: @amb name|off')
                        continue
                    emit(('amb', args[0]), where)
                elif cmd == 'fx':
                    if not args or args[0] not in FX:
                        diag.err(where, f'unknown @fx {" ".join(args)}')
                        continue
                    k = args[0]
                    if k == 'ripple':
                        if len(args) != 2 or args[1] not in ('on', 'off'):
                            diag.err(where, 'usage: @fx ripple on|off')
                            continue
                        emit(('fx', 'ripple_' + args[1], 0), where)
                    elif k == 'wait':
                        if len(args) != 2 or not args[1].isdigit() or not 0 < int(args[1]) < 65536:
                            diag.err(where, 'usage: @fx wait N (frames, 1..65535)')
                            continue
                        emit(('fx', 'wait', int(args[1])), where)
                    else:
                        if len(args) != 1:
                            diag.err(where, f'@fx {k} takes no argument')
                        emit(('fx', k, 0), where)
                elif cmd in ('set', 'clr', 'setg', 'clrg'):
                    if len(args) != 1:
                        diag.err(where, f'usage: @{cmd} flag')
                        continue
                    n = args[0]
                    c = cond(n, where)
                    if cmd in ('set', 'clr'):
                        if c[2]:
                            diag.err(where, f'"{n}" is a global flag: use @setg / @clrg')
                        local_flags.add(n)
                        emit((cmd, n), where)
                    else:
                        if n in ending_ids:
                            diag.err(where, f'"{n}" is an ending (set by @end)')
                        if n not in gnames:
                            gnames.append(n)
                        emit((cmd, n), where)
                elif cmd in ('if', 'ifnot', 'ifg'):
                    if len(args) != 2:
                        diag.err(where, f'usage: @{cmd} flag label')
                        continue
                    c = cond(args[0], where)
                    if cmd == 'ifg' and not c[2]:
                        diag.err(where, f'@ifg {args[0]}: not a global flag ({", ".join(gnames)} or an ending id)')
                    emit(('if', (c[0], c[1] != (cmd == 'ifnot'), c[2]), args[1]), where)
                elif cmd == 'goto':
                    if len(args) != 1:
                        diag.err(where, 'usage: @goto label')
                        continue
                    emit(('goto', args[0]), where)
                elif cmd == 'end':
                    if len(args) != 1:
                        diag.err(where, 'usage: @end ID')
                        continue
                    if args[0] not in ending_ids:
                        diag.err(where, f'@end {args[0]}: not in endings.txt')
                    emit(('end', args[0]), where)
                elif cmd == 'page':
                    emit(('page',), where)
                else:
                    diag.err(where, f'unknown command @{cmd}')
                continue
            # a paragraph
            text = name_vars(normalize(s, font))
            bad = sorted({c for c in text if not font.has(c) and c not in '\x03\x04'})
            if bad:
                diag.err(where, f'characters not in the font: {" ".join(f"{c}(U+{ord(c):04X})" for c in bad)}')
                text = ''.join(c for c in text if c not in bad) or '　'
            try:
                lines_ = wrap(text)
            except ScriptError as e:
                diag.err(where, str(e))
                continue
            k = check_kinsoku(lines_)
            if k:
                diag.warn(where, f'kinsoku: {k}: {lines_}')
            chunks = [lines_[i:i + PAGE_LINES] for i in range(0, len(lines_), PAGE_LINES)]
            emit(('text', prog.text_count, chunks), where)
            prog.text_count += 1
        close_choice()
    # choice ops were built as lists
    prog.ops = [(tuple(op) if isinstance(op, list) else op, w) for op, w in prog.ops]
    prog.gnames = gnames
    prog.local_flags = sorted(local_flags | {c[0] for op, _ in prog.ops if op[0] == 'if' and not op[1][2]
                                             for c in [op[1]]}
                              | {c[0] for op, _ in prog.ops if op[0] == 'choice' for cs, _, _ in op[2]
                                 for c in cs if not c[2]})
    return prog


# ------------------------------------------------------------------ checks
def successors(prog, i):
    op = prog.ops[i][0]
    k = op[0]
    nxt = [i + 1] if i + 1 < len(prog.ops) else ['fall']
    lab = lambda n: prog.labels.get(n, 'undef')
    if k == 'goto':
        return [lab(op[1])]
    if k == 'if':
        return [lab(op[2])] + nxt
    if k == 'choice':
        return [lab(t) for _, _, t in op[2]]
    if k == 'end':
        return []
    return nxt


def entries(prog):
    return [n for n in ('start', 'omake') if n in prog.labels]


def bg_flow(prog):
    """The backgrounds that can be on screen at each op (a set per op index, empty when unreachable).
    The entries start on black; a @bg sets the picture for the ops after it."""
    ops = prog.ops
    at = [set() for _ in ops]
    work = [(prog.labels[n], 'black') for n in entries(prog)]
    while work:
        i, bg = work.pop()
        if not isinstance(i, int) or i >= len(ops) or bg in at[i]:
            continue
        at[i].add(bg)
        out = ops[i][0][1] if ops[i][0][0] == 'bg' else bg
        for s in successors(prog, i):
            work.append((s, out))
    return at


def check(prog, endings, diag, assets):
    """Static checks.  assets: dict(bg=set, sil=set, bgm=set, se=set of known names, bg_files=set, sil_files=set,
    allow_missing_art=bool, unknown_sound_error=bool)."""
    ops = prog.ops
    if 'start' not in prog.labels:
        diag.err('scenario', 'no *start label')
    # label references
    refs = {}
    for i, (op, where) in enumerate(ops):
        targets = []
        if op[0] == 'goto':
            targets = [op[1]]
        elif op[0] == 'if':
            targets = [op[2]]
        elif op[0] == 'choice':
            targets = [t for _, _, t in op[2]]
            if len(op[2]) > MAX_CHOICES:
                diag.err(where, f'{len(op[2])} choices (at most {MAX_CHOICES})')
            if sum(len(t) for _, t, _ in op[2]) > PAGE_LINES - 1:
                diag.err(where, f'the options of this choice take more than {PAGE_LINES - 1} lines')
            if all(any(c[2] for c in cs) for cs, _, _ in op[2]):
                diag.warn(where, 'every option of this choice is gated by a global flag')
        for t in targets:
            refs.setdefault(t, []).append(where)
            if t not in prog.labels:
                diag.err(where, f'undefined label *{t}')
    for name, where in prog.label_where.items():
        if name not in refs and name not in ('start', 'omake'):
            diag.note(where, f'label *{name} is never jumped to (only falls through)')
    # reachability
    seen = set()
    stack = [prog.labels[n] for n in entries(prog)]
    falls = []
    while stack:
        i = stack.pop()
        if i in seen or not isinstance(i, int) or i >= len(ops):
            continue
        seen.add(i)
        for s in successors(prog, i):
            if s == 'fall':
                falls.append(i)
            elif isinstance(s, int):
                stack.append(s)
    for i in sorted(set(falls)):
        diag.err(ops[i][1], 'the scenario runs off its end here (no @goto / @end / @choice after it)')
    for name, idx in prog.labels.items():
        if idx not in seen and idx < len(ops):
            diag.warn(prog.label_where[name], f'label *{name} is unreachable from *start')
    # files must not fall into the next file silently
    reached_endings = {ops[i][0][1] for i in seen if ops[i][0][0] == 'end'}
    for e in endings:
        if e['id'] not in reached_endings:
            used = any(op[0] == 'end' and op[1] == e['id'] for op, _ in ops)
            diag.warn(f'endings.txt:{e["line"]}', f'ending {e["id"]} {e["title"]} is '
                      + ('not reachable from *start' if used else 'never reached (no @end ' + e['id'] + ')'))
    # flags
    tested = {op[1][0] for op, _ in ops if op[0] == 'if' and not op[1][2]} | \
        {c[0] for op, _ in ops if op[0] == 'choice' for cs, _, _ in op[2] for c in cs if not c[2]}
    setf = {op[1] for op, _ in ops if op[0] in ('set',)}
    for f in sorted(tested - setf):
        w = next(w for op, w in ops if (op[0] == 'if' and op[1][0] == f) or
                 (op[0] == 'choice' and any(c[0] == f for cs, _, _ in op[2] for c in cs)))
        diag.warn(w, f'flag "{f}" is tested but never @set')
    for f in sorted(setf - tested):
        w = next(w for op, w in ops if op[0] == 'set' and op[1] == f)
        diag.note(w, f'flag "{f}" is set but never tested')
    # assets
    for op, where in ops:
        if op[0] == 'bg' and op[1] not in BUILTIN_BG:
            if op[1] not in assets['bg_files']:
                if assets['allow_missing_art']:
                    diag.warn(where, f'background "{op[1]}" has no picture (black)')
                else:
                    diag.err(where, f'background "{op[1]}": no assets/yonaki/src/bg/{op[1]}.png '
                             '(use --allow-missing-art to build with black)')
            if op[1] not in assets['bg']:
                diag.warn(where, f'background "{op[1]}" is not a known name (assets/yonaki/prompts.json)')
        if op[0] == 'sil' and op[2]:
            if op[2] not in assets['sil_files']:
                if assets['allow_missing_art']:
                    diag.warn(where, f'silhouette "{op[2]}" has no picture (placeholder figure)')
                else:
                    diag.err(where, f'silhouette "{op[2]}": no assets/yonaki/src/sil/{op[2]}.png '
                             '(use --allow-missing-art)')
            if op[2] not in assets['sil']:
                diag.warn(where, f'silhouette "{op[2]}" is not a known name (assets/yonaki/prompts.json)')
        if op[0] == 'bgm' and op[1] not in ('stop', 'fade') and op[1] not in assets['bgm']:
            (diag.err if assets['unknown_sound_error'] else diag.warn)(where, f'unknown song "{op[1]}"')
        if op[0] == 'se' and op[1] not in assets['se']:
            if op[1] in assets['amb']:
                diag.note(where, f'"@se {op[1]}" starts the ambience {op[1]} (same as @amb {op[1]})')
            else:
                (diag.err if assets['unknown_sound_error'] else diag.warn)(where, f'unknown sound effect "{op[1]}"')
        if op[0] == 'amb' and op[1] != 'off' and op[1] not in assets['amb']:
            (diag.err if assets['unknown_sound_error'] else diag.warn)(where, f'unknown ambience "{op[1]}"')
    return seen


# ------------------------------------------------------------------ simulation (routes)
def simulate(ops, labels, start, flags, gflags, choose, limit=200000):
    """Run the program from label start with local flags (set) and global flags (set: names and ending ids).
    choose(choice_op_index, visible_options) -> option index (into visible) or None to stop.  Returns
    ('end', ending_id, path) or ('stop', op_index, path) where path is a list of (op index, visible index, label)."""
    i = labels[start]
    flags = set(flags)
    path = []
    steps = 0
    while steps < limit:
        steps += 1
        op = ops[i]
        k = op[0]
        if k == 'goto':
            i = labels[op[1]]
            continue
        if k == 'if':
            n, neg, _ = op[1]
            hold = (n in gflags if op[1][2] else n in flags) != neg
            i = labels[op[2]] if hold else i + 1
            continue
        if k == 'set':
            flags.add(op[1])
        elif k == 'clr':
            flags.discard(op[1])
        elif k == 'setg':
            gflags = set(gflags) | {op[1]}
        elif k == 'clrg':
            gflags = set(gflags) - {op[1]}
        elif k == 'end':
            return ('end', op[1], path, flags)
        elif k == 'choice':
            vis = [(j, o) for j, o in enumerate(op[2])
                   if all(((c[0] in gflags) if c[2] else (c[0] in flags)) != c[1] for c in o[0])]
            c = choose(i, vis, flags)
            if c is None:
                return ('stop', i, path, flags)
            path.append((i, c, vis[c][1][2], vis[c][1][1]))
            i = labels[vis[c][1][2]]
            continue
        i += 1
    raise ScriptError('simulation did not finish (a loop without choices?)')


def _tested_flags(ops):
    out = set()
    for op in ops:
        if op[0] == 'if' and not op[1][2]:
            out.add(op[1][0])
        elif op[0] == 'choice':
            for o in op[2]:
                out |= {c[0] for c in o[0] if not c[2]}
    return out


def _advance(ops, labels, i, flags, gflags, tested, limit=100000):
    """Run from op i until a choice or an ending: ('choice', i, flags, visible) / ('end', id, flags) /
    ('stop', i, flags) when the program halts.  flags: frozenset of the tested local flags only."""
    flags = set(flags)
    for _ in range(limit):
        if i >= len(ops):
            return ('stop', i, frozenset(flags), None)
        op = ops[i]
        k = op[0]
        if k == 'goto':
            i = labels[op[1]]
            continue
        if k == 'if':
            n, neg, glob = op[1]
            hold = (n in gflags if glob else n in flags) != neg
            i = labels[op[2]] if hold else i + 1
            continue
        if k == 'set' and op[1] in tested:
            flags.add(op[1])
        elif k == 'clr':
            flags.discard(op[1])
        elif k == 'end':
            return ('end', op[1], frozenset(flags), None)
        elif k == 'choice':
            vis = [o for o in op[2] if all(((c[0] in gflags) if c[2] else (c[0] in flags)) != c[1] for c in o[0])]
            return ('choice', i, frozenset(flags), vis)
        elif k == 'halt':
            return ('stop', i, frozenset(flags), None)
        i += 1
    raise ScriptError('simulation did not finish (a loop without choices?)')


def routes(ops, labels, gflags, start='start', max_states=500000):
    """Breadth-first search over (choice op, tested local flags): the shortest choice path to every ending
    reachable with the given global flags (names and seen ending ids).
    Returns {ending_id: [(choice op index, visible index, target label, text lines)]}."""
    from collections import deque
    tested = _tested_flags(ops)
    found = {}
    seen = set()
    q = deque([(labels[start], frozenset(), ())])
    while q and len(seen) < max_states:
        i, flags, path = q.popleft()
        r = _advance(ops, labels, i, flags, gflags, tested)
        if r[0] == 'end':
            found.setdefault(r[1], list(path))
            continue
        if r[0] != 'choice':
            continue
        key = (r[1], r[2])
        if key in seen:
            continue
        seen.add(key)
        for j, o in enumerate(r[3]):
            q.append((labels[o[2]], r[2], path + ((r[1], j, o[2], o[1]),)))
    return found
