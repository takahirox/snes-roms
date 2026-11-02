"""Build the data of 夜鳴き鐘 (SFC sound novel): scenario + pictures + sound -> build/yonaki/*.

usage: python3 -I tools/yonaki/build.py [--scenario DIR] [--endings FILE] [--allow-missing-art] [--strict]
                                        [--unknown-sound-error] [--quiet]
  --scenario DIR        scenario directory (default data/yonaki/scenario); every *.txt, sorted by name
  --endings FILE        default: endings.txt next to the scenario directory (data/yonaki/endings.txt)
  --allow-missing-art   a background / silhouette without a picture becomes black / a plain figure (warning)
  --strict              warnings are errors (unreachable labels, unreached endings, kinsoku, unknown names)
  --unknown-sound-error an unknown song / sound effect name is an error (default: warning, nothing plays)
  --out DIR             output directory (default build/yonaki; the tests build the fixture into build/yonaki-test)
  --omake-endings N     endings to see before the title shows おまけ (default 10)
  --debug-start         review builds (tests/yonaki/shots.py): はじめから starts at the address in the battery RAM
                        at $1FF2 when $1FF0 holds "DB" at power-on (the battery is reset afterwards as usual)

writes build/yonaki/const.inc, data.inc, yonaki.cfg (ld65 config, generated: as many 32 KiB banks as needed,
rounded up to a ROM size the header can state), the bank blobs, layout.json (for the tests and the tools),
report.txt (diagnostics) and previews/ (every picture as the SNES shows it).
See docs/yonaki/ENGINE.md for the formats.
"""
import sys, re, json, hashlib, pathlib, struct, argparse, collections, importlib.util

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor/pylib'))
sys.path.insert(0, str(ROOT / 'tools/yonaki'))
import font as fontmod          # noqa: E402
import script as sc             # noqa: E402
import pictures                 # noqa: E402
import logo as logomod          # noqa: E402
import numpy as np              # noqa: E402
from PIL import Image           # noqa: E402

OUT = ROOT / 'build/yonaki'
BANK = 0x8000
MAX_BANKS = 128                 # 4 MiB LoROM
SPEEDS = ['遅い', '普通', '速い', '瞬間']
OMAKE_ENDINGS = 10              # the title's おまけ needs this many endings seen
TITLE_BGS = ['oldbath_ext', 'bell']
OP = dict(HALT=0, TEXT=1, BLANK=2, PAGE=3, BG=4, SIL=5, SILCLEAR=6, BGM=7, SE=8, FX=9, SET=10, CLR=11, SETG=12,
          CLRG=13, IF=14, GOTO=15, CHOICE=16, END=17, CHAPTER=18, AMB=19)
BGMODE = dict(cut=0, fade=1, white=2, mosaic=3)
FXK = dict(shake=0, flash=1, redflash=2, ripple_on=3, ripple_off=4, dark=5, light=6, wait=7)
SILCOL = dict(blue=0, white=1, red=2)
SILKEY = dict(l=0, c=1, r=2)
GLYPH_PARA = ''           # blinking wait marks and the choice cursor (drawn in font.CUSTOM)
GLYPH_PAGE = ''
GLYPH_CURSOR = '▸'
OPT_LETTERS = 'ＡＢＣＤＥＦＧＨ'      # before the options, in the order they are shown (script.MAX_CHOICES)
# the name entry (src/yonaki/ui.inc NameEntry): pages of NAME_ROWS x NAME_COLS characters
NAME_COLS, NAME_ROWS = 10, 8
NAME_PAGES = [                       # '　' = an empty cell
    'あいうえおかきくけこ' 'さしすせそたちつてと' 'なにぬねのはひふへほ' 'まみむめもや　ゆ　よ'
    'らりるれろわ　　　ん' 'がぎぐげござじずぜぞ' 'だぢづでどばびぶべぼ' 'ぱぴぷぺぽゃゅょっー',
    'アイウエオカキクケコ' 'サシスセソタチツテト' 'ナニヌネノハヒフヘホ' 'マミムメモヤ　ユ　ヨ'
    'ラリルレロワ　　　ン' 'ガギグゲゴザジズゼゾ' 'ダヂヅデドバビブベボ' 'パピプペポャュョッー',
]
NAME_KANJI = (                       # surnames first, then given names; the first 3 pages' worth are used
    '結城千尋早瀬佐藤鈴木高橋田中伊渡辺山本小林加吉松井上村清水斎森池野川口阪石原内岡前長谷部近坂遠青西東北南'
    '大竹宮崎浦島平福太葉菅沢秋桜岩丸今永安堀杉横矢市菊須賀浅倉関根桑柴有馬広星下河合久保望月白鳥黒澤神片桐志'
    '江尾塚岸丘峰岬渚湊颯樹慎仁純恭章京'
    '一二三子美香奈恵真理優花彩愛菜由紀明光健郎次翔輔介悠斗蓮陽向葵衣凛咲希智也雄誠実直人正浩隆司拓海空遥春夏冬'
    '雪風朗晴舞彦信夫英幸康博文史良和亮洋涼哉輝翼琴音綾華玲蘭桃梨乃沙織詩絵佳未来里穂薫静')
