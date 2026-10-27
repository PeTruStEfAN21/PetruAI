use std::fmt;

use crate::document::Ini;

/// Global keys first, then each section after a blank line; "key = value" lines; values quoted when needed.
impl fmt::Display for Ini {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let mut first = true;
        let ordered = self
            .sections
            .iter()
            .filter(|(name, _)| name.is_empty())
            .chain(self.sections.iter().filter(|(name, _)| !name.is_empty()));
        for (name, keys) in ordered {
            if name.is_empty() && keys.is_empty() {
                continue;
            }
            if !first {
                writeln!(f)?;
            }
            first = false;
            if !name.is_empty() {
                writeln!(f, "[{name}]")?;
            }
            for (key, value) in keys {
                writeln!(f, "{key} = {}", quote(value))?;
            }
        }
        Ok(())
    }
}

fn quote(value: &str) -> String {
    let needs = value != value.trim() || value.contains(';') || value.contains('#') || value.starts_with('"');
    if !needs {
        return value.to_string();
    }
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}
