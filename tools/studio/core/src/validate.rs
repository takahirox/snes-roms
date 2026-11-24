use crate::*;
use std::collections::{BTreeMap, BTreeSet};

pub fn validate(project: &Project) -> Vec<Diagnostic> {
    let mut validator = Validator {
        project,
        diagnostics: Vec::new(),
    };
    if project.version != VERSION {
        validator.error("version", "/version", format!("Expected version {VERSION}"));
    }
    if project.name.trim().is_empty() {
        validator.error("name", "/name", "Enter a project name");
    }
    for (id, asset) in &project.assets {
        let path = format!("/assets/{}", pointer(id));
        validator.check_id(id, &path);
        validator.asset(asset, &format!("{path}/data"));
    }
    validator.diagnostics
}

pub fn require_valid(project: &Project) -> Result<()> {
    let diagnostics = validate(project);
    if diagnostics.iter().any(|d| d.severity == Severity::Error) {
        Err(Error(diagnostics))
    } else {
        Ok(())
    }
}

fn pointer(id: &str) -> String {
    id.replace('~', "~0").replace('/', "~1")
}

struct Validator<'a> {
    project: &'a Project,
    diagnostics: Vec<Diagnostic>,
}

impl<'a> Validator<'a> {
    fn error(&mut self, code: &'static str, path: &str, message: impl Into<String>) {
        self.diagnostics.push(Diagnostic {
            severity: Severity::Error,
            code,
            path: path.into(),
            message: message.into(),
        });
    }

    fn warn(&mut self, code: &'static str, path: &str, message: impl Into<String>) {
        self.diagnostics.push(Diagnostic {
            severity: Severity::Warning,
            code,
            path: path.into(),
            message: message.into(),
        });
    }

