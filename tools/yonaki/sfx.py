"""Sound effects and ambience of 夜鳴き鐘 (original), played by the driver's two effect slots.

An effect: header (flags: bit 0 echo on; companion effect started on the other slot, 0 none), then
steps (100 Hz ticks):
  ('key', src, pitch, vl, vr, env, ticks)   key on.  src: a sample name, or ('noise', clock 0-31);
                                            env: ('adsr', a, d, sl, sr) or ('gain', byte)
  ('rel', gain, ticks)                      switch to a GAIN mode (exponential decrease $A0|rate ...) and wait
  ('vol', vl, vr, ticks)                    change the volume and wait
  ('slide', delta)                          pitch += delta every tick from now (signed; 0 stops)
  ('pitch', p)                              set the pitch (no key-on)
  ('jump', effect name, step index)         continue at a step of another effect (shared data)
The effect ends after its last step: the voice fades out quickly (GAIN), the slot is free.
Pitch $1000 plays a sample at 32 kHz; the effect samples are 16 kHz, so $0800 plays them as made.
"""
import random

ECHO = 1


def adsr(a, d, sl, sr):
    return ('adsr', a, d, sl, sr)


def gain(g):
    return ('gain', g)


DIRECT = gain(0x7F)


def K(src, pitch, v, ticks, env=DIRECT, pan=0):
    """key step with a volume v and pan -64..64."""
    vl = round(v * min(1.0, (64 - pan) / 64))
    vr = round(v * min(1.0, (64 + pan) / 64))
    return ('key', src, pitch, vl, vr, env, ticks)


def V(v, ticks, pan=0):
    return ('vol', round(v * min(1.0, (64 - pan) / 64)), round(v * min(1.0, (64 + pan) / 64)), ticks)


def wait(v, ticks, pan=0):
    out = []
    while ticks > 0:
        t = min(250, ticks)
        out.append(V(v, t, pan))
        ticks -= t
    return out


