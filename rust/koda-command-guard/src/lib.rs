//! koda-command-guard — native regex matcher for tool-dispatcher block patterns.
//!
//! The Python tool dispatcher matches several `BLOCKED_*_PATTERN` regexes on
//! every `<agent_cmd>` invocation (see `koda/services/tool_dispatcher.py` and
//! the patterns at `koda/config.py:479+`). Those patterns are user-input-
//! adjacent, security-critical, and run on the asyncio main thread. Two
//! payoffs from compiling them once with the Rust `regex` crate:
//!
//! 1. Linear-time matching guarantee — `regex` is RE2-style, so a malicious
//!    or malformed input cannot blow up matching with catastrophic
//!    backtracking the way Python's `re` can.
//! 2. Native cost — no GIL contention, no interpreter overhead per
//!    invocation. The Python integration shim is a thin wrapper that calls
//!    into here through PyO3 with a frozen pre-compiled matcher.
//!
//! The pure-Rust API (`Guard::new`, `Guard::is_blocked`) is exercised by the
//! unit tests under `#[cfg(test)]`; the PyO3 binding wraps it for use from
//! `koda/services/command_guard.py`.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use regex::{Regex, RegexBuilder};

/// Compiled regex matcher with case-insensitive matching.
///
/// The Python `re.compile(pattern, re.I)` call sites in `koda/config.py`
/// build their patterns case-insensitive, so this struct mirrors that
/// default. Use `Guard::new` to fail fast on a malformed pattern rather
/// than at first call.
pub struct Guard {
    pattern: Regex,
}

impl Guard {
    pub fn new(pattern: &str) -> Result<Self, regex::Error> {
        let pattern = RegexBuilder::new(pattern).case_insensitive(true).build()?;
        Ok(Self { pattern })
    }

    /// True if the pattern matches anywhere in `text`. Equivalent to
    /// Python `pattern.search(text) is not None`.
    pub fn is_blocked(&self, text: &str) -> bool {
        self.pattern.is_match(text)
    }

    /// Return the first matching span as a `(start, end)` byte offset
    /// pair so callers can highlight the offending substring in audit
    /// events. None when there is no match.
    pub fn first_match_span(&self, text: &str) -> Option<(usize, usize)> {
        self.pattern.find(text).map(|m| (m.start(), m.end()))
    }
}

/// PyO3 wrapper exposing `Guard` to Python.
#[pyclass(name = "Guard", module = "koda_command_guard")]
struct PyGuard {
    inner: Guard,
}

#[pymethods]
impl PyGuard {
    #[new]
    fn new(pattern: &str) -> PyResult<Self> {
        Guard::new(pattern)
            .map(|inner| Self { inner })
            .map_err(|err| PyValueError::new_err(format!("invalid pattern: {err}")))
    }

    fn is_blocked(&self, text: &str) -> bool {
        self.inner.is_blocked(text)
    }

    fn first_match_span(&self, text: &str) -> Option<(usize, usize)> {
        self.inner.first_match_span(text)
    }
}

#[pymodule]
fn koda_command_guard(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyGuard>()?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::Guard;

    #[test]
    fn matches_destructive_shell_command() {
        let g = Guard::new(r"rm\s+-rf|mkfs|dd\s+if=").unwrap();
        assert!(g.is_blocked("rm -rf /"));
        assert!(g.is_blocked("RM -RF /"));
        assert!(g.is_blocked("mkfs.ext4 /dev/sda1"));
        assert!(!g.is_blocked("git status"));
    }

    #[test]
    fn first_match_span_points_at_offending_substring() {
        let g = Guard::new(r"sudo\b").unwrap();
        let text = "please sudo apt-get install";
        let (start, end) = g.first_match_span(text).expect("sudo should match");
        assert_eq!(&text[start..end], "sudo");
    }

    #[test]
    fn rejects_malformed_pattern_at_construction_time() {
        match Guard::new(r"(unclosed") {
            Ok(_) => panic!("expected malformed pattern to fail compile"),
            Err(err) => {
                let _ = err.to_string();
            }
        }
    }
}
