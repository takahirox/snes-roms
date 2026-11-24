use crate::*;
use serde::Serialize;
use std::io::{self, Cursor, Read, Write};
use zip::write::SimpleFileOptions;

pub fn json<T: Serialize>(value: &T) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    write_json(&mut bytes, value).map_err(json_error)?;
    Ok(bytes)
}

pub fn asset_data_json(project: &Project, id: &str) -> Result<Vec<u8>> {
    match asset(project, id)? {
        Asset::Palette(data) => json(data),
        Asset::Tile(data) => json(data),
        Asset::Metatile(data) => json(data),
        Asset::Tileset(data) => json(data),
        Asset::Map(data) => json(data),
        Asset::Sprite(data) => json(data),
        Asset::Font(data) => json(data),
        Asset::Sample(data) => json(data),
        Asset::Sequence(data) => json(data),
        Asset::Vram(data) => json(data),
    }
}

fn write_json(mut output: impl Write, value: &impl Serialize) -> serde_json::Result<()> {
    serde_json::to_writer_pretty(&mut output, value)?;
    output.write_all(b"\n").map_err(serde_json::Error::io)
}

fn json_error(error: serde_json::Error) -> Error {
    Error::new("json", "", error.to_string())
}

pub fn load_project(bytes: &[u8]) -> Result<Project> {
    let decoded;
    let bytes = if bytes.starts_with(b"PK") {
        let mut archive = zip::ZipArchive::new(Cursor::new(bytes)).map_err(zip_error)?;
        if archive.len() != 1
            || !bytes
                .get(archive.central_directory_start() as usize..)
                .is_some_and(has_single_zip_entry)
        {
            return Err(invalid(
                "ZIP must contain exactly one studio.json at its root",
            ));
        }
        let file = archive.by_name(PROJECT_FILE).map_err(zip_error)?;
        if !file.is_file() || file.size() > MAX_PROJECT_BYTES as u64 {
            return Err(invalid("ZIP manifest is missing or exceeds 64 MiB"));
        }
        let mut contents = Vec::new();
        file.take(MAX_PROJECT_BYTES as u64 + 1)
            .read_to_end(&mut contents)
            .map_err(|error| Error::new("zip", PROJECT_FILE, error.to_string()))?;
        decoded = contents;
        &decoded
    } else {
        bytes
    };
    if bytes.len() > MAX_PROJECT_BYTES {
        return Err(invalid("Project manifest exceeds 64 MiB"));
    }
    // Check the envelope before interpreting the version-specific asset schema.
    #[derive(serde::Deserialize)]
    struct Envelope {
        version: u32,
    }
    let envelope: Envelope = serde_json::from_slice(bytes)
        .map_err(|error| Error::new("json", PROJECT_FILE, error.to_string()))?;
    if envelope.version != VERSION {
        return Err(Error::new(
            "version",
            "/version",
            format!("Expected version {VERSION}, got {}", envelope.version),
        ));
    }
    serde_json::from_slice(bytes)
        .map_err(|error| Error::new("json", PROJECT_FILE, error.to_string()))
}

fn has_single_zip_entry(directory: &[u8]) -> bool {
    const CENTRAL_HEADER_BYTES: usize = 46;
    // ZipArchive indexes by name, so len() can hide duplicates. Skip the
    // first central-directory record using its three variable field lengths.
    let Some(lengths) = directory.get(28..34) else {
        return false;
    };
    let variable_length: usize = lengths
        .chunks_exact(2)
        .map(|length| usize::from(u16::from_le_bytes([length[0], length[1]])))
        .sum();
    directory
        .get(CENTRAL_HEADER_BYTES + variable_length..)
        .is_some_and(|rest| !rest.starts_with(b"PK\x01\x02"))
}

struct ManifestWriter<W> {
    output: W,
    remaining: usize,
}

impl<W: Write> Write for ManifestWriter<W> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if bytes.len() > self.remaining {
            return Err(io::ErrorKind::FileTooLarge.into());
        }
        let written = self.output.write(bytes)?;
        self.remaining -= written;
        Ok(written)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.output.flush()
    }
}

fn write_manifest(project: &Project, output: impl Write) -> Result<()> {
    let writer = ManifestWriter {
        output,
        remaining: MAX_PROJECT_BYTES,
    };
    write_json(writer, project).map_err(|error| {
        if error.io_error_kind() == Some(io::ErrorKind::FileTooLarge) {
            invalid("Canonical project manifest exceeds 64 MiB")
        } else {
            json_error(error)
        }
    })
}

pub(crate) fn require_manifest_fits(project: &Project) -> Result<()> {
    write_manifest(project, io::sink())
}

pub fn save_project(project: &Project, archive: bool) -> Result<Vec<u8>> {
    require_valid_content(project)?;
    let mut manifest = Vec::new();
    write_manifest(project, &mut manifest)?;
    if !archive {
        return Ok(manifest);
    }
    let mut writer = zip::ZipWriter::new(Cursor::new(Vec::new()));
    writer
        .start_file(
            PROJECT_FILE,
            SimpleFileOptions::default()
                .compression_method(zip::CompressionMethod::Stored)
                .last_modified_time(zip::DateTime::default())
                .unix_permissions(0o644),
        )
        .map_err(zip_error)?;
    writer
        .write_all(&manifest)
        .map_err(|error| Error::new("zip", PROJECT_FILE, error.to_string()))?;
    Ok(writer.finish().map_err(zip_error)?.into_inner())
}

fn zip_error(error: zip::result::ZipError) -> Error {
    Error::new("zip", PROJECT_FILE, error.to_string())
}

pub fn fingerprint(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    format!("{:x}", Sha256::digest(bytes))
}
