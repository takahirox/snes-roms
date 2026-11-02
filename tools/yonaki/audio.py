"""Sound of 夜鳴き鐘: builds the SPC700 image (driver, samples, songs, effects) for the engine.

    import audio; a = audio.build()
    a['image']   bytes to load at a['load'] ($0200) with the IPL transfer, then start at a['entry'] ($0200)
    a['songs']   {name: n}   play with command $40 + n
    a['sfx']     {name: n}   play with command n (1..)
    a['amb']     {name: k}   start with command $70 + k (fades in ~0.4 s), stop with $7F (fades out)
    a['info']    sizes and the per-song report

CPU protocol (ports $2140-$2143):
  * After the transfer, wait until port 0 reads $5A (the driver is ready).
  * Command: write the command byte to port 0, then write a NEW value to port 1 (e.g. a counter).  The
    driver acts when port 1 changes, reading port 0 then.  Send at most one command per frame (the driver
    polls far faster than that, but two writes in the same frame would overwrite each other).
      $01-$2F  effect n (see a['sfx']; ignored while muted).  Two effect slots: a new effect takes a free
               slot (A first); when both are busy it replaces slot A.
      $30      mute (everything silent, echo too)        $31  unmute
      $40+n    play song n from its start (a running song is cut off with a short release)
      $60      fade the music out (~0.85 s), then stop    $61  stop the music now
      $62      duck the music (about -8 dB)                $63  undo the duck (gradually)
      $64      stop all effects now
      $70+k    ambience k on (fades in)                   $7F  ambience off (fades out)
  * Music state for the CPU: port 2 = song number + 1 while a song plays (0 when stopped / a song without
    a loop has ended), port 3 = beats since the song started (48 ticks; wraps at 256).

DSP voices: 0 = effect slot A, 1 = effect slot B (also the rain ambience while slot B is free),
2-7 = music.  Echo buffer $E000-$FFFF (64 ms); the image must end below $E000.

usage: python3 -I tools/yonaki/audio.py   (writes build/yonaki-audio/spc.bin and info.json)
"""
import json, pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import music, spc, sfx as sfxmod, songs as songsmod

ROOT = pathlib.Path(__file__).resolve().parents[2]


def build():
    S = music.samples()
    E = music.effect_samples()
    assert not set(S) & set(E)
    allS = {**S, **E}
    names = list(allS)
    src = {n: i for i, n in enumerate(names)}
    assert len(names) <= spc.DIR_SLOTS
    blobs = {}
    for n in names:
        blobs[n] = music.encode_sample(allS[n])
    inst = music.Inst(list(music.INSTRUMENTS), allS, src)

    fx_names = sfxmod.compile_effects(src, 0)[2]
    fx_number = {n: i + 1 for i, n in enumerate(fx_names)}
    assert len(fx_names) < 0x30, len(fx_names)
    song_list = songsmod.songs()
    song_names = [s['name'] for s in song_list]
    assert song_names == songsmod.ORDER, song_names
    amb_t = sfxmod.amb_tables(src, fx_number['rumble'])

    a = spc.assemble(len(song_list), len(fx_names), len(sfxmod.AMBIENCE), amb_t)
    a.label('insttab')
    for row in inst.table:
        a.data(row)
    a.label('songptr')
    songptr_ofs = len(a.code)
    a.data(bytes(2 * len(song_list)))
    a.label('sfxptr')
    sfxptr_ofs = len(a.code)
    a.data(bytes(2 * len(fx_names)))
    code = bytearray(a.link())
    dir_addr = (spc.ORG + len(code) + 0xFF) & 0xFF00
    code[a.labels['dir_imm'] - spc.ORG - 2] = dir_addr >> 8
    image = bytearray(code) + bytes(dir_addr - spc.ORG - len(code))
    # sample directory and data
    addr = dir_addr + spc.DIR_SLOTS * 4
    start = {}
    data = bytearray()
    for n in names:
        blob, _ = blobs[n]
        start[n] = addr + len(data)
        data += blob
    dirs = bytearray()
    for n in names:
        blob, loop_ofs = blobs[n]
        lt = allS[n].get('loopto')
        loop_addr = start[lt] if lt else start[n] + (loop_ofs or 0)
        dirs += struct.pack('<HH', start[n], loop_addr)
    image += dirs + bytes(spc.DIR_SLOTS * 4 - len(dirs)) + data
    # effects
    fx_base = spc.ORG + len(image)
    fx_blob, fx_ptrs, _, _ = sfxmod.compile_effects(src, fx_base)
    image += fx_blob
    for i, p in enumerate(fx_ptrs):
        image[sfxptr_ofs + 2 * i:sfxptr_ofs + 2 * i + 2] = struct.pack('<H', p)
    # songs
    seq_base = spc.ORG + len(image)
    seq, entries, report = music.compile_songs(song_list, inst, seq_base)
    image += seq
    for i, (name, hdr, addrs) in enumerate(entries):
        image[songptr_ofs + 2 * i:songptr_ofs + 2 * i + 2] = struct.pack('<H', spc.ORG + len(image))
        image += hdr
        for ad in addrs:
            image += struct.pack('<H', ad)
    end = spc.ORG + len(image)
    if end > spc.ECHO_PAGE << 8:
        raise music.MusicError(f'SPC image too large: ends at ${end:04X} (echo buffer at ${spc.ECHO_PAGE:02X}00)')
    info = dict(load=spc.ORG, entry=spc.ORG, image_bytes=len(image), image_end=f'${end:04X}',
                free_bytes=(spc.ECHO_PAGE << 8) - end, code_bytes=len(code), dir=f'${dir_addr:04X}',
                sample_bytes=len(data), effect_bytes=len(fx_blob), sequence_bytes=len(seq),
                echo=dict(start=f'${spc.ECHO_PAGE:02X}00', edl=spc.ECHO_EDL, bytes=spc.ECHO_EDL * 2048),
                samples={n: dict(bytes=len(blobs[n][0]), dir=src[n], f_nat=allS[n]['f'], looped=allS[n]['loop'] is not None)
                         for n in names},
                instruments={n: dict(base=inst.base[n][0], tune=inst.base[n][1]) for n in inst.names},
                songs={k: {kk: vv for kk, vv in v.items() if kk not in ('notes', 'chords')} for k, v in report.items()})
    return dict(image=bytes(image), load=spc.ORG, entry=spc.ORG,
                songs={n: i for i, n in enumerate(song_names)},
                sfx={n: fx_number[n] for n in sfxmod.PUBLIC},
                amb={n: k for k, n in enumerate(sfxmod.AMBIENCE)},
                info=info, report=report, effect_seconds=sfxmod.durations())


if __name__ == '__main__':
    r = build()
    out = ROOT / 'build/yonaki-audio'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'spc.bin').write_bytes(r['image'])
    meta = dict(songs=r['songs'], sfx=r['sfx'], amb=r['amb'], info=r['info'])
    (out / 'info.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1) + '\n')
    i = r['info']
    print(f"image {i['image_bytes']} bytes, ends {i['image_end']}, free {i['free_bytes']}; code {i['code_bytes']}, "
          f"samples {i['sample_bytes']}, effects {i['effect_bytes']}, sequences {i['sequence_bytes']}")
    for k, v in i['songs'].items():
        print(f"  {k:12s} {v['bpm']:6.1f} bpm {v['bars']:5.1f} bars {v['seconds']:6.1f} s loop from bar {v['loop_bar']}")
