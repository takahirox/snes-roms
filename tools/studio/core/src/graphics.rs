use crate::*;
use png::{BitDepth, ColorType, Transformations};
use serde::{Deserialize, Serialize};
use std::io::Cursor;

pub const fn color_limit(bpp: u8) -> u16 {
    match bpp {
        2 => 4,
        4 => 16,
        8 => 256,
        _ => 0,
    }
}

pub fn bgr555(rgb: [u8; 3]) -> u16 {
    let [r, g, b] = rgb.map(|value| (u16::from(value) * 31 + 127) / 255);
    r | (g << 5) | (b << 10)
}

pub fn rgb(color: u16) -> [u8; 3] {
    [0, 5, 10].map(|shift| {
        let value = (color >> shift) & 31;
        ((value << 3) | (value >> 2)) as u8
    })
}

pub fn quantize(palette: &Palette, rgba: [u8; 4], bpp: u8) -> Result<u8> {
    let count = palette.colors.len().min(usize::from(color_limit(bpp)));
    let transparent = palette
        .transparent
        .filter(|&index| usize::from(index) < count);
    if rgba[3] < 128 {
        return transparent
            .ok_or_else(|| invalid("Transparent pixels require a transparent palette index"));
    }
    nearest_bgr555(
        palette,
        count,
        transparent,
        bgr555([rgba[0], rgba[1], rgba[2]]),
    )
}

fn nearest_bgr555(
    palette: &Palette,
    count: usize,
    transparent: Option<u8>,
    target: u16,
) -> Result<u8> {
    palette.colors[..count]
        .iter()
        .enumerate()
        .filter(|&(index, _)| Some(index as u8) != transparent)
        .min_by_key(|&(_, color)| {
            [0, 5, 10]
                .into_iter()
                .map(|shift| {
                    let difference =
                        i32::from((color >> shift) & 31) - i32::from((target >> shift) & 31);
                    difference * difference
                })
                .sum::<i32>()
        })
        .map(|(index, _)| index as u8)
        .ok_or_else(|| invalid("No opaque colors are available at this bit depth"))
}

fn tile_fits(tile: &Tile, bpp: u8) -> Result<()> {
    let limit = color_limit(bpp);
    if limit == 0 {
        return Err(invalid("Bit depth must be 2, 4 or 8"));
    }
    if tile.pixels.len() != 64 || tile.pixels.iter().any(|&value| u16::from(value) >= limit) {
        return Err(Error::new(
            "tile_preview_bpp",
            "",
            format!("Tile indices do not fit in {bpp}bpp"),
        ));
    }
    Ok(())
}

pub fn planar_tile(tile: &Tile) -> Result<Vec<u8>> {
    tile_fits(tile, tile.bpp)?;
    let mut data = vec![0; usize::from(tile.bpp) * 8];
    for (offset, pixel) in tile.pixels.iter().enumerate() {
        let (x, y) = (offset % 8, offset / 8);
        for plane in 0..usize::from(tile.bpp) {
            let byte = (plane / 2) * 16 + y * 2 + plane % 2;
            data[byte] |= ((pixel >> plane) & 1) << (7 - x);
        }
    }
    Ok(data)
}

pub fn decode_planar_tile(bytes: &[u8], bpp: u8, palette: Id) -> Result<Tile> {
    if color_limit(bpp) == 0 || bytes.len() != usize::from(bpp) * 8 {
        return Err(invalid("Unexpected byte length for a 2, 4 or 8bpp tile"));
    }
    let mut pixels = vec![0; 64];
    for (offset, pixel) in pixels.iter_mut().enumerate() {
        let (x, y) = (offset % 8, offset / 8);
        for plane in 0..usize::from(bpp) {
            let byte = (plane / 2) * 16 + y * 2 + plane % 2;
            *pixel |= ((bytes[byte] >> (7 - x)) & 1) << plane;
        }
    }
    Ok(Tile {
        bpp,
        palette,
        pixels,
    })
}

#[derive(Clone, Debug, PartialEq)]
pub struct Image {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}

const MAX_IMAGE_SIDE: u32 = 4096;

pub(crate) fn checked_image(width: u32, height: u32) -> Result<usize> {
    let pixels = width.saturating_mul(height);
    if width == 0
        || height == 0
        || width > MAX_IMAGE_SIDE
        || height > MAX_IMAGE_SIDE
        || pixels > MAX_PIXELS as u32
    {
        return Err(invalid(
            "Image must be 1–4096 pixels per side and at most 4 megapixels",
        ));
    }
    Ok(pixels as usize)
}

