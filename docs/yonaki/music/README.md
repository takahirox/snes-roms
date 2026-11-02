# The sound of 夜鳴き鐘 (Yonaki Kane) (music, sound effects, ambience, sound driver)

All of the sound in 『夜鳴き鐘』 is made inside this repository: 18 songs, 32 sound effects (13 of them clock chimes that differ only in the number of strokes), 2 ambiences, and the SPC700 sound driver. No music, sounds or samples from any other work are used. Every instrument sound is synthesized from formulas (sine-wave partials, detuned copies, decaying attacks, filtered noise, resonators).

- Review recordings: [`review/`](review/) ([songs](review/songs/), [sound effects](review/sfx/), [ambience](review/amb/), [figures RESULT.json](review/RESULT.json)). Recorded by actually playing them on Snes9x 1.63 (libretro, unmodified).
- Sources:
  - [`tools/yonaki/audio.py`](../../../tools/yonaki/audio.py): the entry point the engine uses (`build()`). The specification of the CPU interface is also written here.
  - [`tools/yonaki/spc.py`](../../../tools/yonaki/spc.py): the driver (SPC700 assembly written in Python)
  - [`tools/yonaki/music.py`](../../../tools/yonaki/music.py): sound synthesis, BRR encoder, MML, score compiler
  - [`tools/yonaki/songs.py`](../../../tools/yonaki/songs.py): the scores
  - [`tools/yonaki/sfx.py`](../../../tools/yonaki/sfx.py): sound effects and ambience
- Review script: [`tests/yonaki/music_review.py`](../../../tests/yonaki/music_review.py)

## Use from the engine

```python
import audio                      # tools/yonaki/audio.py
a = audio.build()                 # about 1 s. BRR is cached in build/yonaki-audio/brr-cache/
a['image']                        # 48,523 bytes. Transfer to $0200 with the IPL and run from $0200
a['songs'], a['sfx'], a['amb']    # name -> number
```

Running `python3 -I tools/yonaki/audio.py` writes `build/yonaki-audio/spc.bin` and `info.json`.

### CPU interface (ports $2140-$2143)

The same scheme as 潮鳴りの密室 (Shionari no Misshitsu): repeatedly "write a command to port 0, then change port 1 to a different value".

| Command | Meaning |
|---|---|
| (startup) | After the transfer and start, ready once port 0 reads `$5A` |
| `$01`-`$2F` | Sound effect n (table below). Ignored while muted. There are two sound-effect slots; the free one is used (A first). If both are busy, A is replaced |
| `$30` / `$31` | Mute (music, sound effects, ambience and echo all output 0) / unmute |
| `$40`+n | Play song n from the start (a song already playing is cut with a quick release) |
| `$60` | Fade the song out (about 0.85 s) and stop |
| `$61` | Stop the song immediately (-40 dB in about 0.2 s) |
| `$62` / `$63` | Duck the song (about -8 dB) / restore it (slowly) |
| `$64` | Stop all sound effects |
| `$70`+k | Play ambience k (fades in over about 0.4 s) |
| `$7F` | Stop the ambience (fade out) |

- Send at most one command per frame. If two are written in the same frame, the first is overwritten.
- While a song is playing, port 2 holds "song number + 1". It is 0 when stopped and when a non-looping song has ended. Port 3 is the number of beats since the song started (counted in quarter notes, wrapping at 256).

### Numbers

| Song | n | Song | n | Song | n |
|---|---|---|---|---|---|
| title | 0 | unease | 6 | dawn | 12 |
| journey | 1 | horror | 7 | badend | 13 |
| inn | 2 | chase | 8 | staff | 14 |
| dinner | 3 | investigate | 9 | oyura | 15 |
| night | 4 | deduce | 10 | chizuru | 16 |
| legend | 5 | sorrow | 11 | omake | 17 |

Sound effects: bell 1, bell_far 2, thunder 3, rumble 4, door 5, door_bang 6, steps 7, knock 8, water 9, drip 10, heart 11, shock 12, glass 13, clock 14 (3 strokes), tick 15, match 16, camera 17, radio 18, thud 19, wind 20, clock1 21 … clock12 32 (N strokes). scream is not made, because without samples it does not become a convincing voice.

Ambience: rain 0 (`$70`), storm 1 (`$71`; rain with distant thunder mixed in every 6 to 16 seconds).

### DSP voices and SPC RAM

