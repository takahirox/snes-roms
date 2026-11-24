use crate::*;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub fn sprite_frame<'a>(sprite: &'a Sprite, frame: Option<&str>) -> Result<&'a Frame> {
    match frame {
        Some(id) => sprite.frames.iter().find(|frame| frame.id == id),
        None => sprite.frames.first(),
    }
    .ok_or_else(|| invalid("Sprite frame does not exist"))
}

pub fn frame_at(sprite: &Sprite, elapsed_ms: u64) -> Option<&Frame> {
    let duration: u64 = sprite
        .frames
        .iter()
        .map(|frame| u64::from(frame.duration_ms))
        .sum();
    if duration == 0 {
        return None;
    }
    let mut position = elapsed_ms % duration;
    sprite.frames.iter().find(|frame| {
        let duration = u64::from(frame.duration_ms);
        if position < duration {
            true
        } else {
            position -= duration;
            false
        }
    })
}

pub fn over_budget_line(sprite: &Sprite, frame: &Frame) -> Option<u16> {
    // The preview uses a 256-pixel coordinate space. Validate up to the full
    // 239 active lines of non-interlaced overscan.
    let mut objects = [0_u16; 239];
    let mut fetches = [0_u16; 239];
    for object in frame.objects.iter().take(129) {
        let (width, height) = object_size(sprite.size_mode, object.large)?;
        let tiles = (0..width / 8)
            .filter(|column| {
                let x = i32::from(object.x) + i32::from(*column) * 8;
                object.x == -256 || (-7..256).contains(&x)
            })
            .count() as u16;
        if tiles == 0 {
            continue;
        }
        for row in 0..height {
            let y = (i32::from(object.y) + i32::from(row)).rem_euclid(256) as usize;
            if y < objects.len() {
                objects[y] += 1;
                fetches[y] += tiles;
            }
        }
    }
    objects
        .iter()
        .zip(fetches)
        .position(|(&objects, tiles)| objects > 32 || tiles > 34)
        .map(|line| line as u16)
}

pub(crate) fn object_placements(sprite: &Sprite, frame: &Frame) -> Result<Vec<usize>> {
    if frame.objects.len() > 128 {
        return Err(invalid("There are more than 128 OBJs"));
    }
    type Shape<'a> = (usize, usize, &'a [Id]);
    let mut order: Vec<(usize, Shape<'_>)> = Vec::new();
    for (index, object) in frame.objects.iter().enumerate() {
        let (width, height) = object_size(sprite.size_mode, object.large)
            .ok_or_else(|| invalid("Invalid OBJ size mode"))?;
        order.push((
            index,
            (
                usize::from(height / 8),
                usize::from(width / 8),
                &object.tiles,
            ),
        ));
    }
    // Pack larger rectangles first and reuse identical tile rectangles.
    order.sort_by_key(|&(index, (rows, columns, _))| (std::cmp::Reverse(rows * columns), index));
    let mut occupied = [[0_u16; 16]; 2];
    let mut placed = BTreeMap::new();
    let mut placements = vec![0; order.len()];
    for (index, shape @ (rows, columns, _)) in order {
        if let Some(&start) = placed.get(&shape) {
            placements[index] = start;
            continue;
        }
        let mask = (1_u16 << columns) - 1;
        let (page, row, column) = (0..2)
            .flat_map(|page| {
                (0..=16 - rows)
                    .flat_map(move |row| (0..=16 - columns).map(move |column| (page, row, column)))
            })
            .find(|&(page, row, column)| {
                occupied[page][row..row + rows]
                    .iter()
                    .all(|bits| bits & (mask << column) == 0)
            })
            .ok_or_else(|| {
                Error::new(
                    "object_tile_budget",
                    "",
                    "OBJ graphics do not fit in two 16×16 tile pages",
                )
            })?;
        for bits in &mut occupied[page][row..row + rows] {
            *bits |= mask << column;
        }
        let start = page * 256 + row * 16 + column;
        placed.insert(shape, start);
        placements[index] = start;
    }
    Ok(placements)
}

pub struct SpriteExport {
    pub oam: Vec<u8>,
    pub chr: Vec<u8>,
    pub cgram: Vec<u8>,
}

