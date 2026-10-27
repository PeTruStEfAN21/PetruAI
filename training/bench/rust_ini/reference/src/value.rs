use crate::document::Ini;
use crate::error::ValueError;

impl Ini {
    pub fn get_int(&self, section: &str, key: &str) -> Result<i64, ValueError> {
        let raw = self.require(section, key)?;
        raw.trim().parse().map_err(|_| invalid(section, key, raw, "integer"))
    }

    pub fn get_bool(&self, section: &str, key: &str) -> Result<bool, ValueError> {
        let raw = self.require(section, key)?;
        match raw.trim().to_ascii_lowercase().as_str() {
            "true" | "yes" | "on" | "1" => Ok(true),
            "false" | "no" | "off" | "0" => Ok(false),
            _ => Err(invalid(section, key, raw, "boolean")),
        }
    }

    /// Comma-separated items, trimmed; an empty value is an empty list.
    pub fn get_list(&self, section: &str, key: &str) -> Result<Vec<String>, ValueError> {
        let raw = self.require(section, key)?;
        if raw.trim().is_empty() {
            return Ok(Vec::new());
        }
        Ok(raw.split(',').map(|item| item.trim().to_string()).collect())
    }
}

fn invalid(section: &str, key: &str, value: &str, expected: &'static str) -> ValueError {
    ValueError::Invalid { section: section.into(), key: key.into(), value: value.into(), expected }
}