impl Image {
    pub fn blank(width: u32, height: u32) -> Result<Self> {
        Ok(Self {
            width,
            height,
            rgba: vec![0; checked_image(width, height)? * 4],
        })
    }

    fn set(&mut self, x: i32, y: i32, rgba: [u8; 4]) {
        if x >= 0 && y >= 0 && (x as u32) < self.width && (y as u32) < self.height {
            let index = (y as usize * self.width as usize + x as usize) * 4;
            self.rgba[index..index + 4].copy_from_slice(&rgba);
        }
    }

    fn rect(&mut self, x: u32, y: u32, width: u32, height: u32, rgba: [u8; 4]) {
        for y in y..y + height {
            for x in x..x + width {
                self.set(x as i32, y as i32, rgba);
            }
        }
    }

    pub fn png(&self) -> Result<Vec<u8>> {
        if self.rgba.len() != checked_image(self.width, self.height)? * 4 {
            return Err(invalid(
                "RGBA buffer length does not match image dimensions",
            ));
        }
        encode_png(
            self.width,
            self.height,
            ColorType::Rgba,
            BitDepth::Eight,
            None,
            &self.rgba,
        )
    }
}

fn png_error(error: impl std::fmt::Display) -> Error {
    Error::new("png", "", error.to_string())
}

fn encode_png(
    width: u32,
    height: u32,
    color: ColorType,
    depth: BitDepth,
    palette: Option<&Palette>,
    pixels: &[u8],
) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    let mut encoder = png::Encoder::new(&mut bytes, width, height);
    encoder.set_color(color);
    encoder.set_depth(depth);
    if let Some(palette) = palette {
        encoder.set_palette(
            palette
                .colors
                .iter()
                .flat_map(|&color| rgb(color))
                .collect::<Vec<_>>(),
        );
        if let Some(index) = palette.transparent {
            let mut alpha = vec![255; usize::from(index) + 1];
            alpha[usize::from(index)] = 0;
            encoder.set_trns(alpha);
        }
    }
    let mut writer = encoder.write_header().map_err(png_error)?;
    writer.write_image_data(pixels).map_err(png_error)?;
    writer.finish().map_err(png_error)?;
    Ok(bytes)
}

pub fn export_indexed(project: &Project, id: &str, bpp: Option<u8>) -> Result<Vec<u8>> {
    require_valid(project)?;
    let Asset::Tile(tile) = asset(project, id)? else {
        return Err(invalid("Expected a tile"));
    };
    let bpp = bpp.unwrap_or(tile.bpp);
    let depth = match bpp {
        2 => BitDepth::Two,
        4 => BitDepth::Four,
        8 => BitDepth::Eight,
        _ => return Err(invalid("Bit depth must be 2, 4 or 8")),
    };
    let count = usize::from(color_limit(bpp));
    tile_fits(tile, bpp)?;
    let mut palette = palette(project, &tile.palette).clone();
    palette.colors.truncate(count);
    palette.transparent = palette
        .transparent
        .filter(|&index| usize::from(index) < count);
    let mut packed = vec![0; usize::from(bpp) * 8];
    let per_byte = 8 / usize::from(bpp);
    for (index, pixel) in tile.pixels.iter().enumerate() {
        packed[index / per_byte] |= pixel << ((per_byte - 1 - index % per_byte) * usize::from(bpp));
    }
    encode_png(8, 8, ColorType::Indexed, depth, Some(&palette), &packed)
}

pub(crate) fn asset<'a>(project: &'a Project, id: &str) -> Result<&'a Asset> {
    project
        .assets
        .get(id)
        .ok_or_else(|| Error::new("missing_asset", id, "Asset ID does not exist"))
}

// These lookups are used after project validation.
fn palette<'a>(project: &'a Project, id: &str) -> &'a Palette {
    let Asset::Palette(value) = &project.assets[id] else {
        unreachable!()
    };
    value
}

fn tile<'a>(project: &'a Project, id: &str) -> &'a Tile {
    let Asset::Tile(value) = &project.assets[id] else {
        unreachable!()
    };
    value
}

#[derive(Clone, Copy, Default)]
struct Placement {
    x: i32,
    y: i32,
    flip_x: bool,
    flip_y: bool,
}

