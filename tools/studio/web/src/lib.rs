use studio_core as studio;
use wasm_bindgen::prelude::*;

fn error(error: studio::Error) -> JsValue {
    JsValue::from_str(&serde_json::to_string(&error.0).expect("diagnostics serialize"))
}

fn parse<T: serde::de::DeserializeOwned>(text: &str) -> Result<T, JsValue> {
    serde_json::from_str(text)
        .map_err(|cause| error(studio::Error::new("json", "", cause.to_string())))
}

#[wasm_bindgen]
pub struct Studio {
    editor: studio::Editor,
    clipboard: Option<studio::Selection>,
    picked_metadata: studio::Metadata,
}

#[wasm_bindgen]
impl Studio {
    #[wasm_bindgen(constructor)]
    pub fn new(bytes: &[u8]) -> Result<Studio, JsValue> {
        let project = studio::load_project(bytes).map_err(error)?;
        Ok(Self {
            editor: studio::Editor::new(project),
            clipboard: None,
            picked_metadata: studio::Metadata::default(),
        })
    }

    #[wasm_bindgen(js_name = empty)]
    pub fn empty() -> Studio {
        Self {
            editor: studio::Editor::default(),
            clipboard: None,
            picked_metadata: studio::Metadata::default(),
        }
    }

    pub fn manifest(&self) -> String {
        serde_json::to_string(self.editor.project()).expect("project serializes")
    }

    #[wasm_bindgen(js_name = mapMetadata)]
    pub fn map_metadata(&self, id: &str, layer: Option<String>) -> Result<String, JsValue> {
        let Some(studio::Asset::Map(map)) = self.editor.project().assets.get(id) else {
            return Err(error(studio::Error::new(
                "invalid_input",
                id,
                "Expected a map",
            )));
        };
        let metadata = match layer {
            Some(id) => {
                &map.layers
                    .iter()
                    .find(|layer| layer.id == id)
                    .ok_or_else(|| {
                        error(studio::Error::new(
                            "invalid_input",
                            id,
                            "Map layer does not exist",
                        ))
                    })?
                    .metadata
            }
            None => &map.metadata,
        };
        Ok(serde_json::to_string_pretty(metadata).expect("metadata serializes"))
    }

    pub fn diagnostics(&self) -> String {
        serde_json::to_string(&studio::validate(self.editor.project()))
            .expect("diagnostics serialize")
    }

    pub fn apply(&mut self, edits: &str) -> Result<bool, JsValue> {
        let edits = studio::edits_from_json(edits.as_bytes()).map_err(error)?;
        self.editor.edit(&edits).map_err(error)
    }

    #[wasm_bindgen(js_name = putAsset)]
    pub fn put_asset(&mut self, id: String, kind: &str, data_json: &str) -> Result<bool, JsValue> {
        let edit = studio::put_asset_from_json(id, kind, data_json).map_err(error)?;
        self.editor.edit(&[edit]).map_err(error)
    }

    #[wasm_bindgen(js_name = pickMapCellMetadata)]
    pub fn pick_map_cell_metadata(
        &mut self,
        id: &str,
        layer: &str,
        x: u16,
        y: u16,
    ) -> Result<String, JsValue> {
        let rect = studio::Rect {
            x,
            y,
            width: 1,
            height: 1,
        };
        let selection =
            studio::copy_selection(self.editor.project(), id, layer, rect).map_err(error)?;
        let cell = selection
            .cells
            .into_iter()
            .next()
            .flatten()
            .ok_or_else(|| {
                error(studio::Error::new(
                    "invalid_input",
                    "",
                    "The active layer has no artwork at the cursor",
                ))
            })?;
        self.picked_metadata = cell.metadata;
        Ok(serde_json::to_string_pretty(&self.picked_metadata).expect("metadata serializes"))
    }

    #[wasm_bindgen(js_name = paintMap)]
    pub fn paint_map(
        &mut self,
        edits: &str,
        metadata_json: Option<String>,
    ) -> Result<bool, JsValue> {
        let mut edits = studio::edits_from_json(edits.as_bytes()).map_err(error)?;
        let metadata = metadata_json
            .as_deref()
            .map(studio::metadata_from_edit_json)
            .transpose()
            .map_err(error)?;
        let metadata = metadata.as_ref().unwrap_or(&self.picked_metadata);
        for edit in &mut edits {
            match edit {
                studio::Edit::Place { cell, .. } | studio::Edit::Fill { cell, .. } => {
                    if let Some(cell) = cell {
                        cell.metadata.clone_from(metadata);
                    }
                }
                _ => {
                    return Err(error(studio::Error::new(
                        "invalid_input",
                        "",
                        "Expected map brush edits",
                    )));
                }
            }
        }
        self.editor.edit(&edits).map_err(error)
    }

    pub fn revision(&self) -> u64 {
        self.editor.revision()
    }

    pub fn undo(&mut self) -> bool {
        self.editor.undo()
    }

    pub fn redo(&mut self) -> bool {
        self.editor.redo()
    }

    #[wasm_bindgen(js_name = canUndo)]
    pub fn can_undo(&self) -> bool {
        self.editor.can_undo()
    }

    #[wasm_bindgen(js_name = canRedo)]
    pub fn can_redo(&self) -> bool {
        self.editor.can_redo()
    }

