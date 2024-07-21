# automata/service_manager.py

from loguru import logger
import yaml
from automata.service import Service, Config, resolve_variables
from automata.install import BinaryInstaller, BrewInstaller, BinInstaller


class ServiceManager:
    def __init__(self, yaml_file_path: str):
        self.yaml_file_path = yaml_file_path
        self.services: list[Service] = []
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
            if isinstance(port, int):
                port = [port]
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
            elif installer_data["type"] == "local_bin":
                installer = BinInstaller(
                    service_name=name,
                    source_path=installer_data["source_path"],
                    install_path=installer_data["install_path"],
                    bin_path=bin_path,
                    executables=installer_data["executables"],
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

    def _log_operation_order(self, operation: str, order: list[list[str]] | list[str]):
        if isinstance(order[0], list):
            # For start order
            formatted_order = " -> ".join(
                ["[" + ", ".join(group) + "]" for group in order]
            )
        else:
            # For stop order
            formatted_order: str = " -> ".join(order)  # type: ignore
        logger.info(f"{operation.capitalize()} order: {formatted_order}")

    def _get_start_order(self) -> list[list[str]]:
        order: list[list[str]] = []
        started_services: set[str] = set()
        no_deps_services: list[str] = []

        def add_service(service: Service):
            if service.name in started_services:
                return

            # If the service has no dependencies, add it to no_deps_services
            if not service.depends_on:
                if service.name not in no_deps_services:
                    no_deps_services.append(service.name)
                return

            # Add dependencies first
            for dep in service.depends_on:
                if dep not in started_services:
                    add_service(self.get_service(dep))

            # Add the service itself if not already added
            if service.name not in started_services:
                order.append([service.name])
                started_services.add(service.name)

        # First, process services with dependencies
        for service in self.services:
            add_service(service)

        # Then, add services with no dependencies at the beginning
        if no_deps_services:
            order.insert(0, no_deps_services)
            started_services.update(no_deps_services)
        return order

    def _get_start_order_for_specific(
        self, specific_services: list[Service]
    ) -> list[list[str]]:
        order: list[list[str]] = []
        started_services: set[str] = set()
        no_deps_services: list[str] = []

        def add_service(service: Service):
            if service.name in started_services:
                return

            # Add dependencies first
            for dep in service.depends_on:
                dep_service = self.get_service(dep)
                if dep_service.name not in started_services:
                    add_service(dep_service)

            # Add the service itself if not already added
            if service.name not in started_services:
                if service.depends_on:
                    order.append([service.name])
                else:
                    no_deps_services.append(service.name)
                started_services.add(service.name)

        service_names_set = {service.name for service in specific_services}
        for service in specific_services:
            service_names_set.update(service.depends_on)

        # First, process services with dependencies
        for service_name in service_names_set:
            service = self.get_service(service_name)
            add_service(service)

        # Then, add services with no dependencies at the beginning
        if no_deps_services:
            order.insert(0, no_deps_services)
        return order

    def _get_stop_order(self) -> list[list[str]]:
        order: list[list[str]] = []
        stopped_services: set[str] = set()
        dependents_map: dict[str, set[str]] = {
            service.name: set() for service in self.services
        }

        # Create a map of each service to its dependents
        for service in self.services:
            for dep in service.depends_on:
                dependents_map[dep].add(service.name)

        def add_service(service: Service):
            if service.name in stopped_services:
                return

            # Collect all services that depend on the current service
            dependents = dependents_map[service.name]
            if dependents:
                for dependent in dependents:
                    if dependent not in stopped_services:
                        add_service(self.get_service(dependent))

            # Add the service itself if not already added
            if service.name not in stopped_services:
                if order and not dependents:
                    order[-1].append(service.name)
                else:
                    order.append([service.name])
                stopped_services.add(service.name)

        # Process all services
        for service in self.services:
            add_service(service)

        return order

    def _get_stop_order_for_specific(
        self, specific_services: list[Service]
    ) -> list[list[str]]:
        order: list[list[str]] = []
        stopped_services: set[str] = set()
        dependents_map: dict[str, set[str]] = {
            service.name: set() for service in self.services
        }

        # Create a map of each service to its dependents
        for service in self.services:
            for dep in service.depends_on:
                dependents_map[dep].add(service.name)

        def add_service(service: Service):
            if service.name in stopped_services:
                return

            # Collect all services that depend on the current service
            dependents = dependents_map.get(service.name, set())
            for dependent in dependents:
                dep_service = self.get_service(dependent)
                if dep_service.name not in stopped_services:
                    add_service(dep_service)

            # Add the service itself if not already added
            if service.name not in stopped_services:
                if dependents:
                    order.append([service.name])
                else:
                    if order and not dependents:
                        order[-1].append(service.name)
                    else:
                        order.append([service.name])
                stopped_services.add(service.name)

        # Process all services
        for service in specific_services:
            add_service(service)

        return order

    def install_all_services(self):
        order = self._get_start_order()
        logger.info("Planning to install all services")
        self._log_operation_order("planned install", order)

        logger.info("Executing planned install order")
        for group in order:
            for service_name in group:
                logger.info(f"Installing service: {service_name}")
                service = self.get_service(service_name)
                service.installer.install()

    def install_specific_services(self, service_names: list[str]):
        logger.info("Planning to install specific services")
        specific_services = [self.get_service(name) for name in service_names]
        specific_services_order = self._get_start_order_for_specific(specific_services)
        self._log_operation_order("planned specific install", specific_services_order)

        logger.info("Executing planned specific install order")
        for group in specific_services_order:
            for service_name in group:
                logger.info(f"Installing service: {service_name}")
                service = self.get_service(service_name)
                service.installer.install()

    def start_all_services(self):
        order = self._get_start_order()
        logger.info("Planning to start all services")
        self._log_operation_order("planned start", order)

        logger.info("Executing planned start order")
        for group in order:
            for service_name in group:
                logger.info(f"Starting service: {service_name}")
                self.get_service(service_name).start_service()

    def start_specific_services(self, service_names: list[str]):
        logger.info("Planning to start specific services")
        specific_services = [self.get_service(name) for name in service_names]
        specific_services_order = self._get_start_order_for_specific(specific_services)
        self._log_operation_order("planned specific start", specific_services_order)

        logger.info("Executing planned specific start order")
        for group in specific_services_order:
            for service_name in group:
                logger.info(f"Starting service: {service_name}")
                self.get_service(service_name).start_service()

    def stop_all_services(self):
        order = self._get_stop_order()
        logger.info("Planning to stop all services")
        self._log_operation_order("planned stop", order)

        logger.info("Executing planned start order")
        for group in order:
            for service_name in group:
                logger.info(f"Stopping service: {service_name}")
                self.get_service(service_name).stop_service()

    def stop_specific_services(self, service_names: list[str]):
        logger.info("Planning to stop specific services")
        specific_services = [self.get_service(name) for name in service_names]
        specific_services_order = self._get_stop_order_for_specific(specific_services)
        self._log_operation_order("planned specific stop", specific_services_order)

        logger.info("Executing planned specific stop order")
        for group in specific_services_order:
            for service_name in group:
                logger.info(f"Stopping service: {service_name}")
                self.get_service(service_name).stop_service()

    def uninstall_all_services(self):
        order = self._get_stop_order()
        logger.info("Planning to uninstall all services")
        self._log_operation_order("planned uninstall", order)

        logger.info("Executing planned uninstall order")
        for group in order:
            for service_name in group:
                logger.info(f"Uninstalling service: {service_name}")
                service = self.get_service(service_name)
                service.uninstall()

    def uninstall_specific_services(self, service_names: list[str]):
        logger.info("Planning to uninstall specific services")
        specific_services = [self.get_service(name) for name in service_names]
        specific_services_order = self._get_stop_order_for_specific(specific_services)
        self._log_operation_order("planned specific uninstall", specific_services_order)

        logger.info("Executing planned specific uninstall order")
        for group in specific_services_order:
            for service_name in group:
                logger.info(f"Uninstalling service: {service_name}")
                service = self.get_service(service_name)
                service.uninstall()

    def install_specific_services_no_deps(self, service_names: list[str]):
        logger.info("Planning to install specific services without dependencies")
        for service_name in service_names:
            logger.info(f"Installing service: {service_name}")
            service = self.get_service(service_name)
            service.install()

    def start_specific_services_no_deps(self, service_names: list[str]):
        logger.info("Planning to start specific services without dependencies")
        for service_name in service_names:
            logger.info(f"Starting service: {service_name}")
            self.get_service(service_name).start_service()

    def stop_specific_services_no_deps(self, service_names: list[str]):
        logger.info("Planning to stop specific services without dependencies")
        for service_name in service_names:
            logger.info(f"Stopping service: {service_name}")
            self.get_service(service_name).stop_service()

    def uninstall_specific_services_no_deps(self, service_names: list[str]):
        logger.info("Planning to uninstall specific services without dependencies")
        for service_name in service_names:
            logger.info(f"Uninstalling service: {service_name}")
            service = self.get_service(service_name)
            service.uninstall()
