"""Scores of 潮鳴りの密室 (original compositions), compiled by tools/adv/music.py.

Song numbers are the driver's ($40 + n plays song n):
  0 opening    D minor, 80 bpm.  2 bars of bell and strings (the notice), 8 bars of harp under the four
               prologue pictures (one picture every 2 bars), 2 bars of timpani roll on black, then the
               main theme from bar 13 (the title appears there) -- the loop is bars 13-28.
  1 title      the same song from bar 13 (the title after the ending, or a skipped prologue)
  2 investigate  A minor, 96 bpm: a wood-block clock, bass ostinato, clarinet (the warehouse,
               the signal station, the police station)
  3 sea        D dorian, 3/4, 63 bpm: harp, pad, a buoy bell, flute (the pier, the lighthouse)
  4 cafe       F major, 100 bpm: electric-piano comping, bossa bass, shaker, flute (喫茶「浮標」)
  5 deduce     D minor, 72 bpm: a pedal with a falling inner line (D C# C B), heartbeat timpani, oboe
  6 dawn       D major, 76 bpm: the main theme in major (the finale and the ending)
Chords are written per bar ("Gm A" splits the bar); the accompaniment is generated from them below.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from music import mml, TPQ, MusicError

SONG_IDS = dict(opening=0, title=1, investigate=2, sea=3, cafe=4, deduce=5, dawn=6)

PC = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)
QUAL = {'': (0, 4, 7), 'm': (0, 3, 7), '7': (0, 4, 7, 10), 'm7': (0, 3, 7, 10), 'maj7': (0, 4, 7, 11),
        'sus4': (0, 5, 7), '7sus4': (0, 5, 7, 10), 'm7b5': (0, 3, 6, 10), 'm6': (0, 3, 7, 9),
        'mM7': (0, 3, 7, 11), 'm9': (0, 3, 7, 10, 14), '6': (0, 4, 7, 9)}


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
    """'Dm' / 'Gm A' per bar -> [(bar index, chord, ticks)]."""
    out = []
    for bi, b in enumerate(bars):
        parts = b.split()
        t = TPQ * beats // len(parts)
        for p in parts:
            out.append((bi, p, t))
    return out


def tones(name, low):
    """Chord tones ascending from the lowest root >= low (MIDI)."""
    r, q = chord(name)
    root = low + (r - low) % 12
    return sorted(root + i + 12 * k for k in range(4) for i in q)


def with_bars(seg_events, beats):
    """Insert bar lines after each bar's events: seg_events = [(bar, [events])]."""
    out, last = [], 0
    for bi, ev in seg_events:
        if bi != last:
            out.append(('bar',))
            last = bi
        out += ev
    out.append(('bar',))
    return out


