"""Build-time Python runtime staging; public skills are downloaded at installation."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid


def redirected(path: Path) -> bool:
    try:
        # lstat also detects Windows junctions on Python 3.11 (before is_junction).
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False


def checked_output(path: Path, dist: Path) -> Path:
    """Only the fixed runtime or this invocation's sibling staging/backup may move/delete."""
    if (path.parent.resolve() != dist or
            not (path.name == "skills-python" or path.name.startswith(".skills-python-new-")
                 or path.name.startswith(".skills-python-old-"))):
        raise RuntimeError("Runtime output is outside the build directory")
    if redirected(path) or path.resolve().parent != dist:
        raise RuntimeError("Refusing redirected runtime output")
    if path.exists():
        if not path.is_dir():
            raise RuntimeError("Runtime output must be a directory")
        # Do not move/delete a tree containing junctions or symbolic links.
        for parent, directories, files in os.walk(path, followlinks=False):
            for name in directories + files:
                item = Path(parent) / name
                if redirected(item):
                    raise RuntimeError("Refusing links inside runtime output")
    return path


def cleanup(path: Path, dist: Path):
    if path.exists():
        shutil.rmtree(checked_output(path, dist))


def prepare(source: Path, target: Path):
    for pattern in ("python.exe", "pythonw.exe", "python*.dll", "vcruntime*.dll", "LICENSE*"):
        for item in source.glob(pattern):
            if item.is_file():
                shutil.copy2(item, target / item.name)
    shutil.copytree(source / "DLLs", target / "DLLs", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(source / "Lib", target / "Lib", ignore=shutil.ignore_patterns(
        "site-packages", "__pycache__", "sitecustomize.py", "usercustomize.py", "*.pth"))
    subprocess.run([sys.executable, "-m", "pip", "--isolated", "install", "--disable-pip-version-check",
                    "--only-binary=:all:", "--target", str(target / "Lib/site-packages"),
                    "pip", "packaging"], check=True)
    if not (target / "python.exe").is_file() or not (target / "Lib/site-packages/pip/__main__.py").is_file():
        raise RuntimeError("Prepared Python runtime is incomplete")


def main():
    if os.name != "nt" or sys.version_info < (3, 11):
        raise RuntimeError("Windows Python 3.11+ required")
    source = Path(sys.base_prefix).resolve()
    workspace = Path(__file__).resolve().parent.parent
    dist = workspace / "dist"
    if redirected(dist) or dist.resolve().parent != workspace:
        raise RuntimeError("Refusing redirected build directory")
    dist.mkdir(exist_ok=True)
    dist = dist.resolve()
    target = checked_output(dist / "skills-python", dist)
    if source == target or source.is_relative_to(target):
        raise RuntimeError("Use the build Python, not the runtime being replaced")
    staging = Path(tempfile.mkdtemp(prefix=".skills-python-new-", dir=dist))
    backup = dist / (".skills-python-old-" + uuid.uuid4().hex)
    backed_up = False
    published = False
    try:
        prepare(source, staging)
        # Preparation failure never removes the previous usable/partial runtime.
        checked_output(staging, dist)
        checked_output(target, dist)
        checked_output(backup, dist)
        if target.exists():
            target.rename(backup)
            backed_up = True
        try:
            staging.rename(target)
            published = True
        except BaseException:
            if backed_up and not target.exists():
                checked_output(backup, dist).rename(target)
                backed_up = False
            raise
    finally:
        if not published:
            try:
                cleanup(staging, dist)
            except (OSError, RuntimeError):
                print("Warning: temporary runtime retained; no existing runtime was deleted.", file=sys.stderr)
        if published and backed_up:
            try:
                cleanup(backup, dist)
            except (OSError, RuntimeError):
                # A locked old file must not turn a completed publication into build failure.
                print("Warning: previous runtime backup retained in dist.", file=sys.stderr)
    print("Python skill runtime prepared and replaced; no public skill source included.")


if __name__ == "__main__":
    main()
