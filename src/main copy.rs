mod utils;

use std::{collections::HashMap, fs::read_to_string};

use serde::Deserialize;

use utils::expand_var_recursive;

#[derive(Debug, Deserialize)]
struct ServiceConfig {
    /// A common path where all binaries will be available.
    bin_path: String,
    /// A common path for config and data of apps.
    cfg_path: String,
    /// Groups of list of services.
    groups: Option<String>,
    /// List if services.
    services: Option<Vec<Service>>,
}

#[derive(Debug, Deserialize)]
struct Service {
    name: String,
    version: String,
    ports: Vec<u16>,
    logs_dir: Option<String>,
    installer: Option<Installer>,
}

#[derive(Debug, Deserialize)]
enum InstallerType {
    #[serde(rename = "binary")]
    Binary,
}

#[derive(Debug, Deserialize)]
struct Installer {
    #[serde(rename = "type")]
    installer_type: InstallerType,
    download_url: String,
    is_archive: bool,
    install_path: String,
    executables: HashMap<String, String>,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let service_config_file = read_to_string("services.yaml")?;
    let x = expand_var_recursive(&service_config_file)?;

    let d: ServiceConfig = serde_yaml::from_str(&x)?;

    dbg!(d);

    println!("Hello, world!");

    Ok(())
}
