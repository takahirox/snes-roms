use clap::{Parser, Subcommand, ValueEnum};
use serde_json::json;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use studio::{Diagnostic, Error, ExportOptions, ImageImport, Project, Rect, Result, Severity};
use studio_core as studio;

#[derive(Parser)]
#[command(version, about = "Author and inspect game-agnostic Super Famicom assets", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Create a project JSON, ZIP, or studio.json inside an existing directory.
    Init {
        output: PathBuf,
        #[arg(long, default_value = "Untitled")]
        name: String,
    },
    /// Report stable JSON diagnostics and the fingerprint of the input.
    Validate { project: PathBuf },
    /// Compare two projects and report changes by JSON Pointer.
    Diff { before: PathBuf, after: PathBuf },
    /// Apply a JSON array of edits as a single transaction.
    Edit {
        project: PathBuf,
        edits: PathBuf,
        #[command(flatten)]
        destination: Destination,
    },
    /// Copy a rectangular selection to JSON on stdout.
    Copy {
        project: PathBuf,
        map: String,
        layer: String,
        x: u16,
        y: u16,
        width: u16,
        height: u16,
    },
    /// Write canonical JSON or portable ZIP.
    Pack { project: PathBuf, output: PathBuf },
    /// Render a graphic asset as an RGBA PNG.
    Render {
        project: PathBuf,
        id: String,
        output: PathBuf,
        #[arg(long)]
        frame: Option<String>,
        #[arg(long)]
        text: Option<String>,
        #[arg(long)]
        bpp: Option<u8>,
    },
    /// Export a graphics or audio asset.
    Export {
        project: PathBuf,
        id: String,
        #[arg(value_enum)]
        format: Format,
        output: PathBuf,
        #[arg(long)]
        frame: Option<String>,
        #[arg(long)]
        text: Option<String>,
        #[arg(long)]
        bpp: Option<u8>,
    },
    /// Turn a PNG into a named tileset of 8×8 tiles.
    ImportImage {
        project: PathBuf,
        source: PathBuf,
        tileset: String,
        palette: String,
        #[arg(long, default_value_t = 4)]
        bpp: u8,
        #[arg(long)]
        preserve_indices: bool,
        #[command(flatten)]
        destination: Destination,
    },
    /// Import a mono PCM WAV or raw BRR stream.
    ImportSample {
        project: PathBuf,
        source: PathBuf,
        id: String,
        #[arg(value_enum)]
        format: SampleFormat,
        #[arg(long)]
        rate: Option<u32>,
        #[arg(long)]
        loop_offset: Option<u32>,
        #[command(flatten)]
        destination: Destination,
    },
    /// Inspect a read-only SNES ROM header with an explicit mapping.
    RomHeader {
        rom: PathBuf,
        #[arg(value_enum)]
        layout: RomLayout,
    },
    /// Use the generic Studio RLE v1 codec.
    #[command(subcommand)]
    Rle(Codec),
}

