"""SPC700 sound driver of 潮鳴りの密室 (original), assembled here into build/adv/spc.bin.

The image is loaded at $0200 by the IPL and started there.  Voice 0 plays short effects, voice 1 speech
blips, voices 2-7 the music (tools/adv/music.py, scores in tools/adv/songs.py) with the echo (reverb)
on the music voices only.
CPU protocol: write the command to port 0, then change port 1 (any new value) -- one per frame.
  1-8 effects (cursor, ok, cancel, clue, wrong, page, right, move), $30 mute (master and echo volume 0),
  $31 unmute, $40+n play song n from its start, $60 fade the music out (about a second), $61 stop it,
  $62 duck the music (-10 dB, under the messages and their speech blips), $63 back to full.
  The driver writes $5A to port 0 when it is ready.
Music state for the CPU: port 2 = song number + 1 while a song plays (0 none), port 3 = beats since the
song started (48 ticks; wraps at 256) -- the opening follows the music with it.
Speech mailbox (separate from the commands, only the latest one counts): write the blip byte to port 2,
then change port 3.  Blip byte: bits 0-3 voice (data/adv/voices.txt, tools/adv/voice.py), bit 7 a phrase
starts (the pitch contour restarts).  Ignored while muted.  A blip is a one-shot sample with its own
envelope: it ends by itself (no key-off), so voice 1 never touches KOF.
Every key-on is followed by a short wait (more than 64 SPC700 cycles): the DSP reads KON every other
sample, so a second KON write right after the first would replace it (an effect and a blip together).
The music keys its notes on together, once per music tick.  Notes end by switching the voice from its
ADSR envelope to an exponential GAIN decrease (a soft release that the echo carries), never by KOF.
Timer 0 ticks at 100 Hz (8 kHz / 80) for the effects; timer 1 is the music tempo (per song).
Echo: buffer $D000-$F7FF (EDL 5, 80 ms), cleared before the first write; writes start 300 ms after boot.
"""
import math, pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

ORG = 0x0200
DIR_SLOTS = 32                   # sample directory entries (4 bytes each), on a page after the code
ECHO_PAGE, ECHO_EDL = 0xD0, 5    # echo buffer $D000, 5 x 2 KiB
ECHO_FIR = (0x0C, 0x21, 0x2B, 0x2B, 0x13, 0xFE, 0xF3, 0xF9)   # a gentle low-pass on the echo
ECHO_FEEDBACK = 0x38
ECHO_VOL = 0x1C
MASTER_VOL = 0x40
VIB_SPEED, VIB_DELAY = 16, 12
NCH = 6

# zero page of the driver
LAST, PTR, PTRH, TIMER, AMB_ON, AMB_PHASE, AMB_TICK = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06
LAST3, VSTEP, MUTED, VTMP = 0x07, 0x08, 0x09, 0x0A
SONG_ON, FADE, FADING, BEAT, TICKC, KONACC, CP, TL, VBASE, ECHOWAIT, NT1, SONGNO, TMP, FTARGET = (
    0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x13, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A)
DUCK_LEVEL = 0x50                # music volume x 80/256 (-10 dB) under the messages
# per music channel (8 bytes each, X = channel 0-5)
ON, PTRL, PTRHI, DUR, GATE, ADSR1, ADSR2, REL, VOLL, VOLR, PL, PH, VDEP, VPH, VDLY, KEYED = (
    0x20 + 8 * i for i in range(16))


