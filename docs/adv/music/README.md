# Music and opening (candidate F)

Up to candidate E, the only sounds in 『潮鳴りの密室』 (Shionari no Misshitsu) were these three:

- sound effects
- speech sounds
- the "wave sound" outdoors and on the title. It slowly raised and lowered the volume of the DSP's white noise, and sounded like nothing but wind or noise.

Candidate F drops this wave sound. Instead, six original songs (plus an intro for the title) play on the SPC700. The opening was also rebuilt to follow the flow of commercial Super Famicom software.

- Review recordings: [the opening video (with sound, 52.8 s)](review/opening.mp4) and [each song (songs/)](review/songs/). Recorded by actually running the ROM on Snes9x 1.63, with pad input only.
- Instrument, song and driver sources: [`tools/adv/music.py`](../../../tools/adv/music.py) (instruments and score compiler), [`tools/adv/songs.py`](../../../tools/adv/songs.py) (scores), [`tools/adv/spc.py`](../../../tools/adv/spc.py) (driver)
- Opening: [`src/adv/opening.inc`](../../../src/adv/opening.inc)

## Opening

At power-on the screen proceeds as follows. Beats are those of the song (80 bpm); one beat is 0.75 s.

| Beats | Screen | Music |
|---|---|---|
| 0–7 | On black: 「この物語はフィクションです。／実在の人物・団体とは関係ありません。」 ("This story is fiction. / It has no relation to real persons or organizations.") | A distant bell and strings slowly swell |
| 8–15 | Night harbor picture and 「昭和六十二年　十一月十四日／時化の夜の　汐見港」 ("November 14, Showa 62 / 汐見港 (Shiomi Harbor) on a stormy night") | Harp arpeggios and timpani |
| 16–23 | Lighthouse and 「灯台の光が　くりかえし／暗い海をなでていく」 ("The lighthouse beam, again and again, / strokes the dark sea") | Same as above |
| 24–31 | Signal station and 「時化は　夜半すぎに去った／港の灯が　ひとつずつ消えていく」 ("The storm passed after midnight / the harbor lights go out one by one") | A flute countermelody enters |
| 32–39 | Warehouse No. 3 and 「第三倉庫の二階／内側から鍵のかかった部屋で……」 ("Upstairs in Warehouse No. 3 / in a room locked from the inside……") | Same as above |
| 40–47 | Fade to black | A timpani roll builds up (B♭→A7) |
| 48– | Title (harbor picture, logo, and 「昭和六十二年　汐見港」 ("Showa 62, Shiomi Harbor") above). PUSH START BUTTON blinks | Main theme (one cycle is 16 bars) |

- Pictures and captions fade slowly and independently (a picture fades to black in about 0.5 s, and the next picture fades in).
- Picture changes follow the beat count reported by the driver. The game reads the beat counter on port 3, and the tests confirm that the picture changes exactly every 8 beats (360 frames). If the sound driver does not respond, 45 frames are counted as one beat.
- Pressing A or START during the prologue goes straight to the title, and the music starts from the main theme.
- Pressing A or START on the title opens the menu (はじめから (new game) / つづきから (continue)); B returns to PUSH START.
- If nothing is pressed on the title for one cycle of the main theme (about 48 s), the screen and music fade out and the opening starts again — the attract mode a game shows in a store.
- Pressing A at the ending clears the text, then returns to the title screen with the main theme.

### What was referenced

Within what could be found on the web, there was no material that systematically explains how Super Famicom openings are arranged. The opening combines the following common patterns with the conventions of mystery dramas:

- company logo → intro demo → title and PUSH START → returns to the demo if left idle
- credits and logos fade in and out on black, and music and screen build up together

However, no real company's logo is used; the opening starts with a fiction disclaimer instead. No artwork, music or text from any work is used.

## Songs (`tools/adv/songs.py`)

