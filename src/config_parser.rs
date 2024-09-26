use anyhow::{bail, Error};
use dotenvy::{EnvLoader, EnvMap, EnvSequence};
use regex::Regex;
use serde_yaml::Value;
use std::{fs::File, io, path::Path};

/// Loads environment variables from a `.env` file or the system environment if the file is not found.
///
/// If a `.env` file exists, this function loads variables from both the file and the system environment,
/// with the file taking precedence. If the file is not found, only the system environment variables are loaded.
///
/// # Errors
///
/// Returns an `anyhow::Error` if the `.env` file cannot be opened for reasons other than not being found.
///
/// # Example
/// ```
/// let env_map = get_env_map().unwrap();
/// assert!(env_map.contains_key("HOME"));
/// ```
///
/// # Returns
///
/// A `Result` containing the `EnvMap` with the loaded environment variables or an error if loading failed.
pub(crate) fn get_env_map() -> Result<EnvMap, Error> {
    let path = Path::new(".env");
    let loader = match File::open(path) {
        Ok(file) => EnvLoader::with_reader(file)
            .path(path)
            .sequence(EnvSequence::InputThenEnv),
        Err(e) => {
            if e.kind() == io::ErrorKind::NotFound {
                EnvLoader::default().sequence(EnvSequence::EnvOnly)
            } else {
                return Err(e.into());
            }
        }
    };
    Ok(loader.load()?)
}

/// Recursively expand environment variables in a string using the provided context.
///
/// This function looks for patterns like `${VAR_NAME}` in the string and replaces them
/// with corresponding values from the `EnvMap`. If the variable is not found in the context, an error is returned.
///
/// # Errors
///
/// Returns an error if a variable in the string cannot be resolved.
///
/// # Example
/// ```
/// let mut env_map = get_env_map().unwrap();
/// env_map.insert("MY_VAR".to_string(), "hello".to_string());
/// let result = expand_vars_recursive("Say ${MY_VAR}", &env_map).unwrap();
/// assert_eq!(result, "Say hello");
/// ```
///
/// # Returns
///
/// A `Result` containing the expanded string or an error if variable resolution failed.
fn expand_vars_recursive(value: &str, context: &EnvMap) -> Result<String, Error> {
    let pattern = Regex::new(r"\$\{([^}]+)\}").unwrap();
    let mut result = value.to_string();
    while let Some(captures) = pattern.captures(&result) {
        let var_name = &captures[1];
        if let Some(replacement) = context.get(var_name) {
            result = result.replacen(&captures[0], replacement, 1);
        } else {
            bail!("Variable {} could not be resolved!", var_name);
        }
    }
    Ok(result)
}

