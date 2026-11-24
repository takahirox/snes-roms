use crate::*;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Edit {
    Name {
        name: String,
    },
    Put {
        id: Id,
        asset: Asset,
    },
    Remove {
        id: Id,
    },
    SetColor {
        id: Id,
        index: u8,
        rgb: [u8; 3],
    },
    SetTransparency {
        id: Id,
        index: Option<u8>,
    },
    TrimSample {
        id: Id,
        start: u32,
        end: u32,
    },
    SetPixel {
        id: Id,
        x: u8,
        y: u8,
        index: u8,
    },
    ResizeMap {
        id: Id,
        width: u16,
        height: u16,
    },
    ResizeMetatile {
        id: Id,
        width: u16,
        height: u16,
    },
    SetMetatileCell {
        id: Id,
        x: u16,
        y: u16,
        cell: Option<TileRef>,
    },
    Place {
        id: Id,
        layer: Id,
        x: u16,
        y: u16,
        cell: Option<Cell>,
    },
    Fill {
        id: Id,
        layer: Id,
        x: u16,
        y: u16,
        cell: Option<Cell>,
    },
    Paste {
        id: Id,
        layer: Id,
        x: u16,
        y: u16,
        selection: Selection,
    },
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Rect {
    pub x: u16,
    pub y: u16,
    pub width: u16,
    pub height: u16,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Selection {
    pub width: u16,
    pub height: u16,
    pub cells: Vec<Option<Cell>>,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Change {
    pub path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub before: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub after: Option<Value>,
}

pub fn edits_from_json(bytes: &[u8]) -> Result<Vec<Edit>> {
    serde_json::from_slice(bytes).map_err(|error| Error::new("edit_json", "", error.to_string()))
}

pub fn apply(project: &Project, edits: &[Edit]) -> Result<Project> {
    let mut next = project.clone();
    for edit in edits {
        apply_one(&mut next, edit)?;
    }
    require_valid(&next)?;
    require_manifest_fits(&next)?;
    Ok(next)
}

pub fn diff(before: &Project, after: &Project) -> Result<Vec<Change>> {
    let value = |project| {
        serde_json::to_value(project).map_err(|error| Error::new("json", "", error.to_string()))
    };
    let mut changes = Vec::new();
    diff_value(
        "",
        Some(&value(before)?),
        Some(&value(after)?),
        &mut changes,
    );
    Ok(changes)
}

fn diff_value(
    path: &str,
    before: Option<&Value>,
    after: Option<&Value>,
    changes: &mut Vec<Change>,
) {
    if before == after {
        return;
    }
    match (before, after) {
        (Some(Value::Object(before)), Some(Value::Object(after))) => {
            let keys: BTreeSet<_> = before.keys().chain(after.keys()).collect();
            for key in keys {
                let path = format!("{path}/{}", key.replace('~', "~0").replace('/', "~1"));
                diff_value(&path, before.get(key), after.get(key), changes);
            }
        }
        (Some(Value::Array(before)), Some(Value::Array(after))) if before.len() == after.len() => {
            for (index, (before, after)) in before.iter().zip(after).enumerate() {
                diff_value(
                    &format!("{path}/{index}"),
                    Some(before),
                    Some(after),
                    changes,
                );
            }
        }
        _ => changes.push(Change {
            path: path.into(),
            before: before.cloned(),
            after: after.cloned(),
        }),
    }
}

pub fn copy_selection(project: &Project, id: &str, layer: &str, rect: Rect) -> Result<Selection> {
    let Asset::Map(map) = asset(project, id)? else {
        return Err(invalid("Expected a map"));
    };
    let layer = map
        .layers
        .iter()
        .find(|item| item.id == layer)
        .ok_or_else(|| invalid("Map layer does not exist"))?;
    let mut cells = Vec::new();
    for row in rows(map.width, map.height, rect)? {
        cells.extend_from_slice(
            layer
                .cells
                .get(row)
                .ok_or_else(|| invalid("Map grid does not match its dimensions"))?,
        );
    }
    Ok(Selection {
        width: rect.width,
        height: rect.height,
        cells,
    })
}

fn rows(
    width: u16,
    height: u16,
    rect: Rect,
) -> Result<impl Iterator<Item = std::ops::Range<usize>>> {
    if rect.width == 0
        || rect.height == 0
        || rect.x.checked_add(rect.width).is_none_or(|end| end > width)
        || rect
            .y
            .checked_add(rect.height)
            .is_none_or(|end| end > height)
    {
        return Err(invalid("Selection must fit entirely inside the grid"));
    }
    let stride = usize::from(width);
    Ok((rect.y..rect.y + rect.height).map(move |y| {
        let start = usize::from(y) * stride + usize::from(rect.x);
        start..start + usize::from(rect.width)
    }))
}

fn at(width: u16, height: u16, x: u16, y: u16) -> Result<usize> {
    if x >= width || y >= height {
        return Err(invalid("Coordinates are outside the grid"));
    }
    Ok(usize::from(y) * usize::from(width) + usize::from(x))
}

fn get_asset_mut<'a>(project: &'a mut Project, id: &str) -> Result<&'a mut Asset> {
    project
        .assets
        .get_mut(id)
        .ok_or_else(|| Error::new("missing_asset", id, "Asset ID does not exist"))
}

fn layer_mut<'a>(
    project: &'a mut Project,
    id: &str,
    layer: &str,
) -> Result<(u16, u16, &'a mut [Option<Cell>])> {
    let Asset::Map(map) = get_asset_mut(project, id)? else {
        return Err(invalid("Expected a map"));
    };
    let selected = map
        .layers
        .iter_mut()
        .find(|item| item.id == layer)
        .ok_or_else(|| invalid("Map layer does not exist"))?;
    if selected.cells.len() != usize::from(map.width) * usize::from(map.height) {
        return Err(invalid("Map grid does not match its dimensions"));
    }
    Ok((map.width, map.height, &mut selected.cells))
}