fn draw_tile(
    image: &mut Image,
    project: &Project,
    tile: &Tile,
    palette_id: Option<&str>,
    position: Placement,
) {
    let palette = palette(project, palette_id.unwrap_or(&tile.palette));
    for (offset, &index) in tile.pixels.iter().enumerate() {
        if Some(index) != palette.transparent {
            let (x, y) = (offset as i32 % 8, offset as i32 / 8);
            let x = if position.flip_x { 7 - x } else { x };
            let y = if position.flip_y { 7 - y } else { y };
            let [r, g, b] = rgb(palette.colors[usize::from(index)]);
            image.set(position.x + x, position.y + y, [r, g, b, 255]);
        }
    }
}

fn draw_metatile(
    image: &mut Image,
    project: &Project,
    metatile: &Metatile,
    palette: Option<&str>,
    position: Placement,
) {
    for (index, reference) in metatile.cells.iter().enumerate() {
        let Some(reference) = reference else { continue };
        let (width, height) = (i32::from(metatile.width), i32::from(metatile.height));
        let (x, y) = (index as i32 % width, index as i32 / width);
        let x = if position.flip_x { width - 1 - x } else { x };
        let y = if position.flip_y { height - 1 - y } else { y };
        draw_tile(
            image,
            project,
            tile(project, &reference.tile),
            palette.or(reference.palette.as_deref()),
            Placement {
                x: position.x + x * 8,
                y: position.y + y * 8,
                flip_x: position.flip_x ^ reference.flip_x,
                flip_y: position.flip_y ^ reference.flip_y,
            },
        );
    }
}

fn draw_sprite(image: &mut Image, project: &Project, sprite: &Sprite, frame: &Frame) {
    // Earlier OAM entries win an overlap between objects.
    for object in frame.objects.iter().rev() {
        let (width, _) = object_size(sprite.size_mode, object.large).unwrap();
        let columns = i32::from(width / 8);
        for (index, id) in object.tiles.iter().enumerate() {
            let (column, row) = (index as i32 % columns, index as i32 / columns);
            let column = if object.flip_x {
                columns - 1 - column
            } else {
                column
            };
            // Hardware flips each square half of a rectangular OBJ independently.
            let row = if object.flip_y {
                row / columns * columns + columns - 1 - row % columns
            } else {
                row
            };
            let x = i32::from(object.x) + column * 8;
            let y = (i32::from(object.y) + row * 8).rem_euclid(256);
            draw_tile(
                image,
                project,
                tile(project, id),
                Some(&object.palette),
                Placement {
                    x,
                    y,
                    flip_x: object.flip_x,
                    flip_y: object.flip_y,
                },
            );
            if y > 248 {
                draw_tile(
                    image,
                    project,
                    tile(project, id),
                    Some(&object.palette),
                    Placement {
                        x,
                        y: y - 256,
                        flip_x: object.flip_x,
                        flip_y: object.flip_y,
                    },
                );
            }
        }
    }
}

pub fn render_tile_preview(project: &Project, id: &str, bpp: u8) -> Result<Image> {
    let Asset::Tile(tile) = asset(project, id)? else {
        return Err(invalid(
            "A bit depth override for an RGBA preview needs a tile",
        ));
    };
    tile_fits(tile, bpp)?;
    render(project, id, None, None)
}

