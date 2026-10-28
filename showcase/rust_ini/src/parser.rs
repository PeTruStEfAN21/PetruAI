use crate::document::{Entry, Ini};
use crate::error::{ParseError, ParseErrorKind};

pub fn parse(input: &str) -> Result<Ini, ParseError> {
    let mut sections: Vec<(String, Vec<Entry>)> = Vec::new();
    let mut current_section = String::new();
    let mut global_keys: Vec<Entry> = Vec::new();
    let mut lines = input.lines().peekable();
    let mut line_num: usize = 0;

    while let Some(line) = lines.next() {
        line_num += 1;
        let trimmed = line.trim();

        // Skip blank lines and comments
        if trimmed.is_empty() || trimmed.starts_with(';') || trimmed.starts_with('#') {
            continue;
        }

        // Section header
        if trimmed.starts_with('[') {
            if !trimmed.ends_with(']') {
                return Err(ParseError {
                    line: line_num,
                    kind: ParseErrorKind::UnclosedSection,
                });
            }
            let name = trimmed[1..trimmed.len() - 1].trim().to_string();
            // Find or create section
            let found = sections.iter_mut().find(|(n, _)| n == &name);
            if found.is_none() {
                sections.push((name.clone(), Vec::new()));
            }
            current_section = name;
            continue;
        }

        // Key = value line
        let eq_pos = match trimmed.find('=') {
            Some(pos) => pos,
            None => {
                return Err(ParseError {
                    line: line_num,
                    kind: ParseErrorKind::MissingEquals,
                });
            }
        };

        let key = trimmed[..eq_pos].trim();
        if key.is_empty() {
            return Err(ParseError {
                line: line_num,
                kind: ParseErrorKind::EmptyKey,
            });
        }

        let raw_value = trimmed[eq_pos + 1..].trim_start();

        // Parse the value (handle quotes and inline comments)
        let value = parse_value(raw_value, line_num)?;

        // Check for duplicate keys
        let target_entries = if current_section.is_empty() {
            &mut global_keys
        } else {
            &mut sections
                .iter_mut()
                .find(|(n, _)| n == &current_section)
                .unwrap()
                .1
        };

        if target_entries.iter().any(|e| e.key == key) {
            return Err(ParseError {
                line: line_num,
                kind: ParseErrorKind::DuplicateKey(key.to_string()),
            });
        }

        target_entries.push(Entry {
            key: key.to_string(),
            value,
        });
    }

    // Build the final Ini
    let mut sections_out: Vec<(String, Vec<Entry>)> = Vec::new();

    // Add global keys if any
    if !global_keys.is_empty() {
        sections_out.push((String::new(), global_keys));
    }

    // Add named sections
    sections_out.append(&mut sections);

    Ok(Ini {
        sections: sections_out,
    })
}

fn parse_value(raw: &str, line_num: usize) -> Result<String, ParseError> {
    if raw.starts_with('"') {
        // Quoted value - find closing quote with escape handling
        let mut result = String::new();
        let mut chars = raw.chars().skip(1).peekable();
        while let Some(ch) = chars.next() {
            match ch {
                '\\' => {
                    match chars.next() {
                        Some('"') => result.push('"'),
                        Some('\\') => result.push('\\'),
                        Some(c) => {
                            result.push('\\');
                            result.push(c);
                        }
                        None => {
                            return Err(ParseError {
                                line: line_num,
                                kind: ParseErrorKind::UnterminatedQuote,
                            });
                        }
                    }
                }
                '"' => {
                    // End of quoted string - ignore rest of line
                    return Ok(result);
                }
                _ => result.push(ch),
            }
        }
        // Reached end without closing quote
        Err(ParseError {
            line: line_num,
            kind: ParseErrorKind::UnterminatedQuote,
        })
    } else {
        // Unquoted value - strip inline comments
        // A ; or # that follows whitespace is a comment
        let mut result = String::new();
        let mut chars = raw.chars().peekable();
        let mut prev_was_space = false;

        while let Some(ch) = chars.next() {
            if ch == ' ' || ch == '\t' {
                prev_was_space = true;
                result.push(ch);
            } else if (ch == ';' || ch == '#') && prev_was_space {
                break;
            } else {
                prev_was_space = false;
                result.push(ch);
            }
        }

        // Trim trailing whitespace
        let trimmed = result.trim_end().to_string();
        Ok(trimmed)
    }
}