    fn check_id(&mut self, id: &str, path: &str) {
        if id.is_empty()
            || id.len() > 64
            || !id.as_bytes()[0].is_ascii_alphanumeric()
            || !id
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || b"._-".contains(&byte))
        {
            self.error("id", path, "IDs use 1–64 ASCII letters, digits, dots, underscores or hyphens and start with a letter or digit");
        }
    }

    fn distinct(&mut self, id: &str, seen: &mut BTreeSet<String>, path: &str) {
        self.check_id(id, path);
        if !seen.insert(id.into()) {
            self.error("duplicate_id", path, format!("Duplicate ID {id}"));
        }
    }

    fn asset(&mut self, asset: &Asset, path: &str) {
        match asset {
            Asset::Palette(palette) => self.palette(palette, path),
            Asset::Tile(tile) => {
                if !matches!(tile.bpp, 2 | 4 | 8) {
                    self.error("bpp", path, "Expecting 2, 4 or 8 bits per pixel");
                }
                if tile.pixels.len() != 64 {
                    self.error("pixel_count", path, "An 8×8 tile needs exactly 64 pixels");
                }
                if tile
                    .pixels
                    .iter()
                    .any(|&index| u16::from(index) >= color_limit(tile.bpp))
                {
                    self.error("pixel_index", path, "A pixel exceeds the tile bit depth");
                }
                self.check_tile_palette(tile, &tile.palette, path);
            }
            Asset::Metatile(metatile) => {
                self.grid(
                    path,
                    metatile.width,
                    metatile.height,
                    8,
                    8,
                    metatile.cells.len(),
                );
                for (index, cell) in metatile.cells.iter().enumerate() {
                    if let Some(cell) = cell {
                        self.tile_ref(
                            &cell.tile,
                            cell.palette.as_deref(),
                            &format!("{path}/cells/{index}"),
                        );
                    }
                }
            }
            Asset::Tileset(tileset) => {
                let mut seen = BTreeSet::new();
                for (index, id) in tileset.tiles.iter().enumerate() {
                    let path = format!("{path}/tiles/{index}");
                    self.distinct(id, &mut seen, &path);
                    self.tile_ref(id, None, &path);
                }
                for (index, id) in tileset.metatiles.iter().enumerate() {
                    let path = format!("{path}/metatiles/{index}");
                    self.distinct(id, &mut seen, &path);
                    if !matches!(self.project.assets.get(id), Some(Asset::Metatile(_))) {
                        self.error("reference", &path, format!("Expected metatile {id}"));
                    }
                }
            }
            Asset::Map(map) => self.map(map, path),
            Asset::Sprite(sprite) => self.sprite(sprite, path),
            Asset::Font(font) => {
                if font.glyphs.is_empty() || font.glyphs.len() > MAX_PIXELS / 64 {
                    self.error("glyph_count", path, "A font needs 1–65,536 glyphs");
                }
                for (character, glyph) in &font.glyphs {
                    let path = format!("{path}/glyphs/{}", pointer(&character.to_string()));
                    if !(1..=32).contains(&glyph.advance) {
                        self.error("glyph_advance", &path, "Glyph advance must be 1–32 pixels");
                    }
                    self.tile_ref(&glyph.tile, None, &path);
                }
            }
            Asset::Sample(sample) => {
                if !(1..=192_000).contains(&sample.sample_rate)
                    || sample.pcm.is_empty()
                    || sample.pcm.len() > MAX_SAMPLES
                {
                    self.error(
                        "sample_size",
                        path,
                        "Use 1–192,000 Hz and 1–3,840,000 PCM samples",
                    );
                }
                if sample.pcm.len().div_ceil(16) * 9 > 65_536 {
                    self.warn(
                        "sample_aram_budget",
                        path,
                        "Encoded BRR alone exceeds the S-DSP's 64 KiB of sound RAM",
                    );
                }
                if let Some(start) = sample.loop_start {
                    if start as usize >= sample.pcm.len() {
                        self.error(
                            "sample_loop",
                            path,
                            "Loop start must refer to an existing sample",
                        );
                    } else if start % 16 != 0 {
                        self.warn(
                            "brr_loop_alignment",
                            path,
                            "BRR export requires a loop start on a 16-sample boundary",
                        );
                    }
                }
            }
            Asset::Sequence(sequence) => self.sequence(sequence, path),
            Asset::Vram(vram) => self.vram(vram, path),
        }
    }

    fn palette(&mut self, palette: &Palette, path: &str) {
        if palette.colors.is_empty() || palette.colors.len() > 256 {
            self.error("palette_size", path, "A subpalette needs 1–256 entries");
        }
        if palette.colors.iter().any(|&color| color > 0x7fff) {
            self.error("bgr555", path, "Palette entries must fit in 15 bits");
        }
        if let Some(index) = palette.transparent {
            if usize::from(index) >= palette.colors.len() {
                self.error(
                    "transparent_index",
                    path,
                    "Transparency must refer to an existing entry",
                );
            } else if index != 0 {
                self.warn(
                    "hardware_transparency",
                    path,
                    "Hardware uses index 0 for transparency",
                );
            }
        }
    }

    fn check_tile_palette(&mut self, tile: &Tile, palette: &str, path: &str) {
        if let Some(Asset::Palette(palette)) = self.project.assets.get(palette) {
            if tile
                .pixels
                .iter()
                .any(|&index| usize::from(index) >= palette.colors.len())
            {
                self.error(
                    "palette_index",
                    path,
                    "A pixel refers to a missing palette entry",
                );
            }
        } else {
            self.error("reference", path, format!("Expected palette {palette}"));
        }
    }

    fn tile_ref(&mut self, id: &str, palette: Option<&str>, path: &str) -> Option<&'a Tile> {
        let Some(Asset::Tile(tile)) = self.project.assets.get(id) else {
            self.error("reference", path, format!("Expected tile {id}"));
            return None;
        };
        if let Some(palette) = palette {
            self.check_tile_palette(tile, palette, path);
        }
        Some(tile)
    }

    fn grid(
        &mut self,
        path: &str,
        width: u16,
        height: u16,
        cell_width: u32,
        cell_height: u32,
        len: usize,
    ) {
        if checked_image(
            u32::from(width).saturating_mul(cell_width),
            u32::from(height).saturating_mul(cell_height),
        )
        .is_err()
        {
            self.error("dimensions", path, "Preview dimensions must be positive, at most 4096 per side and at most 4 megapixels");
        }
        if usize::from(width) * usize::from(height) != len {
            self.error("grid_length", path, "Expected width × height cells");
        }
    }

    fn map(&mut self, map: &Map, path: &str) {
        self.metadata(&map.metadata, path);
        let tileset = match self.project.assets.get(&map.tileset) {
            Some(Asset::Tileset(tileset)) => Some(tileset),
            _ => {
                self.error(
                    "reference",
                    path,
                    format!("Expected tileset {}", map.tileset),
                );
                None
            }
        };
        let allowed_tiles: BTreeSet<_> = tileset.iter().flat_map(|set| &set.tiles).collect();
        let allowed_metatiles: BTreeSet<_> =
            tileset.iter().flat_map(|set| &set.metatiles).collect();
        if map.layers.is_empty() {
            self.error("layers", path, "A map needs at least one layer");
        }
        let mut seen = BTreeSet::new();
        for (index, layer) in map.layers.iter().enumerate() {
            let path = format!("{path}/layers/{index}");
            self.distinct(&layer.id, &mut seen, &path);
            self.metadata(&layer.metadata, &path);
            self.grid(
                &path,
                map.width,
                map.height,
                u32::from(map.cell_width) * 8,
                u32::from(map.cell_height) * 8,
                layer.cells.len(),
            );
            for (index, cell) in layer.cells.iter().enumerate() {
                let Some(cell) = cell else { continue };
                let path = format!("{path}/cells/{index}");
                self.metadata(&cell.metadata, &path);
                let size = match self.project.assets.get(&cell.asset) {
                    Some(Asset::Tile(tile)) if allowed_tiles.contains(&cell.asset) => {
                        if let Some(palette) = &cell.palette {
                            self.check_tile_palette(tile, palette, &path);
                        }
                        (1, 1)
                    }
                    Some(Asset::Metatile(metatile)) if allowed_metatiles.contains(&cell.asset) => {
                        if let Some(palette) = &cell.palette {
                            for tile in metatile.cells.iter().flatten() {
                                self.tile_ref(&tile.tile, Some(palette), &path);
                            }
                        }
                        (metatile.width, metatile.height)
                    }
                    _ => {
                        self.error(
                            "tileset_member",
                            &path,
                            format!("{} is not in this tileset", cell.asset),
                        );
                        continue;
                    }
                };
                if size != (map.cell_width, map.cell_height) {
                    self.error(
                        "cell_size",
                        &path,
                        "Placed artwork must match the map cell size",
                    );
                }
            }
        }
    }

    fn metadata(&mut self, metadata: &Metadata, path: &str) {
        for (key, value) in metadata {
            self.metadata_value(value, &format!("{path}/metadata/{}", pointer(key)));
        }
    }

    fn metadata_value(&mut self, value: &serde_json::Value, path: &str) {
        use serde_json::Value;
        const JS_MAX_SAFE_INTEGER: u64 = (1 << 53) - 1;
        match value {
            Value::Number(number)
                if number
                    .as_i64()
                    .is_some_and(|value| value.unsigned_abs() > JS_MAX_SAFE_INTEGER)
                    || number
                        .as_u64()
                        .is_some_and(|value| value > JS_MAX_SAFE_INTEGER)
                    || number.as_f64().is_some_and(|value| {
                        value.fract() == 0.0 && value.abs() > JS_MAX_SAFE_INTEGER as f64
                    }) =>
            {
                self.error(
                    "metadata_integer",
                    path,
                    "Store integers outside the browser's safe numeric range as strings",
                );
            }
            Value::Object(values) => {
                for (key, value) in values {
                    self.metadata_value(value, &format!("{path}/{}", pointer(key)));
                }
            }
            Value::Array(values) => {
                for (index, value) in values.iter().enumerate() {
                    self.metadata_value(value, &format!("{path}/{index}"));
                }
            }
            _ => {}
        }
    }

    fn sprite(&mut self, sprite: &Sprite, path: &str) {
        if !(1..=256).contains(&sprite.width)
            || !(1..=256).contains(&sprite.height)
            || sprite.size_mode > 7
        {
            self.error(
                "sprite_dimensions",
                path,
                "Use a 1–256 pixel canvas and OBJ size mode 0–7",
            );
        }
        if sprite.frames.is_empty() {
            self.error("frames", path, "An animation needs at least one frame");
        }
        let mut seen = BTreeSet::new();
        for (index, frame) in sprite.frames.iter().enumerate() {
            let path = format!("{path}/frames/{index}");
            self.distinct(&frame.id, &mut seen, &path);
            if frame.duration_ms == 0 || frame.objects.len() > 128 {
                self.error(
                    "frame_budget",
                    &path,
                    "A frame needs a positive duration and at most 128 OBJs",
                );
            }
            let mut slots = BTreeMap::new();
            for (index, object) in frame.objects.iter().enumerate() {
                let path = format!("{path}/objects/{index}");
                let Some((width, height)) = object_size(sprite.size_mode, object.large) else {
                    continue;
                };
                if !(-256..=255).contains(&object.x)
                    || !(-128..=255).contains(&object.y)
                    || object.palette_slot > 7
                    || object.priority > 3
                    || object.tiles.len() != usize::from(width / 8) * usize::from(height / 8)
                {
                    self.error("object_attributes", &path, "OBJ position, palette slot, priority or tile count is outside the selected hardware layout");
                }
                if !matches!(self.project.assets.get(&object.palette), Some(Asset::Palette(p)) if p.colors.len() <= 16 && p.transparent == Some(0))
                {
                    self.error(
                        "object_palette",
                        &path,
                        "OBJ subpalettes need at most 16 entries with transparent index 0",
                    );
                }
                if let Some(previous) = slots.insert(object.palette_slot, &object.palette)
                    && previous != &object.palette
                {
                    self.error(
                        "object_palette_slot",
                        &path,
                        "An OBJ palette slot can hold only one subpalette in a frame",
                    );
                }
                for id in &object.tiles {
                    if let Some(tile) = self.tile_ref(id, Some(&object.palette), &path)
                        && tile.bpp != 4
                    {
                        self.error("object_bpp", &path, "OBJ tiles must be 4bpp");
                    }
                }
            }
            if let Some(line) = over_budget_line(sprite, frame) {
                self.warn(
                    "scanline_budget",
                    &path,
                    format!("Scanline {line} exceeds 32 OBJs or 34 eight-pixel tile fetches"),
                );
            }
            if object_placements(sprite, frame).is_err() {
                self.warn(
                    "object_tile_budget",
                    &path,
                    "The frame packer could not fit OBJ graphics into two 16×16 tile pages",
                );
            }
        }
    }

    fn sequence(&mut self, sequence: &Sequence, path: &str) {
        let valid_clock =
            (1..=960).contains(&sequence.ticks_per_beat) && (20..=600).contains(&sequence.bpm);
        if !valid_clock || sequence.tracks.is_empty() || sequence.tracks.len() > 64 {
            self.error(
                "sequence_size",
                path,
                "Use 1–960 ticks per beat, 20–600 BPM and 1–64 tracks",
            );
        } else if sequence.tracks.len() > 8 {
            self.warn(
                "spc_voices",
                path,
                "There are more tracks than the eight S-DSP voices",
            );
        }
        let limit = if valid_clock {
            u32::from(sequence.bpm) * u32::from(sequence.ticks_per_beat) * 2
        } else {
            0
        };
        let mut seen = BTreeSet::new();
        for (index, track) in sequence.tracks.iter().enumerate() {
            let path = format!("{path}/tracks/{index}");
            self.distinct(&track.id, &mut seen, &path);
            if let Voice::Sample { asset, root_note } = &track.voice
                && (*root_note > 127
                    || !matches!(self.project.assets.get(asset), Some(Asset::Sample(_))))
            {
                self.error(
                    "sequence_voice",
                    &path,
                    "Sample voices need a sample ID and a root MIDI note 0–127",
                );
            }
            let mut end = 0;
            for (index, note) in track.notes.iter().enumerate() {
                let next = note.tick.saturating_add(note.length);
                if note.tick < end
                    || next > limit
                    || note.length == 0
                    || note.pitch > 127
                    || note.velocity > 127
                {
                    self.error("sequence_note", &format!("{path}/notes/{index}"), "Use sorted, nonoverlapping notes, pitch and velocity 0–127, and a maximum length of 120 seconds");
                }
                end = next;
            }
        }
    }

    fn vram(&mut self, vram: &Vram, path: &str) {
        let mut regions = Vec::new();
        for (id, region) in &vram.regions {
            let path = format!("{path}/regions/{}", pointer(id));
            self.check_id(id, &path);
            let end = region.start.saturating_add(region.bytes);
            if region.bytes == 0 || end > 65_536 {
                self.error(
                    "vram_range",
                    &path,
                    "VRAM regions must fit inside 64 KiB and have positive length",
                );
            }
            if region.start % region.purpose.alignment() != 0 {
                self.error(
                    "vram_alignment",
                    &path,
                    format!(
                        "Base must be aligned to {} bytes",
                        region.purpose.alignment()
                    ),
                );
            }
            regions.push((region.start, end, path));
        }
        regions.sort();
        let mut previous_end = 0;
        for (start, end, path) in regions {
            if start < previous_end {
                self.error("vram_overlap", &path, "Region overlaps another allocation");
            }
            previous_end = previous_end.max(end);
        }
    }
}
