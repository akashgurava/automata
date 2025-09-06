use std::{collections::HashMap, env, fs::read_to_string};

use anyhow::{bail, Context, Error, Ok};
use dotenvy::EnvMap;
use serde::{de::value, Deserialize};
use serde_yaml::{Mapping, Value};

use crate::config_parser::{expand_vars_recursive, get_env_map, resolve_variables};

fn name_validator<'a>(name: &'a Value) -> Result<&'a str, Error> {
    let name = name.as_str().context(format!(
        "Expected name to be a string. Received: {:?}",
        name
    ))?;
    // TODO: Implement only lower case and alphabets check

    Ok(name)
}

fn value_to_str<'a>(value: &'a Value, identifier: &str) -> Result<&'a str, Error> {
    let str = value
        .get(identifier)
        .context(format!("Expected {identifier} for service!"))?
        .as_str()
        .context(format!("Expected {identifier} to be a string!"))?;

    Ok(str)
}

fn value_to_sequence<'a>(value: &'a Value, identifier: &str) -> Result<&'a Vec<Value>, Error> {
    let seq = value
        .get(identifier)
        .context(format!("Expected {identifier} for service!"))?
        .as_sequence()
        .context(format!("Expected {identifier} to be a sequence!"))?;

    Ok(seq)
}

fn fill_env(env_map: &EnvMap, env: Option<&Value>) -> Result<EnvMap, Error> {
    let mut env_map = env_map.clone();
    if let Some(Value::Mapping(env)) = env {
        for (key, value) in env {
            for (key, value) in env {
                let key = value_to_str(key, "env_key")?.to_string();
                let value = expand_vars_recursive(value_to_str(value, "env_value")?, &env_map)?;
                env_map.insert(key, value);
            }
        }
    }
    Ok(env_map)
}

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
    service_name: String,
    install_path: String,
    // bin_path: String,
    // executables: HashMap<String, String>,
    // #[serde(flatten)]
    // installer_type: InstallerType,
}

impl Installer {
    fn from_value(
        service_name: &str,
        user_bin_path: &str,
        installer_data: &Value,
    ) -> Result<Self, Error> {
        Ok(Self {
            service_name: service_name.to_string(),
            install_path: value_to_str(installer_data, "install_path")?.to_string(),
        })
    }
}

#[derive(Debug, Deserialize)]
struct Service {
    group_name: Option<String>,
    name: String,
    version: String,
    // ports: Vec<u64>,
    // logs_dir: Option<String>,
    // installer: Installer,
    // env: Option<HashMap<String, String>>,
}

impl Service {
    fn from_value(
        group_name: Option<&str>,
        service_name: &str,
        service_config: &Value,
    ) -> Result<Self, Error> {
        let version = value_to_str(service_config, "version")?.to_string();
        // let ports: Result<Vec<u64>, Error> = value_to_sequence(service_data, "ports")?
        //     .into_iter()
        //     .map(|value| value.as_u64().context("Expected port to be a number!"))
        //     .collect();
        // let ports = ports?;
        // let installer = Installer::from_value(
        //     service_name,
        //     "",
        //     service_data.get("installer").expect("Expected a installer"),
        // )?;

        Ok(Self {
            group_name: group_name.map(|str| str.to_string()),
            name: service_name.to_string(),
            version,
            // ports,
            // installer,
        })
    }
}

#[derive(Debug, Deserialize)]
struct ServiceGroup {
    name: String,
    services: HashMap<String, Service>,
}

impl ServiceGroup {
    fn from_value(
        env_map: &EnvMap,
        service_group_name: &str,
        service_group_config: &Value,
    ) -> Result<Self, Error> {
        let env_map = fill_env(env_map, service_group_config.get("env"))?;

        let mut services: HashMap<String, Service> = HashMap::new();
        if let Value::Mapping(service_group_config) = service_group_config {
            for (service_name, service_config) in service_group_config {
                let service_name = name_validator(service_name)?;
                if service_name == "env" {
                    continue;
                }
                let service =
                    Service::from_value(Some(service_group_name), service_name, service_config)?;
                services.insert(service_name.to_string(), service);
            }
        }
        Ok(Self {
            name: service_group_name.to_string(),
            services,
        })
    }
}

#[derive(Debug)]
pub(crate) struct Registry {
    /// List if Services.
    services: Vec<Service>,
    /// List of ServiceGroups.
    service_groups: Vec<ServiceGroup>,
}

impl Registry {
    fn from_value(registry_config: Value) -> Result<Self, Error> {
        let env_map = fill_env(&get_env_map()?, registry_config.get("env"))?;

        let mut defined_service_names: Vec<String> = Vec::new();
        let mut service_groups: Vec<ServiceGroup> = Vec::new();
        if let Some(service_groups_config) = registry_config.get("groups") {
            if let Value::Mapping(service_groups_config) = service_groups_config {
                for (service_group_name, service_group_config) in service_groups_config {
                    let service_group_name = name_validator(service_group_name)?;
                    let service_group = ServiceGroup::from_value(
                        &env_map,
                        service_group_name,
                        service_group_config,
                    )?;

                    defined_service_names.extend(service_group.services.keys().cloned());
                    service_groups.push(service_group);
                }
            } else {
                bail!(
                    "Expected a sequence of Services. Received: {:?}",
                    service_groups_config
                );
            }
        }

        let mut services: Vec<Service> = Vec::new();
        if let Some(services_config) = registry_config.get("services") {
            if let Value::Mapping(services_config) = services_config {
                for (service_name, service_config) in services_config {
                    if let Value::String(service_name) = service_name {
                        let service = Service::from_value(None, service_name, service_config)?;
                        if defined_service_names.contains(&service.name) {
                            bail!("Service name: {}. Duplicated service name!", service.name);
                        }
                        defined_service_names.push(service.name.clone());
                        services.push(service);
                    }
                }
            } else {
                bail!("Expected a sequence of Services. Received: {:?}", services);
            }
        }

        Ok(Self {
            service_groups,
            services,
        })
    }

    pub(crate) fn new(path: &str) -> Result<Self, Error> {
        let config_file_contents = read_to_string(path)?;
        let registry_config: Value = serde_yaml::from_str(&config_file_contents)?;

        // let resolved_data = resolve_variables(&config_file_contents, &env_map)?;
        Self::from_value(registry_config)
    }
}