/// Recursively resolve environment variables in a data structure.
///
/// This function will walk through a YAML data structure and resolve any variables found in
/// strings (e.g., `${VAR_NAME}`) using the provided `EnvMap`. The data structure can be a combination
/// of mappings (YAML dictionaries), sequences (lists), and strings.
///
/// # Errors
///
/// Returns an error if any variable in the data structure cannot be resolved.
///
/// # Example
/// ```
/// let yaml_str = r#"
/// env_path: "${HOME}/my_app"
/// "#;
/// let yaml_data: Value = serde_yaml::from_str(yaml_str).unwrap();
/// let mut env_map = get_env_map().unwrap();
/// let resolved = resolve_variables(&yaml_data, &mut env_map).unwrap();
/// if let Value::Mapping(mapping) = resolved {
///     assert_eq!(mapping.get(&Value::String("env_path".to_string())).unwrap(), &Value::String("/home/user/my_app".to_string()));
/// }
/// ```
///
/// # Returns
///
/// A `Result` containing the resolved `Value` or an error if resolution failed.
pub(crate) fn resolve_variables(data: &Value, context: &EnvMap) -> Result<Value, Error> {
    match data {
        Value::String(s) => {
            // Expand variables in strings
            Ok(Value::String(expand_vars_recursive(s, context)?))
        }
        Value::Mapping(mapping) => {
            // Create a new context for the current level
            let mut new_context = context.clone();

            // First pass: resolve only strings and update the context
            let mut temp_map = serde_yaml::Mapping::new();
            for (key, value) in mapping {
                if let Value::String(ref k) = key {
                    if let Value::String(ref v) = value {
                        // Resolve the value and insert it into the context for further use
                        let resolved_value = expand_vars_recursive(v, &new_context)?;
                        new_context.insert(k.clone(), resolved_value.clone());
                        temp_map.insert(Value::String(k.clone()), Value::String(resolved_value));
                    }
                }
            }

            // Second pass: recursively resolve remaining nested structures using the updated context
            let mut resolved_map = serde_yaml::Mapping::new();
            for (key, value) in mapping {
                let resolved_key = resolve_variables(key, &mut new_context)?;
                let resolved_value = resolve_variables(value, &mut new_context)?;
                resolved_map.insert(resolved_key, resolved_value);
            }

            Ok(Value::Mapping(resolved_map))
        }
        Value::Sequence(seq) => {
            // Handle sequences
            let resolved_seq: Result<Vec<Value>, _> = seq
                .iter()
                .map(|item| resolve_variables(item, context))
                .collect();
            Ok(Value::Sequence(resolved_seq?))
        }
        _ => Ok(data.clone()), // Return other types as-is (e.g., integers, booleans)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_expand_vars_recursive_nested() {
        // Define a deeply nested YAML string with recursive variable usage
        let yaml_str = r#"
    base_path: "${ROOT_DIR}"
    level1:
        service1:
            app_path: "${base_path}/app1"
            config_path: "${app_path}/config"
            logs_path: "${app_path}/logs"
            nested_level:
                install_path: "${base_path}/install"
        service2:
            app_path: "${base_path}/app2"
            config_path: "${app_path}/config"
            logs_path: "${app_path}/logs"
            nested_level:
                install_path: "${base_path}/install"
    "#;

        // Parse the YAML string into a serde_yaml::Value
        let yaml_data: Value = serde_yaml::from_str(yaml_str).unwrap();

        // Create an EnvMap with the base variables
        let mut env_map = EnvMap::new();
        env_map.insert("HOME".to_string(), "/usr/home".to_string());
        env_map.insert("ROOT_DIR".to_string(), "${HOME}/root".to_string());

        // Resolve variables recursively
        let resolved = resolve_variables(&yaml_data, &env_map).unwrap();

        // Check the resolved values in the deeply nested structure
        if let Value::Mapping(mapping) = resolved {
            // Resolve `base_path`
            assert_eq!(
                mapping
                    .get(&Value::String("base_path".to_string()))
                    .unwrap(),
                &Value::String("/usr/home/root".to_string())
            );

            if let Value::Mapping(level1) =
                mapping.get(&Value::String("level1".to_string())).unwrap()
            {
                // Check service1 variables
                if let Value::Mapping(service1) =
                    level1.get(&Value::String("service1".to_string())).unwrap()
                {
                    assert_eq!(
                        service1
                            .get(&Value::String("app_path".to_string()))
                            .unwrap(),
                        &Value::String("/usr/home/root/app1".to_string())
                    );
                    assert_eq!(
                        service1
                            .get(&Value::String("config_path".to_string()))
                            .unwrap(),
                        &Value::String("/usr/home/root/app1/config".to_string())
                    );
                    assert_eq!(
                        service1
                            .get(&Value::String("logs_path".to_string()))
                            .unwrap(),
                        &Value::String("/usr/home/root/app1/logs".to_string())
                    );
                    if let Value::Mapping(nested_level) = service1
                        .get(&Value::String("nested_level".to_string()))
                        .unwrap()
                    {
                        assert_eq!(
                            nested_level
                                .get(&Value::String("install_path".to_string()))
                                .unwrap(),
                            &Value::String("/usr/home/root/install".to_string())
                        );
                    }
                }

                // Check service2 variables
                if let Value::Mapping(service2) =
                    level1.get(&Value::String("service2".to_string())).unwrap()
                {
                    assert_eq!(
                        service2
                            .get(&Value::String("app_path".to_string()))
                            .unwrap(),
                        &Value::String("/usr/home/root/app2".to_string())
                    );
                    assert_eq!(
                        service2
                            .get(&Value::String("config_path".to_string()))
                            .unwrap(),
                        &Value::String("/usr/home/root/app2/config".to_string())
                    );
                    assert_eq!(
                        service2
                            .get(&Value::String("logs_path".to_string()))
                            .unwrap(),
                        &Value::String("/usr/home/root/app2/logs".to_string())
                    );
                    if let Value::Mapping(nested_level) = service2
                        .get(&Value::String("nested_level".to_string()))
                        .unwrap()
                    {
                        assert_eq!(
                            nested_level
                                .get(&Value::String("install_path".to_string()))
                                .unwrap(),
                            &Value::String("/usr/home/root/install".to_string())
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn test_resolve_variables_in_mapping() {
        let yaml_str = r#"
        env_path: "${MY_PATH}"
        "#;
        let yaml_data: Value = serde_yaml::from_str(yaml_str).unwrap();

        let mut env_map = EnvMap::new();
        env_map.insert("MY_PATH".to_string(), "/home/user/my_app".to_string());

        let resolved = resolve_variables(&yaml_data, &env_map).unwrap();
        if let Value::Mapping(mapping) = resolved {
            assert_eq!(
                mapping.get(&Value::String("env_path".to_string())).unwrap(),
                &Value::String("/home/user/my_app".to_string())
            );
        }
    }

    #[test]
    fn test_resolve_variables_in_sequence() {
        let yaml_str = r#"
        paths:
          - "${PATH_ONE}"
          - "${PATH_TWO}"
        "#;
        let yaml_data: Value = serde_yaml::from_str(yaml_str).unwrap();

        let mut env_map = EnvMap::new();
        env_map.insert("PATH_ONE".to_string(), "/path/one".to_string());
        env_map.insert("PATH_TWO".to_string(), "/path/two".to_string());

        let resolved = resolve_variables(&yaml_data, &env_map).unwrap();
        if let Value::Mapping(mapping) = resolved {
            if let Value::Sequence(paths) =
                mapping.get(&Value::String("paths".to_string())).unwrap()
            {
                assert_eq!(paths[0], Value::String("/path/one".to_string()));
                assert_eq!(paths[1], Value::String("/path/two".to_string()));
            }
        }
    }
}