- Voice 0: sound-effect slot A. Voice 1: sound-effect slot B; while slot B is free it is also used for the rain. Voices 2–7: the song's 6 channels.
- If slot B is used while the rain is playing, the raindrops stop until that sound effect ends. thunder, door, water, glass, camera, radio, thud and shock use both slots.

| Range | Contents |
|---|---|
| `$0000-$00EF` | Driver variables |
| `$0100-$01FF` | Channel array (`$0100-$0117`) and stack |
| `$0200-$1049` | Driver code and tables (3,657 bytes: a 96-note pitch table, the instrument table, the rain tables) |
| `$1100-$11FF` | Sample DIR (64 entries) |
| `$1200-` | Samples 32,229 bytes (36 of them), sound effects 1,284 bytes, scores 10,608 bytes (18 songs) |
| `-$BF8A` | End of the image (48,523 bytes). The 8,309 bytes at `$BF8B-$DFFF` are free |
| `$E000-$FFFF` | Echo buffer (EDL 4, 64 ms, 8 KiB; filled with 0 before writing is enabled) |

Largest samples first: bell 5,400, timpani 2,718, strings 2,304, shakuhachi 1,728, dissonant stab 1,728, taiko 1,530 … (all are listed in `info.json`).

## Driver (copied from the 潮鳴りの密室 driver and extended)

The original files (`tools/adv/spc.py` and others) are unchanged. The following was added or changed.

- **A more compact score format**: a note is one byte and reuses the previous length; a length is written only when it changes. Repeats (one level) and subroutine calls are available. The compiler automatically folds repetitions of the same bars (groups of 1 to 4 bars) into repeats. 18 songs take 10.6 KB.
- **Pitch**: from a 96-note pitch table, a base note per instrument and fine tuning (in units of 1/1024). On the Python side every note's pitch is checked with the same arithmetic as the driver.
- Added **bends** (the shakuhachi's upward scoop, the horror low strings' glissando, the ghostly choir) and a per-song vibrato speed.
- **Per-song echo** (feedback and volume). Echo is applied to the song voices and to the sound effects that have it (bell, clock, door, shock, glass, drip).
- **Sound effects written as a sequence of steps**: sample or noise generator, ADSR or GAIN, volume changes, pitch slides, jumps to other sound effects (clock1–12 share one sequence of strokes). A partner sound effect can be played at the same time in the other slot.
- Added the **rain ambience** (described below).
- **Timing**: fades, ducking, sound effects and rain run on a fixed 100 Hz clock, independent of the song's tempo.
- Stopping and release are, as before, done with GAIN exponential decay rather than KOF.

## Songs

The main theme 「夜鳴き鐘」 is in D minor, with a touch of the miyako-bushi scale (E♭). The opening **bell motif** D–A–B♭–A is made of a long, bell-like D, a falling fourth, and a B♭→A sigh. The motif appears in legend (shakuhachi), unease (a semitone off, on celesta), sorrow, dawn (D major), badend (choir) and staff. oyura answers it in the form D–E♭–D–A.

| Song | Scene | Key, tempo | Construction |
|---|---|---|---|
| title | Title | D minor 66 | Two bars of bell and koto, then the 16-bar theme: music box in the first half, shakuhachi in the second. A string pad and koto arpeggios coloured by the hirajōshi scale (9th, minor 6th). A bell at the head of each phrase. Loops from after bar 2 |
| journey | By bus into the valley | A minor 92 | Harp eighth notes as the "wheels", clarinet. A shadow of B♭→E (tritone) at the end |
| inn | The inn (day, evening) | F major 3/4 80 | Flute, lingering koto, strings. B♭m (a borrowed chord) gives loneliness. 24 bars |
| dinner | Dinner | G major 104 | Clarinet and koto, woodblock. Under the cheerful surface, the low strings keep descending by semitones (B–A♯–A–G♯…) |
| night | Rainy night | A minor 3/4 60 | Sparse piano, thin strings, harp, celesta like drips from the eaves. 24 bars (72 s) |
| legend | Telling the legend | miyako-bushi (D E♭ G A B♭) 54 | Shakuhachi (breath noise and scoops), sustained shō, sparse koto, taiko, distant bell |
| unease | Something is wrong | C minor 96 | Repeated pizzicato, taiko beats, tritone strings, the bell motif a semitone off. Builds in the last 8 bars with a timpani roll |
| horror | Horror | 72 | Semitone clusters in 32nd-note tremolo (around E5/F5; not too high), low strings sliding down in glissando, a sliding ghostly choir, a heartbeat (thump, thump), cluster hits |
| chase | Running | D minor 160 | Reed melody, string ostinato, koto 16th notes, taiko and snare, timpani |
| investigate | Investigation, clues | A minor 100 | Woodblock clock, pizzicato, harp 16th notes, clarinet. Circle-of-fifths progression in the second half |
| deduce | The final deduction | C minor 116 | String eighth-note ostinato, timpani, oboe. The lower strings grow steadily stronger |
| sorrow | The truth, the confession | D minor 54 | The theme, slowed. Strings handing over to shakuhachi, harp, bell |
| dawn | True ending | D major 72 | The theme in major. Flute, strings, harp, celesta |
| badend | Bad ending | D minor 50 | 8 bars, no loop. Choir and low strings, timpani; ends quietly with the bell an octave lower (port 2 goes to 0) |
| staff | Staff roll | | Koto theme → the inn melody → the theme in major (137 s). Then loops the major theme |
| oyura | おゆら篇 (the Oyura chapter) | 63 | A ritual: taiko, hyōshigi clappers, shō clusters (E/A clashing with E♭/B♭), ghostly choir, shakuhachi, a bell every 4 bars |
| chizuru | 千鶴篇 (the Chizuru chapter; 1969) | A minor 92 | Shōwa-era kayōkyoku pop: a string melody coloured by the yonanuki minor scale, nylon-string guitar, organ, bass, brush-like snare and shaker. The last 8 bars are an octave-up "chorus" |
| omake | 編集部篇 (the editorial-office chapter) | C major 132 | Oboe melody, pizzicato "oom-pah", off-beat piano, woodblock, celesta |

