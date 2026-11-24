use crate::*;

const PREVIEW_RATE: u32 = 32_000;
const BRR_SILENT_END: [u8; 9] = [1, 0, 0, 0, 0, 0, 0, 0, 0];

fn sample_ok(sample: &Sample) -> Result<()> {
    if !(1..=192_000).contains(&sample.sample_rate)
        || sample.pcm.is_empty()
        || sample.pcm.len() > MAX_SAMPLES
        || sample
            .loop_start
            .is_some_and(|start| start as usize >= sample.pcm.len())
    {
        return Err(invalid("Invalid sample rate, length or loop start"));
    }
    Ok(())
}

fn le16(bytes: &[u8]) -> u16 {
    u16::from_le_bytes(bytes[..2].try_into().unwrap())
}

fn le32(bytes: &[u8]) -> u32 {
    u32::from_le_bytes(bytes[..4].try_into().unwrap())
}

pub fn read_wav(bytes: &[u8]) -> Result<Sample> {
    if bytes.len() < 12 || &bytes[..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return Err(invalid("Expected a RIFF/WAVE file"));
    }
    let size = le32(&bytes[4..8]) as usize;
    let mut chunks = bytes
        .get(12..size.saturating_add(8))
        .ok_or_else(|| invalid("Truncated RIFF/WAVE"))?;
    let (mut rate, mut pcm, mut loop_range) = (None, None, None);
    let mut seen_sampler = false;
    while !chunks.is_empty() {
        if chunks.len() < 8 {
            return Err(invalid("Truncated WAV chunk header"));
        }
        let length = le32(&chunks[4..8]) as usize;
        let payload = chunks
            .get(8..8_usize.saturating_add(length))
            .ok_or_else(|| invalid("Truncated WAV chunk"))?;
        match &chunks[..4] {
            b"fmt " => {
                if rate.is_some()
                    || length < 16
                    || le16(payload) != 1
                    || le16(&payload[2..]) != 1
                    || le16(&payload[12..]) != 2
                    || le16(&payload[14..]) != 16
                {
                    return Err(invalid("WAV must use uncompressed signed 16-bit mono PCM"));
                }
                rate = Some(le32(&payload[4..]));
            }
            b"data" => {
                if pcm.is_some() || !length.is_multiple_of(2) || length / 2 > MAX_SAMPLES {
                    return Err(invalid("Invalid WAV data length"));
                }
                pcm = Some(
                    payload
                        .chunks_exact(2)
                        .map(|sample| le16(sample) as i16)
                        .collect::<Vec<_>>(),
                );
            }
            b"smpl" => {
                if seen_sampler || length < 36 {
                    return Err(invalid("Invalid WAV sampler chunk"));
                }
                seen_sampler = true;
                match le32(&payload[28..]) {
                    0 => {}
                    1 if length >= 60
                        && le32(&payload[40..]) == 0
                        && le32(&payload[52..]) == 0
                        && le32(&payload[56..]) == 0 =>
                    {
                        loop_range = Some((le32(&payload[44..]), le32(&payload[48..])));
                    }
                    _ => return Err(invalid("WAV supports one continuous forward loop")),
                }
            }
            _ => {}
        }
        chunks = chunks
            .get(8_usize.saturating_add(length).saturating_add(length % 2)..)
            .ok_or_else(|| invalid("Missing WAV chunk padding"))?;
    }
    let pcm = pcm.ok_or_else(|| invalid("WAV has no data chunk"))?;
    if loop_range.is_some_and(|(_, end)| end.checked_add(1) != Some(pcm.len() as u32)) {
        return Err(invalid("WAV loop must end at the last sample"));
    }
    let sample = Sample {
        sample_rate: rate.ok_or_else(|| invalid("WAV has no format chunk"))?,
        pcm,
        loop_start: loop_range.map(|(start, _)| start),
    };
    sample_ok(&sample)?;
    Ok(sample)
}

pub fn write_wav(sample: &Sample) -> Result<Vec<u8>> {
    sample_ok(sample)?;
    let pcm_bytes = sample.pcm.len() as u32 * 2;
    let extra = if sample.loop_start.is_some() { 68 } else { 0 };
    let mut bytes = Vec::with_capacity((44 + pcm_bytes + extra) as usize);
    bytes.extend_from_slice(b"RIFF");
    bytes.extend_from_slice(&(36 + pcm_bytes + extra).to_le_bytes());
    bytes.extend_from_slice(b"WAVEfmt ");
    for word in [
        16_u32,
        0x0001_0001,
        sample.sample_rate,
        sample.sample_rate * 2,
        0x0010_0002,
    ] {
        bytes.extend_from_slice(&word.to_le_bytes());
    }
    bytes.extend_from_slice(b"data");
    bytes.extend_from_slice(&pcm_bytes.to_le_bytes());
    for pcm in &sample.pcm {
        bytes.extend_from_slice(&pcm.to_le_bytes());
    }
    if let Some(start) = sample.loop_start {
        bytes.extend_from_slice(b"smpl");
        for word in [
            60,
            0,
            0,
            1_000_000_000 / sample.sample_rate,
            60,
            0,
            0,
            0,
            1,
            0,
            0,
            0,
            start,
            sample.pcm.len() as u32 - 1,
            0,
            0,
        ] {
            bytes.extend_from_slice(&word.to_le_bytes());
        }
    }
    Ok(bytes)
}