def arp(bars, beats, pattern, step, low=45):
    """Broken chords: pattern = tone indices (None = rest) at `step` ticks each, restarting per chord."""
    se = []
    for bi, name, t in segments(bars, beats):
        ts = tones(name, low)
        ev = []
        for k in range(t // step):
            i = pattern[k % len(pattern)]
            ev.append(('rest', step) if i is None else ('note', ts[i], step))
        se.append((bi, ev))
    return with_bars(se, beats)


def bassline(bars, beats, rhythm, low=31):
    """rhythm: {segment ticks: [(token, ticks)]}; tokens R root, 5 fifth, O octave, r rest."""
    se = []
    for bi, name, t in segments(bars, beats):
        r, q = chord(name)
        root = low + (r - low) % 12
        fifth = root + 7 if 7 in q else root + (6 if 6 in q else 7)
        ev = []
        for tok, d in rhythm[t]:
            ev.append(('rest', d) if tok == 'r' else ('note', {'R': root, '5': fifth, 'O': root + 12}[tok], d))
        se.append((bi, ev))
    return with_bars(se, beats)


def pads(bars, beats, top=(65, 76), start=69):
    """Two sustained voices per chord with small moves: upper in `top`, lower a chord tone 3-9 below."""
    up, lo = [], []
    prev = start
    for bi, name, t in segments(bars, beats):
        ts = [x for x in tones(name, 40) if top[0] <= x <= top[1]]
        u = min(ts, key=lambda x: (abs(x - prev), x))
        below = [x for x in tones(name, 40) if 3 <= u - x <= 9]
        l = max(below)
        prev = u
        up.append((bi, [('note', u, t)]))
        lo.append((bi, [('note', l, t)]))
    return with_bars(up, beats), with_bars(lo, beats)


def shells(bars, beats, rhythm):
    """Electric-piano comping: 3rd and 7th (6th) of each chord, one voice each, on `rhythm`."""
    a, b = [], []
    for bi, name, t in segments(bars, beats):
        r, q = chord(name)
        third = [i for i in q if i in (3, 4, 5)][0]
        sev = [i for i in q if i in (9, 10, 11)]
        sev = sev[0] if sev else 7
        lo3 = 53 + (r + third - 53) % 12
        hi7 = lo3 + (r + sev - lo3) % 12
        ea, eb = [], []
        for tok, d in rhythm[t]:
            if tok == 'x':
                ea.append(('note', hi7, d))
                eb.append(('note', lo3, d))
            else:
                ea.append(('rest', d))
                eb.append(('rest', d))
        a.append((bi, ea))
        b.append((bi, eb))
    return with_bars(a, beats), with_bars(b, beats)


def rests(n, beats):
    out = []
    for _ in range(n):
        out += [('rest', TPQ * beats), ('bar',)]
    return out


def ramp(events, v0, v1, pan=64):
    """Volume from v0 to v1 over the notes of `events` (a crescendo / fade)."""
    notes = [i for i, e in enumerate(events) if e[0] in ('note', 'rest')]
    out = []
    k = 0
    for i, e in enumerate(events):
        if e[0] in ('note', 'rest'):
            v = round(v0 + (v1 - v0) * k / max(1, len(notes) - 1))
            out.append(('vol', v, pan))
            k += 1
        out.append(e)
    return out


def S(inst, vol, pan=64, gate=3, vib=0):
    return [('inst', inst), ('vol', vol, pan), ('gate', gate), ('vib', vib)]


# ------------------------------------------------------------------ 0/1 opening + title
def opening():
    beats = 4
    intro = ['Dm', 'Dm']
    pro = ['Dm', 'Bb', 'Gm', 'A', 'Dm', 'Bb', 'Gm', 'A7']
    build = ['Bb', 'A7']
    themeA = ['Dm', 'Bb', 'Gm', 'A', 'Dm', 'F', 'Gm A', 'Dm']
    themeB = ['Bb', 'C', 'Am', 'Dm', 'Gm', 'Bb', 'Em7b5', 'A7']
    theme = themeA + themeB
    # A: lead
    A = S('flute', 0, 60, gate=4, vib=14) + rests(6, beats)
    A += S('flute', 70, 60, gate=4, vib=14) + mml('o5 d2 c4 o4 a4 | b-2. a8 g8 | g2 b-4 o5 d4 | c+1 |')
    A += mml('r1 | r2. o4 f8 g8 |')
    A += [('loop',)] + S('flute', 80, 60, gate=4, vib=16)
    A += mml('o4 a4. g8 f4 e4 | d2 f4 b-4 | a4. g8 b-4 o5 d4 | c+2. o4 a4 |'
             'o5 d4. c8 o4 a4 f4 | o5 c4. o4 b-8 a4 g4 | b-4 g4 a4 o5 c+4 | d1 |')
    A += S('oboe', 74, 60, gate=4, vib=14)
    A += mml('o5 f4. e8 d4 o4 b-4 | o5 e4. d8 c4 o4 g4 | o5 c4. o4 b-8 a4 e4 | f2 a2 |'
             'b-4. a8 g4 o5 d4 | d4. c8 o4 b-4 o5 f4 | e2. f8 e8 | c+2 o4 a2 |')
    # B, C: strings
    u1, l1 = pads(intro + pro + build, beats)
    u2, l2 = pads(theme, beats)
    B = S('slowstr', 30, 76, gate=6) + ramp(u1[:4], 30, 52, 76) + [('vol', 56, 76)] + u1[4:-4]
    B += ramp(u1[-4:], 60, 80, 76)
    B += [('loop',)] + S('strings', 64, 76, gate=6) + u2
    C = S('slowstr', 30, 52, gate=6) + ramp(l1[:4], 30, 50, 52) + [('vol', 52, 52)] + l1[4:-4]
    C += ramp(l1[-4:], 56, 76, 52)
    C += [('loop',)] + S('strings', 58, 52, gate=6) + l2
    # D: harp under the prologue, a rising run in the build, electric piano in the theme
    D = S('harp', 0, 40) + rests(2, beats)
    D += S('harp', 62, 40, gate=2) + arp(pro, beats, [0, 2, 3, 4, 5, 4, 3, 2], 24)
    run = [0, 1, 2, 3, 4, 5, 6, 7, 8, 7, 6, 5, 4, 3, 2, 1]
    D += ramp(arp(build, beats, run, 12), 50, 78, 40)
    D += [('loop',)] + S('ep', 58, 40, gate=2) + arp(theme, beats, [0, 2, 3, 4, 5, 4, 3, 2], 24)
    # E: bass
    E = S('bass', 70) + bassline(intro, beats, {192: [('R', 192)]})
    E += S('bass', 80, gate=4) + bassline(pro, beats, {192: [('R', 96), ('R', 96)]})
    E += bassline(build, beats, {192: [('R', 144), ('R', 24), ('R', 24)]})
    E += [('loop',)] + S('bass', 88, gate=4)
    E += bassline(theme, beats, {192: [('R', 72), ('R', 24), ('5', 48), ('R', 48)], 96: [('R', 72), ('R', 24)]})
    # F: a distant bell, timpani on each picture, a roll into the title, then a high sparkle
    F = S('bell', 46, 88, gate=0) + mml('o5 a2. r4 | f2 e2 |')
    F += S('timp', 82, 64, gate=0)
    for root in ('d', 'g', 'd', 'g'):
        o = 'o2' if root == 'd' else 'o1'
        F += mml(f'{o} {root}2 r2 | r1 |')
    roll = mml('o1 b-16 b-16 b-16 b-16 b-16 b-16 b-16 b-16 b-16 b-16 b-16 b-16 b-16 b-16 b-16 b-16 |'
               'o1 a16 a16 a16 a16 a16 a16 a16 a16 a16 a16 a16 a16 a16 a16 a16 a16 |')
    F += ramp(roll, 30, 96)
    F += [('loop',)] + S('timp', 80, 64, gate=0) + mml('o2 d2 r2 |') + S('bell', 34, 88, gate=0)
    sp = []
    for bi, name, t in segments(theme[1:], beats):
        ts = [x for x in tones(name, 60) if 84 <= x <= 96]
        n = ts[0]
        sp.append((bi, [('rest', t // 4), ('note', n, t // 8), ('rest', t // 8)] * 2))
    F += with_bars(sp, beats)
    return ('opening', 80, beats, [A, B, C, D, E, F], {'title': 'loop'})


# ------------------------------------------------------------------ 2 investigate
def investigate():
    beats = 4
    bars = ['Am', 'Am', 'F', 'E', 'Am', 'Am', 'Dm', 'E', 'F', 'G', 'Em', 'Am', 'Dm', 'Bb', 'E', 'E7']
    A = [('loop',)] + S('clarinet', 74, 58, gate=4, vib=12)
    A += mml('r1 | r1 | o5 c4. o4 b8 a4 e4 | g+2. r4 | o4 a8 b8 o5 c8 d8 e4 d8 c8 | o4 b4 a4 g+4 a4 |'
             'o5 f4. e8 d4 c4 | o4 b2 g+4 e4 |'
             'a4. b8 o5 c4 d4 | d4. c8 o4 b4 g4 | b4. a8 g4 e4 | a2. r4 | o5 d4. e8 f4 a4 |'
             'f4. e8 d4 o4 b-4 | g+2 b4 o5 d4 | e2 r2 |')
    u, l = pads(bars, beats, top=(64, 74), start=67)
    B = [('loop',)] + S('strings', 46, 80, gate=6) + u
    C = [('loop',)] + S('strings', 42, 48, gate=6) + l
    D = [('loop',)] + S('ep', 52, 36, gate=10) + arp(bars, beats, [None, 3, None, 4, None, 5, None, 4], 24, low=48)
    E = [('loop',)] + S('bass', 86, gate=10)
    E += bassline(bars, beats, {192: [('R', 24), ('R', 24), ('O', 24), ('R', 24), ('5', 24), ('R', 24), ('O', 24), ('5', 24)]},
                  low=33)
    F = [('loop',)] + S('wood', 36, 70, gate=0)
    for _ in bars:
        F += [('vol', 34, 70)] + mml('o3 a4') + [('vol', 24, 58)] + mml('o3 e4') + \
             [('vol', 34, 70)] + mml('o3 a4') + [('vol', 24, 58)] + mml('o3 e4 |')
    return ('investigate', 96, beats, [A, B, C, D, E, F], {})


# ------------------------------------------------------------------ 3 sea
def sea():
    beats = 3
    bars = ['Dm9', 'Dm9', 'Bbmaj7', 'Bbmaj7', 'Gm7', 'Gm7', 'Asus4', 'A',
            'Dm9', 'Dm9', 'Fmaj7', 'C', 'Bbmaj7', 'Gm7', 'Asus4', 'A7']
    A = [('loop',)] + S('flute', 0, 60, gate=4, vib=16) + rests(8, beats) + S('flute', 70, 60, gate=4, vib=16)
    A += mml('o5 e2. | d4 c4 o4 a4 | a2 o5 c4 | o4 g2. | o5 d2 c4 | o4 b-4 a4 g4 | a2. | a4 g4 e4 |')
    u, l = pads(bars, beats, top=(62, 72), start=65)
    B = [('loop',)] + S('pad', 44, 78, gate=8) + u
    C = [('loop',)] + S('pad', 40, 50, gate=8) + l
    D = [('loop',)] + S('harp', 56, 44, gate=2) + arp(bars, beats, [0, 2, 4, 5, 4, 2], 24, low=45)
    E = [('loop',)] + S('bass', 66, gate=6) + bassline(bars, beats, {144: [('R', 144)]}, low=33)
    F = [('loop',)] + S('bell', 30, 96, gate=0)
    for i in range(4):
        F += mml('o5 a2. | r2. | r2. | r2. |' if i % 2 == 0 else 'o5 d2. | r2. | r2. | r2. |')
    return ('sea', 63, beats, [A, B, C, D, E, F], {})


# ------------------------------------------------------------------ 4 cafe
def cafe():
    beats = 4
    bars = ['Fmaj7', 'Dm7', 'Gm7', 'C7', 'Fmaj7', 'Dm7', 'Gm7', 'C7',
            'Bbmaj7', 'Am7', 'Gm7', 'C7', 'Am7', 'D7', 'Gm7', 'C7']
    A = [('loop',)] + S('flute', 70, 60, gate=4, vib=14)
    A += mml('o5 e4. c8 o4 a4 g4 | a2 f4 a4 | o5 d4. c8 o4 b-4 a4 | g2. r4 |'
             'o5 e4. f8 g4 e4 | d4 c4 o4 a4 o5 c4 | o4 b-4 a4 g4 f4 | e2 g2 |'
             'f4. a8 o5 d4 c4 | c4 o4 b4 a4 g4 | b-4. a8 g4 f4 | e4 g4 b-4 o5 d4 |'
             'c2 e4 d4 | c4 o4 a4 f+4 a4 | g4. a8 b-4 o5 d4 | c2 r2 |')
    comp = {192: [('x', 36), ('r', 12), ('x', 24), ('r', 24), ('x', 36), ('r', 12), ('x', 24), ('r', 24)]}
    hi, lo = shells(bars, beats, comp)
    B = [('loop',)] + S('ep', 50, 80, gate=4) + hi
    C = [('loop',)] + S('ep', 46, 48, gate=4) + lo
    E = [('loop',)] + S('bass', 84, gate=6) + bassline(bars, beats, {192: [('R', 72), ('5', 24), ('5', 72), ('R', 24)]}, low=33)
    F = [('loop',)] + S('shaker', 30, 76, gate=0)
    for _ in bars:
        for k in range(8):
            F += [('vol', 34 if k % 2 == 0 else 20, 76)] + mml('o4 c8')
        F.append(('bar',))
    D = [('loop',)] + S('bell', 0, 30, gate=0) + rests(16, beats)
    return ('cafe', 100, beats, [A, B, C, D, E, F], {})


# ------------------------------------------------------------------ 5 deduce
def deduce():
    beats = 4
    bars = ['Dm', 'DmM7', 'Dm7', 'Dm6', 'Bbmaj7', 'Bb', 'Asus4', 'A',
            'Dm', 'DmM7', 'Dm7', 'Dm6', 'Gm', 'Gm6', 'A7sus4', 'A7']
    A = [('loop',)] + S('oboe', 0, 60, gate=4, vib=14) + rests(8, beats) + S('oboe', 72, 60, gate=4, vib=14)
    A += mml('o5 a2. g8 f8 | e2. f8 e8 | d2 c4 o4 a4 | b2. r4 | o5 d4. e8 f4 d4 | e2 g4 e4 | d2 e4 d4 | c+1 |')
    B = [('loop',)] + S('strings', 52, 78, gate=0)
    B += mml('o5 d1 | c+1 | c1 | o4 b1 | a1 | b-1 | o5 d1 | c+1 | d1 | c+1 | c1 | o4 b1 | b-1 | o5 e1 | d1 | c+1 |')
    C = [('loop',)] + S('strings', 48, 50, gate=0)
    C += mml('o4 f1 | f1 | f1 | f1 | f1 | f1 | e1 | e1 | f1 | f1 | f1 | f1 | d1 | d1 | g1 | g1 |')
    D = [('loop',)] + S('harp', 40, 36, gate=2) + arp(bars, beats, [2, 4, 3, 4], 12, low=50)
    roots = 'd d d d b- b- a a d d d d g g a a'.split()
    E = [('loop',)] + S('bass', 82, gate=10)
    for r in roots:
        o = 'o2' if r == 'd' else 'o1'
        E += mml(f'{o} ' + f'{r}8 ' * 8 + '|')
    F = [('loop',)] + S('timp', 64, 64, gate=0)
    for r in roots:
        o = 'o2' if r == 'd' else 'o1'
        F += [('vol', 70, 64)] + mml(f'{o} {r}8') + [('vol', 46, 64)] + mml(f'{r}8 r4 r2 |')
    return ('deduce', 72, beats, [A, B, C, D, E, F], {})


# ------------------------------------------------------------------ 6 dawn
def dawn():
    beats = 4
    bars = ['D', 'Bm', 'G', 'A', 'D', 'F#m', 'G A', 'D', 'G', 'A', 'F#m', 'Bm', 'Em7', 'G', 'A7sus4', 'A7']
    A = [('loop',)] + S('flute', 76, 60, gate=4, vib=16)
    A += mml('o4 a4. g8 f+4 e4 | d2 f+4 b4 | a4. g8 b4 o5 d4 | c+2. o4 a4 |'
             'o5 d4. c+8 o4 a4 f+4 | o5 c+4. o4 b8 a4 f+4 | g4 b4 a4 o5 c+4 | d1 |'
             'd4. e8 d4 o4 b4 | o5 c+4. d8 e4 c+4 | o4 a4. b8 o5 c+4 o4 a4 | b2 o5 d2 |'
             'e4. f+8 g4 e4 | g4. f+8 e4 d4 | e2 d2 | c+2 e2 |')
    u, l = pads(bars, beats, top=(66, 76), start=69)
    B = [('loop',)] + S('strings', 64, 78, gate=6) + u
    C = [('loop',)] + S('strings', 58, 50, gate=6) + l
    D = [('loop',)] + S('harp', 56, 40, gate=2) + arp(bars, beats, [0, 2, 3, 4, 5, 4, 3, 2], 24, low=45)
    E = [('loop',)] + S('bass', 80, gate=4) + bassline(bars, beats, {192: [('R', 96), ('5', 96)], 96: [('R', 96)]}, low=33)
    F = [('loop',)] + S('bell', 32, 90, gate=0)
    sp = []
    for bi, name, t in segments(bars, beats):
        ts = [x for x in tones(name, 60) if 84 <= x <= 96]
        sp.append((bi, [('rest', t // 2), ('note', ts[0], t // 4), ('rest', t // 4)]))
    F += with_bars(sp, beats)
    return ('dawn', 76, beats, [A, B, C, D, E, F], {})


def songs():
    out = [opening(), investigate(), sea(), cafe(), deduce(), dawn()]
    return out
