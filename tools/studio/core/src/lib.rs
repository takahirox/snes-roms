mod audio;
mod edit;
mod exchange;
mod graphics;
mod hardware;
mod model;
mod project_io;
mod validate;

pub use audio::*;
pub use edit::*;
pub use exchange::*;
pub use graphics::*;
pub use hardware::*;
pub use model::*;
pub use project_io::*;
pub use validate::*;

use serde::Serialize;
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Error,
    Warning,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Diagnostic {
    pub severity: Severity,
    pub code: &'static str,
    pub path: String,
    pub message: String,
}

#[derive(Debug, Clone)]
pub struct Error(pub Vec<Diagnostic>);

impl Error {
    pub fn new(code: &'static str, path: impl Into<String>, message: impl Into<String>) -> Self {
        Self(vec![Diagnostic {
            severity: Severity::Error,
            code,
            path: path.into(),
            message: message.into(),
        }])
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        for (index, diagnostic) in self.0.iter().enumerate() {
            if index > 0 {
                writeln!(f)?;
            }
            write!(f, "{}: {}", diagnostic.path, diagnostic.message)?;
        }
        Ok(())
    }
}

impl std::error::Error for Error {}

pub type Result<T> = std::result::Result<T, Error>;

pub(crate) fn invalid(message: impl Into<String>) -> Error {
    Error::new("invalid_input", "", message)
}