    pub fn save(&self, archive: bool) -> Result<Vec<u8>, JsValue> {
        studio::save_project(self.editor.project(), archive).map_err(error)
    }

    pub fn copy(&self, id: &str, layer: &str, rect: &str) -> Result<String, JsValue> {
        let selection = studio::copy_selection(self.editor.project(), id, layer, parse(rect)?)
            .map_err(error)?;
        Ok(serde_json::to_string(&selection).expect("selection serializes"))
    }

    #[wasm_bindgen(js_name = copyToClipboard)]
    pub fn copy_to_clipboard(&mut self, id: &str, layer: &str, rect: &str) -> Result<(), JsValue> {
        self.clipboard = Some(
            studio::copy_selection(self.editor.project(), id, layer, parse(rect)?)
                .map_err(error)?,
        );
        Ok(())
    }

    #[wasm_bindgen(js_name = pasteFromClipboard)]
    pub fn paste_from_clipboard(
        &mut self,
        id: &str,
        layer: &str,
        x: u16,
        y: u16,
    ) -> Result<bool, JsValue> {
        let selection = self.clipboard.clone().ok_or_else(|| {
            error(studio::Error::new(
                "invalid_input",
                "",
                "Clipboard is empty",
            ))
        })?;
        self.editor
            .edit(&[studio::Edit::Paste {
                id: id.into(),
                layer: layer.into(),
                x,
                y,
                selection,
            }])
            .map_err(error)
    }

    pub fn export(&self, id: &str, options: &str) -> Result<Vec<u8>, JsValue> {
        studio::export(self.editor.project(), id, &parse(options)?).map_err(error)
    }

    #[wasm_bindgen(js_name = audioPreviewPcm)]
    pub fn audio_preview_pcm(&self, id: &str) -> Result<Vec<f32>, JsValue> {
        let sample = studio::audio_preview(self.editor.project(), id).map_err(error)?;
        Ok(sample
            .pcm
            .into_iter()
            .map(|value| f32::from(value) / 32_768.0)
            .collect())
    }

    pub fn preview(
        &self,
        id: &str,
        frame: Option<String>,
        text: Option<String>,
        bpp: Option<u8>,
    ) -> Result<Vec<u8>, JsValue> {
        let project = self.editor.project();
        let image = match bpp {
            Some(bpp) => studio::render_tile_preview(project, id, bpp),
            None => studio::render(project, id, frame.as_deref(), text.as_deref()),
        }
        .map_err(error)?;
        let mut data = Vec::with_capacity(8 + image.rgba.len());
        data.extend_from_slice(&image.width.to_le_bytes());
        data.extend_from_slice(&image.height.to_le_bytes());
        data.extend(image.rgba);
        Ok(data)
    }

    #[wasm_bindgen(js_name = frameAt)]
    pub fn frame_at(&self, id: &str, elapsed_ms: u32) -> Option<String> {
        let studio::Asset::Sprite(sprite) = self.editor.project().assets.get(id)? else {
            return None;
        };
        studio::frame_at(sprite, u64::from(elapsed_ms)).map(|frame| frame.id.clone())
    }

    #[wasm_bindgen(js_name = importImage)]
    pub fn import_image(&mut self, bytes: &[u8], options: &str) -> Result<(), JsValue> {
        let edits =
            studio::import_png(self.editor.project(), bytes, &parse(options)?).map_err(error)?;
        self.editor.edit(&edits).map_err(error)?;
        Ok(())
    }

    #[wasm_bindgen(js_name = importSample)]
    pub fn import_sample(
        &mut self,
        bytes: &[u8],
        id: String,
        format: &str,
        rate: Option<u32>,
        loop_offset: Option<u32>,
    ) -> Result<(), JsValue> {
        let edit = studio::import_sample(
            self.editor.project(),
            id,
            parse(format)?,
            bytes,
            rate,
            loop_offset,
        )
        .map_err(error)?;
        self.editor.edit(&[edit]).map_err(error)?;
        Ok(())
    }
}

#[wasm_bindgen]
pub fn fingerprint(bytes: &[u8]) -> String {
    studio::fingerprint(bytes)
}

#[wasm_bindgen]
pub fn inspect_rom(bytes: &[u8], layout: &str) -> Result<String, JsValue> {
    let header = studio::inspect_rom(bytes, parse(layout)?).map_err(error)?;
    Ok(serde_json::to_string(&header).expect("header serializes"))
}

#[wasm_bindgen]
pub fn rle(bytes: &[u8], decompress: bool) -> Result<Vec<u8>, JsValue> {
    if decompress {
        studio::decompress_rle(bytes)
    } else {
        studio::compress_rle(bytes)
    }
    .map_err(error)
}

#[wasm_bindgen]
pub fn palette_rgb(color: u16) -> Vec<u8> {
    studio::rgb(color).to_vec()
}

#[wasm_bindgen]
pub fn obj_size(mode: u8, large: bool) -> Vec<u16> {
    studio::object_size(mode, large)
        .map(|(width, height)| vec![width, height])
        .unwrap_or_default()
}

#[wasm_bindgen]
pub fn quantize_color(colors: &str, rgb: &[u8], bpp: u8) -> Result<u8, JsValue> {
    let rgba = rgb
        .try_into()
        .map_err(|_| error(studio::Error::new("invalid_input", "", "Expected RGBA")))?;
    studio::quantize(&parse(colors)?, rgba, bpp).map_err(error)
}
