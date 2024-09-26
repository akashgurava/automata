use std::{collections::HashMap, fs::read_to_string};

use anyhow::Error;
use serde::Deserialize;
use serde_yaml::Value;

use crate::config_parser::{get_env_map, resolve_variables};

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

#[derive(Debug, Deserialize)]
struct Service {
    name: String,
    version: String,
    ports: Vec<u16>,
    logs_dir: Option<String>,
    installer: Option<Installer>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ServiceConfig {
    /// A common path where all binaries will be available.
    bin_path: String,
    /// A common path for config and data of apps.
    cfg_path: String,
    /// Groups of list of services.
    groups: Option<String>,
    /// List if services.
    services: Option<Vec<Service>>,
}

impl ServiceConfig {
    pub(crate) fn new(path: &str) -> Result<Self, Error> {
        let env_map = get_env_map()?;

        let config_file_contents = read_to_string(path)?;
        let config_file_contents: Value = serde_yaml::from_str(&config_file_contents)?;

        let resolved_data = resolve_variables(&config_file_contents, &env_map)?;

        Ok(serde_yaml::from_value(resolved_data)?)
    }
}
