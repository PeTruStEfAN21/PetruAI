use crate::error::StoreError;
use crate::layers::Layers;
use crate::snapshot;

#[derive(Debug)]
pub struct Store {
    layers: Layers,
}

impl Store {
    pub fn new() -> Self {
        Store {
            layers: Layers::new(),
        }
    }

    pub fn set(&mut self, key: &str, value: &str) {
        self.layers.set(key.to_string(), value.to_string());
    }

    pub fn get(&self, key: &str) -> Option<&str> {
        self.layers.get(key)
    }

    pub fn delete(&mut self, key: &str) -> bool {
        self.layers.delete(key)
    }

    pub fn len(&self) -> usize {
        self.layers.len()
    }

    pub fn is_empty(&self) -> bool {
        self.layers.is_empty()
    }

    pub fn count_value(&self, value: &str) -> usize {
        self.layers.count_value(value)
    }

    pub fn keys_with_prefix(&self, prefix: &str) -> Vec<String> {
        self.layers.keys_with_prefix(prefix)
    }

    pub fn begin(&mut self) {
        self.layers.begin();
    }

    pub fn commit(&mut self) -> Result<(), StoreError> {
        self.layers.commit()
    }

    pub fn rollback(&mut self) -> Result<(), StoreError> {
        self.layers.rollback()
    }

    pub fn depth(&self) -> usize {
        self.layers.depth()
    }

    pub fn save(&self, writer: &mut impl std::io::Write) -> Result<(), StoreError> {
        if self.depth() > 0 {
            return Err(StoreError::InTransaction);
        }
        snapshot::save(self, writer)
    }

    pub fn load(reader: &mut impl std::io::Read) -> Result<Self, StoreError> {
        snapshot::load(reader)
    }
}
