from automata import *

yaml_file_path = "services.yaml"
services = Service.create_services(yaml_file_path)
for service in services:
    # service.start_service()
    # service.stop_service()
    service.uninstall_service()
    # print(service.is_service_open())
