//! An INI file parser and writer: sections, comments, quoted values, typed getters, interpolation.

mod document;
mod error;
mod interpolate;
mod parser;
mod value;
mod writer;

pub use document::Ini;
pub use error::{ParseError, ParseErrorKind, ValueError};
