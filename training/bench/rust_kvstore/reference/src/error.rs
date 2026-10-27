use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StoreError {
    NoTransaction,
    InTransaction,
    Corrupt(usize),
    Io(String),
}

impl fmt::Display for StoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StoreError::NoTransaction => write!(f, "no transaction"),
            StoreError::InTransaction => write!(f, "cannot save inside a transaction"),
            StoreError::Corrupt(line) => write!(f, "corrupt snapshot at line {line}"),
            StoreError::Io(message) => write!(f, "io error: {message}"),
        }
    }
}

impl std::error::Error for StoreError {}

impl From<std::io::Error> for StoreError {
    fn from(err: std::io::Error) -> Self {
        StoreError::Io(err.to_string())
    }
}
