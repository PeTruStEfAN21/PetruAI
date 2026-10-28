use kvstore::{Shell, Store};

fn run(shell: &mut Shell, lines: &[&str]) -> Vec<String> {
    lines.iter().map(|line| shell.exec(line)).collect()
}

#[test]
fn basic_commands() {
    let mut shell = Shell::new(Store::new());
    let out = run(
        &mut shell,
        &["SET a 10", "get a", "SET greeting hello   big world", "GET greeting", "GET nope", "DELETE a", "DELETE a"],
    );
    assert_eq!(out, vec!["OK", "10", "OK", "hello   big world", "NULL", "1", "0"]);
}

#[test]
fn counting_keys_and_incr() {
    let mut shell = Shell::new(Store::new());
    let out = run(
        &mut shell,
        &["SET u:1 x", "SET u:2 x", "SET v y", "COUNT x", "KEYS u:", "KEYS zz", "INCR n", "INCR n", "INCR v"],
    );
    assert_eq!(out, vec!["OK", "OK", "OK", "2", "u:1 u:2", "(empty)", "1", "2", "ERROR value is not an integer"]);
    assert_eq!(shell.store().get("n"), Some("2"));
}

#[test]
fn transactions() {
    let mut shell = Shell::new(Store::new());
    let out = run(
        &mut shell,
        &["SET a 1", "BEGIN", "SET a 2", "INCR a", "GET a", "ROLLBACK", "GET a", "ROLLBACK", "BEGIN", "SET b 5", "COMMIT", "GET b", "COMMIT"],
    );
    assert_eq!(
        out,
        vec!["OK", "OK", "OK", "3", "3", "OK", "1", "ERROR no transaction", "OK", "OK", "OK", "5", "ERROR no transaction"]
    );
}

#[test]
fn errors() {
    let mut shell = Shell::new(Store::new());
    let out = run(&mut shell, &["FLY away", "SET a", "GET", "DELETE a b", "BEGIN now", "", "   "]);
    assert_eq!(
        out,
        vec![
            "ERROR unknown command FLY",
            "ERROR wrong number of arguments for SET",
            "ERROR wrong number of arguments for GET",
            "ERROR wrong number of arguments for DELETE",
            "ERROR wrong number of arguments for BEGIN",
            "ERROR empty command",
            "ERROR empty command",
        ]
    );
}