Instruments (27 kinds; 21 samples for the songs): music box, koto (the pitch settles slightly just after the pluck), harp / nylon guitar, piano, bass / pizzicato, strings (3 detuned copies), choir "oo", organ, shō / reed, clarinet, oboe, flute, shakuhachi (breath noise inside the loop too), celesta, bell, timpani, taiko, snare, shaker, woodblock, dissonant stab.

## Sound effects

| Name | Construction |
|---|---|
| bell | A small bronze bell (the most important sound). Hum (0.5), fundamental, minor third (1.19), fifth, nominal (2.0), and inharmonic partials at 2.54, 2.67, 3.27, 4.21…; higher partials die away faster. The fundamental and the nominal are each a pair detuned by 2.5 Hz, so they beat slowly. With echo; about 5.3 s to -40 dB |
| bell_far | The same bell slightly lower, quieter, panned to the other side. A higher echo ratio makes it sound distant |
| thunder | Slot A: a "crack" from the noise generator (rapid hits with falling frequency). Slot B: a low looping brown-noise "rumble" (swelling volume, slowly falling pitch). About 3.4 s |
| rumble | Distant thunder. Low, quiet, slow to rise |
| door | A sliding door, "rattle… thunk": 8 small wooden knocks (random pitch and strength), resonant noise of scraping along the sill, and finally the hit against the frame |
| door_bang | A big wooden hit with a low body resonance (echo) |
| steps | 5 steps on an old floor. After 2–3 dull footfalls, a creak of wood (stick-slip pulses through two wooden resonances, with pitch going up and down). Moves from left to right |
| knock | 3 knocks on a door |
| water | A splash (noise attack and decay) and 10 scattered droplets |
| drip | A short rising "plink" and one more small drop (echo) |
| heart | Thump-thump (80 bpm), 4 times |
| shock | The sound-novel "jaaan" sting: a cluster of semitone clashes over 3 octaves (with a breathy attack) and a low hit. With echo |
| glass | A breaking sound (noise), then inharmonic shards scattered over both slots |
| clock, clock1–12 | Pendulum clock strikes (the bell sample an octave lower), N strokes 1.5 s apart. clock is 3 strokes |
| tick | Clock tick-tock, 6 times |
| match | Striking a match (two short noises) and the flare (low noise) |
| camera | Polaroid: the shutter "click" and the film-ejecting motor (square-wave whine and gear noise) |
| radio | Business radio: wavering static, a heterodyne whistle, and a final "click" |
| thud | A person falling: a low, heavy hit and a small bounce |
| wind | A gust of wind: a noise loop with two resonances; the volume swells and the pitch rises, then falls |

### Rain (the fix for the previous game's "just noise")

The previous game's surf was only white noise with its volume slowly going up and down, and it was criticized as "sounding like nothing but noise". This time the driver generates the rain drop by drop on the fly.

