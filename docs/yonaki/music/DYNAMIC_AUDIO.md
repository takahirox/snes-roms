# Yonaki SPC700 resource loading and command reliability

The resident image fits all 18 songs, effects and ambience with 8,309 bytes free before the echo buffer. Two score buffers would recover 8,650 bytes. A shorter upload reduced the test ROM's IPL boot by 15 frames. The shipping game already waits 150 NMIs before initializing the presentation, so that upload saving would fit inside an existing wait. Keep the resident image for the current soundtrack. A runtime loader would add a transfer deadline to each uncached transition and is only worth testing when a concrete resource no longer fits.

## RAM and transfer measurements

| SPC RAM range | Bytes | Contents |
| --- | ---: | --- |
| `$0000–$01FF` | 512 | Working RAM, memory-mapped I/O, channel arrays and stack |
| `$0200–$1048` | 3,657 | Driver and fixed tables, including song and effect pointers |
| `$1049–$10FF` | 183 | DIR alignment padding |
| `$1100–$11FF` | 256 | Sample directory, 36 of 64 slots used |
| `$1200–$8FE4` | 32,229 | BRR samples |
| `$8FE5–$94E8` | 1,284 | Effect bytecode |
| `$94E9–$BE58` | 10,608 | Music bytecode |
| `$BE59–$BF8A` | 306 | Music headers and channel pointers |
| `$BF8B–$DFFF` | 8,309 | Free |
| `$E000–$FFFF` | 8,192 | DSP echo, 64 ms |

The size experiment recompiles each score at a shared destination with Yonaki's compiler. It counts each sequence, its 5-byte header and its six 16-bit channel pointers. The common prefix is 37,609 bytes, including all BRR, effects and ambience data. The 18 score banks total 10,914 bytes and range from 207 bytes (`badend`) to 1,132 bytes (`staff`). `title` is 683 bytes and `journey` is 571 bytes. One 1,132-byte window would leave 18,091 bytes free. Two such windows would leave 16,959 bytes free before any new loader code, bookkeeping or alignment. Absolute score loop and channel pointers would need to be linked for the chosen window or relocated during loading.

| Snes9x 1.63 measurement | Result |
| --- | --- |
| Game reset to visible `$5A` readiness flag | Host frame 108, with 103 NMIs elapsed between enabling NMI for audio init and recording readiness |
| Game reset to first command sent | Host frame 172 |
| Review ROM reset to `$5A`, 48,523 bytes uploaded | Frame 79 |
| Review ROM reset to `$5A`, 38,292-byte prefix | Frame 64 |
| Bell and title onset from the command frame | 1 ms and 26 ms, respectively |
| `title` to `journey` with storm playing | Mix first differs from a control recording after 9 ms |
| Port 2 reports the new song under storm playback | By the next frame's read for all 18 songs, including `journey` to `title` with thunder active |
| One switch per frame | All 18 song IDs observed in order |

The review ROM samples port 2 immediately after writing the command and again at the next frame, about 16.64 ms later. Port 2 reports song setup. The PCM threshold is 200 on the 16-bit mono mix or on the difference from the control mix. The measured difference includes the outgoing song's release. The short upload measures readiness only, using a prefix with the same byte count as the common data plus `title`. Boot measurements include echo clearing and driver initialization. The shipping ROM and review ROM have different reset code and IPL upload loops.

## Published loading designs

