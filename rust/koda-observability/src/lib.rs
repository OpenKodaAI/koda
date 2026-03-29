use std::collections::HashMap;

use tracing_subscriber::EnvFilter;

pub fn init_tracing(service_name: &str) {
    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(format!("{service_name}=info,tonic=info")));
    let _ = tracing_subscriber::fmt()
        .with_env_filter(env_filter)
        .with_target(false)
        .json()
        .try_init();
}

pub fn health_details(service_name: &str) -> HashMap<String, String> {
    let mut details = HashMap::new();
    details.insert("service".to_string(), service_name.to_string());
    details.insert("version".to_string(), env!("CARGO_PKG_VERSION").to_string());
    details
}
