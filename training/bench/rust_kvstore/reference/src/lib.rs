//! An in-memory key-value store with nested transactions, text snapshots and a command shell.

mod error;
mod layers;
mod shell;
mod snapshot;
mod store;

pub use error::StoreError;
pub use shell::Shell;
pub use store::Store;
