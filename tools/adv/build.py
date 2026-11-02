"""Build the data of 潮鳴りの密室 (SFC adventure) from data/adv/story.txt and assets/adv/*.png.

usage: python3 -I tools/adv/build.py
writes build/adv/const.inc (assembler constants), build/adv/data.inc (tables, scripts, segments),
build/adv/*.bin (font, text banks, pictures, portraits, mouth frames), build/adv/manifest.json (source hashes,
sizes), build/adv/layout.json (lists, flags and texts for the tests and the QA).

Lip-sync: a page spoken by a person (a "NAME> text" script line) carries the speaker code $FFE0|id after
the yellow name (id = person order + 1, SPEAKER_ME for わたし); data/adv/mouths.txt gives the half-open
and open mouth of each portrait (tools/adv/mouth.py), quantized with the picture (tools/adv/quantize.py).
Speech blips: data/adv/voices.txt (tools/adv/voice.py) gives each speaker's voice; the samples and the
per-voice tables go into the driver (tools/adv/spc.py), SpeakerVoice / SpeakerGap / GlyphVoice into data.inc.

Everything is checked here: line widths in pixels, kinsoku, undefined flags/clues, the reachability of
every clue from the start, and that each deduction question is answerable when deduction can start.
"""
import sys, json, hashlib, pathlib, re, struct

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/adv'))
import png_codec                          # shared deterministic PNG reader (read-only use)
import story as storymod
import quantize
import spc
import songs as songsmod
import voice as voicemod
import mouth as mouthmod

OUT = ROOT / 'build/adv'
STORY = ROOT / 'data/adv/story.txt'
MOUTHS = ROOT / 'data/adv/mouths.txt'
VOICES = ROOT / 'data/adv/voices.txt'
FONT_K = ROOT / 'assets/shinonome/shnmk12.bdf'
FONT_A = ROOT / 'assets/shinonome/shnm6x12r.bdf'

# ------------------------------------------------------------------ screen layout (screen pixels)
MSG_X0 = 12
MSG_LINE_PX = 216            # 18 full-width characters
MSG_LINES = 4                # 3 under a speaker name
LIST_LABEL_PX = 132          # 11 full-width characters (right box, cursor at x 82, text from x 94)
CMD_LABEL_PX = 48            # left box, 4 characters
HDR_LEFT_PX = 108            # scene name, from x 6
HDR_RIGHT_PX = 138           # status, right-aligned to x 250
ROM_BANKS = 16               # 512 KiB LoROM

COLOR_WHITE, COLOR_GRAY, COLOR_YELLOW, COLOR_CYAN = 2, 5, 6, 7

# lip-sync: speaker code $FFE0 | id (glyph numbers stay below it), the player's id, and the frames the
# mouth stays closed after a glyph (a pause; the largest of the glyphs typed in one frame is used)
SPEAKER_CODE = 0xFFE0
SPEAKER_ME = 0xE
PLAYER_NAMES = {'わたし'}
PAUSE_FRAMES = {**{c: 4 for c in '、，・」』）　'}, **{c: 8 for c in '。．！？…‥'}}

NO_START = set('、。，．・：；？！ー…‥」』）］｝〕〉》】ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々〜')
NO_END = set('「『（［｛〔〈《【')

OP = dict(END=0, TEXT=1, SET=2, CLR=3, IF=4, IFN=5, JMP=6, GOTO=7, IMAGE=8, SFX=9, CALL=10, DEDUCE=11,
          ENDING=12, COUNT=13, RESUME=14, MUSIC=15)
# the prologue of the opening (src/adv/opening.inc): two centred lines per picture
OPENING_CAPTIONS = [
    ('この物語はフィクションです。', '実在の人物・団体とは関係ありません。'),
    ('昭和六十二年　十一月十四日', '時化の夜の　汐見港'),
    ('灯台の光が　くりかえし', '暗い海をなでていく'),
    ('時化は　夜半すぎに去った', '港の灯が　ひとつずつ消えていく'),
    ('第三倉庫の二階', '内側から鍵のかかった部屋で……'),
]
SFX = dict(cursor=1, ok=2, cancel=3, clue=4, wrong=5, page=6, right=7, move=8)


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


class BuildError(Exception):
    pass


# ------------------------------------------------------------------ font
def load_bdf(path, rowbytes):
    glyphs = {}
    enc = bits = None
    for line in path.read_text(encoding='latin-1').splitlines():
        if line.startswith('ENCODING'):
            enc = int(line.split()[1])
        elif line == 'BITMAP':
            bits = []
        elif line == 'ENDCHAR':
            glyphs[enc] = bits
            bits = None
        elif bits is not None:
            bits.append(int(line, 16) << (16 - 8 * rowbytes))
    return glyphs


CUSTOM = {
    # right-pointing cursor triangle (not in JIS X 0208)
    '▶': ['............', '..X.........', '..XX........', '..XXX.......', '..XXXX......', '..XXXXX.....',
          '..XXXX......', '..XXX.......', '..XX........', '..X.........', '............', '............'],
}


class Font:
    def __init__(self):
        self.k = load_bdf(FONT_K, 2)
        self.a = load_bdf(FONT_A, 1)
        self.chars = ['　']          # glyph 0 = full-width space
        self.index = {'　': 0}

    def glyph(self, ch):
        if ch not in self.index:
            self.rows(ch)
            self.index[ch] = len(self.chars)
            self.chars.append(ch)
        return self.index[ch]

    def width(self, ch):
        return 6 if ord(ch) < 0x80 else 12

    def rows(self, ch):
        if ch in CUSTOM:
            return [int(r.replace('X', '1').replace('.', '0') + '0000', 2) for r in CUSTOM[ch]]
        if ch == '　':
            return [0] * 12
        if ord(ch) < 0x80:
            if ord(ch) not in self.a:
                raise BuildError(f'no half-width glyph for {ch!r}')
            return self.a[ord(ch)]
        try:
            jis = ch.encode('iso2022_jp')
        except UnicodeEncodeError:
            raise BuildError(f'character {ch!r} (U+{ord(ch):04X}) is not in JIS X 0208')
        if not (jis[:3] == b'\x1b$B' and len(jis) == 8):
            raise BuildError(f'character {ch!r} is not a JIS X 0208 glyph')
        code = jis[3] << 8 | jis[4]
        if code not in self.k:
            raise BuildError(f'no glyph for {ch!r}')
        return self.k[code]

    def blob(self):
        out = bytearray()
        for ch in self.chars:
            for r in self.rows(ch):
                out += bytes([r >> 8 & 0xFF, r & 0xFF])     # left 8 pixels, right 8 pixels
        return bytes(out)