GLYPH_BLANK_NAME = '＿'
GLYPH_LEFT = ''
GLYPH_RIGHT = ''
fontmod.CUSTOM.update({
    GLYPH_PARA: ['............', '............', '............', '............', '............', '............',
                 '..#######...', '...#####....', '....###.....', '.....#......', '............', '............'],
    GLYPH_PAGE: ['............', '............', '............', '............', '..#######...', '...#####....',
                 '....###.....', '.....#......', '..#######...', '...#####....', '....###.....', '.....#......'],
    GLYPH_LEFT: ['............', '............', '.......#....', '......##....', '.....###....', '....####....',
                 '.....###....', '......##....', '.......#....', '............', '............', '............'],
    GLYPH_RIGHT: ['............', '............', '....#.......', '....##......', '....###.....', '....####....',
                  '....###.....', '....##......', '....#.......', '............', '............', '............'],
})
# user interface strings (the ROM refers to them as Str_<key>)
UI = dict(
    new='はじめから', load='しおりから', endings='結末の一覧', omake='おまけ',
    menu_save='しおりをはさむ', menu_speed='文字の速さ', menu_title='タイトルへ', menu_back='もどる',
    slot_empty='――　なし　――', slot_head_save='どこにはさみますか', slot_head_load='どのしおりから読みますか',
    saved='しおりをはさみました。', title_confirm='タイトルにもどりますか', yes='はい', no='いいえ',
    unknown='？？？？？？', end_back='Ａ　タイトルへ', list_hint='←→　ページ　　Ｂ　もどる',
    nosave='しおりがありません。', slot1='しおり一', slot2='しおり二', slot3='しおり三', notitle='（章なし）',
    empty='', kind0='真の結末', kind1='結末', kind2='悪い結末',
    name_hero='主人公', name_heroine='ヒロイン', name_hero_note='（名字）', name_heroine_note='（名前）',
    name_heroine_family='早瀬', name_hint='Ｂ　けす　　ＳＴＡＲＴ　決定',
    name_cmd0='かな', name_cmd1='カナ', name_cmd2='漢字', name_cmd3='けす', name_cmd4='決定',
    **{f'speed{i}': s for i, s in enumerate(SPEEDS)},
)
DIGITS = '0123456789'


