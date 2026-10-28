use std::fmt;

/// Kind of parse error
#[derive(Debug, PartialEq, Clone)]
pub enum ParseErrorKind {
    MissingEquals,
    UnclosedSection,
    EmptyKey,
    DuplicateKey(String),
    UnterminatedQuote,
}

/// Parse error with line number
#[derive(Debug, PartialEq, Clone)]
pub struct ParseError {
    pub line: usize,
    pub kind: ParseErrorKind,
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.kind {
            ParseErrorKind::MissingEquals => write!(f, "line {}: expected key = value", self.line),
            ParseErrorKind::UnclosedSection => write!(f, "line {}: unclosed section header", self.line),
            ParseErrorKind::EmptyKey => write!(f, "line {}: empty key", self.line),
            ParseErrorKind::DuplicateKey(key) => write!(f, "line {}: duplicate key {}", self.line, key),
            ParseErrorKind::UnterminatedQuote => write!(f, "line {}: unterminated quote", self.line),
        }
    }
}

/// Value error (interpolation errors)
#[derive(Debug, PartialEq, Clone)]
pub enum ValueError {
    Missing { section: String, key: String },
    Invalid { section: String, key: String, value: String, expected: &'static str },
    Cycle(String),
}

impl fmt::Display for ValueError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ValueError::Missing { section, key } => write!(f, "missing {}.{}", section, key),
            ValueError::Invalid { section, key, value, expected } => {
                write!(f, "{}.{}: expected {}, got '{}'", section, key, expected, value)
            }
            ValueError::Cycle(loc) => write!(f, "interpolation cycle at {}", loc),
        }
    }
}
