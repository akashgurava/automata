"""
Module for installing a service.

This module works best under the assumption that services are installed at `install_path`
and the executables are symlinked to a common `bin_path` for all services.
"""

import os
import shutil
import subprocess
import urllib.request
import tarfile
import zipfile
from typing import Optional

from dmglib import (  # type: ignore
    DiskImage,
    dmg_detach_already_attached,
    InvalidOperation,
)
from loguru import logger

from automata.utils import ensure_dir_exists, log_subprocess_output, log_filename


def expandvars_recursive(path: str) -> str:
    while "$" in path:
        expanded_path: str = os.path.expandvars(path)
        if expanded_path == path:
            break
        path = expanded_path
    return path


def run_command_with_logs(service_name: str, command_type: str, command: str):
    """Run a command and write logs."""
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # To load env from .env file
        env=os.environ,
    )
    log_subprocess_output(process.stdout)  # type: ignore
    log_subprocess_output(process.stderr)  # type: ignore

    if process.wait() != 0:
        raise ValueError(
            f"Service: {service_name}. Command Type: {command_type}. Command: {command}. Log: {log_filename}. Failed check logs."
        )


def extract_dmg(service_name: str, src: str, extract_to: str):
    try:
        dmg_detach_already_attached(src, force=True)
    except InvalidOperation:
        pass

    dmg = DiskImage(src)
    try:
        points: list[str] = dmg.attach(f"/Volumes/{service_name}")  # type: ignore
        dmg_contents = os.listdir(points[0])
        content: str | None = None
        for content in dmg_contents:
            if content.endswith(".app"):
                break

        if content:
            shutil.copytree(
                f"/Volumes/{service_name}/{content}",
                f"{extract_to}/{content}",
                dirs_exist_ok=True,
            )
    finally:
        dmg.detach()


