use std::io::{Cursor, Write};
use studio_core::*;

fn fixture() -> Project {
    load_project(include_bytes!("../../fixtures/demo/studio.json")).unwrap()
}

fn asset_tile<'a>(project: &'a Project, id: &str) -> &'a Tile {
    let Asset::Tile(tile) = &project.assets[id] else {
        panic!("expected tile");
    };
    tile
}

#[test]
fn canonical_json_and_zip_round_trip() {
    let bytes = include_bytes!("../../fixtures/demo/studio.json");
    let project = fixture();
    assert!(validate(&project).is_empty());
    assert_eq!(save_project(&project, false).unwrap(), bytes);
    let zip = save_project(&project, true).unwrap();
    assert_eq!(zip, save_project(&project, true).unwrap());
    assert_eq!(load_project(&zip).unwrap(), project);
    let unknown = br#"{"name":"x","version":2,"assets":{"a":{"kind":"new"}}}"#;
    assert_eq!(load_project(unknown).unwrap_err().0[0].code, "version");
    let duplicate = br#"{"name":"x","version":1,"assets":{"p":{"kind":"palette","data":{"colors":[0],"transparent":0}},"p":{"kind":"palette","data":{"colors":[0],"transparent":null}}}}"#;
    assert!(
        load_project(duplicate)
            .unwrap_err()
            .to_string()
            .contains("Duplicate asset ID p")
    );
}

#[test]
fn project_zip_rejects_duplicate_manifest_entries() {
    let zip = |entries: &[(&str, &str)]| {
        let mut writer = zip::ZipWriter::new(Cursor::new(Vec::new()));
        let options = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated);
        for &(path, name) in entries {
            writer.start_file(path, options).unwrap();
            write!(writer, r#"{{"version":1,"name":"{name}","assets":{{}}}}"#).unwrap();
        }
        writer.finish().unwrap().into_inner()
    };
    assert_eq!(
        load_project(&zip(&[(PROJECT_FILE, "First")])).unwrap().name,
        "First"
    );
    let mut archive = zip(&[(PROJECT_FILE, "First"), ("backup.json", "Second")]);
    // The writer rejects duplicate names. Rename the second entry in both headers.
    let offsets: Vec<_> = archive
        .windows(PROJECT_FILE.len())
        .enumerate()
        .filter_map(|(offset, name)| (name == b"backup.json").then_some(offset))
        .collect();
    assert_eq!(offsets.len(), 2);
    for offset in offsets {
        archive[offset..offset + PROJECT_FILE.len()].copy_from_slice(PROJECT_FILE.as_bytes());
    }
    assert!(
        load_project(&archive)
            .unwrap_err()
            .to_string()
            .contains("ZIP must contain exactly one studio.json at its root")
    );
}

#[test]
fn planar_has_correct_plane_and_pixel_order() {
    for bpp in [2, 4, 8] {
        let mut tile = Tile {
            bpp,
            palette: "p".into(),
            pixels: vec![0; 64],
        };
        tile.pixels[0] = (color_limit(bpp) - 1) as u8;
        tile.pixels[15] = 1;
        let bytes = planar_tile(&tile).unwrap();
        assert_eq!(bytes.len(), usize::from(bpp) * 8);
        for plane in 0..usize::from(bpp) {
            assert_eq!(bytes[(plane / 2) * 16 + plane % 2], 0x80);
        }
        assert_eq!(bytes[2], 1);
        assert_eq!(decode_planar_tile(&bytes, bpp, "p".into()).unwrap(), tile);
    }
    assert_eq!(rgb(bgr555([255, 0, 128])), [255, 0, 132]);
}

