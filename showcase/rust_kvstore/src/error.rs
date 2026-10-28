use std::fmt;

#[derive(Debug, PartialEq)]
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
            StoreError::Corrupt(n) => write!(f, "corrupt snapshot at line {}", n),
            StoreError::Io(msg) => write!(f, "io error: {}", msg),
        }
    }
}
