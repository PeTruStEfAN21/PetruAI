use std::collections::{BTreeMap, HashMap};

/// Pending changes of one transaction: Some(value) sets, None deletes.
pub(crate) type Layer = HashMap<String, Option<String>>;

/// The committed data plus a stack of open transactions, newest last.
#[derive(Debug, Default)]
pub(crate) struct Layers {
    pub(crate) base: BTreeMap<String, String>,
    pub(crate) open: Vec<Layer>,
}

impl Layers {
    pub(crate) fn get(&self, key: &str) -> Option<&str> {
        for layer in self.open.iter().rev() {
            if let Some(change) = layer.get(key) {
                return change.as_deref();
            }
        }
        self.base.get(key).map(String::as_str)
    }

    pub(crate) fn write(&mut self, key: &str, value: Option<String>) {
        match self.open.last_mut() {
            Some(layer) => {
                layer.insert(key.to_string(), value);
            }
            None => match value {
                Some(v) => {
                    self.base.insert(key.to_string(), v);
                }
                None => {
                    self.base.remove(key);
                }
            },
        }
    }

    /// Every visible key and value, sorted by key.
    pub(crate) fn view(&self) -> BTreeMap<&str, &str> {
        let mut view: BTreeMap<&str, &str> = self.base.iter().map(|(k, v)| (k.as_str(), v.as_str())).collect();
        for layer in &self.open {
            for (key, change) in layer {
                match change {
                    Some(value) => {
                        view.insert(key.as_str(), value.as_str());
                    }
                    None => {
                        view.remove(key.as_str());
                    }
                }
            }
        }
        view
    }

    /// Folds the newest transaction into the one below it, or into the base.
    pub(crate) fn commit_top(&mut self) -> bool {
        let Some(top) = self.open.pop() else { return false };
        for (key, change) in top {
            self.write(&key, change);
        }
        true
    }

    pub(crate) fn discard_top(&mut self) -> bool {
        self.open.pop().is_some()
    }
}
