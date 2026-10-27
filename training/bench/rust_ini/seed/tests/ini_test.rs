use ini::{Ini, ParseError, ParseErrorKind, ValueError};

const SAMPLE: &str = "\
; global settings
name = demo
debug = Yes

[server]
host = example.org   ; inline comment
port = 8080
tags = a, b ,c
motd = \"  hello ; \\\"world\\\" \"
url = http://x.org/#top

# another comment
[paths]
root = /srv
data = ${root}/data
logs = ${paths.data}/logs
home = ${server.host}:${server.port}
";

fn sample() -> Ini {
    Ini::parse(SAMPLE).expect("sample parses")
}

#[test]
fn reads_sections_and_keys_in_order() {
    let ini = sample();
    assert_eq!(ini.sections(), vec!["", "server", "paths"]);
    assert_eq!(ini.keys("server"), vec!["host", "port", "tags", "motd", "url"]);
    assert_eq!(ini.get("", "name"), Some("demo"));
    assert_eq!(ini.get("server", "host"), Some("example.org"));
    assert_eq!(ini.get("server", "url"), Some("http://x.org/#top"));
    assert_eq!(ini.get("server", "motd"), Some("  hello ; \"world\" "));
    assert_eq!(ini.get("server", "nope"), None);
    assert_eq!(ini.get("nope", "host"), None);
    assert!(ini.keys("nope").is_empty());
}

#[test]
fn no_global_section_without_global_keys() {
    let ini = Ini::parse("[a]\nx = 1\n").unwrap();
    assert_eq!(ini.sections(), vec!["a"]);
}

#[test]
fn reopened_sections_merge() {
    let ini = Ini::parse("[a]\nx = 1\n[b]\ny = 2\n[ a ]\nz = 3\n").unwrap();
    assert_eq!(ini.sections(), vec!["a", "b"]);
    assert_eq!(ini.keys("a"), vec!["x", "z"]);
}

#[test]
fn typed_getters() {
    let ini = sample();
    assert_eq!(ini.get_int("server", "port"), Ok(8080));
    assert_eq!(ini.get_bool("", "debug"), Ok(true));
    assert_eq!(ini.get_list("server", "tags"), Ok(vec!["a".to_string(), "b".to_string(), "c".to_string()]));
    assert_eq!(
        ini.get_int("server", "host"),
        Err(ValueError::Invalid {
            section: "server".into(),
            key: "host".into(),
            value: "example.org".into(),
            expected: "integer",
        })
    );
    assert_eq!(
        ini.get_int("server", "host").unwrap_err().to_string(),
        "server.host: expected integer, got 'example.org'"
    );
    let missing = ini.get_bool("server", "tls").unwrap_err();
    assert_eq!(missing, ValueError::Missing { section: "server".into(), key: "tls".into() });
    assert_eq!(missing.to_string(), "missing server.tls");
}

#[test]
fn booleans_accept_common_spellings() {
    let ini = Ini::parse("a=on\nb=OFF\nc=1\nd=0\ne=True\nf=no\ng=maybe\n").unwrap();
    let got: Vec<_> = ["a", "b", "c", "d", "e", "f"].iter().map(|k| ini.get_bool("", k).unwrap()).collect();
    assert_eq!(got, vec![true, false, true, false, true, false]);
    assert_eq!(ini.get_bool("", "g").unwrap_err().to_string(), ".g: expected boolean, got 'maybe'");
}

#[test]
fn empty_list_and_empty_value() {
    let ini = Ini::parse("[s]\nempty =\n").unwrap();
    assert_eq!(ini.get("s", "empty"), Some(""));
    assert_eq!(ini.get_list("s", "empty"), Ok(Vec::<String>::new()));
}

#[test]
fn parse_errors_carry_line_numbers() {
    let cases: Vec<(&str, usize, ParseErrorKind, &str)> = vec![
        ("a = 1\njunk\n", 2, ParseErrorKind::MissingEquals, "line 2: expected key = value"),
        ("[open\n", 1, ParseErrorKind::UnclosedSection, "line 1: unclosed section header"),
        ("[s]\n = 3\n", 2, ParseErrorKind::EmptyKey, "line 2: empty key"),
        ("[s]\nk=1\n\nk=2\n", 4, ParseErrorKind::DuplicateKey("k".into()), "line 4: duplicate key k"),
        ("k = \"abc\n", 1, ParseErrorKind::UnterminatedQuote, "line 1: unterminated quote"),
    ];
    for (text, line, kind, message) in cases {
        let err: ParseError = Ini::parse(text).unwrap_err();
        assert_eq!(err.line, line, "{text:?}");
        assert_eq!(err.kind, kind, "{text:?}");
        assert_eq!(err.to_string(), message);
    }
}

#[test]
fn interpolation() {
    let ini = sample();
    assert_eq!(ini.interpolated("paths", "data"), Ok("/srv/data".to_string()));
    assert_eq!(ini.interpolated("paths", "logs"), Ok("/srv/data/logs".to_string()));
    assert_eq!(ini.interpolated("paths", "home"), Ok("example.org:8080".to_string()));
    assert_eq!(ini.get("paths", "data"), Some("${root}/data"));
}

#[test]
fn interpolation_errors() {
    let ini = Ini::parse("[a]\nx = ${y}\ny = ${a.x}\nz = ${b.q}\n").unwrap();
    assert_eq!(ini.interpolated("a", "x").unwrap_err().to_string(), "interpolation cycle at a.x");
    assert_eq!(ini.interpolated("a", "z").unwrap_err().to_string(), "missing b.q");
}

#[test]
fn set_remove_and_merge() {
    let mut ini = sample();
    ini.set("server", "port", "9090");
    ini.set("new", "k", "v");
    assert_eq!(ini.get_int("server", "port"), Ok(9090));
    assert_eq!(ini.sections(), vec!["", "server", "paths", "new"]);
    assert!(ini.remove("server", "tags"));
    assert!(!ini.remove("server", "tags"));
    let overrides = Ini::parse("[server]\nhost = local\nextra = 1\n[more]\nm = 2\n").unwrap();
    ini.merge(&overrides);
    assert_eq!(ini.get("server", "host"), Some("local"));
    assert_eq!(ini.keys("server"), vec!["host", "port", "motd", "url", "extra"]);
    assert_eq!(ini.sections().last(), Some(&"more"));
}

#[test]
fn writes_back_a_canonical_file() {
    let mut ini = Ini::parse("top = 1\n[b]\nx=2\n[a]\npad = \"  spaced \"\nsemi = \"a;b\"\n").unwrap();
    ini.set("a", "quote", "say \"hi\"");
    let text = ini.to_string();
    assert_eq!(
        text,
        "top = 1\n\n[b]\nx = 2\n\n[a]\npad = \"  spaced \"\nsemi = \"a;b\"\nquote = say \"hi\"\n"
    );
    assert_eq!(Ini::parse(&text).unwrap(), ini);
}

#[test]
fn round_trips_the_sample() {
    let ini = sample();
    assert_eq!(Ini::parse(&ini.to_string()).unwrap(), ini);
}
