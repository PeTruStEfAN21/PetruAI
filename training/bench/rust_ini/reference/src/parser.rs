use crate::document::Ini;
use crate::error::{ParseError, ParseErrorKind};

pub(crate) fn parse(text: &str) -> Result<Ini, ParseError> {
    let mut ini = Ini::new();
    let mut current = String::new();
    for (index, raw) in text.lines().enumerate() {
        let line_no = index + 1;
        let err = |kind| ParseError { line: line_no, kind };
        let line = raw.trim();
        if line.is_empty() || line.starts_with(';') || line.starts_with('#') {
            continue;
        }
        if let Some(rest) = line.strip_prefix('[') {
            let name = rest.strip_suffix(']').ok_or_else(|| err(ParseErrorKind::UnclosedSection))?;
            current = name.trim().to_string();
            ini.section_mut(&current);
            continue;
        }
        let (key, value) = line.split_once('=').ok_or_else(|| err(ParseErrorKind::MissingEquals))?;
        let key = key.trim();
        if key.is_empty() {
            return Err(err(ParseErrorKind::EmptyKey));
        }
        if ini.get(&current, key).is_some() {
            return Err(err(ParseErrorKind::DuplicateKey(key.to_string())));
        }
        let value = parse_value(value.trim()).ok_or_else(|| err(ParseErrorKind::UnterminatedQuote))?;
        ini.set(&current, key, &value);
    }
    Ok(ini)
}

/// A quoted value keeps everything up to the closing quote (\" and \\ escapes); an unquoted one ends at a
/// comment that follows whitespace. None for an unterminated quote.
fn parse_value(text: &str) -> Option<String> {
    let Some(body) = text.strip_prefix('"') else {
        return Some(strip_comment(text).to_string());
    };
    let mut value = String::new();
    let mut chars = body.chars();
    while let Some(c) = chars.next() {
        match c {
            '\\' => value.push(chars.next()?),
            '"' => return Some(value),
            other => value.push(other),
        }
    }
    None
}

fn strip_comment(text: &str) -> &str {
    let bytes = text.as_bytes();
    for (i, &b) in bytes.iter().enumerate() {
        if (b == b';' || b == b'#') && i > 0 && bytes[i - 1].is_ascii_whitespace() {
            return text[..i].trim_end();
        }
    }
    text
}
