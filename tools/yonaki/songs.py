"""Scores of 夜鳴き鐘 (original compositions), compiled by tools/yonaki/music.py.

The main theme 「夜鳴き鐘」 (D minor with the in-scale colour E-flat): the bell motif D - A - B-flat - A
(a bell-like long D, the falling fourth, the sigh B-flat to A) opens it and comes back in legend (on the
shakuhachi), unease (a semitone low, on the celesta), sorrow, dawn (in D major), badend (choir), staff;
oyura answers it with D - E-flat - D - A.

  0 title      D minor 66 bpm: 2 bars of bell + koto, then the theme (music box, then shakuhachi) over strings
  1 journey    A minor 92 bpm: harp "wheels", clarinet, a B-flat -> E (tritone) shadow at the end
  2 inn        F major 3/4 80 bpm: flute, let-ring koto, strings; the borrowed B-flat minor for the sadness
  3 dinner     G major 104 bpm: clarinet and koto, wood blocks; a low string line creeps down by semitones
  4 night      A minor 3/4 60 bpm: sparse piano, soft strings, harp, celesta "drops from the eaves"
  5 legend     D in-scale 54 bpm: shakuhachi with scoops over sho drones, sparse koto, taiko, the far bell
  6 unease     C minor 96 bpm: pizzicato ostinato, taiko pulse, tritone strings, the bell motif a semitone off
  7 horror     72 bpm: 32nd-note tremolo semitone cluster, falling low strings, sliding ghost choir,
               heartbeat (lub-dub), cluster stabs
  8 chase      D minor 160 bpm: reed lead, string ostinato, koto 16ths, taiko/snare, timpani
  9 investigate  A minor 100 bpm: wood-block clock, pizzicato, harp 16ths, clarinet; B: a circle of fifths
 10 deduce     C minor 116 bpm: string pulse, timpani, oboe; rising lower strings
 11 sorrow     the theme at 54 bpm: strings then shakuhachi, harp, the bell
 12 dawn       the theme in D major 72 bpm: flute, strings, harp, celesta
 13 badend     D minor 50 bpm, 8 bars, no loop: choir, low strings, timpani, the bell an octave low
 14 staff      the theme on koto, the inn melody, the theme in D major (the credits loop on the last part)
 15 oyura      ritual 63 bpm: taiko, clappers, sho clusters, ghost choir, shakuhachi, the bell every 4 bars
 16 chizuru    1969 kayōkyoku, A minor 92 bpm: strings tune in the yonanuki minor colour, nylon guitar,
               organ, bass, brush-like snare and shaker; B: the "sabi" up a register
 17 omake      C major 132 bpm: oboe tune, pizzicato oom-pah, piano after-beats, wood block, celesta

Song numbers ($40 + n) follow ORDER.  Each song: dict(name, bpm, beats, chans=[6 event lists or None],
echo=(feedback, volume), chords=[chord per bar, for the review], vib_hz).
Chords are written per bar ("Gm A" splits the bar); accompaniment is generated from them.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from music import mml, TPQ, MusicError

ORDER = ['title', 'journey', 'inn', 'dinner', 'night', 'legend', 'unease', 'horror', 'chase', 'investigate',
         'deduce', 'sorrow', 'dawn', 'badend', 'staff', 'oyura', 'chizuru', 'omake']

PC = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)
QUAL = {'': (0, 4, 7), 'm': (0, 3, 7), '7': (0, 4, 7, 10), 'm7': (0, 3, 7, 10), 'maj7': (0, 4, 7, 11),
        'sus4': (0, 5, 7), '7sus4': (0, 5, 7, 10), 'm7b5': (0, 3, 6, 10), 'm6': (0, 3, 7, 9), 'dim': (0, 3, 6),
        'mM7': (0, 3, 7, 11), 'm9': (0, 3, 7, 10, 14), '6': (0, 4, 7, 9), 'add9': (0, 4, 7, 14), '9': (0, 4, 7, 10, 14),
        'maj9': (0, 4, 7, 11, 14), '7b9': (0, 4, 7, 10, 13), 'madd9': (0, 3, 7, 14), '5': (0, 7), 'aug': (0, 4, 8)}


def chord(name):
    r = PC[name[0]]
    q = name[1:]
    if q[:1] in ('#', 'b'):
        r += 1 if q[0] == '#' else -1
        q = q[1:]
    if q not in QUAL:
        raise MusicError(f'chord {name}')
    return r % 12, QUAL[q]


def segments(bars, beats):
    out = []
    for bi, b in enumerate(bars):
        parts = b.split()
        t = TPQ * beats // len(parts)
        for p in parts:
            out.append((bi, p, t))
    return out


def tones(name, low):
    r, q = chord(name)
    root = low + (r - low) % 12
    return sorted(root + i + 12 * k for k in range(4) for i in q)


def with_bars(seg_events):
    out, last = [], 0
    for bi, ev in seg_events:
        if bi != last:
            out.append(('bar',))
            last = bi
        out += ev
    out.append(('bar',))
    return out


def arp(bars, beats, pattern, step, low=45):
    """Broken chords: pattern = tone indices (None = rest), restarting per chord."""
    se = []
    for bi, name, t in segments(bars, beats):
        ts = tones(name, low)
        ev = []
        for k in range(t // step):
            i = pattern[k % len(pattern)]
            ev.append(('rest', step) if i is None else ('note', ts[i], step))
        se.append((bi, ev))
    return with_bars(se)


def figure(bars, beats, offsets, step, low=45, minor_ofs=None, special=None):
    """Broken chords by semitone offsets from the root (root >= low).  offsets for major chords;
    minor_ofs for minor ones; special = {chord name: offsets}.  None = rest."""
    se = []
    for bi, name, t in segments(bars, beats):
        r, q = chord(name)
        root = low + (r - low) % 12
        ofs = (special or {}).get(name) or (minor_ofs if (3 in q and minor_ofs) else offsets)
        ev = []
        for k in range(t // step):
            o = ofs[k % len(ofs)]
            ev.append(('rest', step) if o is None else ('note', root + o, step))
        se.append((bi, ev))
    return with_bars(se)


def bassline(bars, beats, rhythm, low=31):
    """rhythm: {segment ticks: [(token, ticks)]}; tokens R root, 5 fifth, O octave, 3 third, 7 seventh, r rest."""
    se = []
    for bi, name, t in segments(bars, beats):
        r, q = chord(name)
        root = low + (r - low) % 12
        fifth = root + (7 if 7 in q else 6 if 6 in q else 8 if 8 in q else 7)
        third = root + (3 if 3 in q else 4 if 4 in q else 5)
        sev = root + (10 if 10 in q else 11 if 11 in q else 12)
        ev = []
        for tok, d in rhythm[t]:
            ev.append(('rest', d) if tok == 'r' else
                      ('note', {'R': root, '5': fifth, 'O': root + 12, '3': third, '7': sev, 'L': fifth - 12}[tok], d))
        se.append((bi, ev))
    return with_bars(se)


def pads(bars, beats, top=(65, 76), start=69, gap=(3, 9)):
    """Two sustained voices per chord with small moves: upper in `top`, lower a chord tone 3-9 below."""
    up, lo = [], []
    prev = start
    for bi, name, t in segments(bars, beats):
        ts = [x for x in tones(name, 36) if top[0] <= x <= top[1]]
        u = min(ts, key=lambda x: (abs(x - prev), x))
        below = [x for x in tones(name, 36) if gap[0] <= u - x <= gap[1]]
        l = max(below)
        prev = u
        up.append((bi, [('note', u, t)]))
        lo.append((bi, [('note', l, t)]))
    return with_bars(up), with_bars(lo)


def rests(n, beats):
    out = []
    for _ in range(n):
        out += [('rest', TPQ * beats), ('bar',)]
    return out


def ramp(events, v0, v1, pan=64):
    """Volume from v0 to v1 over the notes of `events`."""
    idx = [i for i, e in enumerate(events) if e[0] in ('note', 'rest')]
    out, k = [], 0
    for e in events:
        if e[0] in ('note', 'rest'):
            out.append(('vol', round(v0 + (v1 - v0) * k / max(1, len(idx) - 1)), pan))
            k += 1
        out.append(e)
    return out


def S(inst, vol, pan=64, gate=3, vib=0):
    return [('inst', inst), ('vol', vol, pan), ('gate', gate), ('vib', vib)]


def drums(pattern, bars, step, kit):
    """pattern: one bar as characters per step; kit: {char: (inst, midi, vol, pan)}; '.' rest."""
    out = []
    cur = None
    for _ in range(bars):
        for ch in pattern:
            if ch == '.':
                out.append(('rest', step))
                continue
            inst, midi, vol, pan = kit[ch]
            if cur != inst:
                out += [('inst', inst), ('gate', 0)]
                cur = inst
            out += [('vol', vol, pan), ('note', midi, step)]
        out.append(('bar',))
    return out


def transpose(events, n):
    return [(e[0], e[1] + n, *e[2:]) if e[0] == 'note' else e for e in events]


def song(name, bpm, beats, chans, chords, echo=(0x48, 0x22), vib_hz=5.0, dry=()):
    while len(chans) < 6:
        chans.append(None)
    return dict(name=name, bpm=bpm, beats=beats, chans=chans, chords=chords, echo=echo, vib_hz=vib_hz, dry=dry)


# ================================================================== the theme
THEME_CHORDS = ['Dm', 'Bbmaj7', 'Gm A7', 'Dm', 'F', 'Am', 'Gm Eb', 'Dm',
                'Bbmaj7', 'Gm7', 'Ebmaj7', 'A', 'Dm', 'Bbmaj7', 'Eb A7', 'Dm']
THEME = ('o5 d2. o4 a4 | b-2 a2 | g4. f8 e4 c+4 | d1 |'
         'o5 f2. e8 d8 | c2 o4 a2 | b-4. a8 g4 e-4 | d1 |'
         'o5 a2. g4 | f4 e4 d2 | e-2 d4 o4 b-4 | a1 |'
         'o5 d2. o4 a4 | b-2 a2 | g4. e-8 d4 c+4 | d1 |')
# the same melody in D major for the dawn
THEME_MAJ = ('o5 d2. o4 a4 | b2 a2 | g4. f+8 e4 c+4 | d1 |'
             'o5 f+2. e8 d8 | c+2 o4 a2 | b4. a8 g4 e4 | d1 |'
             'o5 a2. g4 | f+4 e4 d2 | e2 d4 o4 b4 | a1 |'
             'o5 d2. o4 a4 | b2 a2 | g4. e8 d4 c+4 | d1 |')
THEME_MAJ_CHORDS = ['D', 'Gadd9', 'Em A7', 'D', 'Bm7', 'F#m', 'Em C', 'D',
                    'Gmaj7', 'Em7', 'Cmaj7', 'Asus4 A', 'D', 'Gmaj7', 'C A7', 'D']

# koto figures (semitones from the root): D hirajoshi colours (the 9th, the minor 6th)
KOTO_MIN = [0, 7, 12, 14, 15, 14, 12, 7]
KOTO_MAJ = [0, 7, 12, 14, 16, 14, 12, 7]


# ------------------------------------------------------------------ 0 title
def title():
    beats = 4
    intro = ['Dm', 'Dm']
    ch = THEME_CHORDS
    A = S('mbox', 0, 52) + rests(2, beats)
    A += [('loop',)] + S('mbox', 96, 52, gate=2) + mml(THEME[:THEME.index('o5 a2.')])
    A += S('shaku', 70, 56, gate=4, vib=26) + [('bend', 10, 8, True)] + mml(THEME[THEME.index('o5 a2.'):])
    u, l = pads(ch, beats, top=(62, 72), start=65)
    iu, il = pads(intro, beats, top=(62, 72), start=65)
    B = S('slowstr', 30, 80, gate=6) + ramp(iu, 24, 44, 80) + [('loop',)] + S('strings', 46, 80, gate=6) + u
    C = S('slowstr', 28, 46, gate=6) + ramp(il, 22, 40, 46) + [('loop',)] + S('strings', 42, 46, gate=6) + l
    D = S('koto', 60, 36, gate=2) + figure(intro, beats, KOTO_MAJ, 24, 50, KOTO_MIN)
    D += [('loop',)] + S('koto', 60, 36, gate=2) + figure(ch, beats, KOTO_MAJ, 24, 45, KOTO_MIN, {'Am': [0, 7, 12, 13, 15, 13, 12, 7]})
    E = S('bass', 0) + rests(2, beats) + [('loop',)] + S('bass', 74, 64, gate=6)
    E += bassline(ch, beats, {192: [('R', 144), ('5', 48)], 96: [('R', 96)]}, low=33)
    # the bell: the motif's D on the phrase starts, a celesta glint at the end of the long notes
    F = S('kane', 56, 90, gate=0) + mml('o5 d1 | r1 |')
    F += [('loop',)] + S('kane', 56, 90, gate=0) + mml('o5 d1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 |')
    F += S('celesta', 30, 96, gate=0) + mml('r1 | r1 | r1 | r2 o6 c+4 e4 |') + S('kane', 50, 90, gate=0) + mml('o5 d1 | r1 | r1 | r1 |')
    return song('title', 66, beats, [A, B, C, D, E, F], ['Dm', 'Dm'] + ch, echo=(0x50, 0x24))


# ------------------------------------------------------------------ 1 journey
def journey():
    beats = 4
    ch = ['Am', 'Am', 'F', 'G', 'Am', 'Am', 'Dm', 'E', 'F', 'G', 'Em', 'Am', 'F', 'Dm', 'Bb', 'E']
    mel = ('o5 e2. d8 c8 | o4 b4 a4 b2 | o5 c2. o4 b8 a8 | b2 g2 | a4. b8 o5 c4 d4 | e2 c2 |'
           'f4. e8 d4 c4 | o4 b2. g+4 | a4. b8 o5 c4 o4 a4 | b4. o5 c8 d4 o4 b4 | g2 e2 | a2. r4 |'
           'o5 c4. d8 c4 o4 a4 | f2 a2 | b-2 o5 d4 c4 | o4 b1 |')
    A = [('loop',)] + S('clarinet', 66, 58, gate=4, vib=20) + mml(mel)
    u, l = pads(ch, beats, top=(60, 69), start=64)
    B = [('loop',)] + S('slowstr', 34, 82, gate=8) + u
    C = [('loop',)] + S('slowstr', 30, 44, gate=8) + l
    D = [('loop',)] + S('harp', 50, 34, gate=4) + figure(ch, beats, [0, 7, 12, 7, 16, 7, 12, 7], 24, 45,
                                                         [0, 7, 12, 7, 15, 7, 12, 7])
    E = [('loop',)] + S('bass', 60, 64, gate=8) + bassline(ch, beats, {192: [('R', 72), ('R', 24), ('5', 96)]}, low=33)
    F = [('loop',)] + drums('hhhhhhhh', 14, 24, {'h': ('shaker', 72, 18, 88)})
    F += S('kane', 0, 90, gate=0) + [('vol', 24, 90)] + mml('o5 d1 | r1 |')
    return song('journey', 92, beats, [A, B, C, D, E, F], ch, echo=(0x40, 0x20))


# ------------------------------------------------------------------ 2 inn
def inn():
    beats = 3
    ch = ['F', 'Am7', 'Bb', 'C7', 'F', 'Dm7', 'Gm7', 'C7', 'Bb', 'Bbm', 'Am7', 'Dm7', 'Gm7', 'C7sus4', 'F', 'C7',
          'Dm', 'Am', 'Bb', 'F', 'Gm7', 'C7', 'F', 'C7']
    mel = ('o5 c4. o4 a8 f4 | g2 e4 | f4 g4 b-4 | o5 c2. | o5 d4. c8 o4 a4 | o5 c2 o4 a4 | b-4. a8 g4 | g2. |'
           'f4. g8 a4 | o5 d-2 c4 | c4 o4 a4 g4 | a2 f4 | b-4. a8 g4 | g2 f4 | f2. | e2. |'
           'o5 f4. e8 d4 | e2 c4 | d4 c4 o4 b-4 | a2. | b-4. a8 g4 | o5 c4 o4 b-4 g4 | a2 f4 | g2. |')
    A = [('loop',)] + S('flute', 54, 58, gate=4, vib=22) + mml(mel)
    u, l = pads(ch, beats, top=(60, 70), start=65)
    B = [('loop',)] + S('strings', 38, 80, gate=6) + u
    C = [('loop',)] + S('strings', 34, 46, gate=6) + l
    D = [('loop',)] + S('koto_l', 56, 34, gate=2) + figure(ch, beats, [None, 7, 12, 16, 12, 7], 24, 45,
                                                            [None, 7, 12, 15, 12, 7])
    E = [('loop',)] + S('bass', 70, 64, gate=6) + bassline(ch, beats, {144: [('R', 96), ('5', 48)]}, low=33)
    F = [('loop',)] + S('celesta', 26, 94, gate=0)
    sp = []
    for bi, name, t in segments(ch, beats):
        ts = [x for x in tones(name, 60) if 84 <= x <= 95]
        sp.append((bi, [('rest', 96), ('note', ts[0], 48)] if bi % 2 == 1 else [('rest', 144)]))
    F += with_bars(sp)
    return song('inn', 80, beats, [A, B, C, D, E, F], ch, echo=(0x44, 0x22))


# ------------------------------------------------------------------ 3 dinner
def dinner():
    beats = 4
    ch = ['G', 'Em', 'C', 'D', 'G', 'Bm', 'C', 'Cm', 'G', 'E7', 'Am', 'Ab7', 'G', 'Em', 'Am7 D7', 'G',
          'C', 'D', 'Bm', 'Em', 'Am7', 'D7', 'G', 'G']
    mel = ('o5 d8 e8 d8 o4 b8 a4 g4 | b4. a8 g4 e4 | g8 a8 g8 e8 d4 c4 | d2. r4 |'
           'o5 d8 e8 d8 o4 b8 a4 g4 | f+4. g8 a4 b4 | o5 c4 o4 b8 a8 g4 e4 | e-2. r4 |'
           'd8 e8 g8 a8 b4 o5 d4 | e4. d8 c4 o4 b4 | a8 b8 o5 c8 d8 e4 c4 | e-4. d8 c4 o4 b-4 |'
           'b4 a8 g8 a4 b4 | g4. f+8 e4 g4 | a4 g4 f+4 a4 | g2. r4 |'
           'o5 e8 d8 c8 d8 e4 g4 | f+4. e8 d4 o4 a4 | b4 a8 b8 o5 d4 f+4 | e2. r4 |'
           'c8 d8 e8 c8 o4 a4 g4 | f+4. g8 a4 o5 c4 | o4 b4 a8 g8 d4 g4 | g2. r4 |')
    A = [('loop',)] + S('clarinet', 70, 56, gate=3, vib=12) + mml(mel)
    D = [('loop',)] + S('koto', 52, 30, gate=2) + figure(ch, beats, [0, None, 7, 12, None, 7, 12, None], 24, 50,
                                                         [0, None, 7, 12, None, 7, 12, None])
    E = [('loop',)] + S('pizz', 82, 64, gate=8) + bassline(ch, beats, {192: [('R', 48), ('5', 48), ('O', 48), ('5', 48)],
                                                                       96: [('R', 48), ('5', 48)]}, low=31)
    # the undercurrent: a low string line that creeps down by semitones under the cheer
    B = [('loop',)] + S('slowstr', 0, 70, gate=4) + rests(4, beats)
    B += S('slowstr', 30, 70, gate=4) + mml('o4 b1 | a+1 | a1 | g+1 |')
    B += S('slowstr', 34, 70, gate=4) + mml('o4 g1 | g+1 | a1 | a-1 |')
    B += S('slowstr', 30, 70, gate=4) + mml('o4 g1 | g1 | f+1 | g1 |')
    B += S('slowstr', 32, 70, gate=4) + mml('o4 g1 | f+1 | f1 | e1 | e-1 | d1 | d1 | d1 |')
    C = [('loop',)] + S('strings', 0, 44, gate=6) + rests(4, beats)
    u, l = pads(ch[4:], beats, top=(55, 64), start=59)
    C += S('slowstr', 26, 44, gate=6) + l
    F = [('loop',)] + drums('w.u.w.u.', 24, 24, {'w': ('wood', 69, 26, 72), 'u': ('wood', 64, 18, 60)})
    return song('dinner', 104, beats, [A, B, C, D, E, F], ch, echo=(0x30, 0x18))


# ------------------------------------------------------------------ 4 night
def night():
    beats = 3
    ch = ['Am9', 'Fmaj7', 'Am9', 'Em7', 'Fmaj7', 'Dm9', 'E7sus4', 'E',
          'Am9', 'Fmaj7', 'Am9', 'Em7', 'Fmaj7', 'Dm9', 'E7sus4', 'Am9',
          'Fmaj7', 'Em7', 'Dm9', 'Cmaj7', 'Fmaj7', 'Em7', 'Dm7', 'E7sus4 E']
    mel = ('o5 e2. | c2 o4 b4 | a2. | b2 g4 | a4 c4 e4 | f2 e4 | d2. | r2. |'
           'o5 e4. d8 c4 | c2 o4 b4 | a2. | g2 b4 | a4 g4 f4 | f2 e4 | e2. | r2. |'
           'o5 c4. o4 b8 a4 | g2 e4 | f4 e4 d4 | e2. | a4. g8 f4 | e2 d4 | c4 d4 f4 | e2. |')
    A = [('loop',)] + S('ep', 92, 54, gate=6) + mml(mel)
    u, l = pads(ch, beats, top=(60, 69), start=64)
    B = [('loop',)] + S('slowstr', 24, 82, gate=10) + u
    C = [('loop',)] + S('slowstr', 22, 44, gate=10) + l
    D = [('loop',)] + S('harp', 36, 30, gate=4) + figure(ch, beats, [0, 7, 14, None, None, None], 24, 45,
                                                         [0, 7, 14, None, None, None])
    E = [('loop',)] + S('bass', 58, 64, gate=8) + bassline(ch, beats, {144: [('R', 144)], 72: [('R', 72)]}, low=33)
    # drops: a high celesta now and then, like water from the eaves
    F = [('loop',)] + S('celesta', 34, 100, gate=0)
    F += mml('r2. | r4 o6 e8 r8 r4 | r2. | r2. | r2 o6 c8 r8 | r2. | r2. | o6 e4 r2 |'
             'r2. | r4 o6 a8 r8 r4 | r2. | r2. | r2 o6 c8 r8 | r2. | r4 o6 b8 r8 r4 | r2. |'
             'r2. | r4 o6 g8 r8 r4 | r2. | r2 o6 e8 r8 | r2. | r2. | r4 o6 a8 r8 r4 | r2. |')
    return song('night', 60, beats, [A, B, C, D, E, F], ch, echo=(0x58, 0x26))


# ------------------------------------------------------------------ 5 legend
def legend():
    beats = 4
    # D in-scale (miyako-bushi): D E-flat G A B-flat; a drone on D and A
    ch = ['D5'] * 4 + ['Gm'] * 2 + ['D5'] * 2 + ['Eb'] * 2 + ['D5'] * 2 + ['Gm', 'Eb', 'D5', 'D5']
    shk = ('o5 d2.. e-8 | d1 | r2 o4 a4 b-4 | a1 |'
           'b-2. o5 d4 | e-2 d4 o4 b-4 | a1 | r1 |'
           'o5 g2. a8 b-8 | a2 g4 e-4 | d1 | r2 o4 a4 b-4 |'
           'o5 d2 e-4 d4 | o4 b-2 a4 g4 | a1 | r1 |')
    A = [('loop',)] + S('shaku', 58, 58, gate=6, vib=30) + [('bend', 12, 10, True)] + mml(shk)
    B = [('loop',)] + S('sho', 58, 76, gate=0) + mml('o4 a1^1^1^1 | b-1^1 | a1^1 | b-1^1 | a1^1 | b-1 | b-1 | a1^1 |')
    C = [('loop',)] + S('sho', 54, 52, gate=0) + mml('o4 d1^1^1^1 | d1^1 | d1^1 | e-1^1 | d1^1 | d1 | e-1 | d1^1 |')
    D = [('loop',)] + S('koto_l', 50, 30, gate=0)
    D += mml('o4 d4 r2. | r1 | r2 a8 b-8 r4 | r1 | g4 r2. | r2 b-8 a8 r4 | d4 r2. | r1 |'
             'e-4 r2. | r2 g8 a8 r4 | d4 r2. | r1 | g4 r2. | e-4 r2. | d2 r2 | r1 |')
    E = [('loop',)] + S('strings', 40, 64, gate=0) + mml('o2 d1^1^1^1 | g1^1 | d1^1 | e-1^1 | d1^1 | g1 | e-1 | d1^1 |')
    F = [('loop',)] + S('kane', 36, 96, gate=0) + mml('o5 d1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 |')
    F += S('taiko', 44, 64, gate=0) + mml('o2 c4 r2. | r1 | r1 | r1 | c4 r2. | r1 | c4 r4 c4 r4 | r1 |')
    return song('legend', 54, beats, [A, B, C, D, E, F],
                ['D5'] * 4 + ['Gm', 'Gm', 'D5', 'D5', 'Eb', 'Eb', 'D5', 'D5', 'Gm', 'Eb', 'D5', 'D5'],
                echo=(0x60, 0x2A), vib_hz=4.5)


# ------------------------------------------------------------------ 6 unease
def unease():
    beats = 4
    ch = ['Cm', 'Cm', 'Abmaj7', 'Cm', 'Cm', 'Db', 'Cm', 'G7b9'] * 2 + ['Fm', 'Fm', 'Cm', 'Cm', 'Ab', 'Db', 'G7b9', 'G7b9']
    ost = 'o2 c8 c8 e-8 c8 d8 c8 g8 f+8 |'
    E = [('loop',)] + S('pizz', 80, 64, gate=6)
    for name in ch:
        r, q = chord(name)
        E += transpose(mml(ost), {0: 0, 8: -4, 1: 1, 7: -5, 5: 5}[r])
    B = [('loop',)] + S('slowstr', 0, 80, gate=0) + rests(2, beats)
    B += S('slowstr', 30, 80, gate=0) + mml('o5 c1 | c1 | c1 | d-1 | c1 | o4 b1 |')
    B += S('slowstr', 36, 80, gate=0) + mml('o5 e-1 | e-1 | e-1 | e-1 | f1 | f1 | f+1 | f1 |')
    B += S('slowstr', 42, 80, gate=0) + mml('o5 a-1 | g1 | g1 | e-1 | e-1 | f1 | f1 | f1 |')
    C = [('loop',)] + S('slowstr', 0, 46, gate=0) + rests(4, beats)
    C += S('slowstr', 28, 46, gate=0) + mml('o4 f+1 | f1 | f+1 | f1 |')
    C += S('slowstr', 30, 46, gate=0) + mml('o4 g1 | g1 | g1 | g1 | a-1 | a-1 | g1 | g1 |')
    C += S('slowstr', 38, 46, gate=0) + mml('o4 c1 | c1 | c1 | c1 | c1 | d-1 | d1 | b1 |')
    # the bell motif, a semitone off and slow, high and quiet
    A = [('loop',)] + S('celesta', 0, 60) + rests(8, beats)
    A += S('celesta', 72, 60, gate=0) + mml('o5 c2. o4 g4 | a-2 g2 | r1 | r1 | o5 c2. o4 g4 | a-2 g2 | f+1 | r1 |')
    A += mml('o5 f2. c4 | d-2 c2 | r1 | r1 | e-2. o4 b-4 | o5 c2 o4 b-2 | b1 | r1 |')
    D = [('loop',)] + S('taiko', 46, 64, gate=0)
    for _ in range(24):
        D += mml('o2 c4 r4 c4 r4 |')
    F = [('loop',)] + S('timp', 0, 64, gate=0) + rests(7, beats) + S('timp', 50, 64, gate=0) + mml('o2 g4 r4 g4 r4 |')
    F += rests(7, beats) + S('timp', 56, 64, gate=0) + mml('o2 g8 g8 g8 g8 g8 g8 g8 g8 |')
    F += S('timp', 50, 64, gate=0) + mml('o2 f4 r2. |') + rests(5, beats) + mml('o2 g4 r4 g4 r4 |') + \
        ramp(mml('o2 g16 g16 g16 g16 g16 g16 g16 g16 g16 g16 g16 g16 g16 g16 g16 g16 |'), 30, 70)
    return song('unease', 96, beats, [A, B, C, D, E, F], ch, echo=(0x48, 0x22))


# ------------------------------------------------------------------ 7 horror
def horror():
    beats = 4
    bars = 8
    # tremolo strings: a semitone cluster that slides, 16th repeats (not too high)
    def trem(notes):
        out = []
        for n in notes.split():
            out += [('rep', 32, mml(f'{n}32')), ('bar',)]
        return out
    A = [('loop',)] + S('trem', 44, 80, gate=1) + trem('o5e o5e o5f o5f o5e o5e o5f+ o5f')
    B = [('loop',)] + S('trem', 40, 48, gate=1) + trem('o5f o5f o5f+ o5f+ o5f o5d+ o5g o5f+')
    # a low string line falling by glissando under it
    C = [('loop',)] + S('slowstr', 56, 64, gate=0) + [('bend', -3, 90, False)]
    C += mml('o3 e1 | d+1 | e1 | c1 | e1 | d+1 | f1 | e1 |')
    # the ghost choir, sliding between notes
    D = [('loop',)] + S('choir', 0, 30, gate=0) + rests(2, beats)
    D += S('choir', 40, 30, gate=8, vib=70) + [('bend', 10, 40, True)] + mml('o4 b2. a+4 | b1 | r1 | o5 c2 o4 b2 | a+1 | r1 |')
    # heartbeat 72 bpm, lub-dub
    E = [('loop',)]
    for _ in range(bars):
        E += S('taiko', 82, 64, gate=0) + mml('o2 c8') + [('vol', 54, 64)] + mml('c+8 r4') + [('vol', 82, 64)] + \
             mml('c8') + [('vol', 54, 64)] + mml('c+8 r4 |')
    F = [('loop',)] + S('stab', 0, 64, gate=0) + rests(3, beats) + S('stab', 66, 64, gate=0) + mml('o3 d4 r2. |')
    F += rests(3, beats) + S('stab', 72, 64, gate=0) + mml('o3 d+8 r8 d4 r2 |')
    return song('horror', 72, beats, [A, B, C, D, E, F], ['Em'] * 8, echo=(0x58, 0x26), vib_hz=6.0)


# ------------------------------------------------------------------ 8 chase
def chase():
    beats = 4
    ch = ['Dm', 'Dm', 'Bb', 'C', 'Dm', 'Dm', 'Gm', 'A', 'Dm', 'Dm', 'Bb', 'C', 'Gm', 'Eb', 'A', 'A7']
    mel = ('o5 d4. d8 f4 e4 | d4 c8 d8 r2 | d4. d8 f4 g4 | e2 c4 r4 |'
           'a4. a8 g4 f4 | e4 d8 e8 r2 | f4 e4 d4 b-4 | c+2. r4 |'
           'd4. d8 f4 e4 | d4 c8 d8 r2 | f4. f8 a4 b-4 | g2 e4 r4 |'
           'b-4. a8 g4 d4 | e-4. f8 g4 b-4 | a2 e4 c+4 | a2. r4 |')
    A = [('loop',)] + S('reed', 86, 58, gate=4, vib=10) + mml(mel)
    B = [('loop',)] + S('trem', 46, 80, gate=3) + figure(ch, beats, [12, 12, 16, 12, 19, 12, 16, 12], 24, 50,
                                                          [12, 12, 15, 12, 19, 12, 15, 12])
    C = [('loop',)] + S('koto', 46, 40, gate=2) + figure(ch, beats, [0, 7, 12, 7], 12, 50, [0, 7, 12, 7])
    E = [('loop',)] + S('bass', 64, 64, gate=6) + bassline(ch, beats, {192: [('R', 24)] * 6 + [('O', 24), ('R', 24)]}, low=33)
    D = [('loop',)] + drums('k.s.kks.', 16, 24, {'k': ('taiko', 60, 72, 64), 's': ('snare', 72, 46, 70)})
    F = [('loop',)] + S('timp', 64, 64, gate=0)
    for name in ch:
        r, q = chord(name)
        F += mml('o2 d4 r2. |') if r == 2 else transpose(mml('o2 d4 r2. |'), (r - 2 + 6) % 12 - 6)
    return song('chase', 160, beats, [A, B, C, D, E, F], ch, echo=(0x30, 0x1A), vib_hz=6.0)


# ------------------------------------------------------------------ 9 investigate
def investigate():
    beats = 4
    ch = ['Am', 'G', 'F', 'E', 'Dm', 'Am', 'Bm7b5', 'E', 'Am', 'C', 'F', 'Dm', 'Bb', 'F', 'E', 'E7',
          'Dm', 'G', 'C', 'F', 'Bm7b5', 'E', 'Am', 'E7']
    mel = ('r1 | r1 | o5 c4. o4 b8 a4 f4 | g+2. r4 |'
           'a8 b8 o5 c8 d8 e4 d8 c8 | o4 b4 a4 g+4 a4 | d4 f4 a4 o5 d4 | o4 b2 g+4 e4 |'
           'a4. b8 o5 c4 e4 | e4. d8 c4 g4 | a4. g8 f4 c4 | d2. r4 |'
           'd4. e8 f4 d4 | c4. o4 b-8 a4 f4 | g+2 b4 o5 d4 | e2 r2 |'
           'o5 d4. e8 f4 d4 | o4 b4. o5 c8 d4 o4 b4 | o5 c4. d8 e4 c4 | o4 a4. b8 o5 c4 o4 a4 |'
           'b4. a8 f4 d4 | g+4 b4 o5 e4 d4 | c2 o4 a2 | b2 g+2 |')
    A = [('loop',)] + S('clarinet', 70, 56, gate=4, vib=14) + mml(mel)
    u, l = pads(ch, beats, top=(62, 72), start=67)
    B = [('loop',)] + S('strings', 34, 80, gate=6) + u
    C = [('loop',)] + S('harp', 42, 40, gate=2) + figure(ch, beats, [12, 16, 19, 16], 12, 45, [12, 15, 19, 15],
                                                          {'Bm7b5': [12, 15, 18, 15]})
    E = [('loop',)] + S('pizz', 82, 64, gate=6) + bassline(ch, beats, {192: [('R', 24), ('r', 24), ('5', 24), ('r', 24),
                                                                             ('O', 24), ('r', 24), ('5', 24), ('r', 24)]}, low=33)
    D = [('loop',)] + drums('tktk', 24, 48, {'t': ('wood', 69, 54, 74), 'k': ('wood', 64, 42, 56)})
    F = [('loop',)] + S('celesta', 0, 96, gate=0) + rests(15, beats) + S('celesta', 26, 96, gate=0) + mml('o6 e8 r8 r4 r2 |')
    F += S('celesta', 30, 96, gate=0) + mml('o6 d4 r2. | r1 | c4 r2. | r1 | o5 b4 r2. | r1 | a4 r2. | g+4 r2. |')
    return song('investigate', 100, beats, [A, B, C, D, E, F], ch, echo=(0x38, 0x1C))


# ------------------------------------------------------------------ 10 deduce
def deduce():
    beats = 4
    ch = ['Cm', 'Ab', 'Fm', 'G', 'Cm', 'Ab', 'Db', 'G', 'Ab', 'Bb', 'Gm', 'Cm', 'Fm', 'Db', 'G', 'G7']
    mel = ('o5 c2. d8 e-8 | c2 o4 a-2 | f4. g8 a-4 o5 c4 | o4 b2. r4 |'
           'o5 e-2. f8 g8 | e-2 c2 | d-4. e-8 f4 a-4 | g2. r4 |'
           'a-2. g8 f8 | b-2 f2 | g4. f8 e-4 d4 | e-2 c2 |'
           'f4. g8 a-4 f4 | a-4. g8 f4 d-4 | d2 f4 a-4 | g1 |')
    A = [('loop',)] + S('oboe', 84, 58, gate=4, vib=16) + mml(mel)
    B = [('loop',)] + S('trem', 40, 82, gate=4) + figure(ch, beats, [12, 16, 19, 16], 24, 48, [12, 15, 19, 15])
    u, l = pads(ch, beats, top=(56, 66), start=60)
    C = [('loop',)] + ramp(S('strings', 30, 46, gate=6) + l[:16], 30, 44, 46) + ramp(l[16:], 44, 56, 46)
    E = [('loop',)] + S('bass', 60, 64, gate=8) + bassline(ch, beats, {192: [('R', 24)] * 8}, low=31)
    D = [('loop',)] + S('timp', 50, 64, gate=0)
    for name in ch:
        r, q = chord(name)
        D += transpose(mml('o2 c4 r4 r4 c8 c8 |'), (r - 0 + 5) % 12 - 5)
    F = [('loop',)] + S('kane', 0, 90, gate=0) + rests(14, beats) + S('stab', 54, 64, gate=0) + mml('o3 g4 r2. | r1 |')
    return song('deduce', 116, beats, [A, B, C, D, E, F], ch, echo=(0x40, 0x1E))


# ------------------------------------------------------------------ 11 sorrow
def sorrow():
    beats = 4
    ch = THEME_CHORDS
    A = [('loop',)] + S('strings', 64, 60, gate=6, vib=24) + mml(THEME[:THEME.index('o5 a2.')])
    A += S('shaku', 70, 60, gate=6, vib=28) + [('bend', 10, 8, True)] + mml(THEME[THEME.index('o5 a2.'):])
    u, l = pads(ch, beats, top=(57, 65), start=60, gap=(3, 8))
    B = [('loop',)] + S('slowstr', 34, 84, gate=10) + u
    C = [('loop',)] + S('slowstr', 30, 40, gate=10) + l
    D = [('loop',)] + S('harp', 40, 30, gate=3) + figure(ch, beats, [0, 7, 12, 16, 19, 16, 12, 7], 24, 38,
                                                         [0, 7, 12, 15, 19, 15, 12, 7])
    E = [('loop',)] + S('bass', 60, 64, gate=10) + bassline(ch, beats, {192: [('R', 192)], 96: [('R', 96)]}, low=33)
    F = [('loop',)] + S('kane', 22, 96, gate=0) + mml('o5 d1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 |') \
        + S('kane', 22, 96, gate=0) + mml('o5 d1 | r1 | r1 | r1 |')
    return song('sorrow', 54, beats, [A, B, C, D, E, F], ch, echo=(0x58, 0x26), vib_hz=4.5)


# ------------------------------------------------------------------ 12 dawn
def dawn():
    beats = 4
    ch = THEME_MAJ_CHORDS
    A = [('loop',)] + S('flute', 62, 58, gate=4, vib=20) + mml(THEME_MAJ)
    u, l = pads(ch, beats, top=(64, 74), start=69)
    B = [('loop',)] + S('strings', 50, 80, gate=6) + u
    C = [('loop',)] + S('strings', 44, 46, gate=6) + l
    D = [('loop',)] + S('harp', 50, 36, gate=2) + figure(ch, beats, [0, 7, 12, 14, 16, 14, 12, 7], 24, 45,
                                                         [0, 7, 12, 14, 15, 14, 12, 7])
    E = [('loop',)] + S('bass', 72, 64, gate=6) + bassline(ch, beats, {192: [('R', 96), ('5', 96)], 96: [('R', 96)]}, low=33)
    F = [('loop',)] + S('celesta', 28, 92, gate=0)
    sp = []
    for bi, name, t in segments(ch, beats):
        ts = [x for x in tones(name, 60) if 84 <= x <= 96]
        sp.append((bi, [('rest', t // 2), ('note', ts[0], t // 4), ('rest', t // 4)]))
    F += with_bars(sp)
    return song('dawn', 72, beats, [A, B, C, D, E, F], ch, echo=(0x48, 0x22))


# ------------------------------------------------------------------ 13 badend (does not loop)
def badend():
    beats = 4
    ch = ['Dm', 'Bb', 'Gm', 'A', 'Dm', 'Eb', 'Dm', 'Dm']
    A = S('choir', 50, 60, gate=12, vib=40) + mml('o4 d2. o3 a4 | b-2 a2 | g2 a2 | a1 | d2 f2 | e-1 | d1^1 |')
    A += [('rest', 96)]
    B = S('slowstr', 40, 82, gate=12) + mml('o4 f1 | f1 | d1 | c+1 | f1 | g1 | f1^1 |') + [('rest', 96)]
    C = S('slowstr', 36, 44, gate=12) + mml('o3 a1 | b-1 | b-1 | e1 | a1 | b-1 | a1^1 |') + [('rest', 96)]
    E = S('strings', 46, 64, gate=12) + mml('o2 d1 | o1 b-1 | g1 | a1 | o2 d1 | e-1 | d1^1 |') + [('rest', 96)]
    F = S('kane', 30, 90, gate=0) + mml('o5 d1 | r1 | r1 | r1 | r1 | r1 |') + S('kane', 22, 90, gate=0) + mml('o4 d1^1 |') \
        + [('rest', 96)]
    D = S('timp', 50, 64, gate=0) + mml('o2 d4 r2. | r1 | r1 | o1 a4 r2. | r1 | r1 |') + \
        S('timp', 40, 64, gate=0) + mml('o2 d4 r2. | r1 |') + [('rest', 96)]
    return song('badend', 50, beats, [A, B, C, D, E, F], ch + ['Dm'], echo=(0x58, 0x26))


# ------------------------------------------------------------------ 14 staff (credits)
def staff():
    beats = 4
    t_ch = THEME_CHORDS
    m_ch = THEME_MAJ_CHORDS
    # part 1: the theme (koto melody, full strings); part 2: the inn melody in F; part 3: the theme in D major
    inn_ch = ['F', 'Am7', 'Bb', 'C7', 'F', 'Dm7', 'Gm7', 'C7']
    inn_mel = ('o5 c2. o4 a4 | g2 e2 | f4 g4 b-4 o5 d4 | c1 | d4. c8 o4 a4 o5 c4 | c2 o4 a2 | b-4. a8 g4 b-4 | g1 |')
    A = S('koto_l', 120, 54, gate=2) + mml(THEME)
    A += S('flute', 64, 58, gate=4, vib=20) + mml(inn_mel)
    A += S('flute', 66, 58, gate=4, vib=20) + mml(THEME_MAJ)
    u1, l1 = pads(t_ch, beats, top=(62, 72), start=65)
    u2, l2 = pads(inn_ch, beats, top=(60, 70), start=65)
    u3, l3 = pads(m_ch, beats, top=(64, 74), start=69)
    B = S('strings', 46, 80, gate=6) + u1 + u2 + u3 + [('loop',)]
    C = S('strings', 42, 46, gate=6) + l1 + l2 + l3 + [('loop',)]
    D = S('harp', 50, 36, gate=2) + figure(t_ch, beats, KOTO_MAJ, 24, 45, KOTO_MIN)
    D += figure(inn_ch, beats, [0, 7, 12, 16, 19, 16, 12, 7], 24, 45, [0, 7, 12, 15, 19, 15, 12, 7])
    D += figure(m_ch, beats, KOTO_MAJ, 24, 45, KOTO_MIN) + [('loop',)]
    E = S('bass', 60, 64, gate=6) + bassline(t_ch, beats, {192: [('R', 144), ('5', 48)], 96: [('R', 96)]}, low=33)
    E += bassline(inn_ch, beats, {192: [('R', 96), ('5', 96)], 96: [('R', 96)]}, low=33)
    E += bassline(m_ch, beats, {192: [('R', 96), ('5', 96)], 96: [('R', 96)]}, low=33) + [('loop',)]
    F = S('kane', 36, 90, gate=0) + mml('o5 d1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 | r1 | o5 d1 | r1 | r1 | r1 |')
    F += S('celesta', 26, 96, gate=0) + rests(7, beats) + mml('r2 o6 c4 e4 |')
    sp = []
    for bi, name, t in segments(m_ch, beats):
        ts = [x for x in tones(name, 60) if 84 <= x <= 96]
        sp.append((bi, [('rest', t // 2), ('note', ts[0], t // 4), ('rest', t // 4)]))
    F += with_bars(sp) + [('loop',)]
    # the credits loop on the last part (from the major theme)
    return song('staff', 70, beats, [_loop_at(x, 24 * 4 * TPQ) for x in (A, B, C, D, E, F)],
                t_ch + inn_ch + m_ch, echo=(0x50, 0x24))


def _loop_at(events, tick):
    """Move the ('loop',) marker to the given tick (the start of the major theme in staff)."""
    ev = [e for e in events if e[0] != 'loop']
    out, t, done = [], 0, False
    for e in ev:
        if not done and t >= tick and e[0] in ('note', 'rest', 'tie'):
            out.append(('loop',))
            done = True
        out.append(e)
        if e[0] in ('note', 'rest', 'tie'):
            t += e[-1] if e[0] != 'note' else e[2]
    if not done:
        out.append(('loop',))
    # re-emit the state after the loop marker: the compiler does that itself
    return out


# ------------------------------------------------------------------ 15 oyura
def oyura():
    beats = 4
    # ritual: taiko, wooden clappers, sho clusters (D E A B / E-flat clashes), a breathy line, the bell
    A = [('loop',)] + S('shaku', 0, 60) + rests(4, beats)
    A += S('shaku', 56, 60, gate=8, vib=34) + [('bend', 14, 12, True)]
    A += mml('o5 d1 | e-2 d2 | o4 a1 | r1 | b-2. a4 | g2 e-2 | d1 | r1 | o5 g2 a2 | b-2 a4 g4 | e-1 | d1 |')
    B = [('loop',)] + S('sho', 60, 80, gate=0) + mml('o5 e1^1^1^1 | e-1^1^1^1 | e1^1^1^1 | e-1^1^1^1 |')
    C = [('loop',)] + S('sho', 56, 48, gate=0) + mml('o4 a1^1^1^1 | b1^1^1^1 | a1^1^1^1 | b-1^1^1^1 |')
    D = [('loop',)] + S('choir', 0, 34, gate=0) + rests(8, beats)
    D += S('choir', 34, 34, gate=10, vib=60) + mml('o4 d1 | e-1 | d1 | r1 | o3 a1 | b-1 | a1 | r1 |')
    E = [('loop',)]
    for i in range(16):
        E += S('taiko', 84, 64, gate=0) + mml('o2 c4') + [('vol', 50, 64)] + mml('c8 c8') + [('vol', 70, 64)] + \
            mml('c4 r4 |' if i % 4 != 3 else 'c8 c8 c8 c8 |')
    F = [('loop',)]
    for i in range(16):
        if i % 4 == 0:
            F += S('kane', 34, 90, gate=0) + mml('o5 d2 r2 |')
        else:
            F += S('wood', 34, 80, gate=0) + mml('o3 c4 r4 r4 c8 c8 |')
    return song('oyura', 63, beats, [A, B, C, D, E, F], ['D5'] * 16, echo=(0x60, 0x2A), vib_hz=4.0)


# ------------------------------------------------------------------ 16 chizuru (1969)
def chizuru():
    beats = 4
    ch = ['Am', 'Dm', 'E7', 'Am', 'F', 'G', 'C', 'E7', 'Am', 'Dm', 'G', 'C', 'F', 'Dm', 'E7', 'Am',
          'F', 'G', 'Em', 'Am', 'Dm', 'G', 'C', 'E7']
    # a kayōkyoku tune in the minor yonanuki colour (A B C E F)
    mel = ('o5 e4. c8 o4 b4 a4 | f2 a4 o5 c4 | o4 b4. a8 g+4 b4 | a2. r4 |'
           'o5 c4. o4 a8 f4 a4 | b4. a8 g4 b4 | o5 c4. d8 e4 g4 | e2. r4 |'
           'e4. f8 e4 c4 | d4. e8 f4 a4 | g4. f8 e4 d4 | c2. e4 |'
           'f4. e8 c4 o4 a4 | o5 d4. c8 o4 b4 a4 | g+4 b4 o5 e4 d4 | c2 o4 a2 |'
           'o5 a4. g8 f4 a4 | b4. a8 g4 b4 | o6 c4. o5 b8 g4 e4 | a2. r4 |'
           'f4. e8 d4 f4 | g4. f8 d4 o4 b4 | o5 c4. d8 e4 g4 | e4 d4 o4 b4 g+4 |')
    A = [('loop',)] + S('strings', 68, 58, gate=4, vib=26) + mml(mel)
    B = [('loop',)] + S('organ', 0, 82, gate=6) + rests(8, beats)
    u, l = pads(ch[8:], beats, top=(60, 69), start=64)
    B += S('organ', 30, 82, gate=6) + u
    C = [('loop',)] + S('guitar', 50, 40, gate=2) + figure(ch, beats, [0, 7, 12, 16, 12, 7, 12, 16], 24, 45,
                                                           [0, 7, 12, 15, 12, 7, 12, 15])
    E = [('loop',)] + S('bass', 62, 64, gate=6) + bassline(ch, beats, {192: [('R', 72), ('R', 24), ('5', 72), ('5', 24)]}, low=33)
    D = [('loop',)] + drums('s..ss..s', 24, 24, {'s': ('shaker', 72, 50, 84)})
    F = [('loop',)] + drums('k.s.k.s.', 24, 24, {'k': ('taiko', 67, 36, 64), 's': ('snare', 60, 30, 60)})
    return song('chizuru', 92, beats, [A, B, C, D, E, F], ch, echo=(0x40, 0x20), vib_hz=5.5)


# ------------------------------------------------------------------ 17 omake
def omake():
    beats = 4
    ch = ['C', 'Am', 'Dm7 G7', 'C', 'F', 'Fm', 'C Am', 'D7 G7', 'C', 'Am', 'Dm7 G7', 'C', 'F', 'Fm', 'Dm7 G7', 'C']
    mel = ('o4 g8 r8 o5 c8 r8 e4 c8 r8 | a4. g8 e4 r4 | f8 r8 a8 r8 g8 r8 f8 r8 | e4 c4 r2 |'
           'f8 r8 a8 r8 o6 c4 o5 a8 r8 | a-4. g8 f4 r4 | e8 f8 g8 e8 c4 a4 | f+4 g4 r2 |'
           'o4 g8 r8 o5 c8 r8 e4 c8 r8 | a4. g8 e4 r4 | d8 e8 f8 g8 a8 g8 f8 d8 | c4 e4 g4 r4 |'
           'a4. g8 f4 a4 | a-4. g8 f4 a-4 | g8 r8 f8 r8 d8 r8 o4 b8 r8 | o5 c4 r4 c4 r4 |')
    A = [('loop',)] + S('oboe', 70, 56, gate=4) + mml(mel)
    C = [('loop',)] + S('celesta', 40, 82, gate=2) + figure(ch, beats, [None, 12, None, 16, None, 12, None, 19], 24, 48,
                                                            [None, 12, None, 15, None, 12, None, 19])
    E = [('loop',)] + S('pizz', 84, 64, gate=8) + bassline(ch, beats, {192: [('R', 48), ('L', 48), ('R', 48), ('5', 48)],
                                                                       96: [('R', 48), ('5', 48)]}, low=33)
    D = [('loop',)] + drums('w.w.w.ww', 16, 24, {'w': ('wood', 72, 46, 70)})
    F = [('loop',)] + drums('....s...', 16, 24, {'s': ('snare', 60, 44, 60)})
    B = [('loop',)] + S('ep', 40, 84, gate=10) + figure(ch, beats, [None, 16, None, 19], 48, 48, [None, 15, None, 19])
    return song('omake', 132, beats, [A, B, C, D, E, F], ch, echo=(0x28, 0x16))


def songs():
    out = [title(), journey(), inn(), dinner(), night(), legend(), unease(), horror(), chase(), investigate(),
           deduce(), sorrow(), dawn(), badend(), staff(), oyura(), chizuru(), omake()]
    return out