class Asm:
    def __init__(self, org):
        self.org = org
        self.code = bytearray()
        self.labels = {}
        self.fix = []            # (offset, label, kind)

    def here(self):
        return self.org + len(self.code)

    def label(self, name):
        assert name not in self.labels, name
        self.labels[name] = self.here()

    def b(self, *v):
        self.code += bytes(v)

    def rel(self, op, label):
        self.b(op, 0)
        self.fix.append((len(self.code) - 1, label, 'rel'))

    def absop(self, op, label, add=0):
        self.b(op, 0, 0)
        self.fix.append((len(self.code) - 2, (label, add), 'abs'))

    # instructions used by the driver
    def mov_dp_imm(self, dp, v): self.b(0x8F, v, dp)
    def mov_dp_a(self, dp): self.b(0xC4, dp)
    def mov_a_dp(self, dp): self.b(0xE4, dp)
    def mov_a_imm(self, v): self.b(0xE8, v)
    def mov_x_a(self): self.b(0x5D)
    def mov_a_x(self): self.b(0x7D)
    def mov_y_imm(self, v): self.b(0x8D, v)
    def mov_a_ind_y(self, dp): self.b(0xF7, dp)          # MOV A,[dp]+Y
    def mov_a_absx(self, label, add=0): self.absop(0xF5, label, add)
    def cmp_a_imm(self, v): self.b(0x68, v)
    def cmp_a_dp(self, dp): self.b(0x64, dp)
    def adc_a_dp(self, dp): self.b(0x84, dp)
    def adc_a_imm(self, v): self.b(0x88, v)
    def and_a_imm(self, v): self.b(0x28, v)
    def asl_a(self): self.b(0x1C)
    def bpl(self, l): self.rel(0x10, l)
    def bcc(self, l): self.rel(0x90, l)
    def dbnz_y(self, l): self.rel(0xFE, l)
    def inc_y(self): self.b(0xFC)
    def inc_dp(self, dp): self.b(0xAB, dp)
    def dec_dp(self, dp): self.b(0x8B, dp)
    def clrc(self): self.b(0x60)
    def beq(self, l): self.rel(0xF0, l)
    def bne(self, l): self.rel(0xD0, l)
    def bcs(self, l): self.rel(0xB0, l)
    def bra(self, l): self.rel(0x2F, l)
    def call(self, l): self.absop(0x3F, l)
    def jmp(self, l): self.absop(0x5F, l)

    def beq_far(self, l):
        self.b(0xD0, 3)                 # BNE over the JMP
        self.jmp(l)
    def ret(self): self.b(0x6F)

    def dsp(self, reg, v):
        self.mov_dp_imm(0xF2, reg)
        self.mov_dp_imm(0xF3, v)

    def dsp_a(self, reg):
        self.mov_dp_imm(0xF2, reg)
        self.mov_dp_a(0xF3)

    def data(self, bs):
        self.code += bytes(bs)

    # more instructions (music)
    def mov_a_dpx(self, dp): self.b(0xF4, dp)          # MOV A,dp+X
    def mov_dpx_a(self, dp): self.b(0xD4, dp)          # MOV dp+X,A
    def mov_y_dpx(self, dp): self.b(0xFB, dp)          # MOV Y,dp+X
    def dec_dpx(self, dp): self.b(0x9B, dp)
    def cmp_a_dpx(self, dp): self.b(0x74, dp)
    def sbc_a_dpx(self, dp): self.b(0xB4, dp)
    def mov_a_absy(self, label, add=0): self.absop(0xF6, label, add)
    def or_a_absx(self, label, add=0): self.absop(0x15, label, add)
    def or_a_imm(self, v): self.b(0x08, v)
    def or_a_dp(self, dp): self.b(0x04, dp)
    def eor_a_imm(self, v): self.b(0x48, v)
    def sbc_a_imm(self, v): self.b(0xA8, v)
    def mov_dp_y(self, dp): self.b(0xCB, dp)
    def mov_y_dp(self, dp): self.b(0xEB, dp)
    def mov_y_a(self): self.b(0xFD)
    def mov_a_y(self): self.b(0xDD)
    def mov_x_imm(self, v): self.b(0xCD, v)
    def cmp_x_imm(self, v): self.b(0xC8, v)
    def inc_x(self): self.b(0x3D)
    def mov_ind_y_a(self, dp): self.b(0xD7, dp)        # MOV [dp]+Y,A
    def mul(self): self.b(0xCF)                         # MUL YA
    def xcn(self): self.b(0x9F)
    def addw(self, dp): self.b(0x7A, dp)                # ADDW YA,dp
    def push_a(self): self.b(0x2D)
    def pop_a(self): self.b(0xAE)
    def setc(self): self.b(0x80)
    def dbnz_dp(self, dp, l):
        self.b(0x6E, dp, 0)
        self.fix.append((len(self.code) - 1, l, 'rel'))
    def bmi(self, l): self.rel(0x30, l)

    def bne_far(self, l):
        self.b(0xF0, 3)                 # BEQ over the JMP
        self.jmp(l)

    def dsp_v(self, reg):
        """DSP register VBASE | reg <- A (keeps A)."""
        self.push_a()
        self.mov_a_dp(VBASE)
        self.or_a_imm(reg)
        self.mov_dp_a(0xF2)
        self.pop_a()
        self.mov_dp_a(0xF3)


    def link(self):
        for off, target, kind in self.fix:
            if kind == 'rel':
                d = self.labels[target] - (self.org + off + 1)
                assert -128 <= d <= 127, (target, d)
                self.code[off] = d & 0xFF
            else:
                lab, add = target
                a = self.labels[lab] + add
                self.code[off:off + 2] = struct.pack('<H', a)
        return bytes(self.code)



def brr(samples, loop=True):
    """Encode 16-bit samples (len multiple of 16) as BRR blocks, filter 0, a fixed range (the effects)."""
    out = bytearray()
    n = len(samples) // 16
    peak = max(1, max(abs(s) for s in samples))
    rng = 0
    while rng < 12 and (7 << rng) >> 1 < peak:
        rng += 1
    for i in range(n):
        hdr = rng << 4 | (0x02 if loop else 0) | (0x01 if i == n - 1 else 0)
        out.append(hdr)
        blk = samples[i * 16:(i + 1) * 16]
        nib = [max(-8, min(7, round(s * 2 / (1 << rng)))) & 15 for s in blk]
        for j in range(0, 16, 2):
            out.append(nib[j] << 4 | nib[j + 1])
    return bytes(out)


