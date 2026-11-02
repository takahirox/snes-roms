"""Review recordings of the music and the opening of 潮鳴りの密室 (for listening / viewing; not a test).

From the ROM on the unmodified Snes9x 1.63 libretro core, pad input only:
  opening.mp4      power-on without input: the notice, the four pictures of the prologue, black, the title
                   (PUSH START BUTTON) and 15 seconds of its theme -- video and sound of the same frames
  songs/<n>.m4a    each song as the game plays it, one loop and a little more, no effects or speech: the
                   title (the opening's theme), the warehouse, the pier, the cafe, the deduction, the ending
  RESULT.json      ROM SHA-256, frames, the song of each recording (music_cur), peaks
Output: docs/adv/music/review/ (or the folder given).

usage: python3 -I tests/adv/music_review.py [OUT_DIR]
"""
import sys, json, pathlib, subprocess, hashlib, struct, wave
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from drive import Driver, ROOT, M_CMD, M_OPEN, OP_TITLE
import routes

FPS = 60.0988
RATE = 32040
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'docs/adv/music/review'


def pcm_stats(pcm):
    v = struct.unpack(f'<{len(pcm) // 2}h', pcm)
    return dict(seconds=round(len(v) / 2 / RATE, 1), peak=max(abs(x) for x in v), clipped=sum(1 for x in v if abs(x) >= 32767))


def encode_audio(pcm, path):
    wav = path.with_suffix('.wav')
    with wave.open(str(wav), 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(pcm)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(wav), '-c:a', 'aac', '-b:a', '192k',
                    str(path)], check=True)
    wav.unlink()


def opening_video(rec):
    g = Driver()
    g.e.audio_pcm = bytearray()
    g.e.record_audio = True
    w = h = fmt = None
    raw = OUT / 'opening.video.raw'
    with open(raw, 'wb') as fv:
        title_at = None
        while True:
            g.run(1)
            fw, fh, pitch, data = g.e.frame
            bpp = 2 if g.e.pixel_format != 1 else 4
            w, h = fw, fh
            fmt = {1: 'bgra', 2: 'rgb565le'}.get(g.e.pixel_format, 'rgb555le')
            fv.write(b''.join(data[y * pitch:y * pitch + w * bpp] for y in range(h)))
            if title_at is None and g.w('mode') == M_OPEN and g.w('op_state') == OP_TITLE:
                title_at = g.frame
            if title_at is not None and g.frame >= title_at + int(15 * FPS):
                break
    pcm = bytes(g.e.audio_pcm)
    wav = OUT / 'opening.wav'
    with wave.open(str(wav), 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(pcm)
    mp4 = OUT / 'opening.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'rawvideo', '-pixel_format', fmt, '-video_size', f'{w}x{h}', '-framerate', str(FPS),
                    '-i', str(raw), '-i', str(wav),
                    '-vf', 'scale=768:672:flags=neighbor', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '14',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart',
                    str(mp4)], check=True)
    raw.unlink()
    wav.unlink()
    rec['opening'] = dict(mp4=str(mp4.relative_to(ROOT)), frames=g.frame, title_frame=title_at,
                          title_s=round(title_at / FPS, 2), **pcm_stats(pcm))
    g.close()


def songs(rec):
    g = Driver()
    out = {}

    def take(name, seconds):
        g.e.audio_pcm = bytearray()
        g.e.record_audio = True
        cur = set()
        for _ in range(int(seconds * FPS)):
            g.run(1)
            cur.add(g.w('music_cur'))
        g.e.record_audio = False
        pcm = bytes(g.e.audio_pcm)
        path = OUT / 'songs' / f'{name}.m4a'
        encode_audio(pcm, path)
        out[name] = dict(file=str(path.relative_to(ROOT)), music_cur=sorted(cur), **pcm_stats(pcm))
        print(name, out[name], flush=True)
    g.title_screen()
    take('1_title', 46)
    g.tap('START', 2, 4)
    g.tap('A')
    g.settle()
    assert g.mode() == M_CMD
    take('2_investigate', 42)
    g.move(routes.PIER)
    g.quiet()
    take('3_sea', 48)
    g.move(routes.CAFE)
    g.quiet()
    take('4_cafe', 40)
    g.move(routes.WAREHOUSE)
    routes.standard(g)
    g.note('すいりする')
    take('5_deduce', 55)
    for ans in routes.ANSWERS:
        g.pick(g.layout['clue_names'][ans] if ans in g.layout['clue_names'] else ans)
    g.settle()
    take('6_dawn', 52)
    g.close()
    rec['songs'] = out


def main():
    (OUT / 'songs').mkdir(parents=True, exist_ok=True)
    rom = ROOT / 'build/adv/shionari.sfc'
    rec = dict(rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(), core='Snes9x 1.63 libretro (unmodified)',
               note='recordings for listening and viewing; the checks are tests/adv/run.py (opening, audio) and '
                    'tests/adv/speech.py')
    opening_video(rec)
    songs(rec)
    (OUT / 'RESULT.json').write_text(json.dumps(rec, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(rec, ensure_ascii=False))


if __name__ == '__main__':
    main()
