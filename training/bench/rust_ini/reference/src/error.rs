use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ParseErrorKind {
    MissingEquals,
    UnclosedSection,
    EmptyKey,
    DuplicateKey(String),
    UnterminatedQuote,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParseError {
    pub line: usize,
    pub kind: ParseErrorKind,
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: ", self.line)?;
        match &self.kind {
            ParseErrorKind::MissingEquals => write!(f, "expected key = value"),
            ParseErrorKind::UnclosedSection => write!(f, "unclosed section header"),
            ParseErrorKind::EmptyKey => write!(f, "empty key"),
            ParseErrorKind::DuplicateKey(key) => write!(f, "duplicate key {key}"),
            ParseErrorKind::UnterminatedQuote => write!(f, "unterminated quote"),
        }
    }
}

impl std::error::Error for ParseError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ValueError {
    Missing { section: String, key: String },
    Invalid { section: String, key: String, value: String, expected: &'static str },
    Cycle(String),
}

impl fmt::Display for ValueError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ValueError::Missing { section, key } => write!(f, "missing {section}.{key}"),
            ValueError::Invalid { section, key, value, expected } => {
                write!(f, "{section}.{key}: expected {expected}, got '{value}'")
            }
            ValueError::Cycle(at) => write!(f, "interpolation cycle at {at}"),
        }
    }
}

impl std::error::Error for ValueError {}