pub fn export_sprite(project: &Project, id: &str, frame: Option<&str>) -> Result<SpriteExport> {
    require_valid_content(project)?;
    let Asset::Sprite(sprite) = asset(project, id)? else {
        return Err(invalid("Expected a sprite"));
    };
    let frame = sprite_frame(sprite, frame)?;
    let placements = object_placements(sprite, frame)?;
    let mut output = SpriteExport {
        oam: vec![0; 544],
        chr: vec![0; 16_384],
        cgram: vec![0; 256],
    };
    for index in 0..128 {
        // X=-255 hides unused objects without the X=-256 fetch quirk.
        output.oam[index * 4] = 1;
        output.oam[512 + index / 4] |= 1 << (index % 4 * 2);
    }
    for (index, (object, start)) in frame.objects.iter().zip(placements).enumerate() {
        let attribute = ((start / 256) as u8)
            | (object.palette_slot << 1)
            | (object.priority << 4)
            | (u8::from(object.flip_x) << 6)
            | (u8::from(object.flip_y) << 7);
        output.oam[index * 4..index * 4 + 4].copy_from_slice(&[
            object.x as u8,
            object.y as u8,
            start as u8,
            attribute,
        ]);
        let shift = index % 4 * 2;
        let high = u8::from(object.x < 0) | (u8::from(object.large) << 1);
        let byte = &mut output.oam[512 + index / 4];
        *byte = (*byte & !(3 << shift)) | (high << shift);

        let (width, _) = object_size(sprite.size_mode, object.large).unwrap();
        let columns = usize::from(width / 8);
        for (index, id) in object.tiles.iter().enumerate() {
            let Asset::Tile(tile) = &project.assets[id] else {
                unreachable!()
            };
            let offset = (start + index / columns * 16 + index % columns) * 32;
            output.chr[offset..offset + 32].copy_from_slice(&planar_tile(tile)?);
        }
        let Asset::Palette(palette) = &project.assets[&object.palette] else {
            unreachable!()
        };
        let offset = usize::from(object.palette_slot) * 32;
        for (index, color) in palette.colors.iter().enumerate() {
            output.cgram[offset + index * 2..offset + index * 2 + 2]
                .copy_from_slice(&color.to_le_bytes());
        }
    }
    Ok(output)
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RomLayout {
    LoRom,
    HiRom,
    ExHiRom,
}

#[derive(Debug, Serialize)]
pub struct RomHeader {
    pub layout: RomLayout,
    pub copier_bytes: usize,
    pub header_offset: usize,
    pub file_rom_bytes: usize,
    pub title: String,
    pub map_mode: u8,
    pub cartridge_type: u8,
    pub rom_size_code: u8,
    pub ram_size_code: u8,
    pub region: u8,
    pub maker: u8,
    pub revision: u8,
    pub checksum: u16,
    pub checksum_complement: u16,
    pub checksum_pair_valid: bool,
    pub reset_vector: u16,
}

pub fn inspect_rom(bytes: &[u8], layout: RomLayout) -> Result<RomHeader> {
    let copier_bytes = if bytes.len() % 0x8000 == 512 { 512 } else { 0 };
    let offset = copier_bytes
        + match layout {
            RomLayout::LoRom => 0x7fc0,
            RomLayout::HiRom => 0xffc0,
            RomLayout::ExHiRom => 0x40ffc0,
        };
    let header = bytes
        .get(offset..offset + 64)
        .ok_or_else(|| invalid("ROM is too short for the selected header offset"))?;
    let word = |index| u16::from_le_bytes([header[index], header[index + 1]]);
    let checksum = word(30);
    let checksum_complement = word(28);
    Ok(RomHeader {
        layout,
        copier_bytes,
        header_offset: offset,
        file_rom_bytes: bytes.len() - copier_bytes,
        title: String::from_utf8_lossy(&header[..21])
            .trim_end_matches([' ', '\0'])
            .into(),
        map_mode: header[21],
        cartridge_type: header[22],
        rom_size_code: header[23],
        ram_size_code: header[24],
        region: header[25],
        maker: header[26],
        revision: header[27],
        checksum,
        checksum_complement,
        checksum_pair_valid: checksum ^ checksum_complement == 0xffff,
        reset_vector: word(60),
    })
}

pub fn compress_rle(bytes: &[u8]) -> Result<Vec<u8>> {
    if bytes.len() > MAX_PROJECT_BYTES {
        return Err(invalid("RLE input exceeds 64 MiB"));
    }
    let mut output = b"SRL\x01".to_vec();
    output.extend_from_slice(&(bytes.len() as u32).to_le_bytes());
    let mut i = 0;
    while i < bytes.len() {
        let run = repeat_count(&bytes[i..]);
        if run >= 3 {
            output.extend_from_slice(&[0x80 | (run as u8 - 1), bytes[i]]);
            i += run;
        } else {
            let start = i;
            i += 1;
            while i < bytes.len() && i - start < 128 && repeat_count(&bytes[i..]) < 3 {
                i += 1;
            }
            output.push((i - start - 1) as u8);
            output.extend_from_slice(&bytes[start..i]);
        }
    }
    Ok(output)
}

fn repeat_count(bytes: &[u8]) -> usize {
    bytes
        .iter()
        .take(128)
        .take_while(|&&value| value == bytes[0])
        .count()
}

pub fn decompress_rle(bytes: &[u8]) -> Result<Vec<u8>> {
    if bytes.len() < 8 || !bytes.starts_with(b"SRL\x01") {
        return Err(invalid("Expected a Studio RLE v1 header"));
    }
    let size = u32::from_le_bytes(bytes[4..8].try_into().unwrap()) as usize;
    if size > MAX_PROJECT_BYTES {
        return Err(invalid("RLE output exceeds 64 MiB"));
    }
    let mut data = &bytes[8..];
    let mut output = Vec::with_capacity(size.min(data.len()));
    while let Some((&packet, tail)) = data.split_first() {
        let count = usize::from(packet & 0x7f) + 1;
        if output.len() + count > size {
            return Err(invalid("RLE data exceeds declared size"));
        }
        if packet & 0x80 == 0 {
            let (literal, tail) = tail
                .split_at_checked(count)
                .ok_or_else(|| invalid("Truncated RLE literal"))?;
            output.extend_from_slice(literal);
            data = tail;
        } else {
            let (&value, tail) = tail
                .split_first()
                .ok_or_else(|| invalid("Truncated RLE run"))?;
            output.resize(output.len() + count, value);
            data = tail;
        }
    }
    if output.len() != size {
        return Err(invalid("RLE size does not match header"));
    }
    Ok(output)
}
