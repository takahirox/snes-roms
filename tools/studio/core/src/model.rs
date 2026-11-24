use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

pub type Id = String;
pub type Metadata = BTreeMap<String, Value>;
pub const PROJECT_FILE: &str = "studio.json";
pub const VERSION: u32 = 1;
pub const MAX_PROJECT_BYTES: usize = 64 * 1024 * 1024;
pub const MAX_PIXELS: usize = 4 * 1024 * 1024;
pub const MAX_SAMPLES: usize = 32_000 * 120;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Project {
    pub version: u32,
    pub name: String,
    #[serde(deserialize_with = "unique_assets")]
    pub assets: BTreeMap<Id, Asset>,
}

fn unique_assets<'de, D>(deserializer: D) -> std::result::Result<BTreeMap<Id, Asset>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    struct UniqueAssets;

    impl<'de> serde::de::Visitor<'de> for UniqueAssets {
        type Value = BTreeMap<Id, Asset>;

        fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            formatter.write_str("an object of assets with unique IDs")
        }

        fn visit_map<A: serde::de::MapAccess<'de>>(
            self,
            mut entries: A,
        ) -> std::result::Result<Self::Value, A::Error> {
            let mut assets = BTreeMap::new();
            while let Some((id, asset)) = entries.next_entry::<Id, Asset>()? {
                match assets.entry(id) {
                    std::collections::btree_map::Entry::Vacant(entry) => {
                        entry.insert(asset);
                    }
                    std::collections::btree_map::Entry::Occupied(entry) => {
                        return Err(serde::de::Error::custom(format!(
                            "Duplicate asset ID {}",
                            entry.key()
                        )));
                    }
                }
            }
            Ok(assets)
        }
    }

    deserializer.deserialize_map(UniqueAssets)
}

impl Default for Project {
    fn default() -> Self {
        Self {
            version: VERSION,
            name: "Untitled".into(),
            assets: BTreeMap::new(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "data", rename_all = "snake_case")]
pub enum Asset {
    Palette(Palette),
    Tile(Tile),
    Metatile(Metatile),
    Tileset(Tileset),
    Map(Map),
    Sprite(Sprite),
    Font(Font),
    Sample(Sample),
    Sequence(Sequence),
    Vram(Vram),
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Palette {
    pub colors: Vec<u16>,
    pub transparent: Option<u8>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Tile {
    pub bpp: u8,
    pub palette: Id,
    pub pixels: Vec<u8>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TileRef {
    pub tile: Id,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub palette: Option<Id>,
    #[serde(default)]
    pub flip_x: bool,
    #[serde(default)]
    pub flip_y: bool,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Metatile {
    pub width: u16,
    pub height: u16,
    pub cells: Vec<Option<TileRef>>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Tileset {
    pub tiles: Vec<Id>,
    pub metatiles: Vec<Id>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Cell {
    pub asset: Id,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub palette: Option<Id>,
    #[serde(default)]
    pub flip_x: bool,
    #[serde(default)]
    pub flip_y: bool,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub metadata: Metadata,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Map {
    pub tileset: Id,
    pub width: u16,
    pub height: u16,
    pub cell_width: u16,
    pub cell_height: u16,
    pub layers: Vec<Layer>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub metadata: Metadata,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Layer {
    pub id: Id,
    pub visible: bool,
    pub cells: Vec<Option<Cell>>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub metadata: Metadata,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Sprite {
    pub width: u16,
    pub height: u16,
    pub size_mode: u8,
    pub frames: Vec<Frame>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Frame {
    pub id: Id,
    pub duration_ms: u16,
    pub objects: Vec<Object>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Object {
    pub x: i16,
    pub y: i16,
    pub large: bool,
    pub tiles: Vec<Id>,
    pub palette: Id,
    pub palette_slot: u8,
    pub priority: u8,
    pub flip_x: bool,
    pub flip_y: bool,
}

pub fn object_size(mode: u8, large: bool) -> Option<(u16, u16)> {
    const SIZES: [[(u16, u16); 2]; 8] = [
        [(8, 8), (16, 16)],
        [(8, 8), (32, 32)],
        [(8, 8), (64, 64)],
        [(16, 16), (32, 32)],
        [(16, 16), (64, 64)],
        [(32, 32), (64, 64)],
        [(16, 32), (32, 64)],
        [(16, 32), (32, 32)],
    ];
    SIZES
        .get(usize::from(mode))
        .map(|pair| pair[usize::from(large)])
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Font {
    pub glyphs: BTreeMap<char, Glyph>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Glyph {
    pub tile: Id,
    pub advance: u8,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Sample {
    pub sample_rate: u32,
    pub pcm: Vec<i16>,
    pub loop_start: Option<u32>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Sequence {
    pub usage: SequenceUsage,
    pub ticks_per_beat: u16,
    pub bpm: u16,
    pub tracks: Vec<Track>,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SequenceUsage {
    Music,
    Sfx,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Track {
    pub id: Id,
    pub voice: Voice,
    pub notes: Vec<Note>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Voice {
    Square,
    Triangle,
    Sample { asset: Id, root_note: u8 },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Note {
    pub tick: u32,
    pub length: u32,
    pub pitch: u8,
    pub velocity: u8,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Vram {
    pub regions: BTreeMap<Id, Region>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Region {
    pub start: u32,
    pub bytes: u32,
    pub purpose: RegionPurpose,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RegionPurpose {
    BgTiles,
    BgMap,
    ObjTiles,
    Other,
}

impl RegionPurpose {
    pub fn alignment(self) -> u32 {
        match self {
            Self::BgTiles => 8192,
            Self::BgMap => 2048,
            Self::ObjTiles => 16384,
            Self::Other => 1,
        }
    }
}