def effects():
    """Ordered {name: (flags, companion name or None, steps)}; effect numbers are 1.. in this order."""
    E = {}
    rnd = random.Random(7)

    # --- the bell: the small bronze bell in the rafters, struck once; inharmonic, long decay, echo
    E['bell'] = (ECHO, None, [K('kane', 0x0800, 124, 250, adsr(15, 7, 7, 10), pan=-8)] + wait(124, 550, -8)
                 + [('rel', 0xA0 | 14, 80)])
    E['bell_far'] = (ECHO, None, [K('kane', 0x0790, 40, 250, adsr(13, 7, 7, 10), pan=12)] + wait(40, 400, 12)
                     + [('rel', 0xA0 | 14, 60)])
    # --- thunder: a tearing noise crack (slot A), the rolling rumble (slot B)
    crack = [K(('noise', 31), 0, 120, 2), V(70, 1), K(('noise', 30), 0, 115, 3), V(60, 1),
             K(('noise', 31), 0, 100, 2), K(('noise', 29), 0, 105, 4, adsr(15, 3, 2, 18)),
             K(('noise', 27), 0, 90, 20, adsr(15, 3, 3, 13)), K(('noise', 25), 0, 70, 30, adsr(15, 2, 4, 12)),
             ('rel', 0xA0 | 13, 70)]
    E['thunder'] = (0, 'thunder_roll', crack)
    E['thunder_roll'] = (0, None, [K('rumble', 0x0240, 100, 30, adsr(11, 7, 7, 0)), ('slide', -1), V(115, 40),
                                   V(90, 40), V(105, 50), V(70, 60), ('rel', 0xA0 | 14, 120)])
    E['rumble'] = (0, None, [K('rumble', 0x01C0, 40, 60, adsr(6, 7, 7, 0)), ('slide', -1), V(58, 60), V(44, 50),
                             V(52, 60), V(34, 60), ('rel', 0xA0 | 13, 100)])
    # --- doors
    rattle = []
    for i in range(8):
        rattle.append(K('knock', 0x0600 + rnd.randrange(0, 0x380), 26 + rnd.randrange(0, 18), 6 + rnd.randrange(0, 3),
                        adsr(15, 5, 1, 20), pan=-10))
    E['door'] = (0, 'door_run', rattle + [K('knock', 0x0700, 80, 30, adsr(15, 4, 2, 16), pan=-10)])
    E['door_run'] = (0, None, [K('scrape', 0x0500, 30, 8, adsr(10, 7, 7, 0), pan=-10), ('slide', 3), V(36, 30, -10),
                               V(26, 16, -10), ('rel', 0xA0 | 22, 6)])
    E['door_bang'] = (ECHO, 'door_body', [K('knock', 0x0480, 120, 40, adsr(15, 4, 2, 15))])
    E['door_body'] = (0, None, [K('taiko', 0x0500, 100, 40)])
    # --- footsteps on old boards: thuds and a creak now and then
    st = []
    for i in range(5):
        p = -24 + 12 * i
        st.append(K('knock', 0x0300 + rnd.randrange(0, 0x60), 70 - 4 * i, 8, adsr(15, 5, 1, 18), pan=p))
        if i in (1, 3):
            st += [K('creak', 0x0380, 30, 3, adsr(11, 7, 7, 0), pan=p), ('slide', 12), V(36, 10, p), V(24, 10, p),
                   ('slide', -8), V(14, 8, p), ('rel', 0xA0 | 22, 18), ('slide', 0)]
        else:
            st.append(('rel', 0xA0 | 20, 41))
    E['steps'] = (0, None, st)
    E['knock'] = (0, None, [K('knock', 0x0640, 110, 16, adsr(15, 4, 1, 16)), K('knock', 0x0620, 105, 16, adsr(15, 4, 1, 16)),
                            K('knock', 0x0640, 110, 40, adsr(15, 4, 1, 16))])
    # --- water
    E['water'] = (0, 'water_drops', [K(('noise', 29), 0, 90, 4, adsr(15, 4, 4, 17)), K(('noise', 28), 0, 70, 50,
                                                                                      adsr(15, 2, 3, 16))])
    dr = []
    for i in range(10):
        dr.append(K(f'drop{rnd.randrange(0, 3)}', 0x0600 + rnd.randrange(0, 0x600), 70 - 6 * i, 3 + rnd.randrange(0, 6),
                    pan=rnd.randrange(-30, 30)))
    E['water_drops'] = (0, None, [V(0, 6)] + dr)
    E['drip'] = (ECHO, None, [K('plink', 0x0800, 110, 80, pan=-6), K('plink', 0x0860, 46, 70, pan=-6)])
    # --- heartbeat: lub-dub at 80 bpm, four beats
    hb = []
    for i in range(4):
        hb += [K('taiko', 0x0250, 120, 16), K('taiko', 0x0290, 88, 59)]
    E['heart'] = (0, None, hb)
    # --- the shock stinger: a dissonant cluster with a boom under it
    E['shock'] = (ECHO, 'shock_boom', [K('stab', 0x1000, 120, 60, adsr(15, 3, 3, 11)), ('rel', 0xA0 | 15, 100)])
    E['shock_boom'] = (ECHO, None, [K('taiko', 0x0300, 127, 80)])
    # --- breaking glass
    gl = [K(('noise', 31), 0, 90, 3, adsr(15, 5, 1, 20))]
    for i in range(7):
        gl.append(K('tink', 0x0800 + rnd.randrange(0, 0x900), 70 - 7 * i, 3 + rnd.randrange(0, 6), pan=rnd.randrange(-40, 40)))
    gl.append(('rel', 0xA0 | 18, 30))
    E['glass'] = (ECHO, 'glass_b', gl)
    gb = [V(0, 2)]
    for i in range(6):
        gb.append(K('tink', 0x0900 + rnd.randrange(0, 0x900), 50 - 6 * i, 4 + rnd.randrange(0, 7), pan=rnd.randrange(-40, 40)))
    E['glass_b'] = (ECHO, None, gb)
    # --- the pendulum clock: a gong rod struck N times (clock1-clock12 share one chain)
    strikes = []
    for i in range(12):
        strikes += [K('kane', 0x0400, 70, 150, adsr(15, 6, 5, 13))]
    strikes.append(('rel', 0xA0 | 13, 150))
    E['clock12'] = (ECHO, None, strikes)
    for n in range(1, 12):
        E[f'clock{n}'] = (ECHO, None, [('jump', 'clock12', 12 - n)])
    E['clock'] = (ECHO, None, [('jump', 'clock12', 9)])
    tk = []
    for i in range(6):
        tk.append(K('wood', 0x1100 if i % 2 == 0 else 0x0E80, 80 if i % 2 == 0 else 66, 50, pan=-6))
    E['tick'] = (0, None, tk)
    # --- a match: the strike, the flare
    E['match'] = (0, None, [K(('noise', 30), 0, 50, 3, adsr(13, 6, 2, 20)), K(('noise', 31), 0, 64, 8, adsr(15, 5, 2, 19)),
                            K(('noise', 26), 0, 50, 30, adsr(9, 3, 4, 16)), V(36, 20), ('rel', 0xA0 | 18, 20)])
    # --- instant camera: shutter, then the film eject whirr
    E['camera'] = (0, 'camera_gear', [K('knock', 0x0E00, 80, 3, adsr(15, 6, 1, 22)), K('knock', 0x0B80, 70, 12, adsr(15, 6, 1, 22)),
                                      K('square', 0x0260, 0, 1), V(14, 4), ('slide', 2), V(18, 10), ('slide', 0),
                                      V(20, 50), ('slide', -3), V(14, 10), ('rel', 0xA0 | 24, 4)])
    E['camera_gear'] = (0, None, [V(0, 16), K('scrape', 0x0D00, 14, 70, adsr(12, 7, 7, 0)), ('rel', 0xA0 | 24, 4)])
    # --- the office radio: static that swells and cuts, a heterodyne whistle under it
    rs = [K(('noise', 31), 0, 30, 3, adsr(12, 7, 7, 0))]
    for i in range(14):
        rs.append(V(20 + rnd.randrange(0, 40), 3 + rnd.randrange(0, 3)))
    rs += [K('knock', 0x1000, 40, 4, adsr(15, 6, 1, 22))]
    E['radio'] = (0, 'radio_tone', rs)
    E['radio_tone'] = (0, None, [K('sine', 0x2400, 8, 4, adsr(12, 7, 7, 0)), ('slide', -40), V(10, 30), V(6, 20),
                                 ('rel', 0xA0 | 26, 2)])
    # --- a body falling: the heavy hit and a small bounce
    E['thud'] = (0, 'thud_b', [K('taiko', 0x0260, 127, 14), K('taiko', 0x02C0, 60, 40)])
    E['thud_b'] = (0, None, [K('knock', 0x0260, 100, 14, adsr(15, 4, 1, 16)), K('knock', 0x02A0, 40, 30, adsr(15, 4, 1, 16))])
    # --- one gust of wind: a moaning resonance that swells and falls away
    E['wind'] = (0, None, [K('gust', 0x0500, 10, 10, adsr(5, 7, 7, 0), pan=-20), ('slide', 3), V(24, 30, -10), V(36, 30, 0),
                           ('slide', -2), V(30, 40, 10), V(18, 40, 20), ('slide', -4), V(8, 30, 20), ('rel', 0xA0 | 18, 20)])
    return E


