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
from typing import List, Set, Tuple

def get_default_lists() -> List[str]:
    """Returns a list of strings pointing to default
    lists in config directory for .txt, .org, and .md files."""

    config_dir = os.path.expanduser('~/.config/pipac')
    os.makedirs(config_dir, exist_ok=True) # Ensure config directory exists

    default_lists = []
    base_names = ['packages', os.uname().nodename]
    extensions = ['.txt', '.org', '.md']

    for name in base_names:
        for ext in extensions:
            path = os.path.join(config_dir, f'{name}{ext}')
            if os.path.exists(path):
                default_lists.append(path)

    return default_lists


def create_parser() -> argparse.ArgumentParser:
    """Create and return the argument parser with documentation.

    This function sets up the command-line interface for managing
    package lists. The parser includes options to install packages
    that are not currently installed or prune packages that are not in
    the list, and specify one or more package list files as arguments.
    """
    parser = argparse.ArgumentParser(
        description='Maintain system with package lists.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="More usage info: https://github.com/j4kub5/pipac")

    parser.add_argument(
        '-i', '--install',
        action='store_true',
        help='install packages from lists that are not currently installed'
    )

    parser.add_argument(
        '-p', '--prune',
        action='store_true',
        help='prune packages not in lists (mark as dependencies)'
    )

    parser.add_argument(
        '-n', '--new',
        action='store_true',
        help='print installed explicit packages missing from the lists'
    )

    parser.add_argument(
        'package_lists',
        nargs='*',
        metavar='package_list',
        default=get_default_lists(),
        help='one or more package list files'
    )

    return parser

def get_package_manager() -> str:
    """Return the available package manager.
    The order of preference is: yay > paru > pacman.
    If no supported package manager is found, raise a SystemError."""
    for pm in ['yay', 'paru', 'pacman']:
        try:
            subprocess.run(['which', pm], capture_output=True, check=True)
            if pm == 'pacman':
                return 'sudo pacman'
            return pm
        except subprocess.CalledProcessError:
            continue
    raise SystemError("No supported package manager found")

def get_installed_packages(pm: str) -> Tuple[Set[str], Set[str]]:
    """Return sets of explicitly installed packages and optional dependencies."""
    # Get explicitly installed packages
    cmd = f"{pm} -Qe"
    result = subprocess.run(cmd.split(), capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Failed to get explicitly installed \
        packages: {result.stderr}")

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
            with open(filename, 'r') as f:
                for line in f:
                    # Remove comments and strip whitespace
                    line = re.split(r'[#*;]', line)[0].strip()
                    if not line:
                        continue

                    # Split line into packages
                    packages = line.split()
                    for pkg in packages:
                        if pkg.startswith('&'):
                            optional_packages.add(pkg[1:])  # Remove & prefix
                        else:
                            regular_packages.add(pkg)

        except FileNotFoundError:
            print(f"Error: Package list '{filename}' \
            not found", file=sys.stderr)
            sys.exit(1)

    return regular_packages, optional_packages

def install_packages(pm: str, packages: Set[str],
                     as_deps: bool = False) -> None:
    """Install packages using the specified package manager."""
    if not packages:
        return

    cmd = pm.split()
    cmd.extend(['-S', '--needed', '--sysupgrade', '--refresh'])

    if as_deps:
        cmd.extend(['--asdeps'])

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
    return confirm in ['y', 'yes']


def mark_as_deps(pm: str, packages: Set[str]) -> None:
    """Mark packages as dependencies."""
    if not packages:
        return

    cmd = pm.split()
    cmd.extend(['-D', '--asdeps'])
    cmd.extend(packages)

    if not confirm_operation(cmd, packages, "dependencies"):
        print("Operation cancelled.")
        return

    try:
        subprocess.run(cmd, check=True)
        print("Packages successfully marked as dependencies. Remove orphans manually.")
    except subprocess.CalledProcessError as e:
        print(f"Error marking packages as dependencies: {e}", file=sys.stderr)
        sys.exit(1)


def mark_as_explicit(pm: str, packages: Set[str]) -> None:
    """Mark packages as explicit."""
    if not packages:
        return

    cmd = pm.split()
    cmd.extend(['-D', '--asexplicit'])
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
    parser = create_parser()
    args = parser.parse_args()

    # If no action specified, show help and exit
    if not (args.install or args.prune or args.new):
        parser.print_help()
        sys.exit(0)

    # Get package manager
    try:
        pm = get_package_manager()
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
        print(*new_packages, sep='\n')
        sys.exit(1)

    # Install missing packages
    if args.install:
        missing_regular = desired_packages - installed_explicit
        missing_optional = desired_optional - installed_optional

        if bad_install_reason:
            print(f"Fixing install reason to explicit: \
            {', '.join(sorted(bad_install_reason))}")
            mark_as_explicit(pm, bad_install_reason)
            missing_regular = missing_regular - bad_install_reason

        if missing_regular:
            print(f"Installing packages: {', '.join(sorted(missing_regular))}")
            install_packages(pm, missing_regular)

        if missing_optional:
            print(f"Installing optional dependencies: \
            {', '.join(sorted(missing_optional))}")
            install_packages(pm, missing_optional, as_deps=True)

    # Prune packages not in lists
    if args.prune:
        if bad_install_reason:
            print(f"Fixing install reason to explicit: \
            {', '.join(sorted(bad_install_reason))}")
            mark_as_explicit(pm, bad_install_reason)

        to_prune = installed_explicit - desired_packages
        if to_prune:
            print(f"Marking as dependencies: {', '.join(sorted(to_prune))}")
            mark_as_deps(pm, to_prune)

if __name__ == '__main__':
    main()
