use crate::store::Store;

/// A line-oriented command interpreter over a Store; every command answers with one line.
pub struct Shell {
    store: Store,
}

impl Shell {
    pub fn new(store: Store) -> Self {
        Shell { store }
    }

    pub fn store(&self) -> &Store {
        &self.store
    }

    pub fn exec(&mut self, line: &str) -> String {
        let trimmed = line.trim();
        let Some((name, rest)) = split_word(trimmed) else {
            return "ERROR empty command".to_string();
        };
        let command = name.to_ascii_uppercase();
        let args: Vec<&str> = rest.split_whitespace().collect();
        let arity_error = || format!("ERROR wrong number of arguments for {command}");
        match command.as_str() {
            "SET" => match split_word(rest) {
                Some((key, value)) if !value.is_empty() => {
                    self.store.set(key, value);
                    "OK".to_string()
                }
                _ => arity_error(),
            },
            "GET" if args.len() == 1 => self.store.get(args[0]).unwrap_or("NULL").to_string(),
            "DELETE" if args.len() == 1 => (self.store.delete(args[0]) as u8).to_string(),
            "COUNT" if args.len() == 1 => self.store.count_value(args[0]).to_string(),
            "KEYS" if args.len() <= 1 => {
                let keys = self.store.keys_with_prefix(args.first().copied().unwrap_or(""));
                if keys.is_empty() { "(empty)".to_string() } else { keys.join(" ") }
            }
            "INCR" if args.len() == 1 => self.incr(args[0]),
            "BEGIN" if args.is_empty() => {
                self.store.begin();
                "OK".to_string()
            }
            "COMMIT" if args.is_empty() => outcome(self.store.commit()),
            "ROLLBACK" if args.is_empty() => outcome(self.store.rollback()),
            "GET" | "DELETE" | "COUNT" | "KEYS" | "INCR" | "BEGIN" | "COMMIT" | "ROLLBACK" => arity_error(),
            _ => format!("ERROR unknown command {name}"),
        }
    }

    fn incr(&mut self, key: &str) -> String {
        let current = match self.store.get(key) {
            None => 0,
            Some(value) => match value.parse::<i64>() {
                Ok(n) => n,
                Err(_) => return "ERROR value is not an integer".to_string(),
            },
        };
        let next = current + 1;
        self.store.set(key, &next.to_string());
        next.to_string()
    }
}

/// The first word and the rest of the line after the whitespace that follows it.
fn split_word(text: &str) -> Option<(&str, &str)> {
    let text = text.trim_start();
    if text.is_empty() {
        return None;
    }
    match text.find(char::is_whitespace) {
        Some(end) => Some((&text[..end], text[end..].trim_start())),
        None => Some((text, "")),
    }
}

fn outcome(result: Result<(), crate::error::StoreError>) -> String {
    match result {
        Ok(()) => "OK".to_string(),
        Err(err) => format!("ERROR {err}"),
    }
}
