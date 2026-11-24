"""Measure the resident Yonaki sound driver without changing the game ROM.

Run after `make yonaki-test` to use its real_E13 pad trace. Writes JSON and
lossless recordings under build/yonaki-audio/profile/.
"""
import hashlib
import io
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buildrom
from drive import Driver, ROOT
from music_review import FPS, RATE, Player, audio, mono, onset_s
from host_libretro_replay import Frontend

OUT = ROOT / 'build/yonaki-audio/profile'
VENDOR = ROOT / 'tools/vendor'
EXT = 'dylib' if sys.platform == 'darwin' else 'so'
CORES = {
    'snes9x': VENDOR / f'snes9x-1.63/libretro/snes9x_libretro.{EXT}',
    'bsnes': VENDOR / f'bsnes-63ee22f7af8f/bsnes_libretro.{EXT}',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sequence_banks(sound):
    """Size relocated score payloads with the existing compiler and shared samples."""
    info = sound['info']
    music = audio.music
    samples = {**music.samples(), **music.effect_samples()}
    src = {name: row['dir'] for name, row in info['samples'].items()}
    instruments = music.Inst(list(music.INSTRUMENTS), samples, src)
    base = info['load'] + info['image_bytes'] - info['sequence_bytes']
    base -= len(sound['songs']) * (5 + 2 * audio.spc.NCH)
    banks = {}
    for song in audio.songsmod.songs():
        seq, [(_, header, channels)], _ = music.compile_songs([song], instruments, base)
        banks[song['name']] = len(seq) + len(header) + 2 * len(channels)
    assert base - info['load'] + sum(banks.values()) == info['image_bytes']
    return base - info['load'], banks


def profile_driver(sound, common_bytes, banks):
    player = Player(sound['image'], OUT / 'driver.sfc')
    try:
        ready = player.ready_frame
        pcm, _ = player.record(0.25, sound['sfx']['bell'])
        bell_ms = round(1000 * onset_s(mono(pcm), RATE), 1)
        player.cmd(0x64)
        player.run(90)
        pcm, _ = player.record(0.25, 0x40 + sound['songs']['title'])
        title_ms = round(1000 * onset_s(mono(pcm), RATE), 1)
        player.cmd(0x71)  # storm remains active during switches
        player.run(60)
        switch = {}
        songs = ['journey', *(n for n in sound['songs'] if n != 'journey')]
        for name in songs:
            number = sound['songs'][name]
            if name == 'title':
                player.cmd(sound['sfx']['thunder'])
            _, ports = player.record(0.1, 0x40 + number)
            # Offset 0 is the frame that writes the command. The test ROM samples
            # port 2 immediately after that write and once every subsequent frame.
            switch[name] = next(i for i, (song, _) in enumerate(ports) if song == number + 1)
        # At one send per frame, each previous song should appear at the next
        # snapshot. The initial song is already playing from the previous loop.
        observed = []
        for name in songs:
            _, [(song, _)] = player.record(1 / FPS, 0x40 + sound['songs'][name])
            observed.append(song)
        _, [(last, _)] = player.record(1 / FPS)
        assert observed[1:] + [last] == [sound['songs'][n] + 1 for n in songs], observed
    finally:
        player.close()

    # Readiness only. At reset the driver does not read any score or song header.
    # This prefix tests IPL time at the same byte count as common data plus title.
    prefix = Player(sound['image'][:common_bytes + banks['title']], OUT / 'prefix.sfc')
    try:
        return dict(full_ready_frame=ready, prefix_ready_frame=prefix.ready_frame, fps=FPS,
                    bell_onset_ms=bell_ms, title_onset_ms=title_ms, switch_frame_offsets=switch,
                    consecutive_switches=len(observed))
    finally:
        prefix.close()


def profile_game_boot():
    game = Driver(sram=bytes(8192))
    try:
        game.until(lambda: game.w('spc_ready') == 1, 300, '$5A ready')
        ready = game.frame
        game.until(lambda: game.w('snd_sent') > 0, 300, 'first sound command')
        return dict(ready_frame=ready, boot_nmis=game.w('boot_frames'), first_command_frame=game.frame)
    finally:
        game.close()


def profile_transition(sound):
    """Measure the first audible effect of a live switch against an unchanged mix."""
    def capture(next_song):
        player = Player(sound['image'], OUT / 'driver.sfc')
        try:
            player.cmd(0x40 + sound['songs']['title'])
            player.cmd(0x71)
            player.run(120)
            pcm, _ = player.record(0.25, next_song)
            return mono(pcm)
        finally:
            player.close()

    control = capture(None)
    switched = capture(0x40 + sound['songs']['journey'])
    assert len(control) == len(switched)
    changed = onset_s([b - a for a, b in zip(control, switched)], RATE)
    assert changed is not None, 'switch produced the same mix'
    return round(changed * 1000)


def profile_queue(sound):
    fixture = OUT / 'fixture'
    shutil.copytree(buildrom.FIXTURE, fixture, dirs_exist_ok=True)
    main = fixture / 'scenario/00_main.txt'
    # Eight effects followed by a song, all before the VM next yields. Ask for
    # the dropped song again once the queue drains, then ask for a different one.
    burst = '@se bell\n' * 8 + '@bgm horror\n@fx wait 10\n@bgm horror\n@fx wait 10\n@bgm deduce\n'
    source = main.read_text()
    assert source.count('@amb rain\n') == 1
    main.write_text(source.replace('@amb rain\n', burst + '@amb rain\n'))
    build = OUT / 'queue'
    buildrom.build(build, fixture / 'scenario', ['--omake-endings', '3'])
    game = Driver(build, sram=bytes(8192))
    try:
        horror, deduce = (sound['songs'][n] for n in ('horror', 'deduce'))
        game.title()
        game.title_pick(0)
        game.until(lambda: game.w('music_cur') == horror, 500, 'sound burst')
        assert game.w('snd_count') == 14
        assert game.b('snd_queue', 14) == bytes((sound['sfx']['bell'], 0)) * 7
        sent = game.w('snd_sent')
        game.until(lambda: game.w('music_cur') == deduce, 30, 'next song')
        drained = game.w('snd_sent') - sent
        pending = list(game.b('snd_queue', game.w('snd_count'))[::2])
        assert drained == 8 and pending == [0x70], (drained, pending)
        return dict(queued_effects=8, drained_after_first_send=drained - 1,
                    dropped_song='horror', suppressed_retry='horror', next_song='deduce')
    finally:
        game.close()


def record_route(core, rom, trace_path, out):
    trace = json.loads(trace_path.read_text())
    initial_sram = trace_path.with_suffix('.in.srm').read_bytes()
    assert sha(initial_sram) == trace['input_sram_sha256']
    out.mkdir(parents=True, exist_ok=True)
    (out / 'yonaki.srm').write_bytes(initial_sram)
    frontend = Frontend(core, rom, out)
    pcm = io.BytesIO()
    frontend.audio_file = pcm
    try:
        for mask in trace['masks']:
            frontend.step(mask)
        samples = pcm.getvalue()
        rate = round(frontend.av['sample_rate'])
    finally:
        frontend.close()
    with wave.open(str(out / 'route.wav'), 'wb') as wav:
        wav.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
        wav.writeframes(samples)
    onset = onset_s(mono(samples), rate)
    assert onset is not None, 'route recording is silent'
    result = dict(pcm_sha256=sha(samples), sample_frames=len(samples) // 4, rate_hz=rate, first_audio_seconds=onset)
    (out / 'pcm.json').write_text(json.dumps(result, indent=2) + '\n')


def compare_route():
    trace_path = ROOT / 'build/yonaki-test/traces/real_E13.json'
    trace = json.loads(trace_path.read_text())
    roms = {'released': ROOT / 'dist/yonaki.sfc', 'rebuilt': ROOT / trace['rom']}
    assert sha(roms['rebuilt'].read_bytes()) == trace['rom_sha256']
    result = {}
    for name in CORES:
        recordings = {}
        for kind, rom in roms.items():
            out = OUT / name / kind
            # Start a fresh process for each capture. bsnes keeps audio callback
            # state across unload/load in the same process.
            subprocess.run([sys.executable, '-I', __file__, '--record-route', name,
                            str(rom), str(trace_path), str(out)], check=True)
            recordings[kind] = json.loads((out / 'pcm.json').read_text())
        assert recordings['released'] == recordings['rebuilt'], (name, recordings)
        result[name] = recordings
    return dict(trace=trace_path.stem, frames=len(trace['masks']), recordings=result)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sound = audio.build()
    common, banks = sequence_banks(sound)
    driver = profile_driver(sound, common, banks)
    driver['title_to_journey_mix_change_ms'] = profile_transition(sound)
    summary = dict(image_sha256=sha(sound['image']), common_bytes=common, sequence_banks=banks,
                   game_boot=profile_game_boot(), driver=driver,
                   queue=profile_queue(sound), route=compare_route())
    text = json.dumps(summary, indent=2) + '\n'
    (OUT / 'RESULT.json').write_text(text)
    print(text, end='')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--record-route']:
        _, _, core, rom, trace, out = sys.argv
        record_route(CORES[core], Path(rom), Path(trace), Path(out))
    else:
        main()