# names the scenario uses (in this order the effect numbers 1..); helpers (companions) follow
PUBLIC = ['bell', 'bell_far', 'thunder', 'rumble', 'door', 'door_bang', 'steps', 'knock', 'water', 'drip', 'heart',
          'shock', 'glass', 'clock', 'tick', 'match', 'camera', 'radio', 'thud', 'wind'] + [f'clock{n}' for n in range(1, 13)]

# ambience: AMB 0 rain, 1 storm (rain + a distant rumble every 6-16 s on slot A)
AMBIENCE = ['rain', 'storm']


def amb_tables(src_index, rumble_number):
    """Droplet tables for the driver (random index -> value)."""
    return dict(
        amb_level=[0x1E, 0x26],
        # ticks to the next droplet (10 ms each): mostly 1-3, a few longer gaps
        amb_gap=[1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 4, 5, 6],
        amb_src=[src_index['drop0'], src_index['drop0'], src_index['drop1'], src_index['drop1'], src_index['drop0'],
                 src_index['drop1'], src_index['drop2'], src_index['drop3']],
        amb_pitch=[0x0580, 0x0600, 0x0680, 0x06C0, 0x0700, 0x0740, 0x0780, 0x07C0,
                   0x0800, 0x0840, 0x0880, 0x0900, 0x0980, 0x0A00, 0x0B00, 0x0C00],
        # loudness: mostly faint, a few near drops
        amb_vol=[40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 124, 136, 150, 170, 200, 250],
        amb_pan=[128, 140, 150, 160, 170, 180, 190, 200, 210, 220, 230, 240, 250, 255, 200, 160],
        rumble_sfx=rumble_number)