pub fn trim_sample(sample: &Sample, start: u32, end: u32) -> Result<Sample> {
    sample_ok(sample)?;
    if start >= end || end as usize > sample.pcm.len() {
        return Err(invalid(
            "Trim interval must be nonempty and inside the sample",
        ));
    }
    Ok(Sample {
        sample_rate: sample.sample_rate,
        pcm: sample.pcm[start as usize..end as usize].to_vec(),
        loop_start: sample
            .loop_start
            .filter(|&loop_start| (start..end).contains(&loop_start))
            .map(|loop_start| loop_start - start),
    })
}

#[derive(Clone, Copy, Default)]
struct History {
    last: i32,
    previous: i32,
}

impl History {
    fn prediction(self, filter: u8) -> i32 {
        let (last, prior) = (self.last, self.previous / 2);
        match filter {
            0 => 0,
            1 => (last / 2) + (-last >> 5),
            2 => last - prior + (prior >> 4) + ((-3 * last) >> 6),
            3 => last - prior + ((3 * prior) >> 4) + ((-13 * last) >> 7),
            _ => unreachable!(),
        }
    }

    fn decode(&mut self, nibble: i32, shift: u8, filter: u8) -> i16 {
        let delta = if shift <= 12 {
            (nibble << shift) >> 1
        } else if nibble < 0 {
            -2048
        } else {
            0
        };
        let internal = (delta + self.prediction(filter)).clamp(-32_768, 32_767);
        let output = (internal * 2) as i16;
        self.previous = self.last;
        self.last = i32::from(output);
        output
    }
}

pub fn read_brr(bytes: &[u8], rate: u32, loop_offset: Option<u32>) -> Result<Sample> {
    // A silent terminator after the audio is a playback marker, not PCM.
    let audio = bytes
        .strip_suffix(&BRR_SILENT_END)
        .filter(|audio| !audio.is_empty())
        .unwrap_or(bytes);
    if bytes.is_empty() || !bytes.len().is_multiple_of(9) || audio.len() / 9 > MAX_SAMPLES / 16 {
        return Err(invalid(
            "Expected one or more complete nine-byte BRR blocks",
        ));
    }
    let loop_flag = bytes[bytes.len() - 9] & 2 != 0;
    if loop_flag != loop_offset.is_some()
        || loop_offset.is_some_and(|offset| offset % 9 != 0 || offset as usize >= bytes.len())
    {
        return Err(invalid(
            "A looping BRR stream needs an in-range loop byte offset divisible by 9",
        ));
    }
    let mut pcm = Vec::with_capacity(audio.len() / 9 * 16);
    let mut history = History::default();
    for (index, block) in audio.chunks_exact(9).enumerate() {
        let header = block[0];
        if (header & 1 != 0) != (index + 1 == bytes.len() / 9) {
            return Err(invalid("BRR end flag must appear on the final block only"));
        }
        for byte in &block[1..] {
            for nibble in [
                (*byte as i8 >> 4) as i32,
                (((*byte << 4) as i8) >> 4) as i32,
            ] {
                pcm.push(history.decode(nibble, header >> 4, (header >> 2) & 3));
            }
        }
    }
    let sample = Sample {
        sample_rate: rate,
        pcm,
        loop_start: loop_offset.map(|offset| offset / 9 * 16),
    };
    sample_ok(&sample)?;
    Ok(sample)
}

pub(crate) fn brr_size(sample: &Sample) -> usize {
    (sample.pcm.len().div_ceil(16) + usize::from(sample.loop_start.is_none())) * 9
}

pub fn write_brr(sample: &Sample) -> Result<Vec<u8>> {
    sample_ok(sample)?;
    if sample.loop_start.is_some_and(|start| start % 16 != 0) {
        return Err(invalid("BRR loop start must be divisible by 16 samples"));
    }
    let mut bytes = Vec::with_capacity(brr_size(sample));
    let mut history = History::default();
    for (index, chunk) in sample.pcm.chunks(16).enumerate() {
        let mut pcm = [0; 16];
        pcm[..chunk.len()].copy_from_slice(chunk);
        if let Some(start) = sample.loop_start.filter(|_| chunk.len() < 16) {
            // Continue the beginning of the loop through the padding.
            let loop_body = &sample.pcm[start as usize..];
            for (index, value) in pcm[chunk.len()..].iter_mut().enumerate() {
                *value = loop_body[index % loop_body.len()];
            }
        }
        let reset = index == 0 || sample.loop_start == Some(index as u32 * 16);
        let (block, next) = encode_block(&pcm, history, reset);
        bytes.extend_from_slice(&block);
        history = next;
    }
    if sample.loop_start.is_some() {
        let last_header = bytes.len() - 9;
        bytes[last_header] |= 3;
    } else {
        // END without LOOP mutes the S-DSP voice as soon as it sees the header.
        bytes.extend_from_slice(&BRR_SILENT_END);
    }
    Ok(bytes)
}

