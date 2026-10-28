use std::collections::{BTreeMap, BTreeSet};

use crate::error::StoreError;

/// A single change in a transaction level.
#[derive(Clone, Debug)]
enum Change {
    /// Set key to value. original_committed is Some if key existed in committed before this change.
    Set { value: String, original_committed: Option<String> },
    /// Delete key. original_committed is Some if key existed in committed before this change.
    Del { original_committed: Option<String> },
}

#[derive(Debug)]
pub struct Layers {
    committed: BTreeMap<String, String>,
    // Each level is a list of changes
    stack: Vec<Vec<(String, Change)>>,
}

impl Layers {
    pub fn new() -> Self {
        Layers {
            committed: BTreeMap::new(),
            stack: Vec::new(),
        }
    }

    pub fn set(&mut self, key: String, value: String) {
        if self.stack.is_empty() {
            self.committed.insert(key, value);
        } else {
            let original = self.committed.get(&key).cloned();
            if let Some(level) = self.stack.last_mut() {
                level.retain(|(k, _)| k != &key);
                level.push((key, Change::Set { value, original_committed: original }));
            }
        }
    }

    pub fn get(&self, key: &str) -> Option<&str> {
        for level in self.stack.iter().rev() {
            if let Some((_k, change)) = level.iter().find(|(k, _)| k == key) {
                return match change {
                    Change::Set { value, .. } => Some(value.as_str()),
                    Change::Del { .. } => None,
                };
            }
        }
        self.committed.get(key).map(|v| v.as_str())
    }

    pub fn delete(&mut self, key: &str) -> bool {
        if self.stack.is_empty() {
            return self.committed.remove(key).is_some();
        }

        // Check if key exists in any stack level
        let mut found = false;
        for level in &self.stack {
            if level.iter().any(|(k, _)| k == key) {
                found = true;
                break;
            }
        }

        if found {
            // Key exists in stack - remove the previous change and record a deletion
            let original = self.committed.get(key).cloned();
            self.stack.last_mut().unwrap().retain(|(k, _)| k != key);
            self.stack.last_mut().unwrap().push((
                key.to_string(),
                Change::Del { original_committed: original },
            ));
        } else {
            // Key not in stack - check committed and record original value for rollback
            let original = self.committed.get(key).cloned();
            self.committed.remove(key);
            let was_present = original.is_some();
            self.stack.last_mut().unwrap().push((
                key.to_string(),
                Change::Del { original_committed: original },
            ));
            found = was_present;
        }

        found
    }

    pub fn begin(&mut self) {
        self.stack.push(Vec::new());
    }

    pub fn commit(&mut self) -> Result<(), StoreError> {
        if self.stack.is_empty() {
            return Err(StoreError::NoTransaction);
        }
        if self.stack.len() == 1 {
            // Last level - apply to committed
            let current = self.stack.pop().unwrap();
            for (key, change) in current {
                match change {
                    Change::Set { value, .. } => {
                        self.committed.insert(key, value);
                    }
                    Change::Del { .. } => {
                        self.committed.remove(&key);
                    }
                }
            }
        } else {
            // Nested commit - merge into parent level
            let current = self.stack.pop().unwrap();
            // Collect keys from current level
            let mut current_keys: Vec<String> = Vec::new();
            for (key, _) in &current {
                current_keys.push(key.clone());
            }
            // Remove superseded changes from parent level
            if let Some(parent) = self.stack.last_mut() {
                parent.retain(|(k, _)| !current_keys.contains(k));
            }
            // Add current level changes to parent
            for (key, change) in current {
                if let Some(parent) = self.stack.last_mut() {
                    parent.push((key, change));
                }
            }
        }
        Ok(())
    }

    pub fn rollback(&mut self) -> Result<(), StoreError> {
        if self.stack.is_empty() {
            return Err(StoreError::NoTransaction);
        }
        let current = self.stack.pop().unwrap();
        // Undo each change in reverse order
        for (key, change) in current.into_iter().rev() {
            match change {
                Change::Set { original_committed, .. } => {
                    // Was a set - restore original committed value
                    if let Some(val) = original_committed {
                        self.committed.insert(key, val);
                    } else {
                        self.committed.remove(key.as_str());
                    }
                }
                Change::Del { original_committed } => {
                    // Was a delete - restore original committed value if it existed
                    if let Some(val) = original_committed {
                        self.committed.insert(key, val);
                    }
                }
            }
        }
        Ok(())
    }

    pub fn depth(&self) -> usize {
        self.stack.len()
    }

    pub fn len(&self) -> usize {
        let mut keys: BTreeSet<&str> = BTreeSet::new();
        for k in self.committed.keys() {
            keys.insert(k.as_str());
        }
        for level in &self.stack {
            for (k, change) in level {
                match change {
                    Change::Set { .. } => { keys.insert(k.as_str()); }
                    Change::Del { .. } => { keys.remove(k.as_str()); }
                }
            }
        }
        keys.len()
    }

    pub fn is_empty(&self) -> bool {
        self.committed.is_empty() && self.stack.is_empty()
    }

    /// Count keys whose effective value equals the given string.
    pub fn count_value(&self, value: &str) -> usize {
        let mut effective: BTreeMap<&str, &str> = BTreeMap::new();
        for (k, v) in &self.committed {
            effective.insert(k.as_str(), v.as_str());
        }
        for level in &self.stack {
            for (k, change) in level {
                match change {
                    Change::Set { value: val, .. } => { effective.insert(k.as_str(), val.as_str()); }
                    Change::Del { .. } => { effective.remove(k.as_str()); }
                }
            }
        }
        effective.values().filter(|v| **v == value).count()
    }

    /// Return keys starting with prefix, sorted.
    pub fn keys_with_prefix(&self, prefix: &str) -> Vec<String> {
        let mut effective_keys: Vec<&str> = Vec::new();
        for k in self.committed.keys() {
            effective_keys.push(k.as_str());
        }
        for level in &self.stack {
            for (k, change) in level {
                match change {
                    Change::Set { .. } => {
                        if !effective_keys.contains(&k.as_str()) {
                            effective_keys.push(k.as_str());
                        }
                    }
                    Change::Del { .. } => {
                        effective_keys.retain(|&x| x != k.as_str());
                    }
                }
            }
        }
        effective_keys.sort();
        effective_keys.into_iter().filter(|k| k.starts_with(prefix)).map(|s| s.to_string()).collect()
    }
}