#[test]
fn indexed_png_preserves_indices_and_quantized_palette() {
    let project = fixture();
    for (id, bpp) in [("letter-f", 2), ("compass", 4), ("compass", 8)] {
        let png = export_indexed(&project, id, Some(bpp)).unwrap();
        assert_eq!(export_indexed(&project, id, Some(bpp)).unwrap(), png);
        let mut reader = png::Decoder::new(Cursor::new(&png)).read_info().unwrap();
        assert_eq!(reader.info().color_type, png::ColorType::Indexed);
        assert_eq!(reader.info().bit_depth as u8, bpp);
        let mut bytes = vec![0; reader.output_buffer_size().unwrap()];
        reader.next_frame(&mut bytes).unwrap();

        let import = ImageImport {
            tileset: "sheet".into(),
            palette: "imported".into(),
            bpp,
            preserve_indices: true,
        };
        let result = apply(&project, &import_png(&project, &png, &import).unwrap()).unwrap();
        let tile = asset_tile(&result, "sheet-0000");
        let original = asset_tile(&project, id);
        assert_eq!(tile.pixels, original.pixels);
        assert_eq!(result.assets["imported"], project.assets[&original.palette]);
    }
    let source = render(&project, "compass", None, None).unwrap();
    let options = ImageImport {
        tileset: "quantized".into(),
        palette: "signals".into(),
        bpp: 4,
        preserve_indices: false,
    };
    let quantized = apply(
        &project,
        &import_png(&project, &source.png().unwrap(), &options).unwrap(),
    )
    .unwrap();
    assert_eq!(
        render(&quantized, "quantized-0000", None, None).unwrap(),
        source
    );
    assert!(export_indexed(&project, "compass", Some(2)).is_err());
}

#[test]
fn shared_edits_are_transactional_and_history_restores_noop_state() {
    let initial = fixture();
    let mut editor = Editor::new(initial.clone());
    let edits = edits_from_json(include_bytes!("../../fixtures/paint.json")).unwrap();
    assert!(editor.edit(&edits).unwrap());
    let changed = editor.project().clone();
    assert!(!diff(&initial, &changed).unwrap().is_empty());
    assert!(!editor.edit(&edits).unwrap());
    let bad = [
        edits[0].clone(),
        Edit::Remove {
            id: "signals".into(),
        },
    ];
    assert!(editor.edit(&bad).is_err());
    assert_eq!(editor.project(), &changed);
    assert!(editor.undo());
    assert_eq!(editor.project(), &initial);
    assert!(editor.redo());
    assert_eq!(editor.project(), &changed);
    assert!(editor.undo());
    assert!(!editor.can_undo());
    assert!(!editor.edit(&[]).unwrap());
    assert!(editor.can_redo());
    assert!(
        editor
            .edit(&[Edit::Name {
                name: "another project".into()
            }])
            .unwrap()
    );
    assert!(!editor.can_redo());
}

#[test]
fn map_flip_fill_paste_and_resize() {
    let initial = fixture();
    let map = "console-grid".to_string();
    let layer = "panels".to_string();
    let rect = Rect {
        x: 0,
        y: 0,
        width: 2,
        height: 1,
    };
    let copied = copy_selection(&initial, &map, &layer, rect).unwrap();
    assert_eq!(copied.cells[0].as_ref().unwrap().asset, "console");
    assert!(copied.cells[1].is_none());
    let malformed = Edit::Paste {
        id: map.clone(),
        layer: layer.clone(),
        x: 1,
        y: 1,
        selection: copied.clone(),
    };
    assert!(apply(&initial, &[malformed]).is_err());
    let next = apply(
        &initial,
        &[
            Edit::Paste {
                id: map.clone(),
                layer: layer.clone(),
                x: 0,
                y: 1,
                selection: copied.clone(),
            },
            Edit::Fill {
                id: map.clone(),
                layer: layer.clone(),
                x: 1,
                y: 0,
                cell: copied.cells[0].clone(),
            },
            Edit::ResizeMap {
                id: map.clone(),
                width: 3,
                height: 2,
            },
        ],
    )
    .unwrap();
    let image = render(&initial, &map, None, None).unwrap();
    let panel = render(&initial, "console", None, None).unwrap();
    let pixel = |image: &Image, x, y| {
        let index = (y * image.width + x) as usize * 4;
        <[u8; 4]>::try_from(&image.rgba[index..index + 4]).unwrap()
    };
    for y in 0..16 {
        for x in 0..16 {
            assert_eq!(pixel(&image, x, y), pixel(&panel, x, y));
            assert_eq!(pixel(&image, x + 16, y + 16), pixel(&panel, 15 - x, 15 - y));
        }
    }
    let rect = Rect {
        x: 0,
        y: 0,
        width: 3,
        height: 2,
    };
    let snapshot = copy_selection(&next, &map, &layer, rect).unwrap();
    assert_eq!(
        snapshot
            .cells
            .iter()
            .map(Option::is_some)
            .collect::<Vec<_>>(),
        [true, true, false, true, true, false]
    );
}

