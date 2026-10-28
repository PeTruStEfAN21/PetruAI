use std::fmt;
use std::collections::HashSet;

use crate::error::{ParseError, ValueError};
use crate::interpolate::InterpolationContext;

/// A single key-value pair.
#[derive(Debug, Clone, PartialEq)]
pub struct Entry {
    pub key: String,
    pub value: String,
}

/// An INI document with sections and keys in file order.
#[derive(Debug, Clone, PartialEq)]
pub struct Ini {
    pub(crate) sections: Vec<(String, Vec<Entry>)>,
}

impl Ini {
    /// Parse an INI string into an Ini document.
    pub fn parse(input: &str) -> Result<Ini, ParseError> {
        crate::parser::parse(input)
    }

    /// Return section names in file order (global section "" only if it has keys).
    pub fn sections(&self) -> Vec<&str> {
        self.sections
            .iter()
            .filter(|(_, entries)| !entries.is_empty())
            .map(|(name, _)| name.as_str())
            .collect()
    }

    /// Return key names for a section in file order.
    pub fn keys(&self, section: &str) -> Vec<&str> {
        self.sections
            .iter()
            .find(|(name, _)| name == section)
            .map(|(_, entries)| entries.iter().map(|e| e.key.as_str()).collect())
            .unwrap_or_default()
    }

    /// Get the raw value for a key in a section.
    pub fn get(&self, section: &str, key: &str) -> Option<&str> {
        self.sections
            .iter()
            .find(|(name, _)| name == section)
            .and_then(|(_, entries)| {
                entries.iter().find(|e| e.key == key).map(|e| e.value.as_str())
            })
    }

    /// Set a key's value, replacing if it exists or appending.
    /// Creates the section at the end if it doesn't exist.
    pub fn set(&mut self, section: &str, key: &str, value: &str) {
        if let Some((_, entries)) = self.sections.iter_mut().find(|(name, _)| name == section) {
            if let Some(entry) = entries.iter_mut().find(|e| e.key == key) {
                entry.value = value.to_string();
                return;
            }
            entries.push(Entry {
                key: key.to_string(),
                value: value.to_string(),
            });
        } else {
            self.sections.push((
                section.to_string(),
                vec![Entry {
                    key: key.to_string(),
                    value: value.to_string(),
                }],
            ));
        }
    }

    /// Remove a key from a section. Returns true if the key was found.
    pub fn remove(&mut self, section: &str, key: &str) -> bool {
        if let Some((_, entries)) = self.sections.iter_mut().find(|(name, _)| name == section) {
            let before = entries.len();
            entries.retain(|e| e.key != key);
            entries.len() < before
        } else {
            false
        }
    }

    /// Merge another Ini into this one.
    pub fn merge(&mut self, other: &Ini) {
        for (other_section, other_entries) in &other.sections {
            if let Some((_, entries)) = self.sections.iter_mut().find(|(name, _)| name == other_section) {
                for entry in other_entries {
                    if let Some(existing) = entries.iter_mut().find(|e| e.key == entry.key) {
                        existing.value = entry.value.clone();
                    } else {
                        entries.push(entry.clone());
                    }
                }
            } else {
                self.sections.push((other_section.clone(), other_entries.clone()));
            }
        }
    }

    /// Get the value as an integer.
    pub fn get_int(&self, section: &str, key: &str) -> Result<i64, ValueError> {
        crate::value::get_int(self, section, key)
    }

    /// Get the value as a boolean.
    pub fn get_bool(&self, section: &str, key: &str) -> Result<bool, ValueError> {
        crate::value::get_bool(self, section, key)
    }

    /// Get the value as a comma-separated list of strings.
    pub fn get_list(&self, section: &str, key: &str) -> Result<Vec<String>, ValueError> {
        crate::value::get_list(self, section, key)
    }

    /// Interpolate a value, resolving ${key} and ${section.key} references.
    pub fn interpolated(&self, section: &str, key: &str) -> Result<String, ValueError> {
        let ctx = InterpolationContext::new(self);
        let raw = self.get(section, key).ok_or_else(|| ValueError::Missing {
            section: section.to_string(),
            key: key.to_string(),
        })?;
        let mut visited = HashSet::new();
        ctx.interpolate(section, key, raw, &mut visited)
    }

    /// Internal: iterate over all sections (for writer).
    pub(crate) fn iter_sections(&self) -> impl Iterator<Item = (&String, &Vec<Entry>)> {
        self.sections.iter().map(|(name, entries)| (name, entries))
    }
}

impl fmt::Display for Ini {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        crate::writer::IniWriter::new(self).fmt(f)
    }
}
