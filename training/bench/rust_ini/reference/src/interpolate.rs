use crate::document::Ini;
use crate::error::ValueError;

impl Ini {
    /// The value with every ${key} (same section) or ${section.key} replaced, recursively.
    pub fn interpolated(&self, section: &str, key: &str) -> Result<String, ValueError> {
        let mut stack = Vec::new();
        self.resolve(section, key, &mut stack)
    }

    fn resolve(&self, section: &str, key: &str, stack: &mut Vec<String>) -> Result<String, ValueError> {
        let id = format!("{section}.{key}");
        if stack.contains(&id) {
            return Err(ValueError::Cycle(id));
        }
        let raw = self.require(section, key)?;
        stack.push(id);
        let mut out = String::new();
        let mut rest = raw;
        while let Some(start) = rest.find("${") {
            let Some(len) = rest[start + 2..].find('}') else { break };
            out.push_str(&rest[..start]);
            let reference = &rest[start + 2..start + 2 + len];
            let (ref_section, ref_key) = reference.split_once('.').unwrap_or((section, reference));
            out.push_str(&self.resolve(ref_section, ref_key, stack)?);
            rest = &rest[start + 3 + len..];
        }
        out.push_str(rest);
        stack.pop();
        Ok(out)
    }
}