def normalize(s):
    """Half-width digits and Latin in prose become full-width; keep ASCII only where asked with {}."""
    out = []
    for ch in s:
        o = ord(ch)
        if 0x21 <= o <= 0x7E:
            out.append(chr(o + 0xFEE0))
        elif ch == ' ':
            out.append('　')
        else:
            out.append(ch)
    return ''.join(out)


# ------------------------------------------------------------------ texts
class Texts:
    def __init__(self, font):
        self.font = font
        self.items = []          # list of (codes(list of words), info)
        self.lookup = {}
        self.layout = []         # for layout.json
        self.speaker_ids = {}    # name -> lip-sync speaker id (set by the builder)

    def add(self, codes, info):
        key = tuple(codes)
        if key in self.lookup:
            return self.lookup[key]
        self.items.append(codes)
        self.layout.append(info)
        self.lookup[key] = len(self.items) - 1
        return self.lookup[key]

    def width(self, s):
        return sum(self.font.width(c) for c in s)

    def label(self, s, maxpx, what, color=None, raw=False):
        s = s if raw else normalize(s)
        w = self.width(s)
        if w > maxpx:
            raise BuildError(f'{what}: "{s}" is {w}px wide (max {maxpx})')
        codes = ([0xFFFC, color] if color else []) + [self.font.glyph(c) for c in s] + [0xFFFF]
        return self.add(codes, dict(kind='label', text=s, width=w, max=maxpx, what=what))

    def wrap(self, s, what):
        lines, cur, w = [], [], 0
        for ch in s:
            cw = self.font.width(ch)
            if w + cw > MSG_LINE_PX:
                carry = []
                # kinsoku: do not start a line with ch in NO_START, do not end it with NO_END
                if ch in NO_START:
                    while cur and len(carry) < 3:
                        carry.insert(0, cur.pop())
                        if carry[0] not in NO_START:
                            break
                while cur and cur[-1] in NO_END:
                    carry.insert(0, cur.pop())
                if not cur:
                    raise BuildError(f'{what}: cannot break "{s}"')
                lines.append(''.join(cur))
                cur = carry
                w = sum(self.font.width(c) for c in cur)
            cur.append(ch)
            w += cw
        if cur:
            lines.append(''.join(cur))
        for ln in lines[1:]:
            if ln and ln[0] in NO_START:
                raise BuildError(f'{what}: line starts with "{ln[0]}": {ln}')
            if self.width(ln) > MSG_LINE_PX:
                raise BuildError(f'{what}: line too wide: {ln}')
        return lines

    def message(self, paras, what, voiced=False):
        """paras: list of (speaker or None, text) or ('--', None) page breaks.  Returns a text id.
        voiced: the speakers are people of the script (NAME> lines): each named page gets the speaker
        code after the name.  Other names (notebook headings, ヒント, system titles) get no code."""
        pages = []          # list of (speaker, [lines])
        cur = None
        for sp, text in paras:
            if sp == '--':
                cur = None
                continue
            text = normalize(text)
            lines = self.wrap(text, what)
            cap = MSG_LINES - (1 if sp else 0)
            if cur is None or cur[0] != sp:
                cur = (sp, [])
                pages.append(cur)
            for ln in lines:
                if len(cur[1]) >= cap:
                    cur = (sp, [])
                    pages.append(cur)
                cur[1].append(ln)
        if not pages:
            raise BuildError(f'{what}: empty message')
        codes = []
        ids = []
        for i, (sp, lines) in enumerate(pages):
            if i:
                codes.append(0xFFFD)
            sid = None
            if sp:
                name = normalize(sp)
                if self.width(name) > MSG_LINE_PX:
                    raise BuildError(f'{what}: speaker name too wide')
                codes += [0xFFFC, COLOR_YELLOW] + [self.font.glyph(c) for c in name] + [0xFFFE, 0xFFFC, COLOR_WHITE]
                if voiced:
                    if sp not in self.speaker_ids:
                        raise BuildError(f'{what}: speaker "{sp}" is neither a @person name nor {sorted(PLAYER_NAMES)}')
                    sid = self.speaker_ids[sp]
                    codes.append(SPEAKER_CODE | sid)
            ids.append(sid)
            for j, ln in enumerate(lines):
                if j:
                    codes.append(0xFFFE)
                codes += [self.font.glyph(c) for c in ln]
        codes.append(0xFFFF)
        return self.add(codes, dict(kind='message', what=what,
                                    pages=[dict(speaker=sp, speaker_id=sid, lines=lines)
                                           for (sp, lines), sid in zip(pages, ids)]))

    def encode_banks(self, first_bank):
        """Pack the texts into 32 KiB banks without crossing; returns (bank blobs, long addresses)."""
        banks, addrs = [bytearray()], []
        for codes in self.items:
            data = b''.join(struct.pack('<H', c) for c in codes)
            if len(banks[-1]) + len(data) > 0x8000:
                banks.append(bytearray())
            addrs.append(((first_bank + len(banks) - 1) << 16) | (0x8000 + len(banks[-1])))
            banks[-1] += data
        return [bytes(b) for b in banks], addrs