fn apply_one(project: &mut Project, edit: &Edit) -> Result<()> {
    match edit {
        Edit::Name { name } => project.name.clone_from(name),
        Edit::Put { id, asset } => {
            project.assets.insert(id.clone(), asset.clone());
        }
        Edit::Remove { id } => {
            if project.assets.remove(id).is_none() {
                return Err(Error::new("missing_asset", id, "Asset ID does not exist"));
            }
        }
        Edit::SetColor { id, index, rgb } => {
            let Asset::Palette(palette) = get_asset_mut(project, id)? else {
                return Err(invalid("Expected a palette"));
            };
            *palette
                .colors
                .get_mut(usize::from(*index))
                .ok_or_else(|| invalid("Palette entry does not exist"))? = bgr555(*rgb);
        }
        Edit::SetTransparency { id, index } => {
            let Asset::Palette(palette) = get_asset_mut(project, id)? else {
                return Err(invalid("Expected a palette"));
            };
            palette.transparent = *index;
        }
        Edit::TrimSample { id, start, end } => {
            let Asset::Sample(sample) = get_asset_mut(project, id)? else {
                return Err(invalid("Expected a sample"));
            };
            *sample = trim_sample(sample, *start, *end)?;
        }
        Edit::SetPixel { id, x, y, index } => {
            let Asset::Tile(tile) = get_asset_mut(project, id)? else {
                return Err(invalid("Expected a tile"));
            };
            let offset = at(8, 8, u16::from(*x), u16::from(*y))?;
            *tile
                .pixels
                .get_mut(offset)
                .ok_or_else(|| invalid("Tile does not have 64 pixels"))? = *index;
        }
        Edit::ResizeMap { id, width, height } => {
            let Asset::Map(map) = get_asset_mut(project, id)? else {
                return Err(invalid("Expected a map"));
            };
            checked_image(
                u32::from(*width).saturating_mul(u32::from(map.cell_width) * 8),
                u32::from(*height).saturating_mul(u32::from(map.cell_height) * 8),
            )?;
            for layer in &mut map.layers {
                resize_grid(&mut layer.cells, map.width, map.height, *width, *height)?;
            }
            (map.width, map.height) = (*width, *height);
        }
        Edit::ResizeMetatile { id, width, height } => {
            let Asset::Metatile(metatile) = get_asset_mut(project, id)? else {
                return Err(invalid("Expected a metatile"));
            };
            checked_image(u32::from(*width) * 8, u32::from(*height) * 8)?;
            resize_grid(
                &mut metatile.cells,
                metatile.width,
                metatile.height,
                *width,
                *height,
            )?;
            (metatile.width, metatile.height) = (*width, *height);
        }
        Edit::SetMetatileCell { id, x, y, cell } => {
            let Asset::Metatile(metatile) = get_asset_mut(project, id)? else {
                return Err(invalid("Expected a metatile"));
            };
            let index = at(metatile.width, metatile.height, *x, *y)?;
            metatile
                .cells
                .get_mut(index)
                .ok_or_else(|| invalid("Metatile grid does not match its dimensions"))?
                .clone_from(cell);
        }
        Edit::Place {
            id,
            layer,
            x,
            y,
            cell,
        } => {
            let (width, height, cells) = layer_mut(project, id, layer)?;
            cells[at(width, height, *x, *y)?].clone_from(cell);
        }
        Edit::Fill {
            id,
            layer,
            x,
            y,
            cell,
        } => {
            let (width, height, cells) = layer_mut(project, id, layer)?;
            flood(cells, usize::from(width), at(width, height, *x, *y)?, cell);
        }
        Edit::Paste {
            id,
            layer,
            x,
            y,
            selection,
        } => {
            let (width, height, cells) = layer_mut(project, id, layer)?;
            if selection.cells.len() != usize::from(selection.width) * usize::from(selection.height)
            {
                return Err(invalid("Clipboard length does not match its dimensions"));
            }
            let rect = Rect {
                x: *x,
                y: *y,
                width: selection.width,
                height: selection.height,
            };
            for (target, source) in rows(width, height, rect)?
                .zip(selection.cells.chunks_exact(usize::from(rect.width)))
            {
                cells[target].clone_from_slice(source);
            }
        }
    }
    Ok(())
}

