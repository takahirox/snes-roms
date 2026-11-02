# Speech sound (voice-like sound for text display) — design and verification method

Added in candidate E. While the body text of a page spoken by a character is being typed out, a short, round sound close to "po" plays, with a slightly different pitch and timbre per speaker. It is not a reading voice and is not matched to phonemes. Reference research: [REFERENCE_NOTES.md](REFERENCE_NOTES.md).

## When it plays and when it does not
- Plays: in the body text of pages from script lines `NAME> ` (the six people and 「わたし」 ("I", the player)), in frames where a character other than a "silent character" was actually drawn. It does not depend on whether a portrait is shown (波多野 (Hatano) without a portrait, わたし, and someone speaking in front of another person's portrait all use their own voice). The speaker is determined from the same body-text speaker code `$FFE0|id` used by the lip sync.
- Interval: at least 4 frames from one sound of the same speaker to the next (at normal speed about once every 2 characters, about 15 per second). Fast-forward with A/B (6 characters per frame) uses the same minimum interval, so sounds are thinned out instead of playing per character. Speech sounds are not queued, so they never keep playing late.
- Does not play: narration, the yellow person names, notebook / hint / system headings, lists and menus, page and end-of-text waits, scene changes, the title and ending, and while 「おと：なし」 (sound: off) is set. Punctuation, brackets, symbols and spaces (`silent:` in `data/adv/voices.txt`) do not sound. After punctuation, sound stops for the same number of frames as the lip sync (、= 4, 。= 8), and the next sound starts a new phrase (the pitch contour returns to its start).
- End: each sound fades out naturally in twenty-odd ms (a one-shot waveform with the decay built in). No new sound starts after a wait begins.
- Text speed, lip-sync motion, script, portraits, mouth shapes and save format are the same as in D.

## Sound data (`data/adv/voices.txt`)
Processing and data are separated. For each person the file gives the timbre (harmonic ratios), starting pitch, pitch fall, length, attack, volume and minimum interval. The small pitch ups and downs over 8 sounds within a phrase (`contour`, %) are in the same file.

| Speaker | Timbre | Pitch (Hz) | Fall | Length (ms) | Volume | Interval |
|---|---|---|---|---|---|---|
| 波多野 (Hatano) | round (1, .32, .10, .04) | 370 | −7% | 24 | 22 | 4 |
| 古賀 (Koga) | dark (1, .22, .05) | 300 | −8% | 28 | 24 | 4 |
| 辰巳 (Tatsumi) | soft (1, .45, .20, .08, .03) | 345 | −6% | 24 | 20 | 4 |
| ゆき子 (Yukiko) | soft | 540 | −5% | 22 | 18 | 4 |
| 大河内 (Ookouchi) | dark | 325 | −6% | 26 | 23 | 4 |
| 修一 (Shuichi) | round | 420 | −6% | 23 | 20 | 4 |
| わたし | round | 455 | −5% | 22 | 17 | 4 |

Phrase intonation: +2.0, +0.5, +1.0, 0, +0.5, −1.0, 0, −1.5 % (from the 9th sound on, the 5th–8th repeat).

## Waveforms (`tools/adv/voice.py`)
- All made from formulas (no recordings, existing sounds or material from other works). Sine harmonics are stacked, the pitch falls slightly over the length (a round "po"), and a raised-cosine attack and decay make it start at 0 and end at 0. Made for 16 kHz (DSP pitch $0800) and normalized to a peak of 12000.
- BRR conversion uses the same computation as S-DSP decoding (4 filters, range, 16-bit clamping and doubling) and searches each block for the filter and range with the smallest error. The first block uses filter 0, and at the end come 2 silent blocks and a silent end block (no loop). Since the DSP silences a one-shot sound as soon as it enters the end block, the waveform is brought back to 0 before that.
- 1710 bytes for 7 voices. `python3 -I tools/adv/voice.py --preview OUT.wav` is a synthesis for listening on a PC, not the hardware's Gaussian interpolation. It is not used for verification.

## SPC700 driver (`tools/adv/spc.py`)
- Voice 1 is dedicated to speech sounds. Sound effects (voice 0) and waves (voice 2) are unchanged. Voice 1 uses direct GAIN $7F; the shape of the sound is carried by the waveform itself. Key-off is not used.
- From the CPU it is received through a "latest one only" inbox separate from the sound-effect queue (ports 0/1, one command per frame): port 2 gets the voice number and a phrase-start mark, then the value of port 3 is changed. It is ignored while muted (`$30`). Speech sounds never fill the sound-effect / mute queue.
- A wait of more than 64 cycles was added after key-on. The DSP reads KON only once every 2 samples, so if key-ons for a sound effect and a speech sound are written back to back, the earlier one is lost.
- The table for the 7 voices (waveform number, volume, 8-step pitch) lives in the driver image, and the position of the volume table is emitted as `speech.spc` in `build/adv/layout.json` (used for the control ROM in the tests).
- The driver code is 952 bytes and the whole image 2834 bytes (1076 in D). The transfer at startup grew, but on Snes9x the title list appears at frame 14 (the test checks at frame 40).

## 65816 (`src/adv/voice.inc`, a few lines in `ui.inc` and `text.inc`)
- When `DrawGlyph` gets as far as drawing a character, it sets `g_drawn`. After drawing a character, `UpdateMsg` calls `VoiceGlyph`, which takes the punctuation stop length from the same table as the lip sync (`GlyphPause`) and counts only when the character was drawn, the body text has a speaker, and `GlyphVoice` is 1. Characters not shown on screen are not counted. The working variables for character drawing and DMA (DMA budget in t5, character count in t7) are not touched.
- `VoiceUpdate` (every frame, after the lip sync): when text is being typed, the body text has a speaker, there is no punctuation stop, the minimum interval has passed, sound is on, and the APU responds, it writes the speaker's voice number (`SpeakerVoice`) and the phrase-start mark to ports 2/3. If the APU did not respond, the game continues silently as before.
- The tables `GlyphVoice` / `SpeakerVoice` / `SpeakerGap` are generated by `build.py` from `voices.txt`. The build stops if a speaker in the script has no voice, if a name with a voice is not in the script, and so on.

## Verification method (`tests/adv/speech.py`, added to `make adv-test`)
Checked with the emulator's audio output (native PCM); internal counts alone are not enough to pass.
- Rule model: for every frame's processing, read the encoded body text in the ROM (around `msg_ptr`), compute "the sounds that should play" from the speaker code, silent characters, punctuation stops, minimum interval, waits and the sound setting, and match them against the send count and voice number in WRAM.
- PCM: for each sound that should play, find it by correlation with that voice's waveform (BRR decoded and resampled to the expected pitch). Where no other sound is present, measure length, peak, RMS, DC, largest step, clipping, true silence before it (160 samples of 0), first and last samples, pitch, and the 2nd-harmonic ratio. In frames where nothing may sound (indoors, 50 or more frames after any command: names, narration, menus, waits, punctuation stops, sound off), the PCM is exactly 0.
- Control ROM (null-volume twin): a ROM from the same source in which only the 7 bytes of the speech-sound volume table in the driver image are 0 (confirmed that only those 7 bytes and the checksum differ). Both are replayed with the same pad input; after confirming that the CPU's progress (mode, body-text position, send count, sound-effect commands…) agrees frame by frame, the PCM difference is taken. The difference is the sound of voice 1 alone: check that every sound that should play is in it with the expected waveform and volume, and that all other samples are 0. This also checks sounds inside the waves and overlapping sound effects, and at the same time shows that sound effects and waves are not changed by speech sounds.
- Fixture ROM (a ROM separate from the real one): a copy of the script with a line spoken by Hatano (in front of 修一 (Shuichi)'s portrait) on fast-forward right after the chime, plus a line by わたし (`build/adv-speechfixture/`, with the story diff, ROM, labels, layout and input recordings stored separately). The difference from the same fixture's control ROM confirms the speech sounds overlapping the chime and that everything other than the chime is 0; as a supplement, the pitch, order, length and strength of the chime's 4 notes are compared with the chime alone. It also confirms that the speaker's own pitch is used even in front of another person's portrait.
- Save compatibility with D: from a D save, D and E continue into the same state, speech sounds play after continuing, and D reads a save written by E identically.
- Two cores: replaying the same input recording on a fresh Snes9x gives byte-identical PCM. bsnes 115 (48 kHz) also replays the real and control ROMs; the difference contains every sound that should play, and everything else is 0. Differences from Snes9x (pitch, peak, start time within the frame) were measured to set tolerances. For the screen, the existing `tests/adv/bsnes.py` also replays and compares the speech-sound test's input recordings (RGB difference within 2, battery match).
- Short recordings for listening (`review`): 7 people, fast-forward and sound off rendered as WAV and MP4 with sound, plus waveform sheets. Pass/fail is decided by the tests above.