- There are 4 kinds of raindrop: a high "tick" (hitting leaves or gravel: 4.2 kHz resonant noise decaying in 2.5 ms), a medium "tick", a "plop" into a puddle (rising pitch), and a dull "tok" on the wooden eaves.
- A drop is chosen at random every 10 ms. The interval (10–60 ms, on average about 40 drops a second), kind, pitch (16 steps), strength (mostly soft, occasionally a close drop) and left-right position are all random, so no pattern repeats.
- The end of each drop runs into a soft band-limited noise loop (shared). Until the next drop comes, that is the quiet background.
- The volume is restrained: 14.8 dB below the quietest song (night), and lower still under other songs.
- To keep its use focused, the songs do not produce rain sounds themselves. The mood of the night scenes comes from the songs (night, legend, unease).

Figures (20 s of rain alone, excluding the first 2 s):

| | Rain | Storm | For comparison: white noise |
|---|---|---|---|
| Drop onsets (per second) | 36.4 | 35.5 | 0 |
| Spectral flatness (0–1; white noise is about 0.56) | 0.078 | 0.049 | 0.565 |
| Volume fluctuation per 10 ms (standard deviation / mean) | 1.11 | 1.07 | 0.03 |
| RMS | -43.6 dBFS | -32.6 dBFS (including distant thunder) | |

The figures show that this is not flat, uniform noise but distinct drops rising above a band-limited background. A spectrogram also confirmed broadband vertical lines (drops) at random intervals.

## What was checked (`tests/yonaki/music_review.py`)

A small test ROM was used (its 65816 code is assembled inside the script). Like the game, this ROM transfers the image with the IPL, waits for `$5A`, then sends the commands written in a WRAM mailbox through ports 0/1, one per frame. It was run on unmodified Snes9x 1.63, and its audio output was recorded and analysed. The whole run takes about 75 s. Songs were recorded for "one loop + 9 s", sound effects for "length + 1.5 s".

### Songs (`songs` in `RESULT.json`)

| Song | Length s | Loop s | Peak | Clipping | RMS dBFS | In-tune ratio | Score-note ratio | Chord-tone ratio | Second-loop match |
|---|---|---|---|---|---|---|---|---|---|
| title | 65.7 | 58.4 | 14917 | 0 | -22.5 | 0.994 | 0.979 | 0.891 | 0.996 |
| journey | 41.9 | 41.9 | 12266 | 0 | -23.7 | 0.993 | 0.850 | 0.758 | 0.999 |
| inn | 54.0 | 54.0 | 13312 | 0 | -21.5 | 0.990 | 0.978 | 0.892 | 1.000 |
| dinner | 55.3 | 55.3 | 12495 | 0 | -23.6 | 0.989 | 0.900 | 0.710 | 1.000 |
| night | 72.1 | 72.1 | 10935 | 0 | -28.7 | 0.976 | 0.965 | 0.884 | 1.000 |
| legend | 71.0 | 71.0 | 14019 | 0 | -22.0 | 0.975 | 0.926 | 0.782 | 0.942 |
| unease | 59.9 | 59.9 | 17991 | 0 | -25.9 | 0.955 | 0.860 | 0.684 | 1.000 |
| horror | 26.7 | 26.7 | 13405 | 0 | -23.5 | 0.910 | 0.810 | 0.384 | 0.999 |
| chase | 23.8 | 23.8 | 20245 | 0 | -21.0 | 0.886 | 0.701 | 0.657 | 1.000 |
| investigate | 57.6 | 57.6 | 12748 | 0 | -24.4 | 0.973 | 0.822 | 0.727 | 1.000 |
| deduce | 33.0 | 33.0 | 15216 | 0 | -21.3 | 0.992 | 0.866 | 0.800 | 1.000 |
| sorrow | 71.0 | 71.0 | 14159 | 0 | -22.7 | 0.996 | 0.979 | 0.911 | 1.000 |
| dawn | 53.4 | 53.4 | 14412 | 0 | -21.4 | 0.992 | 0.990 | 0.859 | 1.000 |
| badend | 40.8 | — | 11838 | 0 | -23.6 | 0.996 | 0.969 | 0.880 | — |
| staff | 137.3 | 54.9 | 14027 | 0 | -22.1 | 0.990 | 0.985 | 0.885 | 0.999 |
| oyura | 61.1 | 61.1 | 14239 | 0 | -22.5 | 0.962 | 0.720 | 0.370 | 0.999 |
| chizuru | 62.8 | 62.8 | 11752 | 0 | -24.4 | 0.978 | 0.948 | 0.855 | 1.000 |
| omake | 29.2 | 29.2 | 12895 | 0 | -26.0 | 0.971 | 0.842 | 0.807 | 1.000 |