class Installer:
    """
    Install a service.

    The installer checks if a service is installed by checking if "`bin_path`/each_executable" exists.
    If it is a symlink, check if the symlink is valid and points to "`install_path`/executable_src_rel_path.
    """

    def __init__(
        self,
        service_name: str,
        install_path: str,
        bin_path: str,
        executables: dict[str, str],
        post_install_cmd: Optional[str] = None,
    ) -> None:
        self._service_name = service_name
        self._install_path = expandvars_recursive(install_path)
        self._bin_path = expandvars_recursive(bin_path)
        self._executables = executables
        self._post_install_cmd = post_install_cmd

        self._is_changed = False

    def __repr__(self):
        return (
            f"Installer(service_name={self._service_name}, "
            f"install_path={self._install_path}, bin_path={self._bin_path}, "
            f"executables={self._executables})"
        )

    @property
    def service_name(self) -> str:
        """Name of the service."""
        return self._service_name

    @property
    def install_path(self) -> str:
        """Path where the service is installed."""
        return self._install_path

    @property
    def bin_path(self) -> str:
        """Path at which the installed executables should be available."""
        return self._bin_path

    @property
    def executables(self) -> dict[str, str]:
        """
        A mapping of executable name to relative path of install_path.
        For example:
        {
            "postgresql": "bin/postgresql",
            "pg_ctl": "bin/pg_ctl",
        }
        """
        return self._executables

    @property
    def is_changed(self) -> bool:
        """Status flag for if the installer made any changes."""
        return self._is_changed

    @property
    def invalid_executables(self) -> list[str]:
        """
        Get list of invalid executables.

        Invalid executables are ones which "`bin_path`/each_executable" does not exist.
        If it is a symlink, check if the symlink is not valid.
        """
        invalid_executables: list[str] = []
        for executable, executable_src_rel_path in self.executables.items():
            executable_path = os.path.join(self.bin_path, executable)
            executable_src_path = os.path.join(
                self.install_path, executable_src_rel_path
            )
            if os.path.islink(executable_path):
                logger.debug(
                    f"Service: {self.service_name}. Executable: {executable}. Symlink."
                )
                link_path = os.readlink(executable_path)
                if not os.path.exists(link_path):
                    logger.debug(
                        f"Service: {self.service_name}. Executable: {executable}. Symlink is invalid."
                    )
                    invalid_executables.append(executable)
                elif link_path != executable_src_path:
                    logger.debug(
                        f"Service: {self.service_name}. Executable: {executable}. Symlink is not pointing to expected location."
                    )
                    invalid_executables.append(executable)
                else:
                    logger.debug(
                        f"Service: {self.service_name}. Executable: {executable}. Symlink is valid."
                    )
            elif not os.path.exists(executable_path):
                logger.debug(
                    f"Service: {self.service_name}. Executable: {executable}. Path does not exist."
                )
                invalid_executables.append(executable)
        return invalid_executables

    @property
    def post_install_cmd(self) -> Optional[str]:
        return self._post_install_cmd

    @property
    def is_installed(self) -> bool:
        """
        Check if service is installed by checking if "`bin_path`/each_executable" exists.
        If it is a symlink, check if the symlink is valid or not.
        """
        invalid_executables = self.invalid_executables
        if len(invalid_executables) == 0:
            logger.debug(f"Service: {self.service_name}. Service is installed.")
            return True
        else:
            logger.debug(
                f"Service: {self.service_name}. Invalid executables: {invalid_executables}. Service is not installed."
            )
            return False

    def _create_symlinks(self):
        """Create symlinks for the executables."""
        for executable, executable_src_rel_path in self.executables.items():
            executable_src_path = os.path.join(
                self.install_path, executable_src_rel_path
            )
            symlink_path = os.path.join(self.bin_path, executable)
            if not os.path.exists(executable_src_path):
                logger.error(
                    f"Service: {self.service_name}. Executable source path does not exist: {executable_src_path}"
                )
                raise Exception(
                    f"Executable source path: {executable_src_path}. Does not exist."
                )
            if os.path.exists(symlink_path) or os.path.islink(symlink_path):
                os.remove(symlink_path)
            os.symlink(executable_src_path, symlink_path)
            logger.info(
                f"Service: {self.service_name}. Created symlink: {symlink_path} -> {executable_src_path}"
            )
            self._is_changed = True

    def install(self) -> None:
        """
        Ensures the services is installed.
        If service is already installed does nothing.
        If not installed installs the service.
        """
        raise NotImplemented("")

    def post_install(self):
        if self.post_install_cmd is None:
            logger.debug(f"Service: {self.service_name}. No post install action.")
            return
        logger.info(
            f"Service: {self.service_name}. Command: {self.post_install_cmd}. Running post install."
        )
        run_command_with_logs(self.service_name, "post_install", self.post_install_cmd)
        logger.info(
            f"Service: {self.service_name}. Command: {self.post_install_cmd}. Post install complete."
        )

    def uninstall(self) -> None:
        """Uninstall the service by removing the symlinks and the installation directory."""
        for executable in self.executables:
            symlink_path = os.path.join(self.bin_path, executable)
            if os.path.exists(symlink_path) or os.path.islink(symlink_path):
                os.remove(symlink_path)
                logger.info(
                    f"Service: {self.service_name}. Removed symlink: {symlink_path}"
                )
            else:
                logger.debug(
                    f"Service: {self.service_name}. Symlink does not exist: {symlink_path}"
                )

        if os.path.exists(self.install_path):
            shutil.rmtree(self.install_path)
            logger.info(
                f"Service: {self.service_name}. Removed install directory: {self.install_path}"
            )
        else:
            logger.debug(
                f"Service: {self.service_name}. Install directory does not exist: {self.install_path}"
            )