| No. | Song | Scenes | Content |
|---|---|---|---|
| 0 | 潮鳴り (Shionari, opening) | At startup | D minor, 80 bpm, 28 bars. Loops the main theme from bar 13 |
| 1 | 潮鳴り (title) | Title | Starts from the main theme of 0 |
| 2 | 捜査 (Investigation) | Warehouse, signal station, police station | A minor, 96 bpm. A wood block ticks like a clock (the time until dawn), a repeating bass line and clarinet |
| 3 | 夜の海 (Night Sea) | Pier No. 2, lighthouse | Triple meter, 63 bpm. Harp, pad, buoy bell, flute |
| 4 | 浮標 (Buoy) | Café | F major, 100 bpm. Electric piano comping on 3rds and 7ths, bossa nova bass, shaker, flute |
| 5 | 推理 (Deduction) | Deduction part | D minor, 72 bpm. Over a D pedal, an inner voice descends D–C#–C–B. Heartbeat-like timpani, oboe |
| 6 | 夜明け (Dawn) | Truth to ending | The main theme restated in D major |

- The song is specified per scene (`music:` in `data/adv/story.txt`). Moving to a scene with the same song keeps the music going without a break.
- Deduction (`music: deduce`) and dawn (`music: dawn`) are specified from scripts. Quitting the deduction midway returns to the scene's song.

## Sound design

- **Instruments (13)**: all synthesized from formulas.
  - Sine harmonics are added, and three slightly detuned copies are fitted into a single loop to give an ensemble thickness (strings and pad).
  - So that only the instant of the attack is rich in harmonics and it quickly becomes a round tone, a decaying attack is followed by the loop (electric piano, harp, bass, celesta, flute).
  - Percussion (timpani, shaker, wood block) is made from noise and sine waves.
  - BRR compression was done with an encoder that searches the 4 filters and ranges using the same decoding as the hardware. Single-cycle tones loop 8 cycles to leave room for using better filters.
- **Driver**:
  - A 6-voice sequencer (DSP voices 2–7). Voice 0 remains sound effects and voice 1 speech sounds.
  - Notes do not end with KOF (key-off). They switch from ADSR to exponential-decay GAIN so the tail fades naturally.
  - Each instrument has vibrato (with delay).
  - Songs can fade out.
  - Echo (80 ms, feedback $38, a gentle low-pass FIR) applies only to the music voices. The echo buffer is filled with zeros before writing starts.
- **Mix during dialogue**:
  - While a message is open, the music is lowered by 10 dB (lowered in about 0.2 s, restored over about 0.7 s).
  - Speech sounds were raised 2.5–3.1×.
  - In measurements, the level of each speech sound (band above 250 Hz, relative to the music over the same interval) has a median of +5 dB and is 0 dB or more even at the bottom 10%.
- **Size**:
  - The whole driver is 31.6 KB. It is placed in ROM bank 13 and transferred in about 1.1 s at startup.
  - Startup has a fixed length of 96 frames, so the first input lands on the same frame on every emulator.
  - No clipping (recorded peak 15012 / 32767).
  - With 「おと：なし」 (sound: off), the output, including music and echo, is exactly 0.

## What was verified

| Test | Content |
|---|---|
| `tests/adv/run.py opening` (new) | Order of captions and pictures, picture change every 8 beats (360 frames), title at beat 48, blinking, opening and closing the menu, returning when idle, skipping starts from the main theme |
| `tests/adv/run.py audio` | The correct song plays in each scene; with おと：なし the output is exactly 0; it plays again when turned back on |
| `tests/adv/speech.py` | Now treats the music instead of the wave sound as the background. The difference from the control ROM with speech sounds muted is exactly the speech-sound waveform, and everything else is exactly 0 (proof that the music also plays identically). The music is lowered during dialogue, and speech sounds are at an audible level |
| Chord check (analysis during development) | Matched the recordings to the chord charts of the scores and looked at the share of each bar's energy taken by chord tones. Investigation 0.71, Night Sea 0.93, Buoy 0.81, Deduction 0.79, Dawn 0.88. The rest is melodic passing tones and chord tensions |

## Unverified and limitations

- The music was checked by waveforms and numbers (pitch, chords, volume, clipping). It has not been evaluated by human listening. It is also unverified on real hardware.
- There are six songs, each cycling in 40–55 s. There are no dedicated songs for climaxes of the case, no jingles (solved / failed), and the sound effects were not remade.
- The opening has no motion (scrolling or scaling), only fades. The pictures reuse existing backgrounds.
- Recordings were checked only on emulators (Snes9x 1.63, bsnes 115).
