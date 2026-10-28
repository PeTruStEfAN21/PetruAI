use std::io::{Read, Write};

use crate::error::StoreError;
use crate::store::Store;

/// Escape a string for snapshot output.
/// Backslash -> \\, tab -> \t, newline -> \n
fn escape(s: &str) -> String {
    let mut result = String::new();
    for ch in s.chars() {
        match ch {
            '\\' => result.push_str("\\\\"),
            '\t' => result.push_str("\\t"),
            '\n' => result.push_str("\\n"),
            _ => result.push(ch),
        }
    }
    result
}

/// Unescape a snapshot string.
fn unescape(s: &str) -> Result<String, StoreError> {
    let mut result = String::new();
    let mut chars = s.chars();
    while let Some(ch) = chars.next() {
        if ch == '\\' {
            match chars.next() {
                Some('n') => result.push('\n'),
                Some('t') => result.push('\t'),
                Some('\\') => result.push('\\'),
                Some(_other) => {
                    return Err(StoreError::Corrupt(0));
                }
                None => {
                    return Err(StoreError::Corrupt(0));
                }
            }
        } else {
            result.push(ch);
        }
    }
    Ok(result)
}

pub fn save(store: &Store, writer: &mut impl Write) -> Result<(), StoreError> {
    if store.depth() > 0 {
        return Err(StoreError::InTransaction);
    }
    
    // Get all committed entries sorted by key
    // We need to iterate over committed data
    // Since Store doesn't expose committed directly, let's collect via keys_with_prefix("")
    let keys = store.keys_with_prefix("");
    for key in &keys {
        let value = store.get(key).unwrap();
        let escaped_key = escape(key);
        let escaped_value = escape(value);
        writeln!(writer, "{}\t{}", escaped_key, escaped_value)
            .map_err(|e| StoreError::Io(e.to_string()))?;
    }
    
    Ok(())
}

pub fn load(reader: &mut impl Read) -> Result<Store, StoreError> {
    let mut store = Store::new();
    
    let mut buf = String::new();
    reader.read_to_string(&mut buf).map_err(|e| StoreError::Io(e.to_string()))?;
    
    for (line_num, line) in buf.lines().enumerate() {
        let line_num = line_num + 1; // 1-based
        let parts: Vec<&str> = line.splitn(2, '\t').collect();
        if parts.len() != 2 {
            return Err(StoreError::Corrupt(line_num));
        }
        let key = unescape(parts[0])?;
        let value = unescape(parts[1])?;
        store.set(&key, &value);
    }
    
    Ok(store)
}