# ------------------------------------------------------------------ build
class Builder:
    def __init__(self):
        self.st = storymod.parse(STORY.read_text(encoding='utf-8'))
        self.font = Font()
        self.tx = Texts(self.font)
        self.flags = {}                   # name -> id (1..)
        self.asm = []                     # data.inc lines (RODATA)
        self.labelno = 0
        self.scripts = {}                 # name -> asm label
        self.pending_calls = []
        self.flag_sources = {}            # flag -> list of where it is set
        self.flag_uses = {}

    # -- flags
    def flag(self, name):
        if name not in self.flags:
            self.flags[name] = len(self.flags) + 1
        return self.flags[name]

    def cond_terms(self, cond, seen=None, where=''):
        terms = []
        for t in cond.split():
            neg = t.startswith('!')
            n = t[1:] if neg else t
            if n == 'seen':
                if seen is None:
                    raise BuildError(f'{where}: "seen" outside an item')
                fid = seen
            else:
                self.check_flag_name(n, where)
                fid = self.flag(n)
                self.flag_uses.setdefault(n, []).append(where)
            terms.append((fid, neg, n))
        return terms

    def check_flag_name(self, n, where):
        if not re.match(r'^(K_|T_|F_|G_|H_)\w+$', n):
            raise BuildError(f'{where}: bad flag name {n}')
        if n[:2] in ('K_', 'T_') and n not in self.st['clues']:
            raise BuildError(f'{where}: unknown clue {n}')
        if n.startswith('G_') and n not in self.st['groups']:
            raise BuildError(f'{where}: unknown group {n}')

    def new_label(self, base='L'):
        self.labelno += 1
        return f'{base}{self.labelno}'

    # -- scripts
    def compile(self, lines, where, seen=None, label=None):
        """Compile script lines into .word statements.  Returns the label."""
        label = label or self.new_label('S')
        out = [f'{label}:']
        paras = []
        stack = []                     # (else_label, end_label, has_else)

        def flush():
            if paras:
                tid = self.tx.message(list(paras), where, voiced=True)
                out.append(f'    .word OP_TEXT, {tid}')
                paras.clear()

        for no, line in lines:
            w = f'{where} (story.txt:{no})'
            m = re.match(r'^([^>\s]*)>\s?(.*)$', line)
            if line.strip() == '--':
                paras.append(('--', None))
                continue
            if m and ':' not in m.group(1):
                sp = m.group(1) or None
                paras.append((sp, m.group(2)))
                continue
            flush()
            if line.startswith('?'):
                body = line[1:].strip()
                if body == 'else':
                    els, end, _ = stack[-1]
                    out.append(f'    .word OP_JMP, {end}')
                    out.append(f'{els}:')
                    stack[-1] = (None, end, True)
                elif body == 'end':
                    els, end, _ = stack.pop()
                    if els:
                        out.append(f'{els}:')
                    out.append(f'{end}:')
                else:
                    els, end = self.new_label('E'), self.new_label('N')
                    for fid, neg, n in self.cond_terms(body, seen, w):
                        out.append(f'    .word {"OP_IF" if neg else "OP_IFN"}, {fid}, {els}   ; {"!" if neg else ""}{n}')
                    stack.append((els, end, False))
                continue
            key, _, val = line.partition(':')
            key, val = key.strip(), val.strip()
            if key == 'get':
                out += self.get_clue(val, w)
            elif key in ('set', 'clr'):
                self.check_flag_name(val, w)
                fid = self.flag(val)
                if key == 'set':
                    self.flag_sources.setdefault(val, []).append(w)
                out.append(f'    .word {"OP_SET" if key == "set" else "OP_CLR"}, {fid}   ; {val}')
            elif key == 'goto':
                if val not in self.st['scenes']:
                    raise BuildError(f'{w}: unknown scene {val}')
                out.append(f'    .word OP_GOTO, {self.st["scene_order"].index(val)}')
            elif key == 'image':
                out.append(f'    .word OP_IMAGE, {self.image_index[val]}')
            elif key == 'sfx':
                out.append(f'    .word OP_SFX, {SFX[val]}')
            elif key == 'music':
                if val == 'scene':
                    out.append('    .word OP_MUSIC, $FF')
                elif val in songsmod.SONG_IDS:
                    out.append(f'    .word OP_MUSIC, {songsmod.SONG_IDS[val]}   ; {val}')
                else:
                    raise BuildError(f'{w}: unknown song {val}')
            elif key == 'call':
                out.append(f'    .word OP_CALL, SCR_{val}')
                self.pending_calls.append((val, w))
            elif line.strip() == 'deduce':
                out.append('    .word OP_DEDUCE')
            elif line.strip() == 'ending':
                out.append('    .word OP_ENDING')
            else:
                raise BuildError(f'{w}: cannot read "{line}"')
        flush()
        if stack:
            raise BuildError(f'{where}: unclosed ?condition')
        out.append('    .word OP_END')
        self.asm += out
        return label

    def get_clue(self, cid, where):
        if cid not in self.st['clues']:
            raise BuildError(f'{where}: unknown clue {cid}')
        self.flag_sources.setdefault(cid, []).append(where)
        c = self.st['clues'][cid]
        skip = self.new_label('G')
        out = [f'    .word OP_IF, {self.flag(cid)}, {skip}   ; {cid}',
               f'    .word OP_SET, {self.flag(cid)}']
        for g, members in self.st['groups'].items():
            if cid in members:
                out.append(f'    .word OP_SET, {self.flag(g)}   ; {g}')
        out.append(f'    .word OP_SFX, {SFX["clue"]}')
        out.append(f'    .word OP_TEXT, {self.clue_get_text[cid]}')
        out.append(f'{skip}:')
        return out

    # -- main
    def run(self):
        OUT.mkdir(parents=True, exist_ok=True)
        st = self.st
        # clue flags first (clue id i+1 has flag i+1), then groups
        for cid in st['clue_order']:
            self.flag(cid)
        for g in st['groups']:
            self.flag(g)
        self.check_groups()
        for i, pid in enumerate(st['person_order']):
            self.tx.speaker_ids[st['persons'][pid]['name']] = i + 1
        for n in PLAYER_NAMES:
            self.tx.speaker_ids[n] = SPEAKER_ME
        if len(st['person_order']) >= SPEAKER_ME:
            raise BuildError('too many people for the speaker code')
        self.images()
        self.system_texts()
        self.clue_tables()
        self.scene_tables()
        self.script_blocks()
        self.hint_script()
        self.deduce_tables()
        self.time_table()
        for name, w in self.pending_calls:
            if name not in self.scripts:
                raise BuildError(f'{w}: call to unknown script {name}')
        self.check_flags()
        self.reachability()
        self.emit()

    def check_groups(self):
        for g, members in self.st['groups'].items():
            for m in members:
                if m not in self.st['clues']:
                    raise BuildError(f'group {g}: unknown clue {m}')

    def system_texts(self):
        L = self.tx.label
        M = lambda key, paras: self.tx.message(paras, 'system ' + key)
        self.sys = dict(
            CMD_TALK=L('はなす', CMD_LABEL_PX, 'command'), CMD_LOOK=L('しらべる', CMD_LABEL_PX, 'command'),
            CMD_SHOW=L('みせる', CMD_LABEL_PX, 'command'), CMD_MOVE=L('いどう', CMD_LABEL_PX, 'command'),
            CMD_NOTE=L('てちょう', CMD_LABEL_PX, 'command'), CMD_DEDUCE=L('すいり', CMD_LABEL_PX, 'command'),
            NOTE_ITEMS=L('しょうこ', LIST_LABEL_PX, 'note'), NOTE_TESTI=L('しょうげん', LIST_LABEL_PX, 'note'),
            NOTE_HINT=L('ヒント', LIST_LABEL_PX, 'note'), NOTE_DEDUCE=L('すいりする', LIST_LABEL_PX, 'note'),
            NOTE_SAVE=L('きろくする', LIST_LABEL_PX, 'note'), NOTE_SOUND_ON=L('おと：あり', LIST_LABEL_PX, 'note'),
            NOTE_SOUND_OFF=L('おと：なし', LIST_LABEL_PX, 'note'),
            TITLE_NEW=L('はじめから', LIST_LABEL_PX, 'title'), TITLE_CONT=L('つづきから', LIST_LABEL_PX, 'title'),
            PROMPT=L('どうする？', LIST_LABEL_PX, 'prompt'),
            HELP=self.tx.label('上下:えらぶ　A:けってい', LIST_LABEL_PX + 12, 'help', COLOR_GRAY, raw=True),
            HDR_BACK=self.tx.label('B:もどる', 60, 'header', COLOR_GRAY, raw=True),
            HDR_TITLE=L('昭和六十二年　汐見港', 200, 'header'),
            HDR_GAME=L('潮鳴りの密室', HDR_LEFT_PX, 'header'),
            HDR_END=L('おわり', 60, 'header'),
            HDR_TALK=L('はなす：', 60, 'header'), HDR_SHOW=L('みせる：', 60, 'header'),
            END_TITLE=L('―　おわり　―', 200, 'ending'),
            END_ACTIONS=L('調べた回数', 120, 'ending'), END_WRONG=L('推理のまちがい', 120, 'ending'),
            END_PRESS=self.tx.label('Aボタンで　タイトルへ', 200, 'ending', COLOR_GRAY, raw=True),
            DEDUCE_Q=L('問', 24, 'deduce'),
            **{f'OPEN_{i}_{j}': L(t, 240, 'opening') for i, pair in enumerate(OPENING_CAPTIONS) for j, t in enumerate(pair)},
            PUSH_START=self.tx.label('PUSH START BUTTON', 200, 'title', raw=True),
            NOBODY=M('nobody', [(None, 'ここには、話を聞ける相手がいない。')]),
            NOCLUE=M('noclue', [(None, '見せられる手がかりが、まだない。')]),
            NOITEMS=M('noitems', [(None, 'まだ、何も書きとめていない。')]),
            SAVED=M('saved', [('記録しました', '捜査の進みぐあいを記録した。タイトルの『つづきから』で、ここから再開できる。')]),
            NORECORD=M('norecord', [(None, '記録がありません。『はじめから』を選んでください。')]),
            BROKEN=M('broken', [(None, '記録が壊れているため、読みこめませんでした。『はじめから』を選んでください。')]),
            SAVEFAIL=M('savefail', [(None, '記録できませんでした。カートリッジの記録用メモリが使えないようです。')]),
            LOADED=M('loaded', [('つづきから', '前回の記録から、捜査を再開します。')]),
            SOUND_ON=M('soundon', [(None, '音を出すようにした。')]),
            SOUND_OFF=M('soundoff', [(None, '音を消した。')]),
            DEDUCE_QUIT=M('deducequit', [(None, 'いったん捜査にもどろう。手がかりを確かめてから、また推理しよう。')]),
            DEDUCE_RIGHT=M('deduceright', [('すいり', '……そうだ。')]),
        )
        self.digits = [self.font.glyph(c) for c in '０１２３４５６７８９']
        self.special = dict(GL_CURSOR=self.font.glyph('▶'), GL_PAGE=self.font.glyph('▼'),
                            GL_UP=self.font.glyph('▲'), GL_DOWN=self.font.glyph('▼'),
                            GL_SLASH=self.font.glyph('/'), GL_SPACE=0)
        for i, ch in enumerate('0123456789'):
            self.font.glyph(ch)
        self.half_digits = [self.font.glyph(c) for c in '0123456789']

    def clue_tables(self):
        st = self.st
        self.clue_get_text = {}
        rows = []
        for i, cid in enumerate(st['clue_order']):
            c = st['clues'][cid]
            name = self.tx.label(c['name'], LIST_LABEL_PX, f'clue {cid}')
            paras = []
            for no, line in c['desc']:
                m = re.match(r'^>\s?(.*)$', line)
                if not m:
                    raise BuildError(f'clue {cid} (story.txt:{no}): description lines start with ">"')
                paras.append((c['name'], m.group(1)))
            desc = self.tx.message(paras, f'clue {cid} description')
            self.clue_get_text[cid] = self.tx.message([('手帳に書きとめた', c['name'])], f'clue {cid} noted')
            rows.append((self.flag(cid), name, desc, 0 if c['kind'] == 'item' else 1, cid))
        self.asm.append('ClueTable:   ; flag, name text, description text, kind (0 thing, 1 testimony)')
        for f, n, d, k, cid in rows:
            self.asm.append(f'    .word {f}, {n}, {d}, {k}   ; {cid}')
        self.clue_rows = rows

    def images(self):
        st = self.st
        files = {}
        self.image_index = {}
        self.image_files = []
        for name in st['image_order']:
            path = st['images'][name]
            if path not in files:
                files[path] = len(self.image_files)
                self.image_files.append(path)
            self.image_index[name] = files[path]
        # portraits per picture file
        per_image = {i: [] for i in range(len(self.image_files))}
        for sid in st['scene_order']:
            sc = st['scenes'][sid]
            if sc['portrait']:
                per_image[self.image_index[sc['image']]].append((sid, sc['portrait']))
        self.mouths = mouthmod.parse(MOUTHS.read_text(encoding='utf-8'))
        used = set()

        def mouth_of(p, x, y):
            m = self.mouths.get(p)
            if m is None:
                raise BuildError(f'portrait {p} has no @mouth in data/adv/mouths.txt')
            used.add(p)
            por = png_codec.read(ROOT / p)
            try:
                rect = mouthmod.check(por, m, x, y)
            except mouthmod.MouthError as e:
                raise BuildError(str(e))
            return dict(key=mouthmod.digest(m), patch=(m['x'], m['y'], m['w'], m['h']), rect=rect,
                        variants=[mouthmod.apply(por, m, f) for f in (1, 2)])
        self.pictures = []
        self.portraits = []           # (scene id, x tile, y tile, w, h, data, mouth)
        self.scene_portrait = {}
        for i, path in enumerate(self.image_files):
            res = quantize.convert(ROOT / path, [(ROOT / p, x, y, mouth_of(p, x, y))
                                                 for sid, (p, x, y) in per_image[i]])
            self.pictures.append(dict(path=path, sha256=sha(ROOT / path), tiles=res['tiles'],
                                      palette=res['palette'], stats=res['stats']))
            for (sid, (p, x, y)), pt in zip(per_image[i], res['portraits']):
                self.scene_portrait[sid] = len(self.portraits)
                self.portraits.append(dict(scene=sid, path=p, sha256=sha(ROOT / p), x=x // 8, y=y // 8,
                                           w=pt['w'], h=pt['h'], data=pt['tiles'], mouth=pt['mouth']))
        unused = set(self.mouths) - used
        if unused:
            raise BuildError(f'data/adv/mouths.txt: no scene shows {sorted(unused)}')

    def scene_tables(self):
        st = self.st
        self.scene_names = {}
        for pid in st['person_order']:
            p = st['persons'][pid]
            p['name_text'] = self.tx.label(p['name'], 60, f'person {pid}')
        for sid in st['scene_order']:
            sc = st['scenes'][sid]
            sc['name_text'] = self.tx.label(sc['name'], HDR_LEFT_PX, f'scene {sid}')
            self.scene_names[sid] = sc['name']

    def item_list(self, label, items, where):
        out = [f'{label}:', f'    .word {len(items)}']
        for it in items:
            seen = self.flag(f'H_SEEN_{where}_{it["n"]}')
            lab = self.tx.label(it['label'], LIST_LABEL_PX, f'{where} item "{it["label"]}"')
            terms = self.cond_terms(it['cond'], seen, f'{where} item "{it["label"]}"')
            if len(terms) > 3:
                raise BuildError(f'{where} item {it["label"]}: more than 3 conditions')
            cw = [(t[0] | (0x8000 if t[1] else 0)) for t in terms] + [0] * (3 - len(terms))
            scr = self.compile(it['lines'], f'{where} "{it["label"]}"', seen)
            out.append(f'    .word {lab}, {cw[0]}, {cw[1]}, {cw[2]}, {scr}, {seen}')
            it['seen'] = seen
            it['text'] = lab
            it['terms'] = terms
        return out

    def script_blocks(self):
        st = self.st
        lists = []
        for name, lines in st['scripts'].items():
            self.scripts[name] = self.compile(lines, f'script {name}', label=f'SCR_{name}')
        # looks
        self.looks = {}
        for sid in st['scene_order']:
            items = [dict(l, n=i) for i, l in enumerate(x for x in st['looks'] if x['scene'] == sid)]
            self.looks[sid] = items
            lists += self.item_list(f'Look_{sid}', items, f'look_{sid}')
        self.topics = {}
        for pid in st['person_order']:
            items = [dict(t, n=i) for i, t in enumerate(x for x in st['topics'] if x['person'] == pid)]
            self.topics[pid] = items
            lists += self.item_list(f'Topic_{pid}', items, f'topic_{pid}')
        # show tables
        self.show_map = {}
        for pid in st['person_order']:
            rows, default = [], None
            for sh in (x for x in st['shows'] if x['person'] == pid):
                scr = self.compile(sh['lines'], f'show {pid} {" ".join(sh["clues"])}')
                for cid in sh['clues']:
                    if cid == '*':
                        default = scr
                        continue
                    if cid not in st['clues']:
                        raise BuildError(f'show {pid}: unknown clue {cid}')
                    rows.append((st['clue_order'].index(cid) + 1, scr))
                    self.show_map[(pid, cid)] = sh
            if default is None:
                raise BuildError(f'person {pid}: no default show reaction (@show {pid} *)')
            lists += [f'Show_{pid}:'] + [f'    .word {c}, {s}' for c, s in rows] + ['    .word 0']
            st['persons'][pid]['default'] = default
        self.asm += lists
        # scene / person tables
        self.asm.append('SceneTable:   ; name, image, person+1, look list, unlock flag, portrait+1, song, 0')
        for sid in st['scene_order']:
            sc = st['scenes'][sid]
            pidx = st['person_order'].index(sc['person']) + 1 if sc['person'] else 0
            unlock = 0
            if sc['cond']:
                terms = self.cond_terms(sc['cond'], None, f'scene {sid}')
                assert len(terms) == 1 and not terms[0][1]
                unlock = terms[0][0]
            por = self.scene_portrait.get(sid, -1) + 1
            if sc['music'] not in songsmod.SONG_IDS:
                raise BuildError(f'scene {sid}: unknown song {sc["music"]}')
            self.asm.append(f'    .word {sc["name_text"]}, {self.image_index[sc["image"]]}, {pidx}, Look_{sid}, '
                            f'{unlock}, {por}, {songsmod.SONG_IDS[sc["music"]]}, 0   ; {sid}')
        self.asm.append('PersonTable:   ; name, topic list, show table, default show script')
        for pid in st['person_order']:
            p = st['persons'][pid]
            self.asm.append(f'    .word {p["name_text"]}, Topic_{pid}, Show_{pid}, {p["default"]}   ; {pid}')

    def hint_script(self):
        st = self.st
        out = ['SCR_hint:']
        for i, h in enumerate(st['hints']):
            nxt = self.new_label('H')
            seen = self.flag(f'H_HINT_{i}')
            for fid, neg, n in self.cond_terms(h['cond'], None, f'hint {i}'):
                out.append(f'    .word {"OP_IF" if neg else "OP_IFN"}, {fid}, {nxt}   ; {"!" if neg else ""}{n}')
            t1 = self.tx.message([('ヒント', h['t1'])], f'hint {i} (1)')
            t2 = self.tx.message([('ヒント', h['t2'])], f'hint {i} (2)')
            two = self.new_label('H')
            out += [f'    .word OP_IF, {seen}, {two}', f'    .word OP_SET, {seen}', f'    .word OP_TEXT, {t1}',
                    '    .word OP_END', f'{two}:', f'    .word OP_TEXT, {t2}', '    .word OP_END', f'{nxt}:']
        out.append('    .word OP_END')
        self.asm += out
        self.scripts['hint'] = 'SCR_hint'

    def deduce_tables(self):
        st = self.st
        # start script: each requirement, then the intro, then the question loop
        out = ['SCR_deduce_start:']
        missing = []
        self.require_sets = []
        for i, rq in enumerate(st['requires']):
            lab = self.new_label('Q')
            req = []
            for t in rq['terms']:
                for fid, neg, n in self.cond_terms(t, None, f'require {i}'):
                    out.append(f'    .word OP_IFN, {fid}, {lab}   ; {n}')
                    req.append(n)
            self.require_sets.append(req)
            paras = [(None, re.match(r'^>\s?(.*)$', l).group(1)) for no, l in rq['lines']]
            missing.append((lab, self.tx.message(paras, f'require {i}')))
        if 'deduce_intro' not in self.scripts:
            raise BuildError('no @script deduce_intro')
        out += ['    .word OP_CALL, SCR_deduce_intro', '    .word OP_DEDUCE', '    .word OP_END']
        for lab, tid in missing:
            out += [f'{lab}:', f'    .word OP_TEXT, {tid}', '    .word OP_END']
        self.asm += out
        rows = []
        self.deduce_info = []
        for qi, q in enumerate(st['deduce']):
            w = f'deduce {qi + 1}'
            if not q['prompt'] or not q['ok']:
                raise BuildError(f'{w}: needs prompt: and ok:')
            if not q['ask']:
                raise BuildError(f'{w}: needs ask: (the short question shown in the header)')
            ask = self.tx.label(q['ask'], 120, f'{w} ask')   # + page + B:もどる after 汐見署
            prompt = self.compile(q['prompt'], f'{w} prompt')
            ok = self.compile(q['ok'], f'{w} ok')
            info = dict(kind=q['kind'], answers=[])
            if q['kind'] == 'choice':
                lst = self.new_label('C')
                ent = []
                for o in q['opts']:
                    lab = self.tx.label(o['label'], LIST_LABEL_PX, f'{w} option')
                    resp = self.compile(o['lines'], f'{w} option {o["label"]}') if o['lines'] else '0'
                    if not o['correct'] and resp == '0':
                        raise BuildError(f'{w}: wrong option {o["label"]} needs a reply')
                    ent.append(f'    .word {lab}, {1 if o["correct"] else 0}, {resp}')
                    if o['correct']:
                        info['answers'].append(o['label'])
                if len(info['answers']) != 1:
                    raise BuildError(f'{w}: exactly one option must be marked opt*')
                info['options'] = [o['label'] for o in q['opts']]
                self.asm += [f'{lst}:', f'    .word {len(ent)}'] + ent
                rows.append(f'    .word 0, {prompt}, {ok}, 0, {lst}, {ask}   ; {w}')
            else:
                if not q['wrong']:
                    raise BuildError(f'{w}: needs wrong:')
                wrong = self.compile(q['wrong'], f'{w} wrong')
                lst = self.new_label('C')
                acc = []
                for cid in q['accept']:
                    if cid not in st['clues']:
                        raise BuildError(f'{w}: unknown clue {cid}')
                    acc.append(st['clue_order'].index(cid) + 1)
                spec = []
                for cid, lines in q['wrong_for'].items():
                    spec.append(f'    .word {st["clue_order"].index(cid) + 1}, {self.compile(lines, f"{w} wrong {cid}")}')
                self.asm += [f'{lst}:', f'    .word {len(acc)}, ' + ', '.join(map(str, acc)), f'    .word {len(spec)}'] + spec
                rows.append(f'    .word 1, {prompt}, {ok}, {wrong}, {lst}, {ask}   ; {w}')
                info['answers'] = q['accept']
                info['specific_wrong'] = list(q['wrong_for'])
                # answerable when deduction can start: at least one accepted clue is required
                req = {n for r in self.require_sets for n in r}
                if not any(a in req for a in q['accept']):
                    raise BuildError(f'{w}: none of the accepted clues is required to start the deduction')
            self.deduce_info.append(info)
        if 'finale' not in self.scripts:
            raise BuildError('no @script finale')
        self.asm.append('DeduceTable:   ; kind (0 choice, 1 clue), prompt, ok, wrong, list, short question')
        self.asm += rows

    def time_table(self):
        self.asm.append('TimeTable:   ; flag (0 = always), text')
        for cond, t in self.st['time']:
            f = 0 if cond == '*' else self.cond_terms(cond, None, 'time')[0][0]
            self.asm.append(f'    .word {f}, {self.tx.label(t, 96, "time")}')

    def check_flags(self):
        for n in self.flags:
            if n.startswith('F_') and n not in self.flag_sources:
                raise BuildError(f'flag {n} is tested but never set')
            if n.startswith(('K_', 'T_')) and n not in self.flag_sources:
                raise BuildError(f'clue {n} can never be noted')
        if len(self.flags) >= 1024:
            raise BuildError('more than 1023 flags')

    # -- reachability: simulate the investigation as a set of flags, with every action available
    def reachability(self):
        st = self.st
        have = set()
        actions = []
        for sid in st['scene_order']:
            sc = st['scenes'][sid]
            scene_cond = sc['cond']
            for it in self.looks[sid]:
                actions.append((scene_cond, it['cond'], it['lines']))
            if sc['person']:
                for it in self.topics[sc['person']]:
                    actions.append((scene_cond, it['cond'], it['lines']))
                for (pid, cid), sh in self.show_map.items():
                    if pid == sc['person']:
                        actions.append((scene_cond, cid, sh['lines']))

        def holds(cond):
            for t in cond.split():
                neg = t.startswith('!')
                n = t.lstrip('!')
                if n == 'seen':
                    continue
                if (n in have) == neg:
                    return False
            return True

        def effects(lines):
            got = set()
            for no, line in lines:
                m = re.match(r'^(get|set):\s*(\w+)', line)
                if m:
                    got.add(m.group(2))
                    for g, mem in st['groups'].items():
                        if m.group(2) in mem:
                            got.add(g)
            return got
        changed = True
        while changed:
            changed = False
            for sc_cond, cond, lines in actions:
                if holds(sc_cond) and holds(cond):
                    new = effects(lines) - have
                    if new:
                        have |= new
                        changed = True
        missing = [c for c in st['clue_order'] if c not in have]
        if missing:
            raise BuildError(f'clues that cannot be reached: {missing}')
        for r in self.require_sets:
            for n in r:
                if n not in have:
                    raise BuildError(f'deduction requirement {n} cannot be reached')
        self.reachable = sorted(have)

    # -- output
    def mouth_tables(self):
        """mouth.bin (closed, half, open tiles of each portrait) and the MouthTable rows.  The closed
        frame must be the portrait's own tiles, and the tiles must be BG1 picture tiles."""
        st = self.st
        blob, rows, info = bytearray(), [], []
        for i, p in enumerate(self.portraits):
            mo = p['mouth']
            tx0, ty0, tw, th = mo['rect']
            if not (p['x'] <= tx0 and tx0 + tw <= p['x'] + p['w'] and p['y'] <= ty0 and ty0 + th <= p['y'] + p['h']):
                raise BuildError(f'{p["path"]}: the mouth tiles leave the portrait')
            base = b''.join(p['data'][((ty - p['y']) * p['w'] + tx - p['x']) * 64:][:64]
                            for ty in range(ty0, ty0 + th) for tx in range(tx0, tx0 + tw))
            if mo['frames'][0] != base:
                raise BuildError(f'{p["path"]}: the closed mouth differs from the portrait tiles')
            for f in (1, 2):
                if mo['frames'][f] == base:
                    raise BuildError(f'{p["path"]}: mouth frame {f} is the same as closed')
            vram = (ty0 * 32 + tx0) * 32
            if not (0 <= vram and (vram + ((th - 1) * 32 + tw) * 32) <= 0x4000):
                raise BuildError(f'{p["path"]}: mouth VRAM outside the BG1 picture tiles')
            offs = []
            for f in range(3):
                offs.append(len(blob))
                blob += mo['frames'][f]
            person = st['scenes'][p['scene']]['person']
            pidx = st['person_order'].index(person) + 1
            rows.append(f'    .word {pidx}, ${vram:04X}, {tw * 64}, {th}, '
                        + ', '.join(f'.loword(MouthTiles)+{o}' for o in offs) + f', ^MouthTiles   ; {p["scene"]}')
            info.append(dict(portrait_index=i, scene=p['scene'], person=person, speaker_id=pidx, path=p['path'],
                             patch=[self.mouths[p['path']][k] for k in ('x', 'y', 'w', 'h')],
                             tile_rect=[tx0, ty0, tw, th], vram_word=vram, bytes_per_row=tw * 64, rows=th,
                             frame_sha256=[hashlib.sha256(f).hexdigest() for f in mo['frames']],
                             frame_offset=offs, patch_error=mo['patch_error']))
        return bytes(blob), rows, info

    def check_speaker_codes(self):
        """Speaker codes only in messages, right after the name (FFFE, FFFC 2), one per page at most."""
        for tid, (codes, info) in enumerate(zip(self.tx.items, self.tx.layout)):
            if max((c for c in codes if c < 0xFFE0), default=0) >= 0xFFE0:
                raise BuildError('glyph number reaches the control codes')
            pos = [i for i, c in enumerate(codes) if c & 0xFFF0 == SPEAKER_CODE]
            if info['kind'] != 'message':
                if pos:
                    raise BuildError(f'text {tid}: speaker code in a label')
                continue
            for i in pos:
                if codes[i - 3:i] != [0xFFFE, 0xFFFC, COLOR_WHITE]:
                    raise BuildError(f'text {tid}: speaker code not after the name')
            n = sum(1 for pg in info['pages'] if pg['speaker_id'] is not None)
            if n != len(pos):
                raise BuildError(f'text {tid}: {len(pos)} speaker codes for {n} spoken pages')

    def emit(self):
        st = self.st
        font_blob = self.font.blob()
        if len(font_blob) > 0x8000:
            raise BuildError('font over one bank')
        widths = [self.font.width(c) for c in self.font.chars]
        # banks: 0 code, 1 font, 2.. text, then pictures, then portraits
        text_banks, text_addrs = self.tx.encode_banks(2)
        bank = 2 + len(text_banks)
        pic_banks = []
        for p in self.pictures:
            pic_banks.append(bank)
            bank += 1
        por_banks = []
        cur = bytearray()
        por_place = []
        for p in self.portraits:
            if len(cur) + len(p['data']) > 0x8000:
                por_banks.append(bytes(cur))
                cur = bytearray()
            por_place.append(((bank + len(por_banks)) << 16) | (0x8000 + len(cur)))
            cur += p['data']
        if cur:
            por_banks.append(bytes(cur))
        last = bank + len(por_banks) - 1
        if last >= ROM_BANKS:
            raise BuildError(f'ROM full: needs bank {last}')
        files = {}
        (OUT / 'font.bin').write_bytes(font_blob)
        files['font.bin'] = font_blob
        seg = []
        seg.append('.segment "BANK1"\nFontData: .incbin "build/adv/font.bin"')
        for i, b in enumerate(text_banks):
            name = f'text{i}.bin'
            (OUT / name).write_bytes(b)
            files[name] = b
            seg.append(f'.segment "BANK{2 + i}"\n    .incbin "build/adv/{name}"')
        for i, p in enumerate(self.pictures):
            name = f'pic{i}.bin'
            (OUT / name).write_bytes(p['tiles'])
            files[name] = p['tiles']
            seg.append(f'.segment "BANK{pic_banks[i]}"\n    .incbin "build/adv/{name}"')
        for i, b in enumerate(por_banks):
            name = f'portrait{i}.bin'
            (OUT / name).write_bytes(b)
            files[name] = b
            seg.append(f'.segment "BANK{bank + i}"\n    .incbin "build/adv/{name}"')
        tmpl = quantize.panel_templates()
        tmpl_bank = bank + len(por_banks)
        last = tmpl_bank
        if last >= ROM_BANKS:
            raise BuildError(f'ROM full: needs bank {last}')
        (OUT / 'templates.bin').write_bytes(tmpl)
        files['templates.bin'] = tmpl
        seg.append(f'.segment "BANK{tmpl_bank}"\nTemplateData: .incbin "build/adv/templates.bin"')
        logo = quantize.logo_tiles(self.font, '潮鳴りの密室')
        (OUT / 'logo.bin').write_bytes(logo)
        files['logo.bin'] = logo
        mouth_blob, mouth_rows, self.mouth_info = self.mouth_tables()
        (OUT / 'mouth.bin').write_bytes(mouth_blob)
        files['mouth.bin'] = mouth_blob
        self.check_speaker_codes()

        c = ['; generated by tools/adv/build.py -- do not edit']
        for k, v in OP.items():
            c.append(f'OP_{k} = {v}')
        for k, v in SFX.items():
            c.append(f'SFX_{k.upper()} = {v}')
        for k, v in self.sys.items():
            c.append(f'TX_{k} = {v}')
        for k, v in self.special.items():
            c.append(f'{k} = {v}')
        c += [f'SCENE_COUNT = {len(st["scene_order"])}', f'PERSON_COUNT = {len(st["person_order"])}',
              f'CLUE_COUNT = {len(st["clue_order"])}', f'FLAG_COUNT = {len(self.flags) + 1}',
              f'IMAGE_COUNT = {len(self.pictures)}', f'PORTRAIT_COUNT = {len(self.portraits)}',
              f'DEDUCE_COUNT = {len(st["deduce"])}', f'TIME_COUNT = {len(st["time"])}',
              f'GLYPH_COUNT = {len(self.font.chars)}', f'TEXT_COUNT = {len(self.tx.items)}',
              *[f'IMAGE_{k.upper()} = {v}' for k, v in self.image_index.items()],
              f'START_SCENE = 0', f'ROM_LAST_BANK = {last + 1}',
              f'SPEAKER_CODE = ${SPEAKER_CODE:04X}', f'SPEAKER_ME = {SPEAKER_ME}']
        for k, v in songsmod.SONG_IDS.items():
            c.append(f'SONG_{k.upper()} = {v}')
        (OUT / 'const.inc').write_text('\n'.join(c) + '\n')

        d = ['; generated by tools/adv/build.py -- do not edit', '.segment "RODATA"']
        d.append('TextTable:')
        for a in text_addrs:
            d.append(f'    .faraddr ${a:06X}')
        d.append('GlyphWidth:')
        for i in range(0, len(widths), 32):
            d.append('    .byte ' + ', '.join(map(str, widths[i:i + 32])))
        d.append('DigitGlyphs: .word ' + ', '.join(map(str, self.digits)))
        d.append('HalfDigitGlyphs: .word ' + ', '.join(map(str, self.half_digits)))
        d.append('ImageTable:   ; bank, palette')
        for i, p in enumerate(self.pictures):
            d.append(f'    .word {pic_banks[i]}, Palette{i}')
        for i, p in enumerate(self.pictures):
            d.append(f'Palette{i}:')
            pal = p['palette']
            for j in range(0, 240, 16):
                d.append('    .word ' + ', '.join(f'${v:04X}' for v in pal[j:j + 16]))
        d.append('PortraitTable:   ; x tile, y tile, width, height, data address, data bank')
        for i, p in enumerate(self.portraits):
            a = por_place[i]
            d.append(f'    .word {p["x"]}, {p["y"]}, {p["w"]}, {p["h"]}, ${a & 0xFFFF:04X}, {a >> 16}   ; {p["scene"]}')
        d.append('MouthTable:   ; person+1, VRAM word, bytes per tile row, tile rows, closed, half, open, bank')
        d += mouth_rows
        d.append('MouthTiles: .incbin "build/adv/mouth.bin"')
        d.append('GlyphPause:   ; frames the mouth stays closed after the glyph')
        pauses = [PAUSE_FRAMES.get(c, 0) for c in self.font.chars]
        for i in range(0, len(pauses), 32):
            d.append('    .byte ' + ', '.join(map(str, pauses[i:i + 32])))
        try:
            voices = voicemod.build(self.tx.speaker_ids, self.font.chars)
        except voicemod.VoiceError as e:
            raise BuildError(f'voices.txt: {e}')
        self.voice_info = dict(voices=voices['report'], silent=voices['silent'], contour=voices['contour'],
                               voiced_glyphs=sum(voices['glyph_voice']), glyphs=len(self.font.chars))
        d.append('GlyphVoice:   ; 1: the glyph may start a speech blip')
        for i in range(0, len(voices['glyph_voice']), 32):
            d.append('    .byte ' + ', '.join(map(str, voices['glyph_voice'][i:i + 32])))
        d.append('SpeakerVoice: ; speaker id -> voice of the driver ($FF none)')
        d.append('    .byte ' + ', '.join(f'${v:02X}' for v in voices['speaker_voice']) + ', 0')
        d.append('SpeakerGap:   ; speaker id -> frames between blips at the least')
        d.append('    .byte ' + ', '.join(map(str, voices['speaker_gap'])) + ', 0')
        d.append('LogoTiles: .incbin "build/adv/logo.bin"')
        spc_img, spc_info = spc.build(voices)
        self.voice_info['spc'] = spc_info
        (OUT / 'spc.bin').write_bytes(spc_img)
        files['spc.bin'] = spc_img
        spc_bank = last + 1
        if len(spc_img) > 0x8000:
            raise BuildError('sound driver image over one bank')
        if spc_bank >= ROM_BANKS:
            raise BuildError(f'ROM full: needs bank {spc_bank}')
        seg.append(f'.segment "BANK{spc_bank}"\nSpcImage: .incbin "build/adv/spc.bin"\nSpcImageEnd:')
        self.voice_info['spc']['bank'] = spc_bank
        d += self.asm
        d += seg
        (OUT / 'data.inc').write_text('\n'.join(d) + '\n')

        # manifest + layout for tests
        sources = {str(p.relative_to(ROOT)): sha(p) for p in
                   [STORY, MOUTHS, VOICES, FONT_K, FONT_A, ROOT / 'tools/adv/build.py', ROOT / 'tools/adv/story.py',
                    ROOT / 'tools/adv/quantize.py', ROOT / 'tools/adv/mouth.py', ROOT / 'tools/adv/spc.py',
                    ROOT / 'tools/adv/voice.py', ROOT / 'tools/png_codec.py']}
        for p in self.pictures:
            sources[p['path']] = p['sha256']
        for p in self.portraits:
            sources[p['path']] = p['sha256']
        manifest = dict(
            target='潮鳴りの密室 (dist/shionari.sfc)', sources=sources,
            outputs={k: hashlib.sha256(v).hexdigest() for k, v in files.items()},
            glyphs=len(self.font.chars), texts=len(self.tx.items),
            text_bytes=sum(len(b) for b in text_banks), text_banks=len(text_banks),
            picture_banks=pic_banks, portrait_banks=list(range(bank, bank + len(por_banks))), last_bank=spc_bank,
            flags=len(self.flags), clues=len(st['clue_order']),
            pictures=[dict(path=p['path'], **p['stats']) for p in self.pictures],
            portraits=[dict(scene=p['scene'], path=p['path'], x=p['x'] * 8, y=p['y'] * 8, w=p['w'] * 8, h=p['h'] * 8)
                       for p in self.portraits],
            mouths=self.mouth_info, speech=self.voice_info,
            art_records=dict(prepared=sha(ROOT / 'assets/adv/PREPARED.json') if (ROOT / 'assets/adv/PREPARED.json').exists() else None,
                             art=sha(ROOT / 'assets/adv/ART.json') if (ROOT / 'assets/adv/ART.json').exists() else None),
        )
        (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')
        layout = dict(
            flags=self.flags, scenes=st['scene_order'], persons=st['person_order'], clues=st['clue_order'],
            clue_kind={c: st['clues'][c]['kind'] for c in st['clue_order']},
            looks={sid: [dict(label=normalize(it['label']), text=it['text'], seen=it['seen'], cond=it['cond'])
                         for it in items] for sid, items in self.looks.items()},
            topics={pid: [dict(label=normalize(it['label']), text=it['text'], seen=it['seen'], cond=it['cond'])
                          for it in items] for pid, items in self.topics.items()},
            scene_person={sid: st['scenes'][sid]['person'] for sid in st['scene_order']},
            scene_cond={sid: st['scenes'][sid]['cond'] for sid in st['scene_order']},
            deduce=self.deduce_info, requires=self.require_sets, system=self.sys,
            clue_names={c: normalize(st['clues'][c]['name']) for c in st['clue_order']},
            texts=self.tx.layout, reachable=self.reachable,
            mouths=self.mouth_info, speaker_ids=self.tx.speaker_ids, speaker_code=SPEAKER_CODE,
            glyph_pause={c: PAUSE_FRAMES[c] for c in self.font.chars if c in PAUSE_FRAMES},
            speech=self.voice_info, glyph_chars=self.font.chars,
            images=self.image_index, scene_song={sid: st['scenes'][sid]['music'] for sid in st['scene_order']},
            songs=songsmod.SONG_IDS, opening_captions=OPENING_CAPTIONS,
        )
        (OUT / 'layout.json').write_text(json.dumps(layout, ensure_ascii=False, indent=0) + '\n')
        print(f'adv data: {len(self.font.chars)} glyphs, {len(self.tx.items)} texts '
              f'({sum(len(b) for b in text_banks)} bytes in {len(text_banks)} banks), {len(self.flags)} flags, '
              f'{len(self.pictures)} pictures, {len(self.portraits)} portraits, last bank {last}')


if __name__ == '__main__':
    try:
        Builder().run()
    except (BuildError, storymod.StoryError) as e:
        sys.exit(f'build error: {e}')