def compile_effects(src_index, base):
    """-> (blob for address `base`, pointer per effect number (1..), names in order)."""
    E = effects()
    names = PUBLIC + [n for n in E if n not in PUBLIC]
    assert set(names) == set(E), set(E) ^ set(names)
    number = {n: i + 1 for i, n in enumerate(names)}
    blob = bytearray()
    ptr, step_addr, jumps = {}, {}, []
    for n in names:
        flags, comp, steps = E[n]
        ptr[n] = base + len(blob)
        blob += bytes((flags, number[comp] if comp else 0))
        step_addr[n] = []
        for s in steps:
            step_addr[n].append(base + len(blob))
            k = s[0]
            if k == 'key':
                _, src, pitch, vl, vr, env, ticks = s
                assert 1 <= ticks <= 255 and 0 <= pitch <= 0x3FFF and -128 <= vl <= 127 and -128 <= vr <= 127, (n, s)
                if isinstance(src, tuple):
                    sb = 0x80 | src[1]
                else:
                    sb = src_index[src]
                    assert sb < 0x80
                if env[0] == 'adsr':
                    a1, a2 = 0x80 | env[2] << 4 | env[1], env[3] << 5 | env[4]
                else:
                    a1, a2 = 0x00, env[1]
                blob += bytes((sb, pitch & 0xFF, pitch >> 8, vl & 0xFF, vr & 0xFF, a1, a2, ticks))
            elif k == 'rel':
                assert 1 <= s[2] <= 255
                blob += bytes((0xFE, s[1], s[2]))
            elif k == 'vol':
                assert 1 <= s[3] <= 255
                blob += bytes((0xFD, s[1] & 0xFF, s[2] & 0xFF, s[3]))
            elif k == 'slide':
                blob += bytes((0xFC, s[1] & 0xFF, (s[1] >> 8) & 0xFF))
            elif k == 'pitch':
                blob += bytes((0xFB, s[1] & 0xFF, s[1] >> 8))
            elif k == 'jump':
                jumps.append((len(blob) + 1, s[1], s[2]))
                blob += bytes((0xF9, 0, 0))
            else:
                raise ValueError((n, s))
        if not steps or steps[-1][0] != 'jump':
            blob.append(0xFF)
    for ofs, target, idx in jumps:
        a = step_addr[target][idx]
        blob[ofs:ofs + 2] = bytes((a & 0xFF, a >> 8))
    return bytes(blob), [ptr[n] for n in names], names, number


def durations():
    """Approximate length of each effect in seconds (for the tests): the sum of the step ticks."""
    E = effects()
    out = {}

    def run(steps, guard=0):
        t = 0
        for s in steps:
            if s[0] == 'key':
                t += s[6]
            elif s[0] == 'rel':
                t += s[2]
            elif s[0] == 'vol':
                t += s[3]
            elif s[0] == 'jump' and guard < 3:
                t += run(E[s[1]][2][s[2]:], guard + 1)
        return t
    for n, (f, c, steps) in E.items():
        t = run(steps)
        if c:
            t = max(t, run(E[c][2]))
        out[n] = t / 100
    return out
