use crate::error::StoreError;
use crate::layers::Layers;

#[derive(Debug, Default)]
pub struct Store {
    pub(crate) layers: Layers,
}

impl Store {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn get(&self, key: &str) -> Option<&str> {
        self.layers.get(key)
    }

    pub fn set(&mut self, key: &str, value: &str) {
        self.layers.write(key, Some(value.to_string()));
    }

    /// True when the key existed.
    pub fn delete(&mut self, key: &str) -> bool {
        let existed = self.get(key).is_some();
        if existed {
            self.layers.write(key, None);
        }
        existed
    }

    pub fn len(&self) -> usize {
        self.layers.view().len()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn count_value(&self, value: &str) -> usize {
        self.layers.view().values().filter(|v| **v == value).count()
    }

    /// Keys starting with `prefix`, in byte order.
    pub fn keys_with_prefix(&self, prefix: &str) -> Vec<String> {
        self.layers.view().keys().filter(|k| k.starts_with(prefix)).map(|k| k.to_string()).collect()
    }

    pub fn depth(&self) -> usize {
        self.layers.open.len()
    }

    pub fn begin(&mut self) {
        self.layers.open.push(Default::default());
    }

    pub fn commit(&mut self) -> Result<(), StoreError> {
        self.layers.commit_top().then_some(()).ok_or(StoreError::NoTransaction)
    }

    pub fn rollback(&mut self) -> Result<(), StoreError> {
        self.layers.discard_top().then_some(()).ok_or(StoreError::NoTransaction)
    }
}