#[derive(ValueEnum, Clone, Copy)]
enum Format {
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

impl From<Format> for studio::Format {
    fn from(value: Format) -> Self {
        match value {
            Format::Png => Self::Png,
            Format::IndexedPng => Self::IndexedPng,
            Format::Chr => Self::Chr,
            Format::Palette => Self::Palette,
            Format::Wav => Self::Wav,
            Format::Brr => Self::Brr,
            Format::Oam => Self::Oam,
            Format::ObjChr => Self::ObjChr,
            Format::ObjCgram => Self::ObjCgram,
        }
    }
}

#[derive(ValueEnum, Clone, Copy)]
enum SampleFormat {
    Wav,
    Brr,
}

#[derive(ValueEnum, Clone, Copy)]
enum RomLayout {
    #[value(name = "lo-rom")]
    Low,
    #[value(name = "hi-rom")]
    High,
    #[value(name = "ex-hi-rom")]
    ExtendedHigh,
}

#[derive(Subcommand)]
enum Codec {
    Compress { input: PathBuf, output: PathBuf },
    Decompress { input: PathBuf, output: PathBuf },
}

#[derive(clap::Args)]
#[group(required = true, multiple = false)]
struct Destination {
    /// Print a JSON diff and diagnostics without writing any file.
    #[arg(long)]
    dry_run: bool,
    /// Write a new project. An existing destination fails.
    #[arg(short, long)]
    output: Option<PathBuf>,
    /// Update the source only if it still matches the supplied SHA-256.
    #[arg(long, value_name = "SHA256")]
    expect: Option<String>,
}

fn main() -> ExitCode {
    let cli = match Cli::try_parse() {
        Ok(cli) => cli,
        Err(error) if !error.use_stderr() => error.exit(),
        Err(error) => {
            return failure(Error::new("usage", "", error.to_string()));
        }
    };
    match run(cli.command) {
        Ok(code) => ExitCode::from(code),
        Err(error) => failure(error),
    }
}

fn failure(error: Error) -> ExitCode {
    let code = if error.0.iter().any(|item| item.code == "conflict") {
        4
    } else if error.0.iter().any(|item| item.code == "io") {
        3
    } else {
        2
    };
    let payload = studio::json(&json!({"ok": false, "diagnostics": error.0})).unwrap();
    let _ = std::io::stderr().lock().write_all(&payload);
    ExitCode::from(code)
}

fn run(command: Command) -> Result<u8> {
    match command {
        Command::Init { output, name } => {
            let project = Project {
                name,
                ..Project::default()
            };
            write_project(&output, &project)?;
        }
        Command::Validate { project } => {
            let (project, revision) = read_project(&project)?;
            let diagnostics = studio::validate(&project);
            let ok = diagnostics
                .iter()
                .all(|diag| diag.severity == Severity::Warning);
            print_json(&json!({"ok": ok, "revision": revision, "diagnostics": diagnostics}))?;
            if !ok {
                return Ok(2);
            }
        }
        Command::Diff { before, after } => {
            print_json(
                &json!({"changes": studio::diff(&read_project(&before)?.0, &read_project(&after)?.0)?}),
            )?;
        }
        Command::Edit {
            project,
            edits,
            destination,
        } => {
            let edits = studio::edits_from_json(&read(&edits)?)?;
            change_project(&project, destination, |_| Ok(edits))?;
        }
        Command::Copy {
            project,
            map,
            layer,
            x,
            y,
            width,
            height,
        } => {
            let rect = Rect {
                x,
                y,
                width,
                height,
            };
            print_json(
                &serde_json::to_value(studio::copy_selection(
                    &read_project(&project)?.0,
                    &map,
                    &layer,
                    rect,
                )?)
                .unwrap(),
            )?;
        }
        Command::Pack { project, output } => write_project(&output, &read_project(&project)?.0)?,
        Command::Render {
            project,
            id,
            output,
            frame,
            text,
            bpp,
        } => {
            let options = ExportOptions {
                format: studio::Format::Png,
                frame,
                text,
                bpp,
            };
            write_new(
                &output,
                &studio::export(&read_project(&project)?.0, &id, &options)?,
            )?;
        }
        Command::Export {
            project,
            id,
            format,
            output,
            frame,
            text,
            bpp,
        } => {
            let options = ExportOptions {
                format: format.into(),
                frame,
                text,
                bpp,
            };
            write_new(
                &output,
                &studio::export(&read_project(&project)?.0, &id, &options)?,
            )?;
        }
        Command::ImportImage {
            project,
            source,
            tileset,
            palette,
            bpp,
            preserve_indices,
            destination,
        } => {
            let options = ImageImport {
                tileset,
                palette,
                bpp,
                preserve_indices,
            };
            let bytes = read(&source)?;
            change_project(&project, destination, |project| {
                studio::import_png(project, &bytes, &options)
            })?;
        }
        Command::ImportSample {
            project,
            source,
            id,
            format,
            rate,
            loop_offset,
            destination,
        } => {
            let format = match format {
                SampleFormat::Wav => studio::SampleFormat::Wav,
                SampleFormat::Brr => studio::SampleFormat::Brr,
            };
            let bytes = read(&source)?;
            change_project(&project, destination, |project| {
                Ok(vec![studio::import_sample(
                    project,
                    id,
                    format,
                    &bytes,
                    rate,
                    loop_offset,
                )?])
            })?;
        }
        Command::RomHeader { rom, layout } => {
            let layout = match layout {
                RomLayout::Low => studio::RomLayout::LoRom,
                RomLayout::High => studio::RomLayout::HiRom,
                RomLayout::ExtendedHigh => studio::RomLayout::ExHiRom,
            };
            print_json(&serde_json::to_value(studio::inspect_rom(&read(&rom)?, layout)?).unwrap())?;
        }
        Command::Rle(Codec::Compress { input, output }) => {
            write_new(&output, &studio::compress_rle(&read(&input)?)?)?
        }
        Command::Rle(Codec::Decompress { input, output }) => {
            write_new(&output, &studio::decompress_rle(&read(&input)?)?)?
        }
    }
    Ok(0)
}

fn print_json(payload: &serde_json::Value) -> Result<()> {
    std::io::stdout()
        .lock()
        .write_all(&studio::json(payload)?)
        .map_err(|error| io(Path::new("<stdout>"), error))
}

fn project_path(path: &Path) -> PathBuf {
    if path.is_dir() {
        path.join(studio::PROJECT_FILE)
    } else {
        path.to_path_buf()
    }
}

fn read_project(path: &Path) -> Result<(Project, String)> {
    let bytes = read(&project_path(path))?;
    Ok((studio::load_project(&bytes)?, studio::fingerprint(&bytes)))
}

fn read(path: &Path) -> Result<Vec<u8>> {
    // Allow the worst-case RLE expansion and portable ZIP's container overhead.
    const LIMIT: u64 = 66 * 1024 * 1024;
    let mut bytes = Vec::new();
    File::open(path)
        .map_err(|error| io(path, error))?
        .take(LIMIT + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| io(path, error))?;
    if bytes.len() as u64 > LIMIT {
        return Err(Error::new(
            "input_size",
            path.display().to_string(),
            "Input exceeds 66 MiB",
        ));
    }
    Ok(bytes)
}

fn archive(path: &Path) -> bool {
    path.extension()
        .is_some_and(|extension| extension.eq_ignore_ascii_case("zip"))
}

fn io(path: &Path, error: std::io::Error) -> Error {
    Error::new("io", path.display().to_string(), error.to_string())
}

fn conflict(path: &Path, message: &str) -> Error {
    Error::new("conflict", path.display().to_string(), message)
}

fn parent_directory(path: &Path) -> &Path {
    path.parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or(Path::new("."))
}

fn stage(path: &Path, bytes: &[u8]) -> Result<tempfile::NamedTempFile> {
    let mut file =
        tempfile::NamedTempFile::new_in(parent_directory(path)).map_err(|error| io(path, error))?;
    file.write_all(bytes).map_err(|error| io(path, error))?;
    file.as_file().sync_all().map_err(|error| io(path, error))?;
    Ok(file)
}

fn is_folder_manifest(path: &Path) -> bool {
    path.file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name.eq_ignore_ascii_case(studio::PROJECT_FILE))
}