pub fn render(
    project: &Project,
    id: &str,
    frame: Option<&str>,
    text: Option<&str>,
) -> Result<Image> {
    require_valid(project)?;
    let selected = asset(project, id)?;
    if (frame.is_some() && !matches!(selected, Asset::Sprite(_)))
        || (text.is_some() && !matches!(selected, Asset::Font(_)))
    {
        return Err(invalid(
            "Use a frame ID with sprites or preview text with fonts",
        ));
    }
    let origin = Placement::default();
    match selected {
        Asset::Palette(palette) => {
            let mut image = Image::blank(128, (palette.colors.len() as u32).div_ceil(16) * 8)?;
            for (index, &color) in palette.colors.iter().enumerate() {
                if Some(index as u8) != palette.transparent {
                    let [r, g, b] = rgb(color);
                    image.rect(
                        index as u32 % 16 * 8,
                        index as u32 / 16 * 8,
                        8,
                        8,
                        [r, g, b, 255],
                    );
                }
            }
            Ok(image)
        }
        Asset::Tile(tile) => {
            let mut image = Image::blank(8, 8)?;
            draw_tile(&mut image, project, tile, None, origin);
            Ok(image)
        }
        Asset::Metatile(metatile) => {
            let mut image = Image::blank(
                u32::from(metatile.width) * 8,
                u32::from(metatile.height) * 8,
            )?;
            draw_metatile(&mut image, project, metatile, None, origin);
            Ok(image)
        }
        Asset::Tileset(tileset) => render_tileset(project, tileset),
        Asset::Map(map) => {
            let cell_width = i32::from(map.cell_width) * 8;
            let cell_height = i32::from(map.cell_height) * 8;
            let mut image = Image::blank(
                u32::from(map.width) * cell_width as u32,
                u32::from(map.height) * cell_height as u32,
            )?;
            for layer in map.layers.iter().filter(|layer| layer.visible) {
                for (index, cell) in layer.cells.iter().enumerate() {
                    let Some(cell) = cell else { continue };
                    let position = Placement {
                        x: index as i32 % i32::from(map.width) * cell_width,
                        y: index as i32 / i32::from(map.width) * cell_height,
                        flip_x: cell.flip_x,
                        flip_y: cell.flip_y,
                    };
                    match &project.assets[&cell.asset] {
                        Asset::Tile(tile) => {
                            draw_tile(&mut image, project, tile, cell.palette.as_deref(), position)
                        }
                        Asset::Metatile(metatile) => draw_metatile(
                            &mut image,
                            project,
                            metatile,
                            cell.palette.as_deref(),
                            position,
                        ),
                        _ => unreachable!(),
                    }
                }
            }
            Ok(image)
        }
        Asset::Sprite(sprite) => {
            let frame = sprite_frame(sprite, frame)?;
            let mut image = Image::blank(u32::from(sprite.width), u32::from(sprite.height))?;
            draw_sprite(&mut image, project, sprite, frame);
            Ok(image)
        }
        Asset::Font(font) => render_font(project, font, text),
        Asset::Vram(vram) => {
            let mut image = Image::blank(256, 256)?;
            image.rect(0, 0, 256, 256, [25, 30, 43, 255]);
            for region in vram.regions.values() {
                let color = match region.purpose {
                    RegionPurpose::BgTiles => [86, 164, 252, 255],
                    RegionPurpose::BgMap => [111, 224, 186, 255],
                    RegionPurpose::ObjTiles => [250, 156, 132, 255],
                    RegionPurpose::Other => [204, 181, 252, 255],
                };
                for address in region.start..region.start + region.bytes {
                    image.set((address % 256) as i32, (address / 256) as i32, color);
                }
            }
            Ok(image)
        }
        Asset::Sample(_) | Asset::Sequence(_) => waveform(&audio_preview(project, id)?),
    }
}

fn waveform(sample: &Sample) -> Result<Image> {
    let mut image = Image::blank(512, 128)?;
    image.rect(0, 0, 512, 128, [25, 30, 43, 255]);
    image.rect(0, 64, 512, 1, [73, 87, 104, 255]);
    let y = |sample: i16| ((32_767 - i32::from(sample)) * 127 / 65_535) as u32;
    for x in 0..512 {
        let start = x * sample.pcm.len() / 512;
        let end = ((x + 1) * sample.pcm.len() / 512).max(start + 1);
        let mut min = i16::MAX;
        let mut max = i16::MIN;
        for &value in &sample.pcm[start..end] {
            min = min.min(value);
            max = max.max(value);
        }
        image.rect(
            x as u32,
            y(max),
            1,
            y(min) - y(max) + 1,
            [111, 224, 186, 255],
        );
    }
    if let Some(start) = sample.loop_start {
        let x = start * 512 / sample.pcm.len() as u32;
        image.rect(x, 0, 1, 128, [250, 156, 132, 255]);
    }
    Ok(image)
}

