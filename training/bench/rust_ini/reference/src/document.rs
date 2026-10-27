use crate::error::{ParseError, ValueError};

/// Sections and keys in file order; the global section is named "".
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Ini {
    pub(crate) sections: Vec<(String, Vec<(String, String)>)>,
}

impl Ini {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn parse(text: &str) -> Result<Ini, ParseError> {
        crate::parser::parse(text)
    }

    /// Section names in order; the global section only when it has keys.
    pub fn sections(&self) -> Vec<&str> {
        self.sections
            .iter()
            .filter(|(name, keys)| !name.is_empty() || !keys.is_empty())
            .map(|(name, _)| name.as_str())
            .collect()
    }

    pub fn keys(&self, section: &str) -> Vec<&str> {
        self.section(section)
            .map(|keys| keys.iter().map(|(k, _)| k.as_str()).collect())
            .unwrap_or_default()
    }

    pub fn get(&self, section: &str, key: &str) -> Option<&str> {
        self.section(section)?.iter().find(|(k, _)| k == key).map(|(_, v)| v.as_str())
    }

    pub(crate) fn require(&self, section: &str, key: &str) -> Result<&str, ValueError> {
        self.get(section, key).ok_or_else(|| ValueError::Missing { section: section.into(), key: key.into() })
    }

    /// Replaces the value in place, or appends the key (and the section) at the end.
    pub fn set(&mut self, section: &str, key: &str, value: &str) {
        let keys = self.section_mut(section);
        match keys.iter_mut().find(|(k, _)| k == key) {
            Some(entry) => entry.1 = value.to_string(),
            None => keys.push((key.to_string(), value.to_string())),
        }
    }

    pub fn remove(&mut self, section: &str, key: &str) -> bool {
        let Some((_, keys)) = self.sections.iter_mut().find(|(name, _)| name == section) else {
            return false;
        };
        let before = keys.len();
        keys.retain(|(k, _)| k != key);
        keys.len() != before
    }

    /// Every key of `other` overrides or extends this one.
    pub fn merge(&mut self, other: &Ini) {
        for (section, keys) in &other.sections {
            for (key, value) in keys {
                self.set(section, key, value);
            }
        }
    }

    fn section(&self, name: &str) -> Option<&Vec<(String, String)>> {
        self.sections.iter().find(|(n, _)| n == name).map(|(_, keys)| keys)
    }

    pub(crate) fn section_mut(&mut self, name: &str) -> &mut Vec<(String, String)> {
        let index = match self.sections.iter().position(|(n, _)| n == name) {
            Some(index) => index,
            None => {
                self.sections.push((name.to_string(), Vec::new()));
                self.sections.len() - 1
            }
        };
        &mut self.sections[index].1
    }
}
