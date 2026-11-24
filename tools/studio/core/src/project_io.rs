use crate::*;
use serde::Serialize;
use std::io::{Cursor, Read, Write};
use zip::write::SimpleFileOptions;

pub fn json<T: Serialize>(value: &T) -> Result<Vec<u8>> {
    let mut bytes = serde_json::to_vec_pretty(value)
        .map_err(|error| Error::new("json", "", error.to_string()))?;
    bytes.push(b'\n');
    Ok(bytes)
}

pub fn load_project(bytes: &[u8]) -> Result<Project> {
    let decoded;
    let bytes = if bytes.starts_with(b"PK") {
        let mut archive = zip::ZipArchive::new(Cursor::new(bytes)).map_err(zip_error)?;
        if archive.len() != 1 {
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

pub fn save_project(project: &Project, archive: bool) -> Result<Vec<u8>> {
    require_valid(project)?;
    let manifest = json(project)?;
    if manifest.len() > MAX_PROJECT_BYTES {
        return Err(invalid("Canonical project manifest exceeds 64 MiB"));
    }
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