An early-versus-late SPC dump of Chunsoft's *Kamaitachi no Yoru* shows additional instrument samples arriving after song start. This is first-hand observation of the game's behavior. Yonaki's experiment uses its own compiler and data. [loveemu's SPC dump investigation](https://loveemu.hatenablog.com/entry/20091026/How_to_Fix_Chunsoft_SPC)

SNES GSS documents shared driver, samples and effects plus one exported sequence per song. Terrific Audio Driver uses shared data, supports time-sliced song loading, and documents separate queues for control and effects. At its default budget of 256 bytes per frame, Yonaki's score banks would consume 1–5 payload frames (3 for `journey`) before setup, validation and commit. This is a budget estimate for a possible Yonaki loader. Prefetch into an inactive window could pay that cost before the script asks for the switch. [SNES GSS export documentation](https://github.com/nathancassano/snesgss#export-and-use) · [Terrific Audio Driver API](https://github.com/undisbeliever/terrific-audio-driver/blob/main/audio-driver/pvsneslib-api/tad-audio.h) · [Loader timing and frame budget](https://undisbeliever.net/blog/20250313-smpspeed.html)

## Command and replacement behavior

- The IPL handshake echoes the byte counter on port 0 and transitions to the entry point after the final byte. `InitSpc` bounds its initial IPL and final driver-ready waits. The `$CC` and per-byte echo waits spin indefinitely if the peer stops responding. At runtime, `SndPump` writes the command on port 0 and changes the port 1 sequence once per frame. The driver polls after its timer work and sends no command acknowledgment. A delayed read can let a later send overwrite the earlier mailbox contents. [Nintendo developer manual, Book I, Appendix D](https://floating.muncher.se/bot/manual/book1_text.pdf)
- The 65816 FIFO accepts eight commands and drops the newest request at capacity. A full queue adds up to seven frames (about 116 ms) of delay to accepted commands at regular frame pacing. The generated stress fixture issued eight bells and then `horror` before the next frame. The first bell went out that frame and the other seven drained over the next seven sends. The rejected song still set `music_cur`. The retry after the drain was suppressed, while a subsequent `deduce` request was sent. `OpAmb` updates `amb_cur` ahead of enqueue in the same way. Separately, the SPC driver takes effect slot A first, then B, and replaces A when both are busy. A companion effect can also occupy B, which rain shares. This voice allocation is part of the current mix.
- A future reliability change could record acceptance explicitly and retain the head command until its sequence is acknowledged. A bounded wait, stale-ack and wraparound tests, and a defined recovery path would cover lost or delayed handshakes. Under saturation, protect story cues and music and ambience state changes ahead of UI sounds, while preserving the order of cues and transitions. Update request deduplication only once a command is queued successfully. Keep ordinary scheduling and voice allocation intact so the change affects overflow or transport failure only.
- For a banked loader, send an explicit destination and length into a reserved inactive range. Acknowledge each chunk, bound per-frame work so both SPC timers can run, and publish the complete bank at a command boundary. A partial or invalid transfer can then be discarded while the current song plays. Retain the active score until its channel and repeat pointers are quiescent.
- If BRR ever needs banking, keep common effects, ambience, and their loop targets resident. Stage complete BRR data and both DIR addresses under unused sample numbers. Publish those entries to the note scheduler only when the data is complete. Keep old banks pinned while a DSP voice can read either the initial or loop address, including during GAIN release. A voice flag in the sequencer can clear before its DSP envelope decays. The echo buffer has a separate fixed region. This approach preserves effect and ambience playback during a transfer and avoids replacing BRR under an active or releasing voice.

## Regression and recording comparison

The measurements on this page use PR #7 revision `393e52f06f0eb6fee58c666ae961102f06088ae6`. At that revision the rebuilt 4 MiB ROM was byte-identical to `dist/yonaki.sfc` (`b0b90ecf9d853f8c975f9c0045712966f114b1463e973a7b91434a97a141c3c7`). Snes9x 1.63 passed all 11 tests, including every one of the 20 story endings. bsnes 115 passed all 41 traces across 282,610 frames, covering the 20 fixture traces, all 20 story endings and the endings list. All final battery images matched byte for byte. The largest RGB channel difference across 73 screenshots was 2.

For the end-to-end PCM comparison, the 1,940-frame `real_E13` trace covers cold boot, title music, scene music, a rumble and the return to title. Each emulator replayed the same controller masks and initial battery image separately against the release and rebuild. Each within-core WAV pair is byte-identical, with first audio at 2.893 s on both. The core output rates differ.

| Core | Stereo sample frames | Hz | PCM SHA-256, both ROMs |
| --- | ---: | ---: | --- |
| Snes9x 1.63 | 1,034,714 | 32,040 | `98aba25df81f7e16665584ae7aef1d2869a2b406fa96cb2727d60e560808921c` |
| bsnes 115 | 1,548,800 | 48,000 | `39640cd04f9b6bec5f8db1af6371209ac14b473ebf9ebfe0cca31d3099cf534e` |

The Snes9x sound review reproduced every recorded metric in the checked-in review for 18 songs, 32 effects, rain, storm and rain under `night`. All nine protocol checks reproduced their reference results. The strongest isolated effect peaked at 23,554, and the layered playback check peaked at 18,730 with zero clipping. [Reference audio review](review/RESULT.json)

Run these checks from the repository root with the pinned dependencies from `tools/bootstrap.py --with-emulator`. Run all commands in the same checkout. `make yonaki-test` generates the `real_E13` trace and its ROM, and the profiler builds a separate baseline ROM from that checkout. Both ROMs must match the hash recorded in the trace before either replay starts. The release comparison above describes the published revision, and the results from the commands below describe your checkout.

```sh
make yonaki-test
python3 -I tests/yonaki/bsnes.py --real
python3 -I tools/yonaki/audio.py
python3 -I tests/yonaki/audio_profile.py
python3 -I tests/yonaki/music_review.py build/yonaki-audio/full-review --no-audio-files
```

The audio profile writes `RESULT.json` and lossless route WAVs under `build/yonaki-audio/profile/`. The audio review writes recording metrics to the specified output and can also write listening clips when run without `--no-audio-files`. Measurements cover the resident implementation on emulators. Hardware behavior and a live resource loader remain unmeasured.
