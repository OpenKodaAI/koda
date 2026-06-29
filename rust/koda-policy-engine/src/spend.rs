//! Spend cap evaluation. Pure logic separated from the store so it can
//! be unit-tested without DB plumbing.
//!
//! Three thresholds matter:
//! - **Allowed budget remaining**: `cap - spent`.
//! - **Warning threshold crossed** when `spent / cap >= warning_fraction`.
//!   Operator sees a structured event but ingestion continues.
//! - **Hard stop crossed** when `spent >= cap`. CheckIngest denies new
//!   messages with `monthly_spend_cap_reached` until the next month.

#[derive(Debug, Clone, Copy)]
pub struct SpendDecision {
    pub remaining_budget_usd: f64,
    pub warning_threshold_crossed: bool,
    pub hard_stop_threshold_crossed: bool,
}

pub fn evaluate_spend(cap_usd: f64, spent_usd: f64, warning_fraction: f64) -> SpendDecision {
    if cap_usd <= 0.0 {
        return SpendDecision {
            remaining_budget_usd: f64::INFINITY,
            warning_threshold_crossed: false,
            hard_stop_threshold_crossed: false,
        };
    }
    let remaining = (cap_usd - spent_usd).max(0.0);
    let warn_at = cap_usd * warning_fraction.clamp(0.0, 1.0);
    SpendDecision {
        remaining_budget_usd: remaining,
        warning_threshold_crossed: spent_usd >= warn_at && warning_fraction > 0.0,
        hard_stop_threshold_crossed: spent_usd >= cap_usd,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cap_zero_disables_all_thresholds() {
        let d = evaluate_spend(0.0, 1_000_000.0, 0.8);
        assert!(d.remaining_budget_usd.is_infinite());
        assert!(!d.warning_threshold_crossed);
        assert!(!d.hard_stop_threshold_crossed);
    }

    #[test]
    fn warns_at_eighty_percent_by_default() {
        let d = evaluate_spend(100.0, 80.0, 0.8);
        assert!(d.warning_threshold_crossed);
        assert!(!d.hard_stop_threshold_crossed);
        assert!((d.remaining_budget_usd - 20.0).abs() < 1e-9);
    }

    #[test]
    fn hard_stops_when_cap_met() {
        let d = evaluate_spend(100.0, 100.0, 0.8);
        assert!(d.hard_stop_threshold_crossed);
        assert_eq!(d.remaining_budget_usd, 0.0);
    }

    #[test]
    fn over_budget_clamps_to_zero() {
        let d = evaluate_spend(100.0, 175.0, 0.8);
        assert!(d.hard_stop_threshold_crossed);
        assert_eq!(d.remaining_budget_usd, 0.0);
    }

    #[test]
    fn warning_fraction_zero_disables_warn_only() {
        let d = evaluate_spend(100.0, 99.0, 0.0);
        assert!(!d.warning_threshold_crossed);
        assert!(!d.hard_stop_threshold_crossed);
    }
}
