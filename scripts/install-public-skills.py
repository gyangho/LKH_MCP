"""Install official GitHub latest stable source at a resolved commit; keep previous active set on failure."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

REPOSITORIES = {"uiux": "nextlevelbuilder/ui-ux-pro-max-skill", "graphify": "Graphify-Labs/graphify"}
LIMIT = 512 * 1024 * 1024
CURRENT_COMPONENT = "setup"
CURRENT_STEP = "initialization"


class InstallFailure(ValueError):
    """A fixed, safe diagnostic code without response bodies or environment data."""

    def __init__(self, code, archive_entry=None):
        self.code = code
        self.archive_entry = archive_entry
        super().__init__(code)


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "LKH-MCP-Installer", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as reply:
        raw = reply.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise InstallFailure("GITHUB_METADATA_TOO_LARGE")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        raise InstallFailure("GITHUB_INVALID_JSON") from None
    if not isinstance(data, dict):
        raise InstallFailure("GITHUB_INVALID_METADATA")
    return data


def release_commit(repository, tag):
    """Resolve lightweight/annotated tags without fetching a commit's file diffs."""
    global CURRENT_STEP
    CURRENT_STEP = "resolve-release-tag"
    reference = get_json("https://api.github.com/repos/" + repository +
                         "/git/ref/tags/" + urllib.parse.quote(tag, safe=""))
    obj = reference.get("object")
    # Annotated tags can point to other annotated tags. Bound the traversal.
    for _ in range(8):
        if not isinstance(obj, dict):
            raise InstallFailure("GITHUB_INVALID_TAG_OBJECT")
        sha = obj.get("sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise InstallFailure("GITHUB_INVALID_TAG_SHA")
        if obj.get("type") == "commit":
            return sha
        if obj.get("type") != "tag":
            raise InstallFailure("GITHUB_UNSUPPORTED_TAG_TARGET")
        CURRENT_STEP = "resolve-annotated-tag"
        annotated = get_json("https://api.github.com/repos/" + repository + "/git/tags/" + sha)
        obj = annotated.get("object")
    raise InstallFailure("GITHUB_TAG_DEPTH_EXCEEDED")


def restore_source_permissions(source, skills):
    """A rename preserves tempfile's private Windows ACL; inherit the install ACL instead."""
    source, skills = Path(source), Path(skills).resolve(strict=True)
    if source.parent.resolve() != skills or source.resolve(strict=True).parent != skills:
        raise ValueError("Source must be a direct child of the installed skills directory")
    # Never apply recursive ACL changes through a link/junction or to a redirected tree.
    for parent, directories, files in os.walk(source, followlinks=False):
        for item in [Path(parent), *(Path(parent) / name for name in directories + files)]:
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Redirected skill source")
    if os.name == "nt":
        subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32/icacls.exe"),
                        str(source), "/reset", "/T", "/Q"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=180, check=True)


def repair_permissions(root):
    """Repair only the two manifest-selected public trees, without downloading or restarting."""
    root = Path(root).resolve(strict=True)
    skills = root / "skills"
    if skills.is_symlink() or skills.resolve(strict=True).parent != root:
        raise ValueError("Unsafe installed skills directory")
    active = json.loads((skills / "active.json").read_text(encoding="utf-8"))
    for name in REPOSITORIES:
        entry = active[name]
        path = entry["path"]
        if not isinstance(path, str) or not re.fullmatch(name + r"-[0-9a-f]{40}-[0-9a-f]{8}", path):
            raise ValueError("Invalid installed source directory")
        restore_source_permissions(skills / path, skills)


