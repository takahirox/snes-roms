use crate::*;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Format {
    Png,
    IndexedPng,
    Chr,
    Palette,
    Wav,
    Brr,
    Oam,
    ObjChr,
    ObjCgram,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExportOptions {
    pub format: Format,
    pub frame: Option<Id>,
    pub text: Option<String>,
    pub bpp: Option<u8>,
}

pub fn export(project: &Project, id: &str, options: &ExportOptions) -> Result<Vec<u8>> {
    if options.bpp.is_some()
        && !matches!(
            options.format,
            Format::Png | Format::Chr | Format::IndexedPng
        )
        || options.bpp.is_some() && (options.text.is_some() || options.frame.is_some())
        || options.text.is_some() && !matches!(options.format, Format::Png)
        || options.frame.is_some()
            && !matches!(
                options.format,
                Format::Png | Format::Oam | Format::ObjChr | Format::ObjCgram
            )
    {
        return Err(invalid("Export option does not apply to this format"));
    }
    let frame = options.frame.as_deref();
    match options.format {
        Format::Png => match options.bpp {
            Some(bpp) => render_tile_preview(project, id, bpp)?.png(),
            None => render(project, id, frame, options.text.as_deref())?.png(),
        },
        Format::IndexedPng => export_indexed(project, id, options.bpp),
        Format::Wav => write_wav(&audio_preview(project, id)?),
        Format::Brr => {
            require_valid_content(project)?;
            let Asset::Sample(sample) = asset(project, id)? else {
                return Err(invalid("Expected a sample"));
            };
            write_brr(sample)
        }
        Format::Palette => {
            require_valid_content(project)?;
            let Asset::Palette(palette) = asset(project, id)? else {
                return Err(invalid("Expected a palette"));
            };
            Ok(palette
                .colors
                .iter()
                .flat_map(|color| color.to_le_bytes())
                .collect())
        }
        Format::Oam => Ok(export_sprite(project, id, frame)?.oam),
        Format::ObjChr => Ok(export_sprite(project, id, frame)?.chr),
        Format::ObjCgram => Ok(export_sprite(project, id, frame)?.cgram),
        Format::Chr => {
            require_valid_content(project)?;
            match asset(project, id)? {
                Asset::Tile(_) => export_chr_tile(project, id, options.bpp),
                Asset::Tileset(tileset) if !tileset.tiles.is_empty() => {
                    let mut bytes = Vec::new();
                    let mut tile_size = None;
                    for id in &tileset.tiles {
                        let tile = export_chr_tile(project, id, options.bpp)?;
                        if tile_size.is_some_and(|previous| previous != tile.len()) {
                            return Err(invalid(
                                "Choose an explicit bit depth for tilesets with mixed bit depths",
                            ));
                        }
                        tile_size = Some(tile.len());
                        bytes.extend(tile);
                    }
                    Ok(bytes)
                }
                _ => Err(invalid("Expected a tile or tileset containing base tiles")),
            }
        }
    }
}

fn export_chr_tile(project: &Project, id: &str, bpp: Option<u8>) -> Result<Vec<u8>> {
    let Asset::Tile(tile) = asset(project, id)? else {
        return Err(invalid("Expected a tile"));
    };
    if let Some(bpp) = bpp {
        let mut tile = tile.clone();
        tile.bpp = bpp;
        planar_tile(&tile)
    } else {
        planar_tile(tile)
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum SampleFormat {
    Wav,
    Brr,
}

pub fn import_sample(
    project: &Project,
    id: Id,
    format: SampleFormat,
    bytes: &[u8],
    rate: Option<u32>,
    loop_offset: Option<u32>,
) -> Result<Edit> {
    if project.assets.contains_key(&id) {
        return Err(Error::new("asset_exists", id, "Choose a new asset ID"));
    }
    let sample = match format {
        SampleFormat::Wav if rate.is_none() && loop_offset.is_none() => read_wav(bytes)?,
        SampleFormat::Wav => return Err(invalid("WAV stores its own sample rate and loop start")),
        SampleFormat::Brr => read_brr(bytes, rate.unwrap_or(32_000), loop_offset)?,
    };
    Ok(Edit::Put {
        id,
        asset: Asset::Sample(sample),
    })
}