# notes: pitch (DSP units; 32-sample period: f = P * 32000 / 4096 / 32), volume, ticks (1/100 s), sample
SQ, SINE = 0, 1
SFX = {
    1: [(0x1400, 0x22, 3, SQ)],                                              # cursor
    2: [(0x0E00, 0x2C, 3, SQ), (0x1500, 0x2C, 6, SQ)],                       # ok
    3: [(0x0C00, 0x24, 3, SQ), (0x0900, 0x24, 5, SQ)],                       # cancel
    4: [(0x0B40, 0x34, 5, SINE), (0x0E30, 0x34, 5, SINE), (0x10F0, 0x34, 5, SINE), (0x1680, 0x38, 18, SINE)],  # clue
    5: [(0x0500, 0x34, 8, SQ), (0x0470, 0x34, 12, SQ)],                      # wrong
    6: [(0x1800, 0x14, 2, SQ)],                                              # page
    7: [(0x0E30, 0x34, 4, SINE), (0x11E0, 0x34, 4, SINE), (0x1680, 0x38, 16, SINE)],  # right
    8: [(0x0A00, 0x24, 4, SINE), (0x0800, 0x24, 8, SINE)],                   # move
}


def adsr_bytes(a, d, sl, sr):
    return 0x80 | d << 4 | a, sl << 5 | sr


