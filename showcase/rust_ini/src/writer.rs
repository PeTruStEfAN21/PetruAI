use std::fmt;
use crate::document::Ini;

pub struct IniWriter<'a> {
    ini: &'a Ini,
}

impl<'a> IniWriter<'a> {
    pub fn new(ini: &'a Ini) -> Self {
        Self { ini }
    }

    fn needs_quoting(value: &str) -> bool {
        if value.is_empty() {
            return false;
        }
        // Quote if leading/trailing spaces
        if value.starts_with(' ') || value.ends_with(' ') {
            return true;
        }
        // Quote if contains ; or #
        if value.contains(';') || value.contains('#') {
            return true;
        }
        false
    }

    fn format_value(value: &str) -> String {
        if Self::needs_quoting(value) {
            // Escape internal quotes for round-trip safety
            let escaped = value.replace('"', "\\\"");
            format!("\"{}\"", escaped)
        } else {
            value.to_string()
        }
    }
}

impl<'a> fmt::Display for IniWriter<'a> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let mut first = true;

        for (section, entries) in self.ini.iter_sections() {
            if entries.is_empty() {
                continue;
            }

            // Blank line before each section (including global if not first)
            if !first {
                writeln!(f)?;
            }
            first = false;

            // Global section has no header line
            if section.is_empty() {
                for entry in entries {
                    let formatted = Self::format_value(&entry.value);
                    writeln!(f, "{} = {}", entry.key, formatted)?;
                }
            } else {
                writeln!(f, "[{}]", section)?;
                for entry in entries {
                    let formatted = Self::format_value(&entry.value);
                    writeln!(f, "{} = {}", entry.key, formatted)?;
                }
            }
        }

        Ok(())
    }
}
