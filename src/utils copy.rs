use std::collections::HashMap;
use std::env;
use std::error::Error;
use std::fs;
use std::fs::File;
use std::io::Read;
use std::io::{self, BufRead};
use std::os::unix::fs::PermissionsExt;
use std::path::Path;

use dotenvy::{EnvLoader, EnvSequence};
use log::{debug, info};
use regex::Captures;
use regex::Regex;

// /// Ensures a directory exists.
// /// If the directory does not exist, it creates it with the given permissions.
// ///
// /// # Arguments
// /// * `path` - Path to the directory.
// /// * `mode` - Permissions to set for the directory.
// ///
// /// # Example
// /// ```
// /// ensure_dir_exists("/tmp/logs", 0o755);
// /// ```
// pub fn ensure_dir_exists(path: &str, mode: u32) {
//     let path_obj = Path::new(path);
//     if !path_obj.exists() {
//         info!(
//             "Path: {}. Directory does not exist. Creating directory.",
//             path
//         );
//         fs::create_dir_all(path).expect("Failed to create directory");
//         let permissions = fs::Permissions::from_mode(mode);
//         fs::set_permissions(path, permissions).expect("Failed to set permissions");
//     } else {
//         debug!("Path: {}. Directory already exists.", path);
//     }
// }

// /// Logs output from a subprocess pipe line by line.
// /// Reads from a subprocess pipe and logs each line at DEBUG level.
// ///
// /// # Arguments
// /// * `pipe` - A file-like object representing the subprocess pipe (stdout or stderr).
// ///
// /// # Example
// /// ```
// /// let child = Command::new("echo")
// ///     .arg("Hello, world!")
// ///     .stdout(Stdio::piped())
// ///     .spawn()
// ///     .expect("Failed to spawn command");
// /// if let Some(stdout) = child.stdout {
// ///     log_subprocess_output(stdout);
// /// }
// /// ```
// pub fn log_subprocess_output<T: Read>(pipe: T) {
//     let reader = io::BufReader::new(pipe);
//     for line in reader.lines() {
//         if let Ok(line) = line {
//             debug!("{}", line);
//         }
//     }
// }

/// Recursively expands environment variables in a given var using `${var}` syntax.
///
/// # Arguments
/// * `var` - A string var that may contain environment variables.
///
/// # Returns
/// * A `Result<String, String>` which is:
///     - `Ok`: The fully expanded var string with all environment variables expanded.
///     - `Err`: An error message if any environment variable cannot be resolved.
///
/// # Example
/// ```
/// let expanded = expand_var_recursive("${HOME}/test_dir");
/// match expanded {
///     Ok(var) => println!("Expanded Path: {}", var),
///     Err(err) => println!("Error: {}", err),
/// }
/// ```
pub fn expand_var_recursive(var: &str) -> Result<String, Box<dyn std::error::Error>> {
    let path = Path::new(".env");
    let loader = match File::open(path) {
        Ok(file) => EnvLoader::with_reader(file)
            .path(path)
            .sequence(EnvSequence::InputThenEnv),
        Err(e) => {
            if e.kind() == io::ErrorKind::NotFound {
                EnvLoader::default().sequence(EnvSequence::EnvOnly)
            } else {
                return Err(Box::new(e));
            }
        }
    };
    let env_map = loader.load()?;

    let mut result = var.to_string();
    let re = Regex::new(r"\$\{(\w+)\}").unwrap();
    let mut unresolved_vars = Vec::new();

    while re.is_match(&result) {
        result = re
            .replace_all(&result, |captures: &Captures| {
                if let Ok(var_value) = env_map.var(&captures[1]) {
                    var_value
                } else {
                    unresolved_vars.push(captures[1].to_string());
                    captures[0].to_string()
                }
            })
            .to_string();

        // If there are , break the loop.
        if !unresolved_vars.is_empty() {
            break;
        }
    }

    if unresolved_vars.is_empty() {
        Ok(result)
    } else {
        Err(format!(
            "Failed to resolve the following environment variables: {:?}",
            unresolved_vars
        )
        .into())
    }
}

// Helper function to extract variables for each service in YAML content
fn extract_yaml_service_vars(yaml_content: &str) -> HashMap<String, HashMap<String, String>> {
    let mut service_vars: HashMap<String, HashMap<String, String>> = HashMap::new();

    // Regex to find services and their versions (captures service name and version)
    let re_service = Regex::new(r#"name:\s*\"([^\"]+)\".*?version:\s*\"([^\"]+)\""#).unwrap();

    for cap in re_service.captures_iter(yaml_content) {
        let service_name = &cap[1];
        let service_version = &cap[2];

        // Create a map for the current service's variables
        let mut vars = HashMap::new();
        vars.insert("version".to_string(), service_version.to_string());

        // Insert into the service_vars map
        service_vars.insert(service_name.to_string(), vars);
    }

    service_vars
}

/// Helper function to resolve variables in the context of the services
fn resolve_variable(
    var_name: &str,
    yaml_vars: &HashMap<String, HashMap<String, String>>,
) -> String {
    for (service_name, vars) in yaml_vars {
        // Check if the current service has the variable
        if let Some(value) = vars.get(var_name) {
            return value.to_string();
        }
    }

    // If the variable is not found in the YAML-defined variables, try environment variables
    env::var(var_name).unwrap_or_else(|_| format!("${{{}}}", var_name))
}

// fn resolve_env_vars(var: &str) -> Result<String, Box<dyn Error>> {
//     let re = Regex::new(r"\$\{([^}]+)\}").unwrap();
//     if !re.is_match(&var) {
//         return Ok(var.to_string());
//     }
//     let resolved = re.replace_all(&var, |caps: &regex::Captures| {
//         env::var(&caps[1]).map_err(|e| format!("{}: {}", e, caps[0]))?
//     });
//     resolve_env_vars(&resolved)
// }

// /// Unit tests for the utility functions.
// #[cfg(test)]
// mod tests {
//     use super::*;
//     use std::env;
//     use std::process::{Command, Stdio};

//     #[test]
//     fn test_ensure_dir_exists() {
//         let path = "/tmp/test_dir";
//         ensure_dir_exists(path, 0o755);
//         assert!(Path::new(path).exists());
//         fs::remove_dir(path).unwrap(); // Clean up
//     }

//     #[test]
//     fn test_log_subprocess_output() {
//         let output = Command::new("echo")
//             .arg("Hello, world!")
//             .stdout(Stdio::piped())
//             .spawn()
//             .expect("Failed to spawn command");

//         if let Some(stdout) = output.stdout {
//             log_subprocess_output(stdout);
//         }
//     }

//     #[test]
//     fn test_expand_vars_recursive() -> Result<(), String> {
//         env::set_var("APP_NAME", "test_app");
//         env::set_var("APP_HOME", "${HOME}/${APP_NAME}");
//         let path = "${APP_HOME}/dir";
//         let expanded = expand_var_recursive(path)?;
//         assert_eq!(
//             expanded,
//             format!("{}/test_app/dir", expand_var_recursive("${HOME}")?)
//         );
//         Ok(())
//     }
// }