#[test]
fn sprite_oam_and_budget_follow_hardware_layout() {
    let mut project = fixture();
    let output = export_sprite(&project, "signal-light", Some("flare")).unwrap();
    assert_eq!(output.oam.len(), 544);
    assert_eq!(output.chr.len(), 16_384);
    assert_eq!(output.cgram.len(), 256);
    assert_eq!(
        &output.oam[..12],
        &[12, 8, 0, 0x22, 4, 12, 1, 0x22, 1, 0, 0, 0]
    );
    assert_eq!(output.oam[512], 0x50);
    assert_eq!(
        &output.chr[..32],
        planar_tile(asset_tile(&project, "compass")).unwrap()
    );
    let Asset::Sprite(sprite) = project.assets.get_mut("signal-light").unwrap() else {
        unreachable!()
    };
    assert_eq!(frame_at(sprite, 199).unwrap().id, "flare");
    assert_eq!(frame_at(sprite, 200).unwrap().id, "dim");
    assert_eq!(frame_at(sprite, 460).unwrap().id, "flare");
    let mut object = sprite.frames[0].objects[0].clone();
    object.x = -256;
    object.y = -3;
    sprite.frames[0].objects = vec![object; 33];
    assert_eq!(over_budget_line(sprite, &sprite.frames[0]), Some(0));
    assert!(
        validate(&project)
            .iter()
            .any(|item| item.code == "scanline_budget" && item.severity == Severity::Warning)
    );
}

#[test]
fn wav_and_brr_round_trip_and_require_explicit_loop_offset() {
    let sample = Sample {
        sample_rate: 32_000,
        pcm: (0..32).map(|i| (i % 8 - 4) * 1024).collect(),
        loop_start: Some(16),
    };
    assert_eq!(read_wav(&write_wav(&sample).unwrap()).unwrap(), sample);
    let mut clipped_wav = write_wav(&sample).unwrap();
    clipped_wav.pop();
    assert!(read_wav(&clipped_wav).is_err());
    let brr = write_brr(&sample).unwrap();
    assert_eq!(brr.len(), 18);
    assert_eq!(brr[9] & 15, 3);
    assert!(read_brr(&brr, 32_000, None).is_err());
    assert_eq!(read_brr(&brr, 32_000, Some(9)).unwrap(), sample);
    let short = trim_sample(&sample, 8, 29).unwrap();
    assert_eq!(short.loop_start, Some(8));
    assert!(write_brr(&short).is_err());
    let vector = [0x81, 0x87, 0x17, 0, 0, 0, 0, 0, 0];
    assert_eq!(
        &read_brr(&vector, 32_000, None).unwrap().pcm[..4],
        &[-2048, 1792, 256, 1792]
    );

    let project = fixture();
    let preview = audio_preview(&project, "lab-chime").unwrap();
    assert_eq!(preview.sample_rate, 32_000);
    assert!(preview.pcm.iter().any(|&value| value != 0));
    assert_eq!(audio_preview(&project, "lab-chime").unwrap(), preview);
}

