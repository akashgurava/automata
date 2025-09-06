#![allow(dead_code, unused_imports, unused_variables, unused_mut)]

use anyhow::Error;
use config::Registry;

mod config;
mod config_parser;

fn main() -> Result<(), Error> {
    let service_config = Registry::new("services.yaml")?;
    dbg!(&service_config);
    // service_config.ensure_installed()?;
    Ok(())
}
