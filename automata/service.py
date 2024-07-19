from __future__ import annotations

import os
import re
import socket
import subprocess
import shutil
from time import sleep
import yaml
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger
from psutil import process_iter
from signal import SIGTERM
from typing import Any, Dict, List

from automata.utils import ensure_dir_exists
from automata.install import BinaryInstaller, Installer, BrewInstaller


# Load environment variables from a .env file
load_dotenv()


def expandvars_recursive(value: str, context: Dict[str, Any]) -> str:
    """
    Recursively expand environment variables in a string using the provided context and environment variables.

    :param value: The string containing environment variables to expand.
    :param context: The context dictionary to use for variable resolution.
    :return: The string with expanded environment variables.
    :raises ValueError: If a variable is not resolvable.
    """
    pattern = re.compile(r"\$\{([^}]+)\}")
    while True:
        match = pattern.search(value)
        if not match:
            break
        var_name = match.group(1)
        replacement = context.get(var_name, os.getenv(var_name, None))
        if replacement is None:
            raise ValueError(f"Variable {var_name} is not resolvable.")
        value = value[: match.start()] + replacement + value[match.end() :]
    return value


def resolve_variables(data: Any, context: Dict[str, Any]) -> Any:
    """
    Recursively resolve environment variables in the provided data structure.

    :param data: The data structure (dict, list, or str) containing environment variables to resolve.
    :param context: The context dictionary to use for variable resolution.
    :return: The data structure with resolved environment variables.
    :raises ValueError: If a variable is not resolvable.
    """
    if isinstance(data, dict):
        # Update context with the current level data first to resolve at the same level
        new_context = context.copy()
        new_context.update(data) # type: ignore

        resolved_data = {}
        for key, value in data.items(): # type: ignore
            if isinstance(value, str):
                resolved_data[key] = expandvars_recursive(value, new_context)
            else:
                resolved_data[key] = resolve_variables(value, new_context)
        return resolved_data # type: ignore
    elif isinstance(data, list):
        return [resolve_variables(item, context) for item in data] # type: ignore
    else:
        return data


class Config:
    def __init__(self, service: str, src: str, dest: str):
        self.service = service
        self.src = src
        self.dest = dest
        self.validate_paths()

    def validate_paths(self):
        if not os.path.exists(self.src):
            raise ValueError(f"Source path does not exist: {self.src}")

        if os.path.isdir(self.src) and (
            os.path.exists(self.dest) and not os.path.isdir(self.dest)
        ):
            raise ValueError(f"Destination must be a directory: {self.dest}")

        if os.path.isfile(self.src) and (
            os.path.exists(self.dest) and not os.path.isfile(self.dest)
        ):
            raise ValueError(f"Destination must be a file: {self.dest}")

    def apply(self):
        if os.path.isdir(self.src):
            ensure_dir_exists(self.dest)
            logger.info(
                f"Service: {self.service}. Src: {self.src}. Dest: {self.dest}. Copyting src dir contents."
            )
            shutil.copytree(self.src, self.dest, dirs_exist_ok=True)
        else:
            dest_dir = os.path.dirname(self.dest)
            ensure_dir_exists(dest_dir)
            logger.info(
                f"Service: {self.service}. Src: {self.src}. Dest: {self.dest}. Copyting src file contents."
            )
            shutil.copy2(self.src, self.dest)

    def __repr__(self):
        return f"Config(src={self.src}, dest={self.dest})"