What the columns mean:

- **In-tune ratio**: of the energy in spectral peaks between 180 Hz and 2.5 kHz (4096-point FFT at 8 kHz), the share lying within ±30 cents of an equal-tempered semitone.
- **Score-note ratio**: per bar, the share of the recorded pitch-class energy that falls in the pitch classes the score plays in that bar. Percussion is excluded on the score side.
- **Chord-tone ratio**: likewise, the share falling in the tones of the chord symbol.
- **Second-loop match**: over 4 s starting 5 s after the loop point (at 40% of the loop for short songs), how well the 10 ms volume envelopes of the first and second passes agree (correlation).
- Songs with a lot of percussion (taiko, snare, woodblock, timpani, stab) put unpitched energy into the recording, which lowers the score-note ratio (chase 0.70, oyura 0.72). Low chord-tone ratios belong to the deliberately dissonant songs (horror's clusters 0.38, oyura's shō clusters 0.37). Passing tones and tensions in the melodies are also counted as outside the chord.

Other checks:

- Balance against the accompaniment: the level of each part was compared using recordings with one channel at a time (analysis during the work) and fixed so that the main melody is not buried. At first, night's piano was 4 dB quieter than the strings, and in chase and staff the bass was louder than the melody.
- Ports: while a song played, port 2 was "song number + 1". The beat count on port 3 matched the value computed from the recording length within ±1 (badend stops counting when the song ends, so it is lower than the computed value).
- Loops: the driver's loop is exact to the DSP sample. In horror, the position of the second pass matched "ticks × divider × 4 samples" (854,016) to within 1 sample. The envelopes matched at 0.996 or better for every song except legend. Some songs have a low correlation of the raw waveform because the phase of long sustained notes drifts: depending on how the 100 Hz clock and the tempo clock line up, key-ons move by a few samples (under 1 ms). This is not an audible difference. The step in the sound at the seam is about the same as when the loop point is first reached on the first pass, and it never goes silent.

### Sound effects (`sfx`)

None of them clip. Onset is about 1 ms after the command. The largest peaks are thunder 23,554 and thud 23,258. The bell takes 5.3 s to reach -40 dB, and the hum, fundamental, minor third, fifth, nominal and their pairs came out at the designed ratios (0.5 / 1.0 / 1.007 / 1.19 / 1.51 / 2.0). The stroke times were as written: heart 0 / 0.74 / 1.49 / 2.24 s, knock 0 / 0.15 / 0.31 s, tick every 0.5 s.

Layering loud sound effects (thunder, thud, shock, door_bang, heart) at various times over the loudest songs (chase, deduce, unease) did not clip (maximum peak 26,672 = -1.8 dBFS).

### Interface checks (`protocol`, all passed)

| Item | Result |
|---|---|
| `$60` fade | Port 2 goes to 0 in 0.85 s, silent afterwards |
| `$61` stop | Port 2 is 0. RMS 0.5 s later is 7 |
| `$30` mute | Song, rain and sound effects (sent while muted) all peak at exactly 0. `$31` restores |
| `$62` ducking | -8.1 dB |
| Switching songs every frame (18 times) | The last song plays correctly and port 2 is correct |
| Layering | Song + storm + thunder + bell + shock together: no clipping, and the song keeps playing |
| `$64` stop sound effects | Gone, including the echo tail, in 0.8 s |
| `$7F` stop ambience | Silent after 1.5 s |
| badend | Port 2 goes to 0 when it ends |

## Not checked, and limitations

- **Not listened to by human ears.** What was checked is only the waveforms and figures (pitch, harmony, volume, clipping, loops, interface) and a visual look at spectrograms. Whether the songs are good as music, whether the rain sounds like rain, and whether the bell is eerie must be judged by actually listening. Figures can only confirm that things "sound as designed".
- Not checked on real hardware. The only emulator used is Snes9x 1.63.
- The rain shares a voice with slot B. While a two-slot sound effect (thunder etc.) plays, the raindrops stop (mostly masked by the thunder). Giving the rain and the songs separate voices would have meant cutting the songs to 5 voices, so this was the choice.
- Song loops are 24 to 72 s (staff has 82 s before its loop). In long reading scenes they repeat many times. 8.3 KB is free and can be used to lengthen the songs.
- The scream sound effect is not made.
- The "score-note ratio" and "chord-tone ratio" come out low for songs with percussion and dissonance. They are rough guides, not pass/fail criteria.