class BuildError(Exception):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------ audio
def load_audio(diag):
    """tools/yonaki/audio.py (the music agent's module) if it exists, else the 潮鳴りの密室 driver with no names."""
    p = ROOT / 'tools/yonaki/audio.py'
    if p.exists():
        spec = importlib.util.spec_from_file_location('yonaki_audio', p)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(p.parent))
        spec.loader.exec_module(mod)
        r = mod.build()
        info = dict(source='tools/yonaki/audio.py', doc=(mod.__doc__ or '').strip()[:2000])
        return dict(image=bytes(r['image']), songs=dict(r.get('songs', {})), sfx=dict(r.get('sfx', {})),
                    load=r.get('load', 0x0200), entry=r.get('entry', r.get('load', 0x0200)),
                    amb=dict(r.get('amb', r.get('ambience', {}))), info=info)
    sys.path.insert(0, str(ROOT / 'tools/adv'))
    spec = importlib.util.spec_from_file_location('adv_spc_fallback', ROOT / 'tools/adv/spc.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    img, _ = mod.build()
    diag.note('audio', 'tools/yonaki/audio.py not found: the 潮鳴りの密室 driver is used with no song / effect names')
    return dict(image=img, songs={}, sfx={}, load=0x0200, entry=0x0200, amb={},
                info=dict(source='fallback: tools/adv/spc.py (no names)'))


# ------------------------------------------------------------------ text encoding
class Encoder:
    """Glyph codes: the 224 most frequent glyphs take one byte ($10-$EF), the others two ($F0+hi, lo).
    Control bytes: $00 end, $01 new line, $02 next page chunk (a line-count byte follows)."""

    def __init__(self, font):
        self.font = font
        self.count = collections.Counter()
        self.glyphs = None

    def feed(self, s):
        for ch in s:
            if ch not in '\x03\x04':
                self.count[ch] += 1

    def freeze(self):
        # the glyphs the engine writes itself (marks, cursor, digits) always have one-byte codes
        fixed = [GLYPH_PARA, GLYPH_PAGE, GLYPH_CURSOR, GLYPH_LEFT, GLYPH_RIGHT, '　', *DIGITS, '／', *OPT_LETTERS]
        order = fixed + sorted((c for c in self.count if c not in fixed), key=lambda c: (-self.count[c], ord(c)))
        self.glyphs = order
        self.index = {c: i for i, c in enumerate(order)}
        if len(order) > 224 + 16 * 256:
            raise BuildError(f'{len(order)} different glyphs (at most {224 + 4096})')

    def code(self, ch):
        if ch in '\x03\x04':            # a name the player set (src/yonaki/text.inc ReadCode)
            return ch.encode()
        g = self.index[ch]
        if g < 224:
            return bytes([0x10 + g])
        g -= 224
        return bytes([0xF0 + (g >> 8), g & 0xFF])

    def string(self, s, end=True):
        out = b''.join(self.code(c) for c in s)
        return out + (b'\x00' if end else b'')

    def lines(self, chunks):
        """Paragraph pages -> bytes: lines joined by $01, chunks by $02 + line count; ends with $00."""
        out = bytearray()
        for k, chunk in enumerate(chunks):
            if k:
                out += bytes([2, len(chunk)])
            for j, ln in enumerate(chunk):
                if j:
                    out.append(1)
                out += self.string(ln, end=False)
        out.append(0)
        return bytes(out)

    def font_blob(self):
        """32 bytes per glyph: 12 rows as little-endian words (bit 15 = leftmost pixel), byte 24 = advance width."""
        out = bytearray()
        for ch in self.glyphs:
            rows = self.font.rows(ch)
            for r in rows:
                out += struct.pack('<H', r & 0xFFFF)
            out += bytes([self.font.width(ch) if ch not in fontmod.CUSTOM else 12]) + bytes(7)
        return bytes(out)


# ------------------------------------------------------------------ ROM space
class Rom:
    """Banks of 32 KiB; bank 0 is code + RODATA (data.inc).  Data blobs are placed from bank 1 up."""

    def __init__(self):
        self.banks = []           # bytearrays (bank 1 = index 0)
        self.names = []

    def new_bank(self, name):
        self.banks.append(bytearray())
        self.names.append(name)
        return len(self.banks)    # ROM bank number

    def cur(self):
        return len(self.banks)

    def free(self):
        return BANK - len(self.banks[-1]) if self.banks else 0

    def put(self, data, name, align=1):
        """Place data in the current bank (a new one if it does not fit); returns the CPU long address."""
        if not self.banks or (-len(self.banks[-1])) % align + len(data) > self.free():
            self.new_bank(name)
        b = self.banks[-1]
        b += bytes((-len(b)) % align)
        a = ((0x80 + len(self.banks)) << 16) | (0x8000 + len(b))
        b += data
        return a

    def linear(self, data, name, align=2048):
        """Place data (any size) contiguously across banks from an aligned offset; returns the long address of
        every align-sized piece (the pieces never cross a bank)."""
        assert BANK % align == 0 and len(data) % align == 0
        if not self.banks or self.free() < align:
            self.new_bank(name)
        else:
            b = self.banks[-1]
            b += bytes((-len(b)) % align)
            if self.free() < align:
                self.new_bank(name)
        addrs = []
        for i in range(0, len(data), align):
            if self.free() < align:
                self.new_bank(name)
            b = self.banks[-1]
            addrs.append(((0x80 + len(self.banks)) << 16) | (0x8000 + len(b)))
            b += data[i:i + align]
        return addrs


# ------------------------------------------------------------------ builder
class Builder:
    def __init__(self, args):
        self.args = args
        self.scn = pathlib.Path(args.scenario).resolve()
        self.endings_path = pathlib.Path(args.endings).resolve() if args.endings else self.scn.parent / 'endings.txt'
        self.diag = sc.Diag(strict=args.strict)
        self.font = fontmod.Font()

    def run(self):
        d = self.diag
        OUT.mkdir(parents=True, exist_ok=True)
        try:
            self.endings = sc.parse_endings(self.endings_path)
        except (sc.ScriptError, FileNotFoundError) as e:
            raise BuildError(str(e))
        for e in self.endings:
            e['title'] = sc.normalize(e['title'], self.font)
            bad = [c for c in e['title'] if not self.font.has(c)]
            if bad:
                d.err(f'endings.txt:{e["line"]}', f'characters not in the font: {bad}')
            if sc.width(e['title']) > 168:
                d.err(f'endings.txt:{e["line"]}', f'ending title too wide (max 14 full-width characters)')
        self.prog = sc.parse(self.scn, self.endings, self.font, d)
        self.audio = load_audio(d)
        prompts = json.loads((ROOT / 'assets/yonaki/prompts.json').read_text())
        bg_files = {p.stem for p in (ROOT / 'assets/yonaki/src/bg').glob('*.png')}
        sil_files = {p.stem for p in (ROOT / 'assets/yonaki/src/sil').glob('*.png')}
        self.assets = dict(bg=set(prompts['bg']), sil=set(prompts['sil']), bgm=set(self.audio['songs']),
                           se=set(self.audio['sfx']), amb=set(self.audio['amb']), bg_files=bg_files, sil_files=sil_files,
                           allow_missing_art=self.args.allow_missing_art,
                           unknown_sound_error=self.args.unknown_sound_error)
        self.reached = sc.check(self.prog, self.endings, d, self.assets)
        if len(self.prog.gnames) > 32:
            d.err('scenario', f'{len(self.prog.gnames)} global flags (at most 32)')
        if len(self.prog.local_flags) > 512:
            d.err('scenario', f'{len(self.prog.local_flags)} local flags (at most 512)')
        if len(self.prog.chapters) > 255:
            d.err('scenario', 'more than 255 chapter titles')
        self.report()
        if d.errors:
            raise BuildError(f'{len(d.errors)} error(s); see above (also build/yonaki/report.txt)')
        self.make_pictures()
        self.make_sils()
        self.encode()
        self.emit()

    def report(self):
        d = self.diag
        lines = [f'error: {e}' for e in d.errors] + [f'warning: {w}' for w in d.warnings] + \
                [f'note: {n}' for n in d.notes]
        (OUT / 'report.txt').write_text('\n'.join(lines) + '\n')
        for l in lines:
            if l.startswith('note:') and self.args.quiet:
                continue
            print(l, file=sys.stderr)

    # -- pictures
    def make_pictures(self):
        names = []
        for op, _ in self.prog.ops:
            if op[0] == 'bg' and op[1] not in names and op[1] not in sc.BUILTIN_BG:
                names.append(op[1])
        self.pic_names = ['black', 'white'] + names + ['@title']
        self.pics = [pictures.solid((0, 0, 0)), pictures.solid((255, 255, 255))]
        prev = OUT / 'previews'
        # the photos a silhouette can appear on get the translucent-figure colours (pictures.TINT_COLORS)
        at = sc.bg_flow(self.prog)
        sil_bgs = set().union(*(at[i] for i, (op, _) in enumerate(self.prog.ops) if op[0] == 'sil' and op[2]))
        for n in names:
            p = ROOT / f'assets/yonaki/src/bg/{n}.png'
            self.pics.append(pictures.background(p, tint=n in sil_bgs) if p.exists() else pictures.solid((0, 0, 0)))
        # the title: the first title background that exists, with the logo
        tb = next((b for b in TITLE_BGS if (ROOT / f'assets/yonaki/src/bg/{b}.png').exists()), None)
        lg = logomod.logo_rgba(self.font)
        self.title_bg = tb
        if tb:
            pos = (pictures.W - lg.shape[1] - 14, max(0, (pictures.H - lg.shape[0]) // 2 - 4))
            self.pics.append(pictures.titled(ROOT / f'assets/yonaki/src/bg/{tb}.png', lg, pos))
        else:
            self.diag.note('title', 'no title background yet (oldbath_ext / bell): logo on black')
            arr = np.zeros((pictures.H, pictures.W, 3))
            pos = ((pictures.W - lg.shape[1]) // 2, 8)
            a = lg[..., 3:4] / 255
            arr[pos[1]:pos[1] + lg.shape[0], pos[0]:pos[0] + lg.shape[1]] = lg[..., :3] * a
            self.pics.append(pictures.convert_photo(arr))
        for n, p in zip(self.pic_names, self.pics):
            pictures.preview_png(p['preview'], prev / f'bg_{n.strip("@")}.png')
        self.pic_index = {n: i for i, n in enumerate(self.pic_names)}

    def make_sils(self):
        """A @sil shows the staged silhouette of its background, character and position
        (assets/yonaki/src/stage/<bg>__<name>__<key>.png, placed where the picture put the person) when there is
        one, else the standing figure assets/yonaki/src/sil/<name>.png at the key's column."""
        at = sc.bg_flow(self.prog)
        names = []
        self.op_sil = {}
        for i, (op, where) in enumerate(self.prog.ops):
            if op[0] != 'sil' or not op[2]:
                continue
            n = op[2]
            bgs = at[i]
            if len(bgs) == 1:
                st = f'{next(iter(bgs))}/{op[2]}/{op[1]}'
                if (ROOT / 'assets/yonaki/src/stage' / (st.replace('/', '__') + '.png')).exists():
                    n = 'stage:' + st
                elif bgs != {'black'}:
                    self.diag.note(where, f'no staged silhouette {st} (standing figure)')
            elif bgs:
                self.diag.note(where, f'silhouette {op[2]} over more than one background {sorted(bgs)} '
                                      f'(standing figure)')
            self.op_sil[i] = n
            if n not in names:
                names.append(n)
        self.sil_names = names
        self.sils = []
        for n in names:
            if n.startswith('stage:'):
                st = n[6:]
                s = pictures.staged_silhouette(ROOT / 'assets/yonaki/src/stage' / (st.replace('/', '__') + '.png'),
                                               ROOT / f'assets/yonaki/src/bg/{st.split("/")[0]}.png')
                if s['stats']['bg_diff'] > 12:
                    self.diag.warn(n, f'the staged picture differs from its background (mean {s["stats"]["bg_diff"]:.1f})')
            else:
                p = ROOT / f'assets/yonaki/src/sil/{n}.png'
                s = pictures.silhouette(p) if p.exists() else pictures.placeholder_silhouette()
            self.sils.append(s)
            pictures.preview_png(s['preview'], OUT / 'previews' / f'sil_{n.replace("stage:", "").replace("/", "__")}.png')
        self.sil_index = {n: i for i, n in enumerate(names)}

    def sil_x(self, key, s):
        if 'x' in s:
            return s['x']
        w = s['w']
        if key == 'c':
            return (32 - w) // 2
        if key == 'l':
            return max(0, 9 - w // 2)
        if key == 'r':
            return min(32 - w, 23 - w // 2)
        return int(key[2:])

    # -- encoding
    def encode(self):
        prog = self.prog
        enc = Encoder(self.font)
        for op, _ in prog.ops:
            if op[0] == 'text':
                for ch in op[2]:
                    for ln in ch:
                        enc.feed(ln)
            elif op[0] == 'choice':
                for _, t, _ in op[2]:
                    for ln in t:
                        enc.feed(ln)
        for t in prog.chapters:
            enc.feed(t)
        for e in self.endings:
            enc.feed(e['title'])
        for s in UI.values():
            enc.feed(s)
        enc.feed('第章')
        cells = NAME_COLS * NAME_ROWS
        kanji = list(dict.fromkeys(c for c in NAME_KANJI if self.font.has(c)))
        if not 2 * cells < len(kanji) <= 3 * cells:
            raise BuildError(f'{len(kanji)} name kanji in the font (want 3 pages of {cells})')
        self.name_pages = NAME_PAGES + [''.join(kanji[i * cells:(i + 1) * cells]).ljust(cells, '　') for i in range(3)]
        for pg in self.name_pages:
            assert len(pg) == cells and all(self.font.has(c) for c in pg), pg
            enc.feed(pg.replace('　', ''))
        enc.feed(GLYPH_BLANK_NAME + ''.join(sc.NAME_VARS))
        enc.freeze()
        self.enc = enc
        self.lflag = {n: i for i, n in enumerate(prog.local_flags)}
        self.gflag = {n: i for i, n in enumerate(prog.gnames)}
        self.eindex = {e['id']: i for i, e in enumerate(self.endings)}
        songs, sfx, amb = self.audio['songs'], self.audio['sfx'], self.audio['amb']

        def cond(c):
            n, neg, glob = c
            v = (self.gflag[n] if n in self.gflag else 32 + self.eindex[n]) if glob else self.lflag[n]
            return v | (0x4000 if glob else 0) | (0x8000 if neg else 0)

        A = lambda lab: struct.pack('<I', self.addr[lab])[:3]
        # pass 1: sizes; pass 2: bytes with addresses
        self.addr = collections.defaultdict(lambda: 0)

        def op_bytes(op, i):
            k = op[0]
            if k == 'text':
                return bytes([OP['TEXT']]) + struct.pack('<H', op[1]) + bytes([len(op[2][0])]) + enc.lines(op[2])
            if k == 'blank':
                return bytes([OP['BLANK']])
            if k == 'page':
                return bytes([OP['PAGE']])
            if k == 'bg':
                return bytes([OP['BG'], self.pic_index[op[1]], BGMODE[op[2]]])
            if k == 'sil':
                key = SILKEY[op[1]] if op[1] in SILKEY else 0x80 | int(op[1][2:])
                if op[2] is None:
                    return bytes([OP['SIL'], key, 0xFF, 0, SILCOL[op[3]]])
                s = self.sil_index[self.op_sil[i]]
                return bytes([OP['SIL'], key, s, self.sil_x(op[1], self.sils[s]), SILCOL[op[3]]])
            if k == 'silclear':
                return bytes([OP['SILCLEAR']])
            if k == 'bgm':
                v = 0xFE if op[1] == 'stop' else 0xFF if op[1] == 'fade' else songs.get(op[1], 0xFD)
                return bytes([OP['BGM'], v])
            if k == 'se':
                if op[1] not in sfx and op[1] in amb:
                    return bytes([OP['AMB'], amb[op[1]]])
                return bytes([OP['SE'], sfx.get(op[1], 0xFF)])
            if k == 'amb':
                return bytes([OP['AMB'], 0xFF if op[1] == 'off' else amb.get(op[1], 0xFE)])
            if k == 'fx':
                return bytes([OP['FX'], FXK[op[1]]]) + struct.pack('<H', op[2])
            if k in ('set', 'clr'):
                return bytes([OP[k.upper()]]) + struct.pack('<H', self.lflag[op[1]])
            if k in ('setg', 'clrg'):
                return bytes([OP[k.upper()], self.gflag[op[1]]])
            if k == 'if':
                return bytes([OP['IF']]) + struct.pack('<H', cond(op[1])) + A(op[2])
            if k == 'goto':
                return bytes([OP['GOTO']]) + A(op[1])
            if k == 'choice':
                out = bytearray([OP['CHOICE']]) + struct.pack('<H', op[1]) + bytes([len(op[2])])
                ofs = []
                for cs, t, lab in op[2]:
                    out += bytes([len(cs)]) + b''.join(struct.pack('<H', cond(c)) for c in cs) + A(lab)
                    out += bytes([len(t)])
                    ofs.append(len(out))
                    out += enc.lines([t])
                self.opt_ofs[op[1]] = ofs
                return bytes(out)
            if k == 'end':
                return bytes([OP['END'], self.eindex[op[1]]])
            if k == 'chapter':
                return bytes([OP['CHAPTER'], op[1]])
            raise AssertionError(op)

        self.opt_ofs = {}
        rom = Rom()
        self.rom = rom
        # font first
        fb = enc.font_blob()
        self.font_bank = rom.cur() + 1
        for i in range(0, len(fb), BANK):
            rom.new_bank('font')
            rom.banks[-1] += fb[i:i + BANK]
        self.font_banks = rom.cur() - self.font_bank + 1
        # script: two passes (the addresses do not change the sizes)
        labels_at = collections.defaultdict(list)
        for name, idx in self.prog.labels.items():
            labels_at[idx].append(name)
        first_script_bank = rom.cur() + 1
        for pas in (1, 2):
            banks = [bytearray()]
            self.op_addr = []
            for i, (op, where) in enumerate(prog.ops):
                data = op_bytes(op, i)
                if len(banks[-1]) + len(data) + 4 > BANK:
                    nxt = ((0x80 + first_script_bank + len(banks)) << 16) | 0x8000
                    banks[-1] += bytes([OP['GOTO']]) + struct.pack('<I', nxt)[:3]
                    banks.append(bytearray())
                a = ((0x80 + first_script_bank + len(banks) - 1) << 16) | (0x8000 + len(banks[-1]))
                self.op_addr.append(a)
                for n in labels_at.get(i, ()):
                    self.addr[n] = a
                banks[-1] += data
            # the end of the program (labels after the last op)
            a = ((0x80 + first_script_bank + len(banks) - 1) << 16) | (0x8000 + len(banks[-1]))
            for n in labels_at.get(len(prog.ops), ()):
                self.addr[n] = a
            banks[-1] += bytes([OP['HALT']])
        for b in banks:
            rom.new_bank('script')
            rom.banks[-1] += b
        self.script_banks = (first_script_bank, len(banks))
        self.script_bytes = sum(len(b) for b in banks)
        self.build_id = int(sha(b''.join(banks) + enc.font_blob())[:8], 16)
        # resume tables: text id -> op address, choice id -> op address (one bank)
        tx = [0] * prog.text_count
        ch = [0] * prog.choice_count
        for i, (op, _) in enumerate(prog.ops):
            if op[0] == 'text':
                tx[op[1]] = self.op_addr[i]
            elif op[0] == 'choice':
                ch[op[1]] = self.op_addr[i]
        tbl = b''.join(struct.pack('<I', a)[:3] for a in tx)
        ctbl = b''.join(struct.pack('<I', a)[:3] for a in ch)
        if len(tbl) + len(ctbl) > BANK:
            raise BuildError(f'{prog.text_count} paragraphs: the resume table is over one bank')
        self.text_table = rom.put(tbl + ctbl, 'tables', align=BANK) if (tbl + ctbl) else rom.put(b'\0\0\0', 'tables')
        self.choice_table = self.text_table + len(tbl)
        # pictures: tiles linear (2048-byte rows), then the palettes
        self.pic_rows = []
        for p in self.pics:
            if p['tiles'] == b'\xff' * len(p['tiles']):
                self.pic_rows.append(None)
            else:
                self.pic_rows.append(rom.linear(p['tiles'], 'pictures'))
        self.pic_pal = [rom.put(struct.pack('<240H', *p['palette']), 'palettes') for p in self.pics]
        self.pic_tint = [rom.put(struct.pack('<224H', *p['tints']), 'palettes') if 'tints' in p else 0
                         for p in self.pics]
        self.sil_addr = [rom.put(s['mask'], 'silhouettes') for s in self.sils]
        img = self.audio['image']
        self.spc_addr = None
        for i in range(0, len(img), BANK):
            rom.new_bank('sound')
            rom.banks[-1] += img[i:i + BANK]
            if self.spc_addr is None:
                self.spc_addr = ((0x80 + rom.cur()) << 16) | 0x8000
        self.spc_len = len(img)
        total = rom.cur() + 1
        if total > MAX_BANKS:
            raise BuildError(f'ROM full: {total} banks of 32 KiB (at most {MAX_BANKS})')
        size = 512 * 1024
        while size < total * BANK:
            size *= 2
        self.rom_size = size
        self.nbanks = size // BANK

    # -- outputs
    def emit(self):
        enc = self.enc
        prog = self.prog
        files = {}
        seg = []
        for i, b in enumerate(self.rom.banks):
            n = f'bank{i + 1:03d}.bin'
            (OUT / n).write_bytes(bytes(b))
            files[n] = bytes(b)
            seg.append(f'.segment "BANK{i + 1}"\n    .incbin "{OUT.relative_to(ROOT)}/{n}"   ; {self.rom.names[i]}')
        # ld65 config
        mem = [' ZP:    start=$000000, size=$0100, type=rw;',
               ' RAM:   start=$000100, size=$1D00, type=rw;     # $1E00-$1FFF: stack',
               ' ROM0:  start=$008000, size=$7FB0, file=%O, fill=yes, fillval=$FF;',
               ' HDR:   start=$00FFB0, size=$0050, file=%O, fill=yes, fillval=$00;']
        segs = [' ZEROPAGE: load=ZP, type=zp;', ' BSS: load=RAM, type=bss, define=yes;',
                ' CODE: load=ROM0, type=ro;', ' RODATA: load=ROM0, type=ro;',
                ' HEADER: load=HDR, type=ro, start=$00FFB0;']
        for i in range(1, self.nbanks):
            mem.append(f' ROM{i}: start=${0x80 + i:02X}8000, size=$8000, file=%O, fill=yes, fillval=$FF;')
            segs.append(f' BANK{i}: load=ROM{i}, type=ro, optional=yes;')
        (OUT / 'yonaki.cfg').write_text(
            '# generated by tools/yonaki/build.py -- 夜鳴き鐘: LoROM (FastROM mirror $80-$FF), '
            f'{self.rom_size // 1024} KiB, 8 KiB battery SRAM\nMEMORY {{\n' + '\n'.join(mem) +
            '\n}\nSEGMENTS {\n' + '\n'.join(segs) + '\n}\n')
        rom_size_byte = {512: 9, 1024: 10, 2048: 11, 4096: 12}[self.rom_size // 1024]
        A = self.addr
        songs, sfx = self.audio['songs'], self.audio['sfx']
        title_song = next((songs[n] for n in ('title', 'yonaki', 'theme') if n in songs), 0xFF)
        ui_se = {k: next((sfx[n] for n in names if n in sfx), 0xFF) for k, names in
                 dict(cursor=('cursor', 'move'), ok=('ok', 'decide', 'select'), cancel=('cancel', 'back'),
                      save=('save', 'ok', 'decide')).items()}
        c = ['; generated by tools/yonaki/build.py -- do not edit']
        c += [f'OP_{k} = {v}' for k, v in OP.items()]
        c += [f'FX_{k.upper()} = {v}' for k, v in FXK.items()]
        c += [f'BGMODE_{k.upper()} = {v}' for k, v in BGMODE.items()]
        c += [f'ROM_SIZE_BYTE = ${rom_size_byte:02X}', f'ROM_BANKS = {self.nbanks}',
              f'FONT_BANK = ${0x80 + self.font_bank:02X}', f'TEXT_TABLE = ${self.text_table:06X}',
              f'CHOICE_TABLE = ${self.choice_table:06X}', f'TEXT_COUNT = {prog.text_count}',
              f'CHOICE_COUNT = {prog.choice_count}', f'PIC_COUNT = {len(self.pics)}', f'PIC_TITLE = {len(self.pics) - 1}',
              f'SIL_COUNT = {len(self.sils)}', f'ENDING_COUNT = {len(self.endings)}',
              f'GFLAG_COUNT = {len(prog.gnames)}', f'LFLAG_COUNT = {len(prog.local_flags)}',
              f'CHAPTER_COUNT = {len(prog.chapters)}', f'START_ADDR = ${A["start"]:06X}',
              f'OMAKE_ADDR = ${A["omake"] if "omake" in prog.labels else 0:06X}', f'OMAKE_ENDINGS = {self.args.omake_endings}', f'DEBUG_START = {int(self.args.debug_start)}',
              f'BUILD_ID_LO = ${self.build_id & 0xFFFF:04X}', f'BUILD_ID_HI = ${self.build_id >> 16:04X}',
              f'SPC_ADDR = ${self.spc_addr:06X}', f'SPC_LEN = {self.spc_len}', f'SPC_LOAD = ${self.audio["load"]:04X}',
              f'SPC_ENTRY = ${self.audio["entry"]:04X}', f'TITLE_SONG = ${title_song:02X}',
              *[f'SE_{k.upper()} = ${v:02X}' for k, v in ui_se.items()],
              f'GLYPH_PARA = {enc.index[GLYPH_PARA]}', f'GLYPH_PAGE = {enc.index[GLYPH_PAGE]}',
              f'GLYPH_CURSOR = {enc.index[GLYPH_CURSOR]}', f'GLYPH_LEFT = {enc.index[GLYPH_LEFT]}',
              f'GLYPH_RIGHT = {enc.index[GLYPH_RIGHT]}', f'GLYPH_OPT_A = {enc.index[OPT_LETTERS[0]]}', f'GLYPH_BLANK_NAME = {enc.index[GLYPH_BLANK_NAME]}',
              f'NAME_COLS = {NAME_COLS}', f'NAME_ROWS = {NAME_ROWS}', f'NAME_PAGES = {len(self.name_pages)}',
              f'NAME_MAX = {sc.NAME_MAX}', f'GLYPH_COUNT = {len(enc.glyphs)}',
              f'OWARI_W = {self.owari_w()}', f'OWARI_H = {self.owari_h}']
        (OUT / 'const.inc').write_text('\n'.join(c) + '\n')

        d = ['; generated by tools/yonaki/build.py -- do not edit', '.segment "RODATA"']
        # pictures: palette long address, 24 row addresses (3 bytes each), the long address of the white and red
        # translucent-figure colours (0: the picture has no translucent figures), 80 bytes per picture
        d.append('PicTable:')
        for i, rows in enumerate(self.pic_rows):
            ent = struct.pack('<I', self.pic_pal[i])[:3]
            ent += b''.join(struct.pack('<I', a)[:3] for a in rows) if rows else bytes(72)
            ent += struct.pack('<I', self.pic_tint[i])[:3]
            ent += bytes(80 - len(ent))
            d.append('    .byte ' + ', '.join(f'${x:02X}' for x in ent) + f'   ; {self.pic_names[i]}')
        d.append('SilTable:   ; width, height (tiles), mask address, bank, top row, 0, 0')
        for i, s in enumerate(self.sils):
            a = self.sil_addr[i]
            top = s.get('top', 24 - s['h'])
            d.append(f'    .byte {s["w"]}, {s["h"]}\n    .word ${a & 0xFFFF:04X}\n    .byte ${a >> 16:02X}, {top}, 0, 0'
                     f'   ; {self.sil_names[i]}')
        d.append('    .byte 0')
        strings = {}

        def string(key, s):
            strings[key] = s
            d.append(f'Str_{key}: .byte ' + ', '.join(f'${x:02X}' for x in enc.string(s)))
        for k, s in UI.items():
            string(k, s)
        for i, t in enumerate(prog.chapters):
            a, _, b = t.partition('　')
            string(f'chapter{i}a', a)
            string(f'chapter{i}b', b.strip('　'))
        for i, e in enumerate(self.endings):
            string(f'ending{i}', e['title'])
        d.append('ChapterTable:   ; the title split at its first full-width space')
        for i in range(len(prog.chapters)):
            d.append(f'    .word Str_chapter{i}a, Str_chapter{i}b')
        d.append('    .word 0, 0')
        d.append('KindNames: .word Str_kind0, Str_kind1, Str_kind2')
        d.append('NameCmds: .word ' + ', '.join(f'Str_name_cmd{i}' for i in range(5)))
        d.append('NameGrid:   ; glyph per cell ($FFFF empty), NAME_ROWS x NAME_COLS a page')
        for pg in self.name_pages:
            d.append('    .word ' + ', '.join('$FFFF' if c == '　' else str(enc.index[c]) for c in pg))
        d.append('NameDefault:   ; length, NAME_MAX glyphs: family name of the hero, given name of the heroine')
        for name in sc.NAME_VARS:
            g = [enc.index[c] for c in name] + [0] * (sc.NAME_MAX - len(name))
            d.append(f'    .word {len(name)}, ' + ', '.join(map(str, g)) + f'   ; {name}')
        # silhouette compensation for the dim level d (src/yonaki/pic.inc Tick): most of the text dim, then
        # down to 0 at the full dim
        dt = int(re.search(r'^DIM_TEXT\s*=\s*(\d+)', (ROOT / 'src/yonaki/yonaki.s').read_text(), re.M)[1])
        comp = [round(d * 0.5) if d <= dt else round(dt * 0.5 * (31 - d) / (31 - dt)) for d in range(32)]
        d.append('SilComp: .byte ' + ', '.join(map(str, comp)))
        # ShiftTable[s][v] = v << (8 - s) (glyph rows shifted into three bytes, src/yonaki/text.inc)
        d.append('ShiftTable:')
        for sh in range(8):
            vals = [(v << 8) >> sh for v in range(256)]
            for i in range(0, 256, 16):
                d.append('    .word ' + ', '.join(f'${x:04X}' for x in vals[i:i + 16]))
        d.append('SpeedTable: .word ' + ', '.join(f'Str_speed{i}' for i in range(4)))
        d.append('SlotNames: .word Str_slot1, Str_slot2, Str_slot3')
        # endings: title, kind (0 true 1 normal 2 bad), global flags set (32-bit mask)
        sets = sc.ending_sets(self.endings)
        d.append('EndingTable:   ; title, kind, global flag mask (lo, hi), 0')
        for i, e in enumerate(self.endings):
            m = sum(1 << self.prog.gnames.index(n) for n in sets[e['id']])
            d.append(f'    .word Str_ending{i}, {["true", "normal", "bad"].index(e["kind"])}, ${m & 0xFFFF:04X}, '
                     f'${m >> 16:04X}   ; {e["id"]} {e["kind"]} {e["scenario"]}')
        d.append('    .word 0')
        d.append('DigitCodes: .byte ' + ', '.join(f'${enc.code(ch)[0]:02X}' for ch in DIGITS))
        assert all(len(enc.code(ch)) == 1 for ch in DIGITS + '／')
        d.append(f'SlashCode: .byte ${enc.code("／")[0]:02X}')
        # ripple: HDMA table for BG1HOFS (one line per entry), 224 + 32 lines; the NMI starts it at phase * 3
        rip = bytearray()
        import math
        for y in range(224 + 32):
            v = round(2.0 * math.sin(2 * math.pi * y / 32)) & 0x3FF
            rip += bytes([1, v & 0xFF, v >> 8])
        rip.append(0)
        d.append('RippleTable: .byte ' + ', '.join(f'${x:02X}' for x in rip))
        d.append('OwariTiles: .byte ' + ', '.join(f'${x:02X}' for x in self.owari_tiles))
        d += seg
        (OUT / 'data.inc').write_text('\n'.join(d) + '\n')

        # layout for the tests and tools
        text_ops = {}
        choice_ops = {}
        label_of = {}
        cur = None
        for i, (op, where) in enumerate(prog.ops):
            for n, idx in prog.labels.items():
                if idx == i:
                    cur = n
            label_of[i] = cur
            if op[0] == 'text':
                text_ops[op[1]] = dict(addr=self.op_addr[i], op=i, label=cur, where=where, pages=op[2])
            elif op[0] == 'choice':
                choice_ops[op[1]] = dict(addr=self.op_addr[i], op=i, label=cur, where=where,
                                         options=[dict(text=''.join(t), lines=t, target=lab, conds=[list(c) for c in cs],
                                                       text_addr=self.op_addr[i] + self.opt_ofs[op[1]][k])
                                                  for k, (cs, t, lab) in enumerate(op[2])])
        layout = dict(
            build_id=self.build_id, scenario=str(self.scn), files=prog.files,
            labels={n: A[n] for n in prog.labels}, label_op=prog.labels,
            texts=text_ops, choices=choice_ops,
            ops=[list(op) if op[0] != 'text' else ['text', op[1]] for op, _ in prog.ops],
            op_addr=self.op_addr, op_where=[w for _, w in prog.ops],
            endings=[dict(id=e['id'], kind=e['kind'], scenario=e['scenario'], title=e['title'],
                          sets=sets[e['id']]) for e in self.endings],
            gflags=prog.gnames, lflags=prog.local_flags, chapters=prog.chapters,
            pictures=self.pic_names, silhouettes=self.sil_names,
            sil_size={n: [s['w'], s['h']] for n, s in zip(self.sil_names, self.sils)},
            songs=songs, sfx=sfx, audio=self.audio['info'], ui=strings, speeds=SPEEDS,
            glyphs=enc.glyphs, omake_endings=self.args.omake_endings, title_bg=self.title_bg,
            rom_size=self.rom_size, banks=self.rom.names, script_bytes=self.script_bytes,
            reached_ops=sorted(self.reached),
        )
        (OUT / 'layout.json').write_text(json.dumps(layout, ensure_ascii=False, indent=0) + '\n')
        manifest = dict(outputs={k: sha(v) for k, v in files.items()}, rom_size=self.rom_size,
                        banks=len(self.rom.banks) + 1, glyphs=len(enc.glyphs),
                        one_byte_glyphs=min(224, len(enc.glyphs)), texts=prog.text_count,
                        choices=prog.choice_count, script_bytes=self.script_bytes,
                        pictures={n: p['stats'] for n, p in zip(self.pic_names, self.pics)})
        (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')
        print(f'yonaki data: {len(prog.files)} files, {prog.text_count} paragraphs, {prog.choice_count} choices, '
              f'{len(prog.labels)} labels, {len(enc.glyphs)} glyphs, script {self.script_bytes} bytes, '
              f'{len(self.pics)} pictures, {len(self.sils)} silhouettes, ROM {self.rom_size // 1024} KiB '
              f'({len(self.rom.banks) + 1} banks used); {len(self.diag.warnings)} warnings')

    # -- 終 (Noto Serif rendering, 2bpp: 1 white, 2 shadow, 3 grey anti-aliasing)
    def owari_w(self):
        m = Image.open(ROOT / 'assets/yonaki/logo/owari_mask.png').convert('L')
        size = 40
        m = m.resize((size, size), Image.LANCZOS)
        a = np.asarray(m, float) / 255
        ys, xs = np.nonzero(a > 0.05)
        a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        h, w = a.shape
        tw, th = (w + 2 + 7) // 8, (h + 2 + 7) // 8
        pix = np.zeros((th * 8, tw * 8), int)
        ox, oy = (tw * 8 - w - 1) // 2, (th * 8 - h - 1) // 2
        cov = np.zeros_like(pix, float)
        cov[oy:oy + h, ox:ox + w] = a
        sh = np.zeros_like(cov)
        sh[1:, 1:] = cov[:-1, :-1]
        pix[sh > 0.35] = 2
        pix[cov > 0.25] = 3
        pix[cov > 0.6] = 1
        out = bytearray()
        for ty in range(th):
            for tx in range(tw):
                for y in range(8):
                    p0 = p1 = 0
                    for x in range(8):
                        v = pix[ty * 8 + y, tx * 8 + x]
                        if v & 1:
                            p0 |= 0x80 >> x
                        if v & 2:
                            p1 |= 0x80 >> x
                    out += bytes([p0, p1])
        self.owari_tiles = bytes(out)
        self.owari_h = th
        return tw


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument('--scenario', default=str(ROOT / 'data/yonaki/scenario'))
    ap.add_argument('--endings')
    ap.add_argument('--allow-missing-art', action='store_true')
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--unknown-sound-error', action='store_true')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--out', default=str(OUT))
    ap.add_argument('--omake-endings', type=int, default=OMAKE_ENDINGS)
    ap.add_argument('--debug-start', action='store_true')
    args = ap.parse_args()
    OUT = pathlib.Path(args.out).resolve()
    try:
        Builder(args).run()
    except (BuildError, sc.ScriptError, fontmod.FontError) as e:
        sys.exit(f'build error: {e}')


if __name__ == '__main__':
    main()
