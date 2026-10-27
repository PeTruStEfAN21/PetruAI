use std::io::{Read, Write};

use crate::error::StoreError;
use crate::store::Store;

/// One "key<TAB>value" line per entry, sorted by key; backslash, tab and newline are escaped.
impl Store {
    pub fn save(&self, out: &mut impl Write) -> Result<(), StoreError> {
        if self.depth() > 0 {
            return Err(StoreError::InTransaction);
        }
        for (key, value) in &self.layers.base {
            writeln!(out, "{}\t{}", escape(key), escape(value))?;
        }
        Ok(())
    }

    pub fn load(input: &mut impl Read) -> Result<Store, StoreError> {
        let mut text = String::new();
        input.read_to_string(&mut text)?;
        let mut store = Store::new();
        for (index, line) in text.lines().enumerate() {
            let (key, value) = line.split_once('\t').ok_or(StoreError::Corrupt(index + 1))?;
            let key = unescape(key).ok_or(StoreError::Corrupt(index + 1))?;
            let value = unescape(value).ok_or(StoreError::Corrupt(index + 1))?;
            store.set(&key, &value);
        }
        Ok(store)
    }
}

fn escape(text: &str) -> String {
    text.replace('\\', "\\\\").replace('\t', "\\t").replace('\n', "\\n")
}

fn unescape(text: &str) -> Option<String> {
    let mut out = String::with_capacity(text.len());
    let mut chars = text.chars();
    while let Some(c) = chars.next() {
        if c != '\\' {
            out.push(c);
            continue;
        }
        match chars.next()? {
            't' => out.push('\t'),
            'n' => out.push('\n'),
            '\\' => out.push('\\'),
            _ => return None,
        }
    }
    Some(out)
}
