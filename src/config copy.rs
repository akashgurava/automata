use std::{
    collections::HashMap,
    fs::{self, read_to_string},
    io::ErrorKind,
    os::unix::fs::symlink,
    path::{Path, PathBuf},
};

use anyhow::Error;
use liblzma::read::XzDecoder;
use reqwest::blocking::get;
use serde::Deserialize;
use serde_yaml::Value;
use tar::Archive;

use crate::config_parser::{get_env_map, resolve_variables};

#[derive(Debug, Deserialize)]
enum InstallerType {
    #[serde(rename = "binary")]
    Binary {
        download_url: String,
        is_archive: bool,
    },
    #[serde(rename = "brew")]
    Brew { formulae: String },
}

#[derive(Debug, Deserialize)]
struct Installer {
    install_path: String,
    executables: HashMap<String, String>,
    #[serde(flatten)]
    installer_type: InstallerType,
}

impl Installer {
    pub(crate) fn is_installed(&self) -> bool {
        for (executable, path) in &self.executables {
            let user_bin_path = format!("${{USER_BIN_PATH}}/{executable}");
            let install_path = format!("{}/{}", self.install_path, path);

            // Check if the executable exists or if it's a valid symlink
            if Path::new(&user_bin_path).exists() {
                // Check if it's a symlink and if it points to the correct target
                if let Ok(metadata) = fs::symlink_metadata(&user_bin_path) {
                    if metadata.file_type().is_symlink() {
                        if let Ok(link_target) = fs::read_link(&user_bin_path) {
                            if link_target != Path::new(&install_path) {
                                return false;
                            }
                        }
                    }
                }
            } else {
                return false;
            }
        }
        return true;
    }
}

#[derive(Debug, Deserialize)]
struct Service {
    name: String,
    version: String,
    ports: Vec<u16>,
    logs_dir: Option<String>,
    installer: Installer,
    env: Option<HashMap<String, String>>,
}

impl Service {
    pub(crate) fn ensure_installed(&self) -> Result<(), Error> {
        if self.installer.is_installed() {
            println!("Service: {}. Service already exists!", self.name);
            return Ok(());
        };

        println!(
            "Service: {}. Service does not exist. Installing now!",
            self.name
        );
        // self.installer.install();
        Ok(())
    }
}

#[derive(Debug, Deserialize)]
struct ServiceGroup {
    services: Vec<Service>,
}

impl ServiceGroup {
    pub(crate) fn ensure_installed(&self) -> Result<(), Error> {
        for service in &self.services {
            service.ensure_installed()?
        }
        Ok(())
    }
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
struct UserEnv {
    user_apps_path: String,
    user_install_path: String,
    user_bin_path: String,
    user_cfg_path: String,
    user_log_path: String,
}

#[derive(Debug, Deserialize)]
pub(crate) struct Registry {
    env: UserEnv,
    /// Groups of list of services.
    groups: Option<HashMap<String, ServiceGroup>>,
    /// List if services.
    services: Option<Vec<Service>>,
}

impl Registry {
    pub(crate) fn ensure_installed(&self) -> Result<(), Error> {
        if let Some(groups) = &self.groups {
            for (_, service_group) in groups {
                service_group.ensure_installed()?
            }
        }
        if let Some(services) = &self.services {
            for service in services {
                service.ensure_installed()?
            }
        }

        Ok(())
    }
}

impl Registry {
    pub(crate) fn new(path: &str) -> Result<Self, Error> {
        let env_map = get_env_map()?;

        let config_file_contents = read_to_string(path)?;
        let config_file_contents: Value = serde_yaml::from_str(&config_file_contents)?;

        let resolved_data = resolve_variables(&config_file_contents, &env_map)?;

        Ok(serde_yaml::from_value(resolved_data)?)
    }
}