def prepare(name, repository, skills):
    global CURRENT_COMPONENT, CURRENT_STEP
    CURRENT_COMPONENT, CURRENT_STEP = name, "latest-release"
    release = get_json("https://api.github.com/repos/" + repository + "/releases/latest")
    tag = release.get("tag_name")
    if release.get("draft") or release.get("prerelease") or not isinstance(tag, str) or not 1 <= len(tag) <= 128:
        raise InstallFailure("GITHUB_STABLE_RELEASE_REQUIRED")
    commit = release_commit(repository, tag)
    with tempfile.TemporaryDirectory(prefix=".download-", dir=skills) as temporary:
        staging = Path(temporary)
        archive = staging / "source.zip"
        digest = hashlib.sha256()
        total = 0
        url = "https://codeload.github.com/" + repository + "/zip/" + commit
        request = urllib.request.Request(url, headers={"User-Agent": "LKH-MCP-Installer"})
        CURRENT_STEP = "download"
        with urllib.request.urlopen(request, timeout=120) as reply, archive.open("xb") as output:
            while block := reply.read(1024 * 1024):
                total += len(block)
                if total > LIMIT:
                    raise InstallFailure("DOWNLOAD_SIZE_LIMIT")
                digest.update(block)
                output.write(block)
        source = staging / "source"
        source.mkdir()
        extracted = 0
        CURRENT_STEP = "archive-files"
        with zipfile.ZipFile(archive) as zipped:
            if len(zipped.infolist()) > 100000:
                raise InstallFailure("ARCHIVE_ENTRY_LIMIT")
            for item in zipped.infolist():
                parts = PurePosixPath(item.filename).parts
                if len(parts) < 2:
                    continue
                relative = PurePosixPath(*parts[1:])
                keep = ((name == "graphify" and relative.parts[0] == "graphify")
                        or (name == "uiux" and relative.parts[:2] == ("src", "ui-ux-pro-max"))
                        or (len(relative.parts) == 1 and (relative.name in ("pyproject.toml", "NOTICE", "README.md")
                            or relative.name.startswith("LICENSE"))))
                # Unselected gallery/docs/tooling are never extracted. Their symlinks
                # must not block installation of the independent selected source tree.
                if not keep:
                    continue
                if (relative.is_absolute() or ".." in relative.parts or "\\" in str(relative)
                        or ":" in str(relative) or stat.S_ISLNK(item.external_attr >> 16)):
                    raise InstallFailure("ARCHIVE_SELECTED_ENTRY_UNSAFE", str(relative))
                if item.is_dir():
                    continue
                extracted += item.file_size
                if extracted > LIMIT or item.file_size > 64 * 1024 * 1024:
                    raise InstallFailure("ARCHIVE_EXTRACTED_SIZE_LIMIT", str(relative))
                destination = source.joinpath(*relative.parts)
                if not destination.resolve().is_relative_to(source.resolve()):
                    raise InstallFailure("ARCHIVE_DESTINATION_OUTSIDE_SOURCE", str(relative))
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(item) as incoming, destination.open("xb") as output:
                    shutil.copyfileobj(incoming, output)
        required = source / ("graphify/__main__.py" if name == "graphify" else "src/ui-ux-pro-max/scripts/search.py")
        CURRENT_STEP = "validate-source"
        if not required.is_file():
            raise InstallFailure("REQUIRED_SOURCE_MISSING")
        CURRENT_STEP = "validate-license"
        if not any(item.is_file() for item in source.glob("LICENSE*")):
            raise InstallFailure("LICENSE_MISSING")
        if name == "graphify":
            import tomllib
            from packaging.requirements import Requirement
            from packaging.version import Version
            project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
            version = Version(project["version"])
            CURRENT_STEP = "compatible-version"
            if not Version("0.9.30") <= version < Version("0.10"):
                raise InstallFailure("GRAPHIFY_VERSION_UNSUPPORTED")
            dependencies = project.get("dependencies", [])
            if not isinstance(dependencies, list) or len(dependencies) > 80:
                raise ValueError("Invalid Graphify dependencies")
            requirements = []
            for dependency in dependencies:
                parsed = Requirement(dependency)
                if parsed.url:
                    raise ValueError("Direct dependency URLs are not allowed")
                if parsed.marker is None or parsed.marker.evaluate({"extra": ""}):
                    requirements.append(str(parsed))
            # All-binary wheel installation into a private version directory; no machine/global pip state.
            if requirements:
                CURRENT_STEP = "dependency-wheels"
                subprocess.run([sys.executable, "-I", "-m", "pip", "--isolated", "install",
                    "--no-input", "--disable-pip-version-check", "--index-url", "https://pypi.org/simple",
                    "--only-binary=:all:", "--target", str(source / "deps"), *requirements],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900, check=True)
            distribution = source / ("graphifyy-" + str(version) + ".dist-info")
            distribution.mkdir()
            (distribution / "METADATA").write_text("Metadata-Version: 2.1\nName: graphifyy\nVersion: " + str(version) + "\n", encoding="utf-8")
        else:
            version = tag
        # The SHA is a download receipt, not an upstream signature. HTTPS + resolved commit identify source.
        metadata = {"repository": repository, "version": str(version), "release": tag,
                    "commit": commit, "sha256": digest.hexdigest()}
        (source / "lkh-source.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        destination = skills / (name + "-" + commit + "-" + uuid.uuid4().hex[:8])
        source.rename(destination)
        CURRENT_STEP = "source-permissions"
        restore_source_permissions(destination, skills)
        return {**metadata, "path": destination.name}


def main():
    if os.name != "nt":
        raise RuntimeError("Windows installer required")
    if len(sys.argv) == 3 and sys.argv[1] == "--repair-permissions":
        repair_permissions(sys.argv[2])
        print("Installed public source permissions repaired.")
        return
    if len(sys.argv) != 1:
        raise ValueError("Invalid installer arguments")
    root = Path(__file__).resolve().parent.parent
    skills = root / "skills"
    if skills.is_symlink() or (skills.exists() and skills.resolve().parent != root):
        raise ValueError("Unsafe installed skills directory")
    skills.mkdir(exist_ok=True)
    active = {name: prepare(name, repository, skills) for name, repository in REPOSITORIES.items()}
    # Publication happens only after both components have downloaded and their files/dependencies were checked.
    manifest = skills / "active.json"
    if manifest.is_symlink():
        raise ValueError("Unsafe skill manifest")
    temporary = skills / ("active-" + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(active, indent=2), encoding="utf-8")
    os.replace(temporary, manifest)
    (skills / "install-status.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    print("Latest stable public skills installed at fixed commits.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        status = {"ok": False, "component": CURRENT_COMPONENT, "step": CURRENT_STEP,
                  "reason": type(exc).__name__}
        if isinstance(exc, InstallFailure):
            status["code"] = exc.code
            if exc.archive_entry is not None:
                # This is a public upstream ZIP path, not a local/user filesystem path.
                status["archive_entry"] = "".join(
                    char for char in exc.archive_entry if char.isprintable())[:256]
        if isinstance(exc, urllib.error.HTTPError):
            status["http_status"] = exc.code
        try:
            root = Path(__file__).resolve().parent.parent
            target = root / "skills/install-status.json"
            if target.parent.is_dir() and not target.is_symlink():
                target.write_text(json.dumps(status, indent=2), encoding="utf-8")
        except OSError:
            pass
        # Installer must fail and preserve the last active manifest; no raw URLs/host environment in logs.
        print("Public skill installation failed. Check network, release compatibility and wheel availability; retry installation.", file=sys.stderr)
        raise SystemExit(1)
