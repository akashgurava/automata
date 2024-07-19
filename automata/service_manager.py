# automata/service_manager.py

from typing import List, Set
import yaml
from automata.service import Service, Config, resolve_variables
from automata.install import BinaryInstaller, BrewInstaller


class ServiceManager:
    def __init__(self, yaml_file_path: str):
        self.yaml_file_path = yaml_file_path
        self.services: List[Service] = []
        self._load_services()
        self._validate_dependencies()

    def _load_services(self):
        with open(self.yaml_file_path, "r") as f:
            data = yaml.safe_load(f)
        parsed_yaml = resolve_variables(data, {})
        bin_path = parsed_yaml["bin_path"]

        for service_data in parsed_yaml.get("services", []):
            name = service_data["name"]
            port = service_data["port"]
            version = service_data["version"]
            logs_dir = service_data["logs_dir"]
            start_cmd = service_data["start_cmd"]
            depends_on = service_data.get("depends_on", [])

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
            elif installer_data["type"] == "brew":
                installer = BrewInstaller(
                    service_name=name,
                    install_path=installer_data["install_path"],
                    bin_path=bin_path,
                    executables=installer_data["executables"],
                    package_name=installer_data["package_name"],
                    post_install_cmd=installer_data.get("post_install_cmd"),
                )
            else:
                raise ValueError(f"Invalid installer type: {installer_data['type']}")

            configs = [
                Config(name, config_item["src"], config_item["dest"])
                for config_item in service_data.get("config", [])
            ]

            service = Service(
                name=name,
                port=port,
                version=version,
                logs_dir=logs_dir,
                installer=installer,
                configs=configs,
                start_cmd=start_cmd,
                depends_on=depends_on,
            )
            self.services.append(service)

    def _validate_dependencies(self):
        service_names = {service.name for service in self.services}

        # Check if depends_on service names are valid
        for service in self.services:
            for dependency in service.depends_on:
                if dependency not in service_names:
                    raise ValueError(
                        f"Invalid dependency '{dependency}' for service '{service.name}'"
                    )

        # Check for circular references
        def check_circular(service: Service, path: list[str]):
            if service.name in path:
                raise ValueError(
                    f"Circular dependency detected: {' -> '.join(path + [service.name])}"
                )
            for dependency in service.depends_on:
                dep_service = next(s for s in self.services if s.name == dependency)
                check_circular(dep_service, path + [service.name])

        for service in self.services:
            check_circular(service, [])

    def get_service(self, name: str) -> Service:
        for service in self.services:
            if service.name == name:
                return service
        raise ValueError(f"Service '{name}' not found")

    def start_service_with_dependencies(
        self, service_name: str, started_services: Set[str]
    ):
        service = self.get_service(service_name)
        if service.name in started_services:
            return

        for dependency in service.depends_on:
            self.start_service_with_dependencies(dependency, started_services)

        service.start_service()
        started_services.add(service.name)

    def start_all_services(self):
        started_services: set[str] = set()
        for service in self.services:
            self.start_service_with_dependencies(service.name, started_services)

    def start_specific_services(self, service_names: List[str]):
        started_services: set[str] = set()
        for name in service_names:
            self.start_service_with_dependencies(name, started_services)

    def stop_all_services(self):
        for service in self.services:
            service.stop_service()

    def stop_specific_services(self, service_names: List[str]):
        for name in service_names:
            service = self.get_service(name)
            service.stop_service()

    def install_all_services(self):
        for service in self.services:
            service.install()

    def install_specific_services(self, service_names: List[str]):
        for name in service_names:
            service = self.get_service(name)
            service.install()

    def uninstall_all_services(self):
        for service in self.services:
            service.uninstall()

    def uninstall_specific_services(self, service_names: List[str]):
        for name in service_names:
            service = self.get_service(name)
            service.uninstall()