fn encode_block(pcm: &[i16; 16], history: History, reset: bool) -> ([u8; 9], History) {
    let mut best = (i64::MAX, [0; 9], history);
    for filter in 0..=if reset { 0 } else { 3 } {
        for shift in 0..=12 {
            let mut candidate = history;
            let mut block = [0_u8; 9];
            block[0] = shift << 4 | filter << 2;
            let mut total = 0;
            for (index, &target) in pcm.iter().enumerate() {
                let unscaled = (i32::from(target) - candidate.prediction(filter) * 2) >> shift;
                let base = unscaled.clamp(-8, 7);
                let (error, nibble) = [base, (base + 1).min(7), (base - 1).max(-8)]
                    .into_iter()
                    .map(|nibble| {
                        let value = candidate.clone().decode(nibble, shift, filter);
                        let difference = i64::from(value) - i64::from(target);
                        (difference * difference, nibble)
                    })
                    .min()
                    .unwrap();
                candidate.decode(nibble, shift, filter);
                block[1 + index / 2] |= (nibble as u8 & 15) << (4 - index % 2 * 4);
                total += error;
                if total >= best.0 {
                    break;
                }
            }
            if total < best.0 {
                best = (total, block, candidate);
            }
        }
    }
    (best.1, best.2)
}

pub fn audio_preview(project: &Project, id: &str) -> Result<Sample> {
    require_valid(project)?;
    match asset(project, id)? {
        Asset::Sample(sample) => Ok(sample.clone()),
        Asset::Sequence(sequence) => render_sequence(project, sequence),
        _ => Err(invalid("Expected a sample or sequence")),
    }
}

// Frequencies of MIDI notes 0–11 in units of 2^-20 Hz. Octaves are
// integer shifts, so oscillator output is identical in native and WASM.
fn frequency(note: u8) -> u64 {
    const OCTAVE: [u32; 12] = [
        8572947, 9082720, 9622807, 10195009, 10801236, 11443511, 12123977, 12844906, 13608704,
        14417920, 15275254, 16183568,
    ];
    u64::from(OCTAVE[usize::from(note % 12)]) << (note / 12)
}

fn render_sequence(project: &Project, sequence: &Sequence) -> Result<Sample> {
    let clock = u64::from(sequence.bpm) * u64::from(sequence.ticks_per_beat);
    let to_pcm = |tick| (u64::from(tick) * 60 * u64::from(PREVIEW_RATE) / clock) as usize;
    let length = sequence
        .tracks
        .iter()
        .filter_map(|track| track.notes.last())
        .map(|note| to_pcm(note.tick + note.length))
        .max()
        .unwrap_or(1)
        .max(1);
    let mut mix = vec![0_i32; length];
    for track in &sequence.tracks {
        let sample = if let Voice::Sample { asset, root_note } = &track.voice {
            let Asset::Sample(sample) = &project.assets[asset] else {
                unreachable!()
            };
            Some((sample, frequency(*root_note)))
        } else {
            None
        };
        for note in &track.notes {
            let frequency = frequency(note.pitch);
            let range = to_pcm(note.tick)..to_pcm(note.tick + note.length);
            let step = if let Some((sample, root)) = sample {
                ((u128::from(frequency) * u128::from(sample.sample_rate)) << 24)
                    / (u128::from(root) * u128::from(PREVIEW_RATE))
            } else {
                (u128::from(frequency) << 12) / u128::from(PREVIEW_RATE)
            } as u64;
            let mut phase = 0_u64;
            for output in &mut mix[range] {
                let value = match (&track.voice, sample) {
                    (_, Some((sample, _))) => {
                        let index = phase >> 24;
                        let length = sample.pcm.len() as u64;
                        let index = if index < length {
                            index
                        } else if let Some(start) = sample.loop_start {
                            let start = u64::from(start);
                            start + (index - start) % (length - start)
                        } else {
                            break;
                        };
                        i32::from(sample.pcm[index as usize])
                    }
                    (Voice::Square, _) => {
                        if phase as u32 & 0x8000_0000 == 0 {
                            8192
                        } else {
                            -8192
                        }
                    }
                    _ => {
                        let ramp = ((phase as u32) >> 16) as i32;
                        (16_384 - (ramp - 32_768).abs()) / 2
                    }
                };
                *output += value * i32::from(note.velocity) / 127;
                phase += step;
            }
        }
    }
    let pcm = mix
        .into_iter()
        .map(|value| value.clamp(-32_768, 32_767) as i16)
        .collect();
    Ok(Sample {
        sample_rate: PREVIEW_RATE,
        pcm,
        loop_start: None,
    })
}