fn blank_atlas(
    count: usize,
    cell_width: u32,
    cell_height: u32,
    preferred_columns: usize,
) -> Result<(Image, usize)> {
    let count = count.max(1);
    let max_columns = count.min((MAX_IMAGE_SIDE / cell_width) as usize);
    let max_rows = (MAX_IMAGE_SIDE / cell_height) as usize;
    let preferred = preferred_columns.min(max_columns);
    // Try the usual width first. Narrower layouts can fit when row padding
    // would push all wider layouts over the pixel budget.
    for columns in (preferred..=max_columns).chain(1..preferred) {
        let rows = count.div_ceil(columns);
        if rows <= max_rows {
            let width = columns as u32 * cell_width;
            let height = rows as u32 * cell_height;
            if width * height <= MAX_PIXELS as u32 {
                return Ok((Image::blank(width, height)?, columns));
            }
        }
    }
    Err(invalid(
        "Atlas does not fit within the preview image limits",
    ))
}

fn render_tileset(project: &Project, tileset: &Tileset) -> Result<Image> {
    let count = tileset.tiles.len() + tileset.metatiles.len();
    let (mut width, mut height) = (8, 8);
    for id in &tileset.metatiles {
        if let Asset::Metatile(metatile) = &project.assets[id] {
            width = width.max(u32::from(metatile.width) * 8);
            height = height.max(u32::from(metatile.height) * 8);
        }
    }
    let (mut image, columns) = blank_atlas(count, width, height, 8)?;
    for (index, id) in tileset.tiles.iter().chain(&tileset.metatiles).enumerate() {
        let position = Placement {
            x: (index % columns) as i32 * width as i32,
            y: (index / columns) as i32 * height as i32,
            ..Placement::default()
        };
        match &project.assets[id] {
            Asset::Tile(tile) => draw_tile(&mut image, project, tile, None, position),
            Asset::Metatile(metatile) => {
                draw_metatile(&mut image, project, metatile, None, position)
            }
            _ => unreachable!(),
        }
    }
    Ok(image)
}