fn resize_grid<T: Clone>(
    cells: &mut Vec<Option<T>>,
    old_width: u16,
    old_height: u16,
    width: u16,
    height: u16,
) -> Result<()> {
    if cells.len() != usize::from(old_width) * usize::from(old_height) {
        return Err(invalid("Grid does not match its dimensions"));
    }
    let mut resized = vec![None; usize::from(width) * usize::from(height)];
    let copied = usize::from(width.min(old_width));
    for y in 0..usize::from(height.min(old_height)) {
        let old_start = y * usize::from(old_width);
        let new_start = y * usize::from(width);
        resized[new_start..new_start + copied]
            .clone_from_slice(&cells[old_start..old_start + copied]);
    }
    *cells = resized;
    Ok(())
}

fn flood(cells: &mut [Option<Cell>], width: usize, start: usize, replacement: &Option<Cell>) {
    let previous = cells[start].clone();
    if &previous == replacement {
        return;
    }
    let mut pending = VecDeque::from([start]);
    cells[start].clone_from(replacement);
    while let Some(index) = pending.pop_front() {
        let x = index % width;
        let neighbors = [
            (x > 0).then(|| index - 1),
            (x < width - 1).then(|| index + 1),
            index.checked_sub(width),
            (index + width < cells.len()).then_some(index + width),
        ];
        for neighbor in neighbors.into_iter().flatten() {
            if cells[neighbor] == previous {
                cells[neighbor].clone_from(replacement);
                pending.push_back(neighbor);
            }
        }
    }
}

#[derive(Default)]
pub struct Editor {
    project: Project,
    revision: u64,
    serial: u64,
    undo: Vec<Revision>,
    redo: Vec<Revision>,
}

struct Revision {
    id: u64,
    name: Option<String>,
    assets: BTreeMap<Id, Option<Asset>>,
}

impl Revision {
    fn swap(&mut self, project: &mut Project, revision: &mut u64) {
        std::mem::swap(&mut self.id, revision);
        if let Some(name) = &mut self.name {
            std::mem::swap(name, &mut project.name);
        }
        for (id, previous) in &mut self.assets {
            *previous = match previous.take() {
                Some(value) => project.assets.insert(id.clone(), value),
                None => project.assets.remove(id),
            };
        }
    }
}

impl Editor {
    pub fn new(project: Project) -> Self {
        Self {
            project,
            ..Self::default()
        }
    }

    pub fn project(&self) -> &Project {
        &self.project
    }

    pub fn revision(&self) -> u64 {
        self.revision
    }

    pub fn edit(&mut self, edits: &[Edit]) -> Result<bool> {
        let next = apply(&self.project, edits)?;
        if next == self.project {
            return Ok(false);
        }
        let mut previous = std::mem::replace(&mut self.project, next);
        let keys: BTreeSet<_> = previous
            .assets
            .keys()
            .chain(self.project.assets.keys())
            .cloned()
            .collect();
        self.serial += 1;
        let mut revision = Revision {
            id: std::mem::replace(&mut self.revision, self.serial),
            name: (previous.name != self.project.name).then_some(previous.name),
            assets: BTreeMap::new(),
        };
        for id in keys {
            if previous.assets.get(&id) != self.project.assets.get(&id) {
                let value = previous.assets.remove(&id);
                revision.assets.insert(id, value);
            }
        }
        if self.undo.len() == 32 {
            self.undo.remove(0);
        }
        self.undo.push(revision);
        self.redo.clear();
        Ok(true)
    }

    pub fn can_undo(&self) -> bool {
        !self.undo.is_empty()
    }

    pub fn can_redo(&self) -> bool {
        !self.redo.is_empty()
    }

    pub fn undo(&mut self) -> bool {
        let Some(mut revision) = self.undo.pop() else {
            return false;
        };
        revision.swap(&mut self.project, &mut self.revision);
        self.redo.push(revision);
        true
    }

    pub fn redo(&mut self) -> bool {
        let Some(mut revision) = self.redo.pop() else {
            return false;
        };
        revision.swap(&mut self.project, &mut self.revision);
        self.undo.push(revision);
        true
    }
}
