"""Create a separate mapinfo12pro application directory from a local MapInfo installation."""

import argparse
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from patch_core import patch


def build(source, destination):
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if destination == source or source in destination.parents:
        raise ValueError("Choose a destination outside the original MapInfo directory.")
    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}")
    for filename in ("MapInfow.exe", "mires.dll", "micore.dll"):
        if not (source / filename).is_file():
            raise FileNotFoundError(f"Missing MapInfo component: {source / filename}")
    core = patch((source / "micore.dll").read_bytes())
    destination.parent.mkdir(parents=True, exist_ok=True)

    def exclude_replaced_cache(folder, names):
        if Path(folder) != source:
            return set()
        return {name for name in names if name.casefold() in {"micore.dll", "micore.dll.bak", "mapinfo12pro.exe"}}

    with TemporaryDirectory(prefix=".mapinfo12pro-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "application"
        shutil.copytree(source, staged, symlinks=True, ignore=exclude_replaced_cache)
        (staged / "micore.dll").write_bytes(core)
        # The core checks the resource version against MapInfow.exe at startup.
        shutil.copy2(staged / "MapInfow.exe", staged / "mapinfo12pro.exe")
        if destination.exists():
            raise FileExistsError(f"Destination already exists: {destination}")
        staged.rename(destination)
    return destination / "mapinfo12pro.exe"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="directory of the installed MapInfo Professional 12.0.2 Build 208")
    parser.add_argument("destination", type=Path, help="new directory for the mapinfo12pro application")
    arguments = parser.parse_args()
    try:
        print(build(arguments.source, arguments.destination))
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