fn render_font(project: &Project, font: &Font, text: Option<&str>) -> Result<Image> {
    if let Some(text) = text {
        let mut positions = Vec::new();
        let (mut x, mut y, mut width) = (0_u32, 0_u32, 1_u32);
        for character in text.chars() {
            if character == '\n' {
                y += 8;
                x = 0;
            } else {
                let glyph = font.glyphs.get(&character).ok_or_else(|| {
                    invalid(format!("Missing glyph U+{:04X}", u32::from(character)))
                })?;
                positions.push((x, y, &glyph.tile));
                width = width.max(x + 8);
                x += u32::from(glyph.advance);
            }
            checked_image(width, y + 8)?;
        }
        let mut image = Image::blank(width, y + 8)?;
        for (x, y, id) in positions {
            draw_tile(
                &mut image,
                project,
                tile(project, id),
                None,
                Placement {
                    x: x as i32,
                    y: y as i32,
                    ..Placement::default()
                },
            );
        }
        Ok(image)
    } else {
        let (mut image, columns) = blank_atlas(font.glyphs.len(), 8, 8, 16)?;
        for (index, glyph) in font.glyphs.values().enumerate() {
            draw_tile(
                &mut image,
                project,
                tile(project, &glyph.tile),
                None,
                Placement {
                    x: (index % columns * 8) as i32,
                    y: (index / columns * 8) as i32,
                    ..Placement::default()
                },
            );
        }
        Ok(image)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ImageImport {
    pub tileset: Id,
    pub palette: Id,
    pub bpp: u8,
    pub preserve_indices: bool,
}

pub fn import_png(project: &Project, bytes: &[u8], options: &ImageImport) -> Result<Vec<Edit>> {
    let count = usize::from(color_limit(options.bpp));
    if count == 0 {
        return Err(invalid("Bit depth must be 2, 4 or 8"));
    }
    let transforms = if options.preserve_indices {
        Transformations::IDENTITY
    } else {
        Transformations::normalize_to_color8()
    };
    let mut decoder = png::Decoder::new(Cursor::new(bytes));
    decoder.set_transformations(transforms);
    let mut reader = decoder.read_info().map_err(png_error)?;
    let info = reader.info();
    let (width, height) = (info.width, info.height);
    checked_image(width, height)?;
    if width % 8 != 0 || height % 8 != 0 {
        return Err(invalid("PNG dimensions must be multiples of 8"));
    }
    let mut edits = Vec::new();
    let palette = if options.preserve_indices {
        if info.color_type != ColorType::Indexed
            || project.assets.contains_key(&options.palette)
            || options.palette == options.tileset
        {
            return Err(invalid(
                "Preserving indices needs an indexed PNG and a new palette ID",
            ));
        }
        let colors: Vec<_> = info
            .palette
            .as_deref()
            .unwrap_or_default()
            .chunks_exact(3)
            .map(|entry| bgr555([entry[0], entry[1], entry[2]]))
            .collect();
        if colors.is_empty() || colors.len() > count {
            return Err(invalid(
                "PNG palette size does not fit the requested bit depth",
            ));
        }
        let mut transparent = None;
        for (index, &alpha) in info.trns.as_deref().unwrap_or_default().iter().enumerate() {
            match alpha {
                255 => {}
                0 if transparent.is_none() && index < colors.len() => {
                    transparent = Some(index as u8)
                }
                _ => {
                    return Err(invalid(
                        "Studio indexed PNGs support one fully transparent entry",
                    ));
                }
            }
        }
        let palette = Palette {
            colors,
            transparent,
        };
        edits.push(Edit::Put {
            id: options.palette.clone(),
            asset: Asset::Palette(palette.clone()),
        });
        palette
    } else {
        let Asset::Palette(palette) = asset(project, &options.palette)? else {
            return Err(invalid("Expected a palette"));
        };
        palette.clone()
    };
    let mut decoded = vec![
        0;
        reader
            .output_buffer_size()
            .ok_or_else(|| invalid("PNG buffer is too large"))?
    ];
    let frame = reader.next_frame(&mut decoded).map_err(png_error)?;
    if (frame.width, frame.height) != (width, height) {
        return Err(invalid("Use a PNG with a full-size first frame"));
    }
    let mut indices = Vec::with_capacity(width as usize * height as usize);
    let depth = frame.bit_depth as usize;
    let mask = (1_usize << depth) - 1;
    let channels = frame.color_type.samples();
    let palette_entries = count.min(palette.colors.len());
    let transparent = palette
        .transparent
        .filter(|&index| usize::from(index) < palette_entries);
    let mut quantized = vec![None; 1 << 15];
    for row in decoded[..frame.buffer_size()].chunks_exact(frame.line_size) {
        for x in 0..width as usize {
            let index = if options.preserve_indices {
                let bit = x * depth;
                usize::from(row[bit / 8]) >> (8 - depth - bit % 8) & mask
            } else {
                let pixel = &row[x * channels..(x + 1) * channels];
                let rgba = match *pixel {
                    [gray] => [gray, gray, gray, 255],
                    [gray, alpha] => [gray, gray, gray, alpha],
                    [r, g, b] => [r, g, b, 255],
                    [r, g, b, a] => [r, g, b, a],
                    _ => unreachable!(),
                };
                if rgba[3] < 128 {
                    usize::from(transparent.ok_or_else(|| {
                        invalid("Transparent pixels require a transparent palette index")
                    })?)
                } else {
                    let target = bgr555([rgba[0], rgba[1], rgba[2]]);
                    let entry = &mut quantized[usize::from(target)];
                    let index = match *entry {
                        Some(index) => index,
                        None => *entry.insert(nearest_bgr555(
                            &palette,
                            palette_entries,
                            transparent,
                            target,
                        )?),
                    };
                    usize::from(index)
                }
            };
            if index >= palette.colors.len() {
                return Err(invalid("PNG references a missing palette entry"));
            }
            indices.push(index as u8);
        }
    }
    let mut ids = Vec::new();
    for y in (0..height as usize).step_by(8) {
        for x in (0..width as usize).step_by(8) {
            let id = format!("{}-{:04}", options.tileset, ids.len());
            if project.assets.contains_key(&id) || id == options.palette {
                return Err(invalid(format!("Asset {id} already exists")));
            }
            let mut pixels = Vec::with_capacity(64);
            for row in y..y + 8 {
                let offset = row * width as usize + x;
                pixels.extend_from_slice(&indices[offset..offset + 8]);
            }
            ids.push(id.clone());
            edits.push(Edit::Put {
                id,
                asset: Asset::Tile(Tile {
                    bpp: options.bpp,
                    palette: options.palette.clone(),
                    pixels,
                }),
            });
        }
    }
    if project.assets.contains_key(&options.tileset) {
        return Err(invalid(format!("Asset {} already exists", options.tileset)));
    }
    edits.push(Edit::Put {
        id: options.tileset.clone(),
        asset: Asset::Tileset(Tileset {
            tiles: ids,
            metatiles: Vec::new(),
        }),
    });
    Ok(edits)
}
