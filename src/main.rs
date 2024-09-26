#![allow(dead_code)]

use config::ServiceConfig;

mod config;
mod config_parser;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let service_config = ServiceConfig::new("services.yaml")?;
    dbg!(service_config);
    Ok(())
}