#[test]
fn one_shot_brr_preserves_audio_before_dsp_mutes() {
    for (length, pulse_start) in [(16, 0), (19, 16)] {
        let mut pcm = vec![0; length];
        pcm[pulse_start..].fill(4096);
        let pulse = Sample {
            sample_rate: 32_000,
            pcm,
            loop_start: None,
        };
        let brr = write_brr(&pulse).unwrap();
        // The S-DSP mutes when it sees END without LOOP. Verify every block
        // carrying the pulse comes before that header, including the tail.
        let mute_offset = brr
            .chunks_exact(9)
            .position(|block| block[0] & 3 == 1)
            .unwrap()
            * 9;
        assert_eq!(mute_offset, length.div_ceil(16) * 9);
        assert_eq!(&brr[mute_offset..], &[1, 0, 0, 0, 0, 0, 0, 0, 0]);
        let decoded = read_brr(&brr, 32_000, None).unwrap();
        assert_eq!(&decoded.pcm[..length], &pulse.pcm);
        assert_eq!(decoded.pcm.len(), length.next_multiple_of(16));
    }
}

#[test]
fn one_shot_brr_terminator_is_excluded_from_sample_and_included_in_aram_budget() {
    let mut brr = vec![0; (MAX_SAMPLES / 16 + 1) * 9];
    let terminator = brr.len() - 9;
    brr[terminator] = 1;
    assert_eq!(read_brr(&brr, 32_000, None).unwrap().pcm.len(), MAX_SAMPLES);

    let mut project = fixture();
    project.assets.insert(
        "budget-sample".into(),
        Asset::Sample(Sample {
            sample_rate: 32_000,
            pcm: vec![0; (65_536 / 9) * 16],
            loop_start: None,
        }),
    );
    assert!(validate(&project).iter().any(|diagnostic| {
        diagnostic.code == "sample_aram_budget" && diagnostic.path == "/assets/budget-sample/data"
    }));
}

#[test]
fn rom_inspection_and_rle_work_on_standalone_data() {
    let mut rom = vec![0; 0x8200];
    let offset = 0x81c0;
    rom[offset..offset + 4].copy_from_slice(b"TEST");
    rom[offset + 21] = 0x20;
    rom[offset + 28..offset + 32].copy_from_slice(&[0xed, 0xcb, 0x12, 0x34]);
    rom[offset + 60..offset + 62].copy_from_slice(&[0x00, 0x80]);
    let report = inspect_rom(&rom, RomLayout::LoRom).unwrap();
    assert_eq!(report.copier_bytes, 512);
    assert_eq!(report.title, "TEST");
    assert_eq!(report.map_mode, 0x20);
    assert_eq!(report.reset_vector, 0x8000);
    assert!(report.checksum_pair_valid);
    assert!(inspect_rom(&rom, RomLayout::HiRom).is_err());
    let mut input = (0..=255).collect::<Vec<u8>>();
    input.extend([0xc2; 320]);
    let compressed = compress_rle(&input).unwrap();
    assert_eq!(decompress_rle(&compressed).unwrap(), input);
    assert_eq!(compress_rle(&input).unwrap(), compressed);
    assert!(decompress_rle(&compressed[..compressed.len() - 1]).is_err());
    assert!(decompress_rle(&[b'S', b'R', b'L', 1, 1, 0, 0, 0, 0xff, 0]).is_err());
}

#[test]
fn invalid_project_has_stable_diagnostics_instead_of_rendering() {
    let mut project = fixture();
    let Asset::Map(map) = project.assets.get_mut("chromatic-lab").unwrap() else {
        unreachable!()
    };
    map.cell_width = u16::MAX;
    map.width = u16::MAX;
    map.metadata.insert(
        "unsafe/value".into(),
        serde_json::json!(9_007_199_254_740_992_u64),
    );
    let diagnostics = validate(&project);
    assert_eq!(diagnostics, validate(&project));
    assert!(
        diagnostics
            .iter()
            .any(|item| item.code == "metadata_integer" && item.path.ends_with("/unsafe~1value"))
    );
    assert!(diagnostics.iter().any(|item| item.code == "dimensions"));
    assert!(diagnostics.iter().any(|item| item.code == "grid_length"));
    assert!(render(&project, "chromatic-lab", None, None).is_err());
}
