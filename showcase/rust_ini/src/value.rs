use crate::error::ValueError;
use crate::document::Ini;

/// Get an integer value from the INI file
pub fn get_int(ini: &Ini, section: &str, key: &str) -> Result<i64, ValueError> {
    let value = ini.get(section, key);
    let (section, key, value) = match value {
        Some(v) => (section.to_string(), key.to_string(), v.to_string()),
        None => return Err(ValueError::Missing { section: section.to_string(), key: key.to_string() }),
    };

    value
        .parse::<i64>()
        .map_err(|_| ValueError::Invalid { section, key, value, expected: "integer" })
}

/// Get a boolean value from the INI file
pub fn get_bool(ini: &Ini, section: &str, key: &str) -> Result<bool, ValueError> {
    let value = ini.get(section, key);
    let (section, key, value) = match value {
        Some(v) => (section.to_string(), key.to_string(), v.to_string()),
        None => return Err(ValueError::Missing { section: section.to_string(), key: key.to_string() }),
    };

    let lower = value.to_lowercase();
    match lower.as_str() {
        "true" | "yes" | "on" | "1" => Ok(true),
        "false" | "no" | "off" | "0" => Ok(false),
        _ => Err(ValueError::Invalid { section, key, value, expected: "boolean" }),
    }
}

/// Get a list of strings from the INI file
pub fn get_list(ini: &Ini, section: &str, key: &str) -> Result<Vec<String>, ValueError> {
    let value = ini.get(section, key);
    let (_section, _key, value) = match value {
        Some(v) => (section.to_string(), key.to_string(), v.to_string()),
        None => return Err(ValueError::Missing { section: section.to_string(), key: key.to_string() }),
    };

    if value.is_empty() {
        return Ok(Vec::new());
    }

    let mut result = Vec::new();
    for part in value.split(',') {
        let trimmed = part.trim().to_string();
        if !trimmed.is_empty() {
            result.push(trimmed);
        }
    }

    Ok(result)
}