class BinaryInstaller(Installer):
    def __init__(
        self,
        service_name: str,
        install_path: str,
        bin_path: str,
        executables: dict[str, str],
        download_url: str,
        is_archive: bool,
        post_install_cmd: Optional[str] = None,
    ):
        super().__init__(
            service_name=service_name,
            install_path=install_path,
            bin_path=bin_path,
            executables=executables,
            post_install_cmd=post_install_cmd,
        )
        self._download_url = download_url
        self._is_archive = is_archive

    def __repr__(self):
        return (
            f"BinaryInstaller(service_name={self._service_name}, "
            f"install_path={self._install_path}, bin_path={self._bin_path}, "
            f"executables={self._executables}, download_url={self._download_url}, "
            f"is_archive={self._is_archive})"
        )

    @property
    def download_url(self) -> str:
        """URL for downloading the service."""
        return self._download_url

    @property
    def is_archive(self) -> bool:
        """Is the downloaded URL an archive like zip or tar, etc."""
        return self._is_archive

    def _download_file(self, url: str, dest_path: str):
        """Download a file from a URL to a destination path."""
        logger.info(
            f"Service: {self.service_name}. URL: {url}. Destination: {dest_path}. Downloading."
        )
        urllib.request.urlretrieve(url, dest_path)
        logger.info(
            f"Service: {self.service_name}. URL: {url}. Destination: {dest_path}. Downloaded."
        )

    def _extract_archive(self, archive_path: str, extract_to: str):
        """Extract an archive to a specified directory."""
        logger.info(
            f"Service: {self.service_name}. Archive Path: {archive_path}. Destination: {extract_to}. Extracting."
        )
        if archive_path.endswith("dmg"):
            extract_dmg(self.service_name, archive_path, extract_to=extract_to)
        elif tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r") as tar:
                tar.extractall(path=extract_to)
        elif zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(path=extract_to)
        else:
            raise ValueError("Service: {self.service_name}. Unsupported archive format")
        logger.info(
            f"Service: {self.service_name}. Archive Path: {archive_path}. Destination: {extract_to}. Extracted."
        )

    def install(self):
        """Install the service by downloading and extracting the binary, then creating symlinks."""
        if self.is_installed:
            logger.info(f"Service: {self.service_name}. Service is already installed.")
            return
        ensure_dir_exists(self.install_path)
        ensure_dir_exists(self.bin_path)

        archive_path = os.path.join(
            self.install_path, os.path.basename(self.download_url)
        )
        try:
            self._download_file(self.download_url, archive_path)
        except Exception as exp:
            logger.exception(
                f"Service: {self.service_name}. URL: {self.download_url}. Archive path: {archive_path}. Unable to download. Reason: {exp}."
            )
            raise

        try:
            if self.is_archive:
                self._extract_archive(archive_path, self.install_path)
        except Exception as exp:
            logger.exception(
                f"Service: {self.service_name}. Archive path: {archive_path}. Extract path: {self.install_path}. Unable to extract. Reason: {exp}."
            )
            raise

        try:
            self._create_symlinks()
        except Exception as exp:
            logger.exception(
                f"Service: {self.service_name}. Unable to create symlinks. Reason: {exp}."
            )
            raise

        if os.path.exists(archive_path):
            os.remove(archive_path)
            logger.info(
                f"Service: {self.service_name}. Removed archive file: {archive_path}"
            )

        self.post_install()


class BrewInstaller(Installer):
    def __init__(
        self,
        service_name: str,
        install_path: str,
        bin_path: str,
        executables: dict[str, str],
        package_name: str,
        post_install_cmd: Optional[str] = None,
    ):
        super().__init__(
            service_name=service_name,
            install_path=install_path,
            bin_path=bin_path,
            executables=executables,
            post_install_cmd=post_install_cmd,
        )
        self._package_name = package_name

    def __repr__(self):
        return (
            f"BinaryInstaller(service_name={self._service_name}, "
            f"install_path={self._install_path}, bin_path={self._bin_path}, "
            f"package_name={self._package_name})"
        )

    @property
    def package_name(self) -> str:
        """Brew package name."""
        return self._package_name

    def install(self) -> None:
        if self.is_installed:
            logger.info(f"Service: {self.service_name}. Service is already installed.")
            return
        ensure_dir_exists(self.bin_path)
        run_command_with_logs(
            self.service_name, "brew_install", f"brew install {self.package_name}"
        )
        self._create_symlinks()

        self.post_install()

    def uninstall(self) -> None:
        ensure_dir_exists("./logs")
        run_command_with_logs(
            self.service_name, "brew_remove", f"brew remove {self.package_name} || true"
        )
        return super().uninstall()


class BinInstaller(Installer):
    """
    BinInstaller copies the contents of a source directory to the install path and creates symlinks for executables.
    """

    def __init__(
        self,
        service_name: str,
        source_path: str,
        install_path: str,
        bin_path: str,
        executables: dict[str, str],
    ):
        super().__init__(service_name, install_path, bin_path, executables)
        self._source_path = os.path.expandvars(source_path)

    def __repr__(self):
        return (
            f"BinInstaller(service_name={self._service_name}, "
            f"source_path={self._source_path}, install_path={self._install_path}, "
            f"bin_path={self._bin_path}, executables={self._executables})"
        )

    def install(self):
        """
        Copies the contents of the source directory to the install path and creates symlinks for the executables.
        """
        ensure_dir_exists(self._install_path)

        # Copy contents from source_path to install_path
        for item in os.listdir(self._source_path):
            s = os.path.join(self._source_path, item)
            d = os.path.join(self._install_path, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

        self._create_symlinks()
        self.post_install()
