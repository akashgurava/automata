# main.py

import argparse
from automata.service_manager import ServiceManager
from loguru import logger


def main():
    parser = argparse.ArgumentParser(description="Service management CLI")
    parser.add_argument(
        "--install-all", action="store_true", help="Install all services"
    )
    parser.add_argument(
        "--install", type=str, help="Install specific services (comma-separated)"
    )
    parser.add_argument("--start-all", action="store_true", help="Start all services")
    parser.add_argument(
        "--start", type=str, help="Start specific services (comma-separated)"
    )
    parser.add_argument("--stop-all", action="store_true", help="Stop all services")
    parser.add_argument(
        "--stop", type=str, help="Stop specific services (comma-separated)"
    )
    parser.add_argument(
        "--uninstall-all", action="store_true", help="Uninstall all services"
    )
    parser.add_argument(
        "--uninstall", type=str, help="Uninstall specific services (comma-separated)"
    )
    parser.add_argument(
        "--yaml-file",
        type=str,
        default="services.yaml",
        help="Path to the YAML file (default: services.yaml)",
    )

    args = parser.parse_args()

    # If no args are provided (ignoring yaml-file), set start_all to True
    if not any(value for key, value in vars(args).items() if key != "yaml_file"):
        args.start_all = True
        logger.info("No arguments provided. Defaulting to start all services.")

    yaml_file_path = args.yaml_file
    service_manager = ServiceManager(yaml_file_path)

    if args.install_all:
        logger.info("Installing all services")
        service_manager.install_all_services()
    elif args.install:
        logger.info(f"Installing specific services: {args.install}")
        service_names = args.install.split(",")
        service_manager.install_specific_services(service_names)
    elif args.start_all:
        logger.info("Starting all services")
        service_manager.start_all_services()
    elif args.start:
        logger.info(f"Starting specific services: {args.start}")
        service_names = args.start.split(",")
        service_manager.start_specific_services(service_names)
    elif args.stop_all:
        logger.info("Stopping all services")
        service_manager.stop_all_services()
    elif args.stop:
        logger.info(f"Stopping specific services: {args.stop}")
        service_names = args.stop.split(",")
        service_manager.stop_specific_services(service_names)
    elif args.uninstall_all:
        logger.info("Uninstalling all services")
        service_manager.uninstall_all_services()
    elif args.uninstall:
        logger.info(f"Uninstalling specific services: {args.uninstall}")
        service_names = args.uninstall.split(",")
        service_manager.uninstall_specific_services(service_names)


if __name__ == "__main__":
    main()