fn claim_folder_save(path: &Path) -> Result<tempfile::NamedTempFile> {
    // The browser uses the same namespace. Each writer announces itself before
    // looking for other writers and keeps its marker until the commit finishes.
    const PREFIX: &str = "studio.json.save-";
    const SUFFIX: &str = ".lock";
    let parent = parent_directory(path);
    let marker = tempfile::Builder::new()
        .prefix(PREFIX)
        .suffix(SUFFIX)
        .tempfile_in(parent)
        .map_err(|error| io(path, error))?;
    for entry in fs::read_dir(parent).map_err(|error| io(path, error))? {
        let name = entry.map_err(|error| io(path, error))?.file_name();
        if Some(name.as_os_str()) != marker.path().file_name()
            && name
                .to_str()
                .is_some_and(|name| name.starts_with(PREFIX) && name.ends_with(SUFFIX))
        {
            return Err(conflict(
                path,
                "Another Studio save holds a marker in this folder. Review the project before retrying.",
            ));
        }
    }
    Ok(marker)
}

fn lock_project(path: &Path) -> Result<(Option<tempfile::NamedTempFile>, File)> {
    let mut lock_name = path.file_name().unwrap().to_os_string();
    lock_name.push(".lock");
    let lock = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(false)
        .open(path.with_file_name(lock_name))
        .map_err(|error| io(path, error))?;
    lock.lock().map_err(|error| io(path, error))?;
    let marker = is_folder_manifest(path)
        .then(|| claim_folder_save(path))
        .transpose()?;
    // Drop the marker before releasing the lock to the next CLI writer.
    Ok((marker, lock))
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<()> {
    let file = stage(path, bytes)?;
    let _save = is_folder_manifest(path)
        .then(|| lock_project(path))
        .transpose()?;
    file.persist_noclobber(path).map_err(|error| {
        if error.error.kind() == std::io::ErrorKind::AlreadyExists {
            conflict(path, "Destination exists. Choose a new path.")
        } else {
            io(path, error.error)
        }
    })?;
    Ok(())
}

fn write_project(path: &Path, project: &Project) -> Result<()> {
    let path = project_path(path);
    write_new(&path, &studio::save_project(project, archive(&path))?)
}

fn change_project(
    path: &Path,
    destination: Destination,
    edit: impl FnOnce(&Project) -> Result<Vec<studio::Edit>>,
) -> Result<()> {
    let (project, revision) = read_project(path)?;
    if let Some(expected) = &destination.expect
        && expected != &revision
    {
        return Err(conflict(
            path,
            "Project fingerprint changed. Read and review the current file before retrying.",
        ));
    }
    let next = studio::apply(&project, &edit(&project)?)?;
    let changes = studio::diff(&project, &next)?;
    let diagnostics: Vec<Diagnostic> = studio::validate(&next);
    let mut saved_revision = None;
    if let Some(output) = destination.output {
        let output = project_path(&output);
        let bytes = studio::save_project(&next, archive(&output))?;
        write_new(&output, &bytes)?;
        saved_revision = Some(studio::fingerprint(&bytes));
    } else if let Some(expected) = destination.expect {
        let path = fs::canonicalize(project_path(path)).map_err(|error| io(path, error))?;
        let _save = lock_project(&path)?;
        let current = read(&path)?;
        if studio::fingerprint(&current) != expected {
            return Err(conflict(
                &path,
                "Project fingerprint changed. Read and review the current file before retrying.",
            ));
        }
        if changes.is_empty() {
            saved_revision = Some(expected);
        } else {
            let bytes = studio::save_project(&next, current.starts_with(b"PK"))?;
            let file = stage(&path, &bytes)?;
            let permissions = fs::metadata(&path)
                .map_err(|error| io(&path, error))?
                .permissions();
            file.as_file()
                .set_permissions(permissions)
                .map_err(|error| io(&path, error))?;
            if studio::fingerprint(&read(&path)?) != expected {
                return Err(conflict(
                    &path,
                    "Project changed while the new file was being prepared.",
                ));
            }
            file.persist(&path)
                .map_err(|error| io(&path, error.error))?;
            saved_revision = Some(studio::fingerprint(&bytes));
        }
    }
    print_json(
        &json!({"ok": true, "dry_run": destination.dry_run, "revision": revision, "saved_revision": saved_revision, "changes": changes, "diagnostics": diagnostics}),
    )
}
