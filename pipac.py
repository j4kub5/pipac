#!/usr/bin/env python3
"""pipac - Prune and Install PACkages

Maintain Arch linux system packages based on package lists
(declarative package management).

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or (at
your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""

import subprocess
import sys
import os
import argparse
import re
import configparser
from typing import List, Set, Tuple


def get_config_dir() -> str:
    """Get config directory."""
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(config_home, "pipac")


def load_config() -> configparser.ConfigParser:
    """Load config file."""
    config = configparser.ConfigParser()
    config_file = os.path.join(get_config_dir(), "pipac.ini")
    if os.path.exists(config_file):
        config.read(config_file)
    return config


def get_lists(config: configparser.ConfigParser = None) -> List[str]:
    """Returns a list of strings pointing to package lists."""
    default_lists = []

    use_defaults = (
        config.getboolean("default", "use_default_lists", fallback=True)
        if config
        else True
    )

    if use_defaults:
        config_dir = get_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        base_names = ["packages", os.uname().nodename]
        extensions = [".txt", ".org", ".md"]
        for name in base_names:
            for ext in extensions:
                path = os.path.join(config_dir, f"{name}{ext}")
                if os.path.exists(path):
                    default_lists.append(path)

    if config and config.has_section("lists"):
        default_lists.extend(
            os.path.expanduser(config.get("lists", option).strip())
            for option in config.options("lists")
            if config.get("lists", option).strip()
        )

    return default_lists


def create_parser(config: configparser.ConfigParser) -> argparse.ArgumentParser:
    """Create and return the argument parser with documentation.

    This function sets up the command-line interface for managing
    package lists. The parser includes options to install packages
    that are not currently installed or prune packages that are not in
    the list, and specify one or more package list files as arguments.
    """

    parser = argparse.ArgumentParser(
        description="Maintain system with package lists.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="More usage info: https://github.com/j4kub5/pipac",
    )

    parser.add_argument(
        "-p",
        "--prune",
        action="store_true",
        help="prune packages not in lists (mark them as dependencies)",
    )

    parser.add_argument("-o", "--orphans", action="store_true", help="remove orphans")

    parser.add_argument(
        "-i",
        "--install",
        action="store_true",
        help="install packages from lists that are not currently installed",
    )

    parser.add_argument(
        "-n",
        "--new",
        action="store_true",
        help="print installed explicit packages missing from the lists",
    )

    parser.add_argument(
        "package_lists",
        nargs="*",
        metavar="package_list",
        default=get_lists(config),
        help="one or more package list files",
    )

    return parser


def get_package_manager(config: configparser.ConfigParser = None) -> str:
    """Return the preferred package manager if available,
    otherwise, the order of preference is: yay > paru > pacman.
    If no supported package manager is found, raise a SystemError."""

    # Check config first
    if config and config.has_option("default", "package_manager"):
        pm = config.get("default", "package_manager").strip()
        if pm:
            result = subprocess.run(["which", pm], capture_output=True)
            if result.returncode == 0:
                return "sudo pacman" if pm == "pacman" else pm
            print(
                f"Warning: Configured package manager '{pm}' not found, falling back to auto-detection",
                file=sys.stderr,
            )

    # Auto-detection
    for pm in ["yay", "paru", "pacman"]:
        result = subprocess.run(["which", pm], capture_output=True)
        if result.returncode == 0:
            return "sudo pacman" if pm == "pacman" else pm

    raise SystemError("No supported package manager found.")


def get_installed_packages(pm: str) -> Tuple[Set[str], Set[str]]:
    """Return sets of explicitly installed packages and optional dependencies."""
    # Get explicitly installed packages
    cmd = f"{pm} -Qe"
    result = subprocess.run(cmd.split(), capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to get explicitly installed \
        packages: {result.stderr}"
        )

    explicit = {line.split()[0] for line in result.stdout.splitlines()}

    # Get packages installed as dependencies
    cmd = f"{pm} -Qd"
    result = subprocess.run(cmd.split(), capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Failed to get optional packages: {result.stderr}")

    optional = {line.split()[0] for line in result.stdout.splitlines()}

    return explicit, optional


def parse_package_lists(filenames: List[str]) -> Tuple[Set[str], Set[str]]:
    """Parse package lists and return sets of regular and optional packages."""
    regular_packages = set()
    optional_packages = set()

    for filename in filenames:
        try:
            with open(filename, "r") as f:
                for line in f:
                    # Remove comments and strip whitespace
                    line = re.split(r"[#*;]", line)[0].strip()
                    if not line:
                        continue

                    # Split line into packages
                    packages = line.split()
                    for pkg in packages:
                        if pkg.startswith("&"):
                            optional_packages.add(pkg[1:])  # Remove & prefix
                        else:
                            regular_packages.add(pkg)

        except FileNotFoundError:
            print(
                f"Error: Package list '{filename}' \
            not found",
                file=sys.stderr,
            )
            sys.exit(1)

    return regular_packages, optional_packages


def install_packages(pm: str, packages: Set[str], as_deps: bool = False) -> None:
    """Install packages using the specified package manager."""
    if not packages:
        return

    cmd = pm.split()
    cmd.extend(["-S", "--needed", "--sysupgrade", "--refresh"])

    if as_deps:
        cmd.extend(["--asdeps"])

    cmd.extend(packages)

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error installing packages: {e}", file=sys.stderr)
        sys.exit(1)


def confirm_operation(cmd: list, packages: Set[str], operation: str) -> bool:
    """Ask for operation confirmation."""
    print(f"About to execute: {' '.join(cmd)}")
    confirm = input("Proceed? (y/N): ").strip().lower()
    return confirm in ["y", "yes"]


def remove_orphans(pm: str) -> None:
    """Remove orphaned packages."""

    if "yay" in pm:
        subprocess.run(["yay", "-Yc"], check=False)
    elif "paru" in pm:
        subprocess.run(["paru", "-c"], check=False)
    else:
        while True:
            orphans_result = subprocess.run(
                ["pacman", "-Qdtq"], capture_output=True, text=True
            )
            if not orphans_result.stdout.strip():
                print("No orphans found.")
                break

            orphans = orphans_result.stdout.strip().split("\n")
            print(f"Found {len(orphans)} orphaned packages: {', '.join(orphans)}")

            if input("Remove? (y/N): ").lower() != "y":
                break

            try:
                cmd = pm.split() + ["-Rns"] + orphans
                subprocess.run(cmd, check=True)
                print(f"Removed {len(orphans)} packages.")
            except subprocess.CalledProcessError:
                print("Error removing packages.")
                break


def mark_as_deps(pm: str, packages: Set[str]) -> None:
    """Mark packages as dependencies."""
    if not packages:
        return

    cmd = pm.split()
    cmd.extend(["-D", "--asdeps"])
    cmd.extend(packages)

    if not confirm_operation(cmd, packages, "dependencies"):
        print("Operation cancelled.")
        return

    try:
        subprocess.run(cmd, check=True)
        print("Packages successfully marked as dependencies.")
    except subprocess.CalledProcessError as e:
        print(f"Error marking packages as dependencies: {e}", file=sys.stderr)
        sys.exit(1)


def mark_as_explicit(pm: str, packages: Set[str]) -> None:
    """Mark packages as explicit."""
    if not packages:
        return

    cmd = pm.split()
    cmd.extend(["-D", "--asexplicit"])
    cmd.extend(packages)

    if not confirm_operation(cmd, packages, "explicit"):
        print("Operation cancelled.")
        return

    try:
        subprocess.run(cmd, check=True)
        print("Packages successfully marked as explicit.")
    except subprocess.CalledProcessError as e:
        print(f"Error marking packages as explicit: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    # Parse command line arguments
    config = load_config()
    parser = create_parser(config)
    args = parser.parse_args()

    # If no action specified, show help and exit
    if not (args.install or args.prune or args.new or args.orphans):
        parser.print_help()
        sys.exit(0)

    # Get package manager
    try:
        pm = get_package_manager(config)
    except SystemError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse package lists
    desired_packages, desired_optional = parse_package_lists(args.package_lists)

    # Get currently installed packages
    installed_explicit, installed_optional = get_installed_packages(pm)
    bad_install_reason = desired_packages.intersection(installed_optional)

    if args.new:
        new_packages = installed_explicit - desired_packages
        print(*new_packages, sep="\n")
        sys.exit(1)

    # Prune packages not in lists
    if args.prune:
        if bad_install_reason:
            print(
                f"Fixing install reason to explicit: \
            {', '.join(sorted(bad_install_reason))}"
            )
            mark_as_explicit(pm, bad_install_reason)

        to_prune = installed_explicit - desired_packages
        if to_prune:
            print(f"Marking as dependencies: {', '.join(sorted(to_prune))}")
            mark_as_deps(pm, to_prune)

    if args.orphans:
        remove_orphans(pm)

    # Install missing packages
    if args.install:
        missing_regular = desired_packages - installed_explicit
        missing_optional = desired_optional - installed_optional

        if bad_install_reason:
            print(
                f"Fixing install reason to explicit: \
            {', '.join(sorted(bad_install_reason))}"
            )
            mark_as_explicit(pm, bad_install_reason)
            missing_regular = missing_regular - bad_install_reason

        if missing_regular:
            print(f"Installing packages: {', '.join(sorted(missing_regular))}")
            install_packages(pm, missing_regular)

        if missing_optional:
            print(
                f"Installing optional dependencies: \
            {', '.join(sorted(missing_optional))}"
            )
            install_packages(pm, missing_optional, as_deps=True)


if __name__ == "__main__":
    main()
