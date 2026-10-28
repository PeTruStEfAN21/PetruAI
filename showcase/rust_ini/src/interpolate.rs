use std::collections::HashSet;
use crate::error::ValueError;
use crate::document::Ini;

/// Context for interpolation operations.
pub struct InterpolationContext<'a> {
    ini: &'a Ini,
}

impl<'a> InterpolationContext<'a> {
    /// Create a new interpolation context.
    pub fn new(ini: &'a Ini) -> Self {
        Self { ini }
    }

    /// Recursively interpolate ${...} patterns in the raw value.
    pub fn interpolate(
        &self,
        section: &str,
        key: &str,
        raw: &str,
        visited: &mut HashSet<String>,
    ) -> Result<String, ValueError> {
        let section_key = format!("{}.{}", section, key);
        if visited.contains(&section_key) {
            return Err(ValueError::Cycle(section_key));
        }
        visited.insert(section_key.clone());

        let mut result = String::new();
        let mut chars = raw.chars().peekable();

        while let Some(ch) = chars.next() {
            if ch == '$' {
                if chars.peek() == Some(&'{') {
                    chars.next(); // consume '{'
                    let mut content = String::new();
                    while let Some(&c) = chars.peek() {
                        if c == '}' {
                            chars.next(); // consume '}'
                            break;
                        }
                        chars.next();
                        content.push(c);
                    }

                    // Resolve the reference
                    let (ref_section, ref_key) = if content.contains('.') {
                        let parts: Vec<&str> = content.splitn(2, '.').collect();
                        (parts[0], parts[1])
                    } else {
                        (section, content.as_str())
                    };

                    let resolved_raw = self.ini.get(ref_section, ref_key).ok_or_else(|| {
                        ValueError::Missing {
                            section: ref_section.to_string(),
                            key: ref_key.to_string(),
                        }
                    })?;

                    // Recursively interpolate the resolved value
                    let interpolated = self.interpolate(ref_section, ref_key, resolved_raw, visited)?;
                    result.push_str(&interpolated);
                } else {
                    result.push(ch);
                }
            } else {
                result.push(ch);
            }
        }

        Ok(result)
    }
}
