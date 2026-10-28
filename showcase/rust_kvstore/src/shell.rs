use crate::store::Store;

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
        
        // Check for empty command
        if trimmed.is_empty() {
            return "ERROR empty command".to_string();
        }
        
        let parts: Vec<&str> = trimmed.splitn(2, ' ').collect();
        let command = parts[0].to_uppercase();
        
        match command.as_str() {
            "SET" => self.cmd_set(trimmed),
            "GET" => self.cmd_get(trimmed),
            "DELETE" => self.cmd_delete(trimmed),
            "COUNT" => self.cmd_count(trimmed),
            "KEYS" => self.cmd_keys(trimmed),
            "INCR" => self.cmd_incr(trimmed),
            "BEGIN" => self.cmd_begin(trimmed),
            "COMMIT" => self.cmd_commit(),
            "ROLLBACK" => self.cmd_rollback(),
            _ => format!("ERROR unknown command {}", parts[0]),
        }
    }

    fn cmd_set(&mut self, line: &str) -> String {
        // SET key value - need exactly 2+ parts (command, key, value)
        let trimmed = line.trim();
        let parts: Vec<&str> = trimmed.splitn(3, ' ').collect();
        if parts.len() < 3 {
            return "ERROR wrong number of arguments for SET".to_string();
        }
        let key = parts[1];
        let value = parts[2];
        self.store.set(key, value);
        "OK".to_string()
    }

    fn cmd_get(&mut self, line: &str) -> String {
        let trimmed = line.trim();
        let parts: Vec<&str> = trimmed.splitn(2, ' ').collect();
        if parts.len() < 2 {
            return "ERROR wrong number of arguments for GET".to_string();
        }
        match self.store.get(parts[1]) {
            Some(val) => val.to_string(),
            None => "NULL".to_string(),
        }
    }

    fn cmd_delete(&mut self, line: &str) -> String {
        let trimmed = line.trim();
        let parts: Vec<&str> = trimmed.split(' ').collect();
        if parts.len() != 2 {
            return "ERROR wrong number of arguments for DELETE".to_string();
        }
        if self.store.delete(parts[1]) {
            "1".to_string()
        } else {
            "0".to_string()
        }
    }

    fn cmd_count(&mut self, line: &str) -> String {
        let trimmed = line.trim();
        let parts: Vec<&str> = trimmed.splitn(2, ' ').collect();
        if parts.len() < 2 {
            return "ERROR wrong number of arguments for COUNT".to_string();
        }
        let count = self.store.count_value(parts[1]);
        count.to_string()
    }

    fn cmd_keys(&mut self, line: &str) -> String {
        let trimmed = line.trim();
        let parts: Vec<&str> = trimmed.split(' ').collect();
        let prefix = if parts.len() > 1 { parts[1] } else { "" };
        let keys = self.store.keys_with_prefix(prefix);
        if keys.is_empty() {
            "(empty)".to_string()
        } else {
            keys.join(" ")
        }
    }

    fn cmd_incr(&mut self, line: &str) -> String {
        let trimmed = line.trim();
        let parts: Vec<&str> = trimmed.splitn(2, ' ').collect();
        if parts.len() < 2 {
            return "ERROR wrong number of arguments for INCR".to_string();
        }
        let key = parts[1];
        let current = self.store.get(key);
        let value: i64 = match current {
            Some(val) => match val.parse::<i64>() {
                Ok(n) => n,
                Err(_) => {
                    return "ERROR value is not an integer".to_string();
                }
            },
            None => 0,
        };
        let new_value = value + 1;
        self.store.set(key, &new_value.to_string());
        new_value.to_string()
    }

    fn cmd_begin(&mut self, line: &str) -> String {
        let trimmed = line.trim();
        let parts: Vec<&str> = trimmed.split(' ').collect();
        if parts.len() > 1 {
            return "ERROR wrong number of arguments for BEGIN".to_string();
        }
        self.store.begin();
        "OK".to_string()
    }

    fn cmd_commit(&mut self) -> String {
        match self.store.commit() {
            Ok(()) => "OK".to_string(),
            Err(_) => "ERROR no transaction".to_string(),
        }
    }

    fn cmd_rollback(&mut self) -> String {
        match self.store.rollback() {
            Ok(()) => "OK".to_string(),
            Err(_) => "ERROR no transaction".to_string(),
        }
    }
}
