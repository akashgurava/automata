#![allow(dead_code, unused_imports)]

use anyhow::Error;
use config::ServiceConfig;

mod config;
mod config_parser;

fn main() -> Result<(), Error> {
    let service_config = ServiceConfig::new("services.yaml")?;
    // dbg!(&service_config);
    service_config.ensure_installed()?;
    Ok(())
}