def build(voices=None):
    """voices: tools/adv/voice.build() result (samples and per-voice tables); None = data/adv/voices.txt
    with placeholder speaker ids (standalone use)."""
    import music, songs as songsmod
    if voices is None:
        import voice
        d = voice.parse()
        voices = voice.build({n: i + 1 for i, n in enumerate(d['voices'])}, [])
    nvoice = len(voices['src'])
    mnames, mblobs, msamples, minfo = music.build_samples()
    first_music = 2 + len(voices['samples'])
    msrc = {n: first_music + i for i, n in enumerate(mnames)}
    inst_names = list(music.INSTRUMENTS)
    inst_index = {n: i for i, n in enumerate(inst_names)}
    song_list = songsmod.songs()
    nsongs = sum(1 + len(s[4]) for s in song_list)

    a = Asm(ORG)
    a.label('start')
    a.mov_dp_imm(0xF1, 0x00)             # timers off
    a.mov_dp_imm(0xFA, 80)               # T0: 8 kHz / 80 = 100 Hz
    a.mov_dp_imm(0xFB, 125)              # T1: the song sets it
    a.dsp(0x6C, 0x60)                    # FLG: muted, echo write off, noise clock 0
    a.dsp(0x5C, 0xFF)                    # KOF all
    a.dsp(0x0C, 0x00)                    # MVOL / EVOL 0 until the echo buffer is clear
    a.dsp(0x1C, 0x00)
    a.dsp(0x2C, 0x00)
    a.dsp(0x3C, 0x00)
    a.dsp(0x6D, ECHO_PAGE)               # ESA
    a.dsp(0x7D, ECHO_EDL)                # EDL
    a.dsp(0x0D, ECHO_FEEDBACK)           # EFB
    for i, c in enumerate(ECHO_FIR):
        a.dsp(0x0F + 0x10 * i, c)
    a.dsp(0x4D, 0xFC)                    # EON: the music voices
    a.dsp(0x3D, 0x00)                    # NON
    a.dsp(0x2D, 0x00)                    # PMON
    a.dsp(0x5D, 0)                       # DIR (the page after the code, set below)
    dir_imm = len(a.code) - 2
    for v in range(8):
        base = v << 4
        a.dsp(base + 0x00, 0)
        a.dsp(base + 0x01, 0)
        a.dsp(base + 0x04, 0)
    a.dsp(0x05, 0xDF)                    # voice 0 ADSR: attack fast, decay 5
    a.dsp(0x06, 0x6F)                    # sustain level 3, release 15
    a.dsp(0x15, 0x00)                    # voice 1: GAIN, direct full (the sample has the envelope)
    a.dsp(0x17, 0x7F)
    # clear the echo buffer
    a.mov_dp_imm(CP, 0)
    a.mov_dp_imm(CP + 1, ECHO_PAGE)
    a.mov_y_imm(0)
    a.label('eclr')
    a.mov_a_imm(0)
    a.mov_ind_y_a(CP)
    a.inc_y()
    a.bne('eclr')
    a.inc_dp(CP + 1)
    a.mov_a_dp(CP + 1)
    a.cmp_a_imm(ECHO_PAGE + ECHO_EDL * 8)
    a.bne('eclr')
    a.dsp(0x6C, 0x20)                    # FLG: not muted, echo write still off
    a.dsp(0x0C, MASTER_VOL)
    a.dsp(0x1C, MASTER_VOL)
    a.dsp(0x2C, ECHO_VOL)
    a.dsp(0x3C, ECHO_VOL)
    a.dsp(0x5C, 0x00)                    # KOF none
    a.mov_dp_imm(ECHOWAIT, 30)           # 300 ms (more than one pass of the old EDL)
    a.mov_dp_imm(TIMER, 0)
    a.mov_dp_imm(VSTEP, 0)
    a.mov_dp_imm(MUTED, 0)
    a.mov_dp_imm(SONG_ON, 0)
    a.mov_dp_imm(FADE, 0xFF)
    a.mov_dp_imm(FTARGET, 0xFF)
    a.mov_x_imm(0)
    a.label('chclr')
    a.mov_a_imm(0)
    a.mov_dpx_a(ON)
    a.mov_dpx_a(KEYED)
    a.mov_dpx_a(VDEP)
    a.inc_x()
    a.cmp_x_imm(8)
    a.bne('chclr')
    a.mov_a_dp(0xF7)
    a.mov_dp_a(LAST3)
    a.mov_a_dp(0xF5)
    a.mov_dp_a(LAST)
    a.mov_dp_imm(0xF6, 0)                # song state for the CPU
    a.mov_dp_imm(0xF7, 0)
    a.mov_dp_imm(0xF1, 0x03)             # T0 + T1 on
    a.mov_a_dp(0xFE)                     # (clear the T1 counter)
    a.mov_dp_imm(0xF4, 0x5A)             # ready
    a.label('loop')
    a.mov_a_dp(0xFD)                     # T0 counter (read clears)
    a.beq('nocmdtick')
    a.call('tick')
    a.label('nocmdtick')
    a.mov_a_dp(0xFE)                     # T1 counter: music ticks
    a.beq('nomusic')
    a.mov_dp_a(NT1)
    a.label('mt')
    a.call('mtick')
    a.dbnz_dp(NT1, 'mt')
    a.label('nomusic')
    a.mov_a_dp(0xF7)                     # speech mailbox
    a.cmp_a_dp(LAST3)
    a.beq('nospeech')
    a.mov_dp_a(LAST3)
    a.mov_a_dp(0xF6)
    a.call('speech')
    a.label('nospeech')
    a.mov_a_dp(0xF5)
    a.cmp_a_dp(LAST)
    a.beq('loop')
    a.mov_dp_a(LAST)
    a.mov_a_dp(0xF4)
    a.call('command')
    a.bra('loop')

    a.label('command')
    a.cmp_a_imm(0x30)
    a.beq_far('mute')
    a.cmp_a_imm(0x31)
    a.beq_far('unmute')
    a.cmp_a_imm(0x60)
    a.beq_far('mfade')
    a.cmp_a_imm(0x61)
    a.beq_far('mstop')
    a.cmp_a_imm(0x62)
    a.beq_far('mduck')
    a.cmp_a_imm(0x63)
    a.beq_far('munduck')
    a.cmp_a_imm(0x40)
    a.bcc('notsong')
    a.cmp_a_imm(0x40 + nsongs)
    a.bcs('cret')
    a.jmp('song')
    a.label('notsong')
    a.cmp_a_imm(9)
    a.bcs('cret')
    a.cmp_a_imm(0)
    a.beq('cret')
    a.asl_a()
    a.mov_x_a()
    a.mov_a_absx('sfxtab', -2)
    a.mov_dp_a(PTR)
    a.mov_a_absx('sfxtab', -1)
    a.mov_dp_a(PTRH)
    a.call('next_note')
    a.label('cret')
    a.ret()

    a.label('next_note')
    a.mov_y_imm(3)
    a.mov_a_ind_y(PTR)
    a.beq('stop')
    a.mov_dp_a(TIMER)
    a.dsp(0x5C, 0x00)                    # KOF off
    a.mov_y_imm(0)
    a.mov_a_ind_y(PTR)
    a.dsp_a(0x02)                        # pitch L
    a.inc_y()
    a.mov_a_ind_y(PTR)
    a.dsp_a(0x03)                        # pitch H
    a.inc_y()
    a.mov_a_ind_y(PTR)
    a.dsp_a(0x00)                        # volume L/R
    a.dsp_a(0x01)
    a.mov_y_imm(4)
    a.mov_a_ind_y(PTR)
    a.dsp_a(0x04)                        # sample
    a.mov_a_imm(0x01)                    # KON voice 0
    a.call('kon')
    a.clrc()
    a.mov_a_dp(PTR)
    a.adc_a_imm(5)
    a.mov_dp_a(PTR)
    a.mov_a_dp(PTRH)
    a.adc_a_imm(0)
    a.mov_dp_a(PTRH)
    a.ret()
    a.label('stop')
    a.dsp(0x5C, 0x01)                    # KOF voice 0
    a.mov_dp_imm(TIMER, 0)
    a.ret()

    # 100 Hz: the effect notes, and the echo writes start after ECHOWAIT ticks
    a.label('tick')
    a.mov_a_dp(ECHOWAIT)
    a.beq('tsfx')
    a.dec_dp(ECHOWAIT)
    a.bne('tsfx')
    a.dsp(0x6C, 0x00)                    # FLG: echo write on
    a.label('tsfx')
    a.mov_a_dp(TIMER)
    a.beq('tret')
    a.dec_dp(TIMER)
    a.bne('tret')
    a.call('next_note')
    a.label('tret')
    a.ret()

    a.label('mute')
    a.mov_dp_imm(MUTED, 1)
    a.dsp(0x0C, 0)
    a.dsp(0x1C, 0)
    a.dsp(0x2C, 0)
    a.dsp(0x3C, 0)
    a.ret()
    a.label('unmute')
    a.mov_dp_imm(MUTED, 0)
    a.dsp(0x0C, MASTER_VOL)
    a.dsp(0x1C, MASTER_VOL)
    a.dsp(0x2C, ECHO_VOL)
    a.dsp(0x3C, ECHO_VOL)
    a.ret()

    # A = key-on bits; then wait > 64 cycles so the DSP has taken this KON before another one is written
    a.label('kon')
    a.dsp_a(0x4C)
    a.mov_y_imm(24)
    a.label('konwait')
    a.dbnz_y('konwait')
    a.ret()

    # ---------------------------------------------------------- music
    # A = $40 + song
    a.label('song')
    a.clrc()
    a.adc_a_imm(0xC0)                    # - $40
    a.mov_dp_a(SONGNO)
    a.call('msilence')
    a.mov_a_dp(SONGNO)
    a.asl_a()
    a.mov_x_a()
    a.mov_a_absx('songptr')
    a.mov_dp_a(CP)
    a.mov_a_absx('songptr', 1)
    a.mov_dp_a(CP + 1)
    a.mov_y_imm(0)
    a.mov_a_ind_y(CP)
    a.mov_dp_a(0xFB)                     # tempo
    a.mov_dp_imm(0xF1, 0x01)             # restart timer 1 (T0 keeps running)
    a.mov_dp_imm(0xF1, 0x03)
    a.mov_a_dp(0xFE)
    a.mov_x_imm(0)
    a.label('sch')
    a.inc_y()
    a.mov_a_ind_y(CP)
    a.mov_dpx_a(PTRL)
    a.mov_dp_a(TMP)
    a.inc_y()
    a.mov_a_ind_y(CP)
    a.mov_dpx_a(PTRHI)
    a.or_a_dp(TMP)
    a.beq('sch0')
    a.mov_a_imm(1)
    a.label('sch0')
    a.mov_dpx_a(ON)
    a.mov_a_imm(1)
    a.mov_dpx_a(DUR)
    a.mov_a_imm(0)
    a.mov_dpx_a(GATE)
    a.mov_dpx_a(VDEP)
    a.mov_dpx_a(KEYED)
    a.mov_dpx_a(VOLL)
    a.mov_dpx_a(VOLR)
    a.inc_x()
    a.cmp_x_imm(NCH)
    a.bne('sch')
    a.mov_a_dp(FTARGET)
    a.mov_dp_a(FADE)                     # a new song starts at the current target (ducked or not)
    a.mov_dp_imm(FADING, 0)
    a.mov_dp_imm(BEAT, 0)
    a.mov_dp_imm(TICKC, 0)
    a.mov_dp_imm(0xF7, 0)
    a.mov_a_dp(SONGNO)
    a.clrc()
    a.adc_a_imm(1)
    a.mov_dp_a(0xF6)
    a.mov_dp_imm(SONG_ON, 1)
    a.ret()

    a.label('mfade')
    a.mov_dp_imm(FADING, 1)
    a.ret()
    a.label('mduck')
    a.mov_dp_imm(FTARGET, DUCK_LEVEL)
    a.ret()
    a.label('munduck')
    a.mov_dp_imm(FTARGET, 0xFF)
    a.ret()
    a.label('mstop')
    a.call('msilence')
    a.mov_dp_imm(SONG_ON, 0)
    a.mov_dp_imm(0xF6, 0)
    a.ret()

    # every music voice released, every channel off
    a.label('msilence')
    a.mov_x_imm(0)
    a.label('msl')
    a.call('vbase')
    a.mov_a_imm(1)
    a.mov_dpx_a(KEYED)
    a.call('release')
    a.mov_a_imm(0)
    a.mov_dpx_a(ON)
    a.inc_x()
    a.cmp_x_imm(NCH)
    a.bne('msl')
    a.ret()

    # VBASE = DSP register base of channel X (voice X + 2)
    a.label('vbase')
    a.mov_a_x()
    a.clrc()
    a.adc_a_imm(2)
    a.xcn()
    a.mov_dp_a(VBASE)
    a.ret()

    # channel X: ADSR off, exponential GAIN decrease (keeps Y)
    a.label('release')
    a.mov_a_dpx(KEYED)
    a.beq('relret')
    a.mov_a_imm(0)
    a.mov_dpx_a(KEYED)
    a.mov_a_dpx(REL)
    a.dsp_v(0x07)
    a.mov_a_dpx(ADSR1)
    a.and_a_imm(0x7F)
    a.dsp_v(0x05)
    a.label('relret')
    a.ret()

    # channel X volume = VOLL/VOLR * FADE / 256 (clobbers Y)
    a.label('setvol')
    a.call('vbase')
    a.mov_y_dpx(VOLL)
    a.mov_a_dp(FADE)
    a.mul()
    a.mov_a_y()
    a.dsp_v(0x00)
    a.mov_y_dpx(VOLR)
    a.mov_a_dp(FADE)
    a.mul()
    a.mov_a_y()
    a.dsp_v(0x01)
    a.ret()

    # one music tick
    a.label('mtick')
    a.mov_a_dp(SONG_ON)
    a.bne('mt_go')
    a.ret()
    a.label('mt_go')
    a.mov_a_dp(FADING)
    a.beq('mt_nofade')
    a.mov_a_dp(FADE)
    a.setc()
    a.sbc_a_imm(4)
    a.bcs('mt_fok')
    a.call('msilence')
    a.mov_dp_imm(SONG_ON, 0)
    a.mov_dp_imm(0xF6, 0)
    a.mov_dp_imm(FADE, 0)
    a.mov_x_imm(0)
    a.label('mt_zero')
    a.call('setvol')
    a.inc_x()
    a.cmp_x_imm(NCH)
    a.bne('mt_zero')
    a.ret()
    a.label('mt_fok')
    a.mov_dp_a(FADE)
    a.mov_x_imm(0)
    a.label('mt_vol')
    a.call('setvol')
    a.inc_x()
    a.cmp_x_imm(NCH)
    a.bne('mt_vol')
    a.jmp('mt_beat')
    a.label('mt_nofade')                 # toward the duck target: down 12 a tick (quick), up 4 (slow)
    a.mov_a_dp(FADE)
    a.cmp_a_dp(FTARGET)
    a.beq('mt_beat')
    a.bcc('mt_up')
    a.setc()
    a.sbc_a_imm(12)
    a.bcc('mt_clamp')
    a.cmp_a_dp(FTARGET)
    a.bcs('mt_store')
    a.label('mt_clamp')
    a.mov_a_dp(FTARGET)
    a.bra('mt_store')
    a.label('mt_up')
    a.clrc()
    a.adc_a_imm(4)
    a.bcs('mt_clamp')
    a.cmp_a_dp(FTARGET)
    a.bcs('mt_clamp')
    a.label('mt_store')
    a.mov_dp_a(FADE)
    a.mov_x_imm(0)
    a.label('mt_dvol')
    a.call('setvol')
    a.inc_x()
    a.cmp_x_imm(NCH)
    a.bne('mt_dvol')
    a.label('mt_beat')
    a.inc_dp(TICKC)
    a.mov_a_dp(TICKC)
    a.cmp_a_imm(48)
    a.bne('mt_nobeat')
    a.mov_dp_imm(TICKC, 0)
    a.inc_dp(BEAT)
    a.mov_a_dp(BEAT)
    a.mov_dp_a(0xF7)
    a.label('mt_nobeat')
    a.mov_dp_imm(KONACC, 0)
    a.mov_x_imm(0)
    a.label('mt_ch')
    a.mov_a_dpx(ON)
    a.beq('mt_next')
    a.call('channel')
    a.label('mt_next')
    a.inc_x()
    a.cmp_x_imm(NCH)
    a.bne('mt_ch')
    a.mov_a_dp(KONACC)
    a.beq('mt_ret')
    a.call('kon')
    a.label('mt_ret')
    a.ret()

    # channel X: count down, fetch, gate, vibrato
    a.label('channel')
    a.call('vbase')
    a.dec_dpx(DUR)
    a.bne('ch_run')
    a.jmp('fetch')
    a.label('ch_run')
    a.mov_a_dpx(DUR)
    a.cmp_a_dpx(GATE)
    a.bne('ch_vib')
    a.mov_a_dpx(PTRL)
    a.mov_dp_a(CP)
    a.mov_a_dpx(PTRHI)
    a.mov_dp_a(CP + 1)
    a.mov_y_imm(0)
    a.mov_a_ind_y(CP)
    a.cmp_a_imm(0x03)
    a.beq('ch_vib')                      # a tie follows: no release
    a.call('release')
    a.label('ch_vib')
    a.mov_a_dpx(VDEP)
    a.beq('ch_ret')
    a.mov_a_dpx(KEYED)
    a.beq('ch_ret')
    a.mov_a_dpx(VDLY)
    a.beq('ch_dov')
    a.dec_dpx(VDLY)
    a.label('ch_ret')
    a.ret()
    a.label('ch_dov')
    a.mov_a_dpx(VPH)
    a.clrc()
    a.adc_a_imm(VIB_SPEED)
    a.mov_dpx_a(VPH)
    a.bpl('ch_up')
    a.eor_a_imm(0xFF)
    a.label('ch_up')
    a.asl_a()                            # triangle 0..254
    a.mov_y_a()
    a.mov_a_dpx(VDEP)
    a.asl_a()
    a.mul()                              # Y = 0 .. 2 * depth
    a.mov_a_y()
    a.setc()
    a.sbc_a_dpx(VDEP)
    a.mov_dp_a(TL)
    a.mov_a_imm(0)
    a.sbc_a_imm(0)
    a.mov_dp_a(TL + 1)                   # TL = signed offset
    a.mov_a_dpx(PL)
    a.mov_y_dpx(PH)
    a.addw(TL)
    a.dsp_v(0x02)
    a.mov_a_y()
    a.dsp_v(0x03)
    a.ret()

    # read the channel's events until a note, rest or tie
    a.label('fetch')
    a.mov_a_dpx(PTRL)
    a.mov_dp_a(CP)
    a.mov_a_dpx(PTRHI)
    a.mov_dp_a(CP + 1)
    a.mov_y_imm(0)
    a.label('f_next')
    a.mov_a_ind_y(CP)
    a.inc_y()
    a.cmp_a_imm(0x01)
    a.bne_far('f_2')
    # note
    a.mov_a_ind_y(CP)
    a.inc_y()
    a.mov_dpx_a(PL)
    a.mov_a_ind_y(CP)
    a.inc_y()
    a.mov_dpx_a(PH)
    a.mov_a_ind_y(CP)
    a.inc_y()
    a.mov_dpx_a(DUR)
    a.mov_a_dpx(ADSR1)
    a.dsp_v(0x05)
    a.mov_a_dpx(ADSR2)
    a.dsp_v(0x06)
    a.mov_a_dpx(PL)
    a.dsp_v(0x02)
    a.mov_a_dpx(PH)
    a.dsp_v(0x03)
    a.mov_a_imm(1)
    a.mov_dpx_a(KEYED)
    a.mov_a_imm(64)
    a.mov_dpx_a(VPH)
    a.mov_a_imm(VIB_DELAY)
    a.mov_dpx_a(VDLY)
    a.mov_a_dp(KONACC)
    a.or_a_absx('konbit')
    a.mov_dp_a(KONACC)
    a.jmp('f_done')
    a.label('f_2')
    a.cmp_a_imm(0x02)
    a.bne('f_3')
    a.mov_a_ind_y(CP)
    a.inc_y()
    a.mov_dpx_a(DUR)
    a.call('release')
    a.jmp('f_done')
    a.label('f_3')
    a.cmp_a_imm(0x03)
    a.bne('f_4')
    a.mov_a_ind_y(CP)
    a.inc_y()
    a.mov_dpx_a(DUR)
    a.jmp('f_done')
    a.label('f_4')
    a.cmp_a_imm(0x04)
    a.bne('f_5')
    a.mov_a_ind_y(CP)
    a.inc_y()
    a.mov_dp_y(TMP)
    a.asl_a()
    a.asl_a()
    a.mov_y_a()
    a.mov_a_absy('insttab')
    a.dsp_v(0x04)
    a.mov_a_absy('insttab', 1)
    a.mov_dpx_a(ADSR1)
    a.mov_a_absy('insttab', 2)
    a.mov_dpx_a(ADSR2)
    a.mov_a_absy('insttab', 3)
    a.mov_dpx_a(REL)
    a.mov_y_dp(TMP)
    a.jmp('f_next')
    a.label('f_5')
    a.cmp_a_imm(0x05)
    a.bne('f_6')
    a.mov_a_ind_y(CP)
    a.inc_y()
    a.mov_dpx_a(VOLL)
    a.mov_a_ind_y(CP)
    a.inc_y()
    a.mov_dpx_a(VOLR)
    a.mov_dp_y(TMP)
    a.call('setvol')
    a.mov_y_dp(TMP)
    a.jmp('f_next')
    a.label('f_6')
    a.cmp_a_imm(0x06)
    a.bne('f_7')
    a.mov_a_ind_y(CP)
    a.inc_y()
    a.mov_dpx_a(GATE)
    a.jmp('f_next')
    a.label('f_7')
    a.cmp_a_imm(0x07)
    a.bne('f_8')
    a.mov_a_ind_y(CP)
    a.inc_y()
    a.mov_dpx_a(VDEP)
    a.jmp('f_next')
    a.label('f_8')
    a.cmp_a_imm(0x08)
    a.bne('f_end')
    a.mov_a_ind_y(CP)
    a.push_a()
    a.inc_y()
    a.mov_a_ind_y(CP)
    a.mov_dp_a(CP + 1)
    a.pop_a()
    a.mov_dp_a(CP)
    a.mov_y_imm(0)
    a.jmp('f_next')
    a.label('f_end')                     # $09 (or anything unknown): the channel stops
    a.mov_a_imm(0)
    a.mov_dpx_a(ON)
    a.call('release')
    a.label('f_done')
    a.mov_a_y()
    a.clrc()
    a.adc_a_dp(CP)
    a.mov_dpx_a(PTRL)
    a.mov_a_dp(CP + 1)
    a.adc_a_imm(0)
    a.mov_dpx_a(PTRHI)
    a.ret()

    # speech blip: A = mailbox byte (bit 7 phrase start, bits 0-3 voice)
    a.label('speech')
    a.mov_dp_a(VTMP)
    a.mov_a_dp(MUTED)
    a.bne('sret')
    a.mov_a_dp(VTMP)
    a.bpl('nophrase')
    a.mov_dp_imm(VSTEP, 0)
    a.label('nophrase')
    a.mov_a_dp(VTMP)
    a.and_a_imm(0x0F)
    a.cmp_a_imm(nvoice)
    a.bcs('sret')
    a.mov_x_a()
    a.mov_a_absx('vsrc')
    a.dsp_a(0x14)                        # voice 1 sample
    a.mov_a_absx('vvol')
    a.dsp_a(0x10)                        # voice 1 volume L/R
    a.dsp_a(0x11)
    a.mov_a_x()
    a.asl_a()
    a.asl_a()
    a.asl_a()
    a.clrc()
    a.adc_a_dp(VSTEP)
    a.asl_a()
    a.mov_x_a()                          # (voice * 8 + step) * 2
    a.mov_a_absx('vpitch')
    a.dsp_a(0x12)                        # voice 1 pitch L/H
    a.mov_a_absx('vpitch', 1)
    a.dsp_a(0x13)
    a.mov_a_imm(0x02)                    # KON voice 1
    a.call('kon')
    a.inc_dp(VSTEP)
    a.mov_a_dp(VSTEP)
    a.cmp_a_imm(8)
    a.bcc('sret')
    a.mov_dp_imm(VSTEP, 4)               # the 5th-8th offsets repeat
    a.label('sret')
    a.ret()

    # effect sequences: 5 bytes per note, a zero-length note ends
    a.label('sfxtab')
    for i in range(1, 9):
        a.b(0, 0)
        a.fix.append((len(a.code) - 2, (f'sfx{i}', 0), 'abs'))
    for i in range(1, 9):
        a.label(f'sfx{i}')
        for p, vol, t, smp in SFX[i]:
            a.data([p & 0xFF, p >> 8, vol, t, smp])
        a.data([0, 0, 0, 0, 0])
    # speech voices (tools/adv/voice.py): sample number, volume, 8 contour pitches
    a.label('vsrc')
    a.data([2 + i for i in voices['src']])
    a.label('vvol')
    a.data(voices['vol'])
    a.label('vpitch')
    for steps in voices['pitch']:
        assert len(steps) == 8
        for p in steps:
            a.data([p & 0xFF, p >> 8])
    # music tables
    a.label('konbit')
    a.data([1 << (c + 2) for c in range(NCH)])
    a.label('insttab')                   # sample, ADSR1, ADSR2, release GAIN
    for n in inst_names:
        smp, adsr, rel, _ = music.INSTRUMENTS[n]
        a1, a2 = adsr_bytes(*adsr)
        a.data([msrc[smp], a1, a2, 0xA0 | rel])
    a.label('songptr')
    songptr_ofs = len(a.code)
    a.data(bytes(2 * nsongs))
    code = bytearray(a.link())
    dir_addr = (ORG + len(code) + 0xFF) & 0xFF00
    code[dir_imm] = dir_addr >> 8
    image = bytearray(code) + bytes(dir_addr - ORG - len(code))
    # samples: soft square and sine, 32-sample period, looped (effects); one-shot speech blips; music
    sq = [6000 if (i // 16) % 2 == 0 else -6000 for i in range(32)]
    sine = [round(9000 * math.sin(2 * math.pi * i / 32)) for i in range(32)]
    blobs = [(brr(sq), 0), (brr(sine), 0)] + [(b, 0) for b in voices['samples']] + mblobs
    assert len(blobs) <= DIR_SLOTS, len(blobs)
    dirs = bytearray()
    data = bytearray()
    addr = dir_addr + DIR_SLOTS * 4
    for bl, loop_ofs in blobs:
        dirs += struct.pack('<HH', addr, addr + loop_ofs)
        data += bl
        addr += len(bl)
    image += dirs + bytes(DIR_SLOTS * 4 - len(dirs)) + data
    # sequences, then the song headers
    seq_base = ORG + len(image)
    seq, entries, song_report = music.compile_songs(song_list, msamples, inst_index, seq_base)
    image += seq
    hdr_addr = []
    for name, div, addrs in entries:
        hdr_addr.append(ORG + len(image))
        image.append(div)
        for ad in addrs:
            image += struct.pack('<H', ad)
    for i, ad in enumerate(hdr_addr):
        image[songptr_ofs + 2 * i:songptr_ofs + 2 * i + 2] = struct.pack('<H', ad)
    end = ORG + len(image)
    assert end <= ECHO_PAGE << 8, f'driver image too large (${end:04X})'
    assert [e[0] for e in entries] == sorted(songsmod.SONG_IDS, key=songsmod.SONG_IDS.get), [e[0] for e in entries]
    return bytes(image), dict(code_bytes=len(code), image_bytes=len(image), image_end=f'${end:04X}', entry=ORG,
                              dir=dir_addr, speech_samples=len(voices['samples']),
                              speech_bytes=sum(len(b) for b in voices['samples']),
                              speech_volume_offset=a.labels['vvol'] - ORG, speech_voices=nvoice,
                              music_samples={n: minfo[n] for n in mnames},
                              music_sample_bytes=sum(len(b) for b, _ in mblobs), sequence_bytes=len(seq),
                              songs=song_report, song_ids=songsmod.SONG_IDS,
                              echo=dict(start=f'${ECHO_PAGE:02X}00', edl=ECHO_EDL, fir=list(ECHO_FIR),
                                        feedback=ECHO_FEEDBACK, volume=ECHO_VOL))


if __name__ == '__main__':
    img, info = build()
    out = pathlib.Path(__file__).resolve().parents[2] / 'build/adv/spc.bin'
    out.write_bytes(img)
    import json
    print(json.dumps({k: v for k, v in info.items() if k != 'music_samples'}, ensure_ascii=False, indent=1))