class Service:
    def __init__(
        self,
        name: str,
        port: int,
        version: str,
        logs_dir: str,
        installer: Installer,
        configs: List[Config],
        start_cmd: str,
    ):
        self.name = name
        self.port = port
        self.version = version
        self.logs_dir = logs_dir
        self.installer = installer
        self.configs = configs
        self.start_cmd = start_cmd

    def __repr__(self):
        return (
            f"Service(name={self.name}, port={self.port}, version={self.version}, "
            f"logs_dir={self.logs_dir}, installer={self.installer}, configs={self.configs}, "
            f"start_cmd={self.start_cmd})"
        )

    @staticmethod
    def create_services(yaml_file_path: str) -> list[Service]:
        with open(yaml_file_path, "r") as f:
            data = yaml.safe_load(f)
        parsed_yaml = resolve_variables(data, {})
        bin_path = parsed_yaml["bin_path"]
        services: list[Service] = []
        for service_data in parsed_yaml.get("services", []):
            name = service_data["name"]
            port = service_data["port"]
            version = service_data["version"]
            logs_dir = service_data["logs_dir"]
            start_cmd = service_data["start_cmd"]

            installer_data = service_data["installer"]
            if installer_data["type"] == "binary":
                installer = BinaryInstaller(
                    service_name=name,
                    install_path=installer_data["install_path"],
                    bin_path=bin_path,
                    executables=installer_data["executables"],
                    download_url=installer_data["download_url"],
                    is_archive=installer_data["is_archive"],
                    post_install_cmd=installer_data.get("post_install_cmd"),
                )
                configs = [
                    Config(name, config_item["src"], config_item["dest"])
                    for config_item in service_data.get("config", [])
                ]
                
            elif installer_data["type"] == "brew":
                installer = BrewInstaller(
                    service_name=name,
                    install_path=installer_data["install_path"],
                    bin_path=bin_path,
                    executables=installer_data["executables"],
                    package_name=installer_data["package_name"],
                    post_install_cmd=installer_data.get("post_install_cmd"),
                )
                configs = [
                    Config(name, config_item["src"], config_item["dest"])
                    for config_item in service_data.get("config", [])
                ]
            else:
                raise ValueError(f"Invalid installer type: {installer_data["type"]}")
            service = Service(
                    name=name,
                    port=port,
                    version=version,
                    logs_dir=logs_dir,
                    installer=installer,
                    configs=configs,
                    start_cmd=start_cmd,
                )
            services.append(service)
        return services

    def is_service_open(self) -> bool:
        """
        Check if a service is open at the given host and port.

        :param host: The hostname or IP address of the service.
        :param port: The port number of the service.
        :return: True if the service is open, False otherwise.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)  # Set a timeout for the connection attempt
            try:
                sock.connect(("localhost", self.port))
                return True
            except (socket.timeout, ConnectionRefusedError):
                return False

    def install(self):
        """Install the service"""
        self.installer.install()

    def start_service(self):
        """
        Start the service. If the service is not already running, check if it's installed,
        apply configuration files, and start it in the background with stdout and stderr
        logged to a file.
        """
        if self.is_service_open():
            logger.info(f"Service: {self.name}. Service already running.")
            return

        self.installer.install()

        for config in self.configs:
            config.apply()

        ensure_dir_exists(self.logs_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(self.logs_dir, f"{self.name}_{timestamp}.log")

        with open(log_file, "wb") as log:
            logger.info(
                f"Service: {self.name}. Command: {self.start_cmd}. Starting service."
            )
            process = subprocess.Popen(
                self.start_cmd, shell=True, stdout=log, stderr=log
            )
            logger.info(
                f"Service: {self.name}. PID {process.pid}. Log: {log_file}. Service triggered."
            )

        # Ensure the service is running
        for _ in range(5):
            if self.is_service_open():
                logger.info(
                    f"Service: {self.name}. PID {process.pid}. Log: {log_file}. Service running."
                )
                return
            sleep(3)
        logger.warning(
            f"Service: {self.name}. PID {process.pid}. Log: {log_file}. Service not running."
        )

    def stop_service(self):
        if not self.is_service_open():
            logger.info(f"Service: {self.name}. Service is not running.")
            return
        for proc in process_iter():
            try:
                for conns in proc.connections(kind="inet"):
                    if conns.laddr.port == self.port:
                        logger.info(f"Service: {self.name}. PID: {proc.pid}. Stopping.")
                        proc.send_signal(SIGTERM)  # or SIGKILL
            except:
                pass

    def uninstall(self):
        """Uninstall the service"""
        self.stop_service()
        self.installer.uninstall()
