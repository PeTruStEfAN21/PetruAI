use kvstore::{Store, StoreError};

#[test]
fn set_get_delete() {
    let mut s = Store::new();
    assert!(s.is_empty());
    s.set("a", "1");
    s.set("b", "two words");
    s.set("a", "3");
    assert_eq!(s.get("a"), Some("3"));
    assert_eq!(s.get("b"), Some("two words"));
    assert_eq!(s.get("c"), None);
    assert_eq!(s.len(), 2);
    assert!(s.delete("a"));
    assert!(!s.delete("a"));
    assert_eq!(s.len(), 1);
}

#[test]
fn count_and_prefix_queries() {
    let mut s = Store::new();
    s.set("user:1", "ana");
    s.set("user:2", "bob");
    s.set("user:10", "ana");
    s.set("team:1", "ana");
    assert_eq!(s.count_value("ana"), 3);
    assert_eq!(s.count_value("zed"), 0);
    assert_eq!(s.keys_with_prefix("user:"), vec!["user:1", "user:10", "user:2"]);
    assert_eq!(s.keys_with_prefix(""), vec!["team:1", "user:1", "user:10", "user:2"]);
    assert!(s.keys_with_prefix("x").is_empty());
}

#[test]
fn rollback_discards_the_innermost_transaction() {
    let mut s = Store::new();
    s.set("a", "1");
    s.begin();
    s.set("a", "2");
    s.set("b", "new");
    s.delete("a");
    assert_eq!(s.get("a"), None);
    assert_eq!(s.depth(), 1);
    s.rollback().unwrap();
    assert_eq!(s.get("a"), Some("1"));
    assert_eq!(s.get("b"), None);
    assert_eq!(s.depth(), 0);
    assert_eq!(s.rollback(), Err(StoreError::NoTransaction));
}

#[test]
fn nested_transactions_commit_into_their_parent() {
    let mut s = Store::new();
    s.set("a", "1");
    s.begin();
    s.set("a", "2");
    s.begin();
    s.set("a", "3");
    s.set("c", "x");
    assert_eq!(s.count_value("3"), 1);
    s.commit().unwrap();
    assert_eq!(s.depth(), 1);
    assert_eq!(s.get("a"), Some("3"));
    s.rollback().unwrap();
    assert_eq!(s.get("a"), Some("1"));
    assert_eq!(s.get("c"), None);
    assert_eq!(s.commit(), Err(StoreError::NoTransaction));
}

#[test]
fn queries_see_uncommitted_changes() {
    let mut s = Store::new();
    s.set("k1", "v");
    s.set("k2", "v");
    s.begin();
    s.delete("k1");
    s.set("k3", "v");
    assert_eq!(s.count_value("v"), 2);
    assert_eq!(s.keys_with_prefix("k"), vec!["k2", "k3"]);
    assert_eq!(s.len(), 2);
    s.commit().unwrap();
    assert_eq!(s.keys_with_prefix("k"), vec!["k2", "k3"]);
}

#[test]
fn snapshots_round_trip_with_escaping() {
    let mut s = Store::new();
    s.set("plain", "value");
    s.set("tab\tkey", "line1\nline2");
    s.set("slash", "a\\b");
    s.set("empty", "");
    let mut buf = Vec::new();
    s.save(&mut buf).unwrap();
    let text = String::from_utf8(buf.clone()).unwrap();
    assert_eq!(text.lines().count(), 4);
    assert!(text.lines().next().unwrap().starts_with("empty\t"));
    let loaded = Store::load(&mut buf.as_slice()).unwrap();
    assert_eq!(loaded.get("tab\tkey"), Some("line1\nline2"));
    assert_eq!(loaded.get("slash"), Some("a\\b"));
    assert_eq!(loaded.get("empty"), Some(""));
    assert_eq!(loaded.len(), 4);
}

#[test]
fn snapshot_errors() {
    let mut s = Store::new();
    s.begin();
    let mut buf = Vec::new();
    assert_eq!(s.save(&mut buf), Err(StoreError::InTransaction));
    assert_eq!(StoreError::InTransaction.to_string(), "cannot save inside a transaction");
    let bad = b"ok\tfine\nno tab here\n".to_vec();
    let err = Store::load(&mut bad.as_slice()).unwrap_err();
    assert_eq!(err, StoreError::Corrupt(2));
    assert_eq!(err.to_string(), "corrupt snapshot at line 2");
    assert_eq!(StoreError::NoTransaction.to_string(), "no transaction");
}
