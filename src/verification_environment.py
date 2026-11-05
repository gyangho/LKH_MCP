"""Opt-in, agent-local verification assets; project commands stay sandboxed.

Profiles are loaded from the private Agent config, never from a queued task or
the repository under test. Preparation copies local assets without executing
them. Even the Gradle help preflight runs via Codex's managed workspace sandbox.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
import stat
import subprocess
import time
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


class PreparationError(RuntimeError):
    """Only fixed, non-sensitive diagnostics may leave this module."""


def _fail(code: str) -> None:
    raise PreparationError(code)


def _relative(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 240:
        _fail("VERIFICATION_INVALID_PROJECT_DIRECTORY")
    value = value.replace("\\", "/")
    p = PurePosixPath(value)
    if (p.is_absolute() or ":" in value or ntpath.splitdrive(value)[0] or
            any(x.casefold() in {"..", ".git", ".lkh-verification"} for x in p.parts)):
        _fail("VERIFICATION_INVALID_PROJECT_DIRECTORY")
    return value


def validate_profiles(profiles: object) -> None:
    if not isinstance(profiles, dict) or len(profiles) > 10:
        _fail("VERIFICATION_INVALID_PROFILES")
    for alias, profile in profiles.items():
        if (not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", alias)
                or not isinstance(profile, dict)
                or set(profile) - {"repository", "path", "gradle", "frontend"}
                or not {"repository", "path"} <= set(profile)
                or not isinstance(profile["repository"], str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", profile["repository"])
                or not ({"gradle", "frontend"} & set(profile))):
            _fail("VERIFICATION_INVALID_PROFILE")
        _absolute(profile["path"])
        for kind, fields in {
            "gradle": {"project_dir", "distribution", "dependency_cache", "java_executable"},
            "frontend": {"project_dir", "snapshot", "node_executable"},
        }.items():
            if kind not in profile:
                continue
            settings = profile[kind]
            optional = {"java_toolchain_homes"} if kind == "gradle" else set()
            if (not isinstance(settings, dict) or not fields <= set(settings)
                    or set(settings) - fields - optional):
                _fail("VERIFICATION_INVALID_PROFILE")
            _relative(settings["project_dir"])
            for key in fields - {"project_dir"}:
                _absolute(settings[key])
            if kind == "gradle":
                homes = settings.get("java_toolchain_homes", [])
                if not isinstance(homes, list) or len(homes) > 10:
                    _fail("VERIFICATION_INVALID_JAVA_TOOLCHAINS")
                for home in homes:
                    _absolute(home)
                    # Commas delimit Gradle installations; CR/LF would inject properties.
                    if "," in home or any(ord(c) < 32 for c in home):
                        _fail("VERIFICATION_INVALID_JAVA_TOOLCHAINS")


def _absolute(value: object) -> Path:
    if (not isinstance(value, str) or not value or "\x00" in value or
            value.startswith(("\\\\", "//")) or not Path(value).is_absolute()):
        _fail("VERIFICATION_LOCAL_ABSOLUTE_PATH_REQUIRED")
    return Path(value)


def select_profile(config: dict, project: str, repository: str, root: Path) -> dict | None:
    profiles = config.get("verification_environments", {})
    validate_profiles(profiles)
    profile = profiles.get(project)
    if profile is not None and (profile["repository"] != repository or
                                Path(profile["path"]).resolve() != root.resolve()):
        _fail("VERIFICATION_PROFILE_BINDING_MISMATCH")
    return profile


def _plain(path: Path) -> os.stat_result:
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or
            getattr(info, "st_file_attributes", 0) & 0x400 or
            not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))):
        _fail("VERIFICATION_LINK_OR_SPECIAL_FILE_REJECTED")
    return info


def _checked(path: Path) -> Path:
    # Check ancestors as well: resolving first would hide junctions/symlinks.
    for item in (path, *path.parents):
        _plain(item)
    return path


def _inside(root: Path, relative: str) -> Path:
    path = root / _relative(relative)
    _checked(path)
    if not path.resolve().is_relative_to(root.resolve()):
        _fail("VERIFICATION_PROJECT_DIRECTORY_ESCAPED")
    return path


def _asset(value: str, kind: str, *, directory: bool = True) -> Path:
    try:
        path = _checked(_absolute(value))
        if not (path.is_dir() if directory else path.is_file()):
            _fail(f"VERIFICATION_{kind}_UNAVAILABLE")
        return path
    except OSError:
        _fail(f"VERIFICATION_{kind}_UNAVAILABLE")


def _dependency_cache(path: Path) -> None:
    # A mistaken profile must not turn a whole user home into model-readable
    # assets. Accept only the Gradle module-cache layout, not arbitrary folders.
    if path.name != "modules-2" or not _checked(path / "files-2.1").is_dir():
        _fail("VERIFICATION_DEPENDENCY_CACHE_LAYOUT_INVALID")
    for child in path.iterdir():
        info = _plain(child)
        if child.name.endswith(".lock") or child.name == "gc.properties":
            continue
        if not stat.S_ISDIR(info.st_mode) or not re.fullmatch(
                r"(?:files|metadata|resources)-\d+(?:\.\d+)*", child.name):
            _fail("VERIFICATION_DEPENDENCY_CACHE_LAYOUT_INVALID")


def _java_version(home: Path, *, required: bool) -> str:
    """Read approved JDK metadata without executing an outside-worktree command."""
    try:
        release = _checked(home / "release")
        if release.stat().st_size > 64 * 1024:
            _fail("VERIFICATION_JAVA_TOOLCHAIN_VERSION_INVALID")
        match = re.search(r'^JAVA_VERSION="([0-9][0-9A-Za-z.+_-]{0,79})"$',
                          release.read_text(encoding="utf-8"), re.M)
        if match:
            return match[1]
    except OSError:
        if not required:
            return "unknown"
    if required:
        _fail("VERIFICATION_JAVA_TOOLCHAIN_VERSION_INVALID")
    return "unknown"


def _java_toolchains(settings: dict) -> list[dict]:
    toolchains = []
    for value in settings.get("java_toolchain_homes", []):
        home = _asset(value, "JAVA_TOOLCHAIN")
        # The Agent runs on Windows, but supporting Unix fixtures keeps validation portable.
        for executable in ("java", "javac"):
            found = next((home / "bin" / name for name in (executable + ".exe", executable)
                          if (home / "bin" / name).is_file()), None)
            if found is None:
                _fail("VERIFICATION_JAVA_TOOLCHAIN_UNAVAILABLE")
            _checked(found)
        toolchains.append({"home": str(home), "version": _java_version(home, required=True)})
    return toolchains


class _Copier:
    def __init__(self):
        self.files = 0
        self.bytes = 0
        self.started = time.monotonic()

    def copy(self, source: Path, destination: Path, *, cache: bool = False) -> None:
        if time.monotonic() - self.started > 300:
            _fail("VERIFICATION_ASSET_COPY_TIMEOUT")
        if destination.resolve().is_relative_to(source.resolve()):
            _fail("VERIFICATION_ASSET_SOURCE_OVERLAPS_WORKSPACE")
        info = _plain(source)
        if stat.S_ISDIR(info.st_mode):
            destination.mkdir()
            for child in sorted(source.iterdir()):
                if cache and (child.name.endswith(".lock") or child.name == "gc.properties"):
                    continue
                self.copy(child, destination / child.name, cache=cache)
        else:
            self.files += 1
            self.bytes += info.st_size
            if self.files > 200000 or self.bytes > 8 * 1024**3:
                _fail("VERIFICATION_ASSET_LIMIT_EXCEEDED")
            # Recheck the opened identity before reading; no source ACLs or
            # executable hooks are copied. Destination inherits workspace ACLs.
            with source.open("rb") as src:
                opened = os.fstat(src.fileno())
                if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    _fail("VERIFICATION_ASSET_CHANGED")
                with destination.open("xb") as dst:
                    remaining = info.st_size
                    while remaining:
                        if time.monotonic() - self.started > 300:
                            _fail("VERIFICATION_ASSET_COPY_TIMEOUT")
                        block = src.read(min(remaining, 1024 * 1024))
                        if not block:
                            _fail("VERIFICATION_ASSET_CHANGED")
                        dst.write(block)
                        remaining -= len(block)
                    if src.read(1):
                        _fail("VERIFICATION_ASSET_CHANGED")
            after = source.lstat()
            if (after.st_ino, after.st_size, after.st_mtime_ns) != (
                    info.st_ino, info.st_size, info.st_mtime_ns):
                _fail("VERIFICATION_ASSET_CHANGED")


def _digest(path: Path) -> bytes:
    _checked(path)
    if path.stat().st_size > 16 * 1024**2:
        _fail("VERIFICATION_METADATA_TOO_LARGE")
    return hashlib.sha256(path.read_bytes()).digest()


def _frontend_locks(project: Path, snapshot: Path) -> None:
    for filename in ("package.json", "package-lock.json"):
        if _digest(project / filename) != _digest(snapshot / filename):
            _fail("VERIFICATION_FRONTEND_LOCK_MISMATCH")
    lock = json.loads((project / "package-lock.json").read_text(encoding="utf-8"))
    hidden = _checked(snapshot / "node_modules/.package-lock.json")
    if hidden.stat().st_size > 16 * 1024**2:
        _fail("VERIFICATION_METADATA_TOO_LARGE")
    installed = json.loads(hidden.read_text(encoding="utf-8")).get("packages")
    expected = lock.get("packages")
    if not isinstance(expected, dict) or not isinstance(installed, dict):
        _fail("VERIFICATION_FRONTEND_LOCK_FORMAT_UNSUPPORTED")
    for name in set(expected) | set(installed):
        if name == "":
            continue
        wanted, actual = expected.get(name), installed.get(name)
        if (not name.startswith("node_modules/") or _relative(name) != name or
                not isinstance(wanted, dict) or wanted.get("link")):
            _fail("VERIFICATION_FRONTEND_LOCK_MISMATCH")
        if actual is None and wanted.get("optional"):
            if os.path.lexists(snapshot / name):
                _fail("VERIFICATION_FRONTEND_LOCK_MISMATCH")
            continue
        if not isinstance(actual, dict) or any(
                actual.get(k) != wanted[k] for k in ("version", "integrity") if k in wanted):
            _fail("VERIFICATION_FRONTEND_LOCK_MISMATCH")
        _checked(snapshot / name)


def _sandbox(command: list[str], root: Path, env: dict, codex: str,
             *, frontend: bool = False) -> str:
    # Built-in workspace permissions and managed requirements remain in force.
    # No network/ACL overrides, escalation or arbitrary host-side build commands.
    # npm-installed Codex may resolve to a .cmd launcher on Windows. Python's
    # list quoting is not cmd.exe metacharacter escaping; fail closed rather
    # than let a path become an extra shell command through that launcher.
    if any(re.search(r'[&|<>^()%!"\r\n]', value) for value in (codex, str(root), *command)):
        _fail("VERIFICATION_UNSAFE_LAUNCH_ARGUMENT")
    result = subprocess.run(
        [codex, "sandbox", "--include-managed-config", "--permission-profile", ":workspace",
         "--cd", str(root), "--", *command], cwd=root, env=env, shell=False,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", timeout=180, check=False)
    if result.returncode:
        output = result.stdout.lower()
        if "getsockopt" in output and "permission denied" in output:
            _fail("VERIFICATION_LOOPBACK_DENIED: tests not run; review sandbox network policy")
        if "no cached version" in output or "not available for offline mode" in output:
            _fail("VERIFICATION_OFFLINE_DEPENDENCY_MISSING: tests not run")
        if any(marker in output for marker in (
                "cannot find a java installation", "no matching toolchains found",
                "no locally installed toolchains match")):
            _fail("VERIFICATION_JAVA_TOOLCHAIN_MISSING: tests not run")
        if any(marker in output for marker in (
                "unsupportedclassversionerror", "unsupported class file major version",
                "requires jvm", "requires java", "could not determine java version")):
            _fail("VERIFICATION_JAVA_RUNTIME_UNSUPPORTED: tests not run")
        if frontend:
            _fail("VERIFICATION_FRONTEND_DEPENDENCY_PREFLIGHT_FAILED: tests not run")
        _fail(f"VERIFICATION_SANDBOX_PREFLIGHT_FAILED: exit {result.returncode}; tests not run")
    return result.stdout


def _confirm_toolchains(output: str, configured: list[dict]) -> None:
    """Gradle can exit successfully after ignoring an invalid/inaccessible JDK."""
    discovered = set()
    for block in re.split(r"(?m)^\s*\+ ", output):
        location = re.search(r"(?m)^\s*\| Location:\s*(.+?)\s*$", block)
        is_jdk = re.search(r"(?m)^\s*\| Is JDK:\s*true\s*$", block, re.I)
        if location and is_jdk:
            discovered.add(location[1].replace("\\", "/").rstrip("/").casefold())
    if any(item["home"].replace("\\", "/").rstrip("/").casefold() not in discovered
           for item in configured):
        _fail("VERIFICATION_JAVA_TOOLCHAIN_NOT_DETECTED: tests not run")


_FRONTEND_PREFLIGHT = r"""// Runs only inside the managed workspace sandbox.
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
(async () => {
  const project = process.argv[2];
  const pkg = JSON.parse(fs.readFileSync(path.join(project, 'package.json'), 'utf8'));
  const deps = Object.assign({}, pkg.dependencies, pkg.devDependencies);
  for (const name of Object.keys(deps)) {
    if (!/^(?:@[a-z0-9._-]+\/)?[a-z0-9][a-z0-9._-]*$/i.test(name)) {
      throw new Error('Unsupported dependency name');
    }
    if (!fs.existsSync(path.join(project, 'node_modules', name, 'package.json'))) {
      if (pkg.optionalDependencies && name in pkg.optionalDependencies) continue;
      throw new Error('Installed direct dependency is missing');
    }
  }
  // Starting the common build libraries catches incomplete/platform-incompatible installs.
  // Unknown build systems still get the installed dependency check; no full build runs here.
  for (const name of ['vite', 'typescript', 'webpack', 'next']) {
    if (!(name in deps)) continue;
    const modulePath = require.resolve(name, {paths: [project]});
    await import(pathToFileURL(modulePath).href);
  }
})().catch(() => { console.error('Frontend dependency preflight failed'); process.exitCode = 1; });
"""


_GRADLE_DEPENDENCY_PREFLIGHT = """// Staged by the Agent; project execution remains sandboxed/offline.
gradle.projectsEvaluated {
    gradle.rootProject.tasks.register('lkhVerificationDependencies') {
        doLast {
            def resolved = 0
            gradle.rootProject.allprojects.each { p ->
                ['compileClasspath', 'runtimeClasspath', 'testCompileClasspath',
                 'testRuntimeClasspath', 'annotationProcessor', 'testAnnotationProcessor'].each { name ->
                    def configuration = p.configurations.findByName(name)
                    if (configuration != null && configuration.canBeResolved) {
                        configuration.resolve()
                        resolved++
                    }
                }
            }
            println('LKH_DEPENDENCY_CONFIGURATIONS=' + resolved)
        }
    }
}
"""


def prepare(root: Path, profile: dict, env: dict, codex: str) -> tuple[dict, dict]:
    """Return a worktree-local command manifest and a sanitized child environment.

    No download/install/build command is executed by the host-side preparation.
    A failed preflight never proceeds to the model or reports passing tests.
    """
    try:
        validate_profiles({"preparation": profile})
        return _prepare(root, profile, env, codex)
    except PreparationError:
        raise
    except subprocess.TimeoutExpired:
        _fail("VERIFICATION_PREFLIGHT_TIMEOUT: tests not run")
    except (OSError, ValueError, KeyError, TypeError):
        # Paths, package metadata and subprocess output may contain secrets.
        _fail("VERIFICATION_ASSET_UNAVAILABLE_OR_INVALID: tests not run")


def _prepare(root: Path, profile: dict, env: dict, codex: str) -> tuple[dict, dict]:
    staging = root / ".lkh-verification"
    staging.mkdir()  # Fail closed on collisions, including a tracked directory.
    (staging / "tmp").mkdir()
    runtime = dict(env)
    runtime.update(TEMP=str(staging / "tmp"), TMP=str(staging / "tmp"))
    manifest = {"schema_version": 1, "tests_executed": 0}
    copier = _Copier()
    if "gradle" in profile:
        settings = profile["gradle"]
        project = _inside(root, settings["project_dir"])
        wrapper = _checked(project / "gradle/wrapper/gradle-wrapper.properties")
        if wrapper.stat().st_size > 64 * 1024:
            _fail("VERIFICATION_METADATA_TOO_LARGE")
        text = wrapper.read_text(encoding="utf-8")
        match = re.search(r"^distributionUrl\s*=\s*(\S+)\s*$", text, re.M)
        filename = unquote(urlsplit(match[1].replace("\\:", ":")).path).rsplit("/", 1)[-1] if match else ""
        version_match = re.fullmatch(r"gradle-(\d+(?:\.\d+){1,2})-(?:bin|all)\.zip", filename)
        if version_match is None:
            _fail("VERIFICATION_WRAPPER_VERSION_UNSUPPORTED")
        version = version_match[1]
        distribution = _asset(settings["distribution"], "GRADLE_DISTRIBUTION")
        java = _asset(settings["java_executable"], "JAVA", directory=False)
        toolchains = _java_toolchains(settings)
        # Gradle 9 CLI layout. These files must match the pinned wrapper version.
        cli = f"lib/gradle-gradle-cli-main-{version}.jar"
        instrumentation = f"lib/agents/gradle-instrumentation-agent-{version}.jar"
        for filename in (cli, instrumentation):
            if not _checked(distribution / filename).is_file():
                _fail("VERIFICATION_GRADLE_DISTRIBUTION_MISMATCH")
        copier.copy(distribution, staging / "gradle")
        home = staging / "gradle-home"
        (home / "caches").mkdir(parents=True)
        cache = _asset(settings["dependency_cache"], "DEPENDENCY_CACHE")
        _dependency_cache(cache)
        copier.copy(cache, home / "caches/modules-2", cache=True)
        properties = ["org.gradle.java.installations.auto-download=false"]
        if toolchains:
            properties.extend([
                "org.gradle.java.installations.auto-detect=false",
                "org.gradle.java.installations.paths=" + ",".join(
                    # Java Properties.load accepts Unicode escapes, preserving Korean paths.
                    json.dumps(Path(item["home"]).as_posix(), ensure_ascii=True)[1:-1]
                    for item in toolchains),
            ])
        (home / "gradle.properties").write_text("\n".join(properties) + "\n", encoding="utf-8")
        dependency_check = staging / "dependency-preflight.gradle"
        dependency_check.write_text(_GRADLE_DEPENDENCY_PREFLIGHT, encoding="utf-8")
        runtime.update(GRADLE_USER_HOME=str(home), JAVA_HOME=str(java.parent.parent))
        command = [str(java), "-Xmx64m", "-Xms64m",
                   f"-javaagent:{staging / 'gradle' / instrumentation}",
                   "-Dorg.gradle.appname=gradle", "-jar", str(staging / "gradle" / cli),
                   "--gradle-user-home", str(home), "-p", str(project),
                   "--offline", "--no-daemon", "--stacktrace", "--no-problems-report"]
        manifest["gradle"] = {
            "version": version, "command": command, "preflight": "pending",
            "runtime_java_executable": str(java),
            "runtime_java_version": _java_version(java.parent.parent, required=False),
            "java_toolchains": toolchains,
            "dependency_preflight": "pending",
            "dependency_command": command + ["--no-configuration-cache", "--init-script",
                                              str(dependency_check), "lkhVerificationDependencies"],
        }
    if "frontend" in profile:
        settings = profile["frontend"]
        project = _inside(root, settings["project_dir"])
        snapshot = _asset(settings["snapshot"], "FRONTEND_SNAPSHOT")
        _frontend_locks(project, snapshot)
        copier.copy(snapshot / "node_modules", project / "node_modules")
        _frontend_locks(project, project)  # Check the staged copy, not only its source.
        node = _asset(settings["node_executable"], "NODE", directory=False)
        (staging / "npm-cache").mkdir()
        for name in ("npm-user.conf", "npm-global.conf"):
            with (staging / name).open("x", encoding="utf-8"):
                pass
        runtime["PATH"] = str(node.parent) + os.pathsep + runtime.get("PATH", "")
        runtime.update(NPM_CONFIG_USERCONFIG=str(staging / "npm-user.conf"),
                       NPM_CONFIG_GLOBALCONFIG=str(staging / "npm-global.conf"),
                       NPM_CONFIG_CACHE=str(staging / "npm-cache"), NPM_CONFIG_OFFLINE="true",
                       NPM_CONFIG_AUDIT="false", NPM_CONFIG_FUND="false",
                       NPM_CONFIG_UPDATE_NOTIFIER="false")
        manifest["frontend"] = {"project_dir": settings["project_dir"],
                                "node_executable": str(node), "preflight": "pending",
                                "dependency_preflight": "pending"}
        frontend_check = staging / "frontend-preflight.cjs"
        frontend_check.write_text(_FRONTEND_PREFLIGHT, encoding="utf-8")
    # Assets are fully staged before untrusted build code executes in a sandbox.
    # Do not write host-side files after preflight: build code could replace a
    # destination with a link. The completed manifest is passed in memory only.
    if "gradle" in manifest:
        _sandbox(manifest["gradle"]["command"] + ["--version"], root, runtime, codex)
        _sandbox(manifest["gradle"]["command"] + ["help"], root, runtime, codex)
        if manifest["gradle"]["java_toolchains"]:
            output = _sandbox(manifest["gradle"]["command"] + ["javaToolchains"], root, runtime, codex)
            _confirm_toolchains(output, manifest["gradle"]["java_toolchains"])
        output = _sandbox(manifest["gradle"]["dependency_command"], root, runtime, codex)
        count = re.search(r"(?m)^LKH_DEPENDENCY_CONFIGURATIONS=(\d+)\s*$", output)
        if count is None:
            _fail("VERIFICATION_DEPENDENCY_REPORT_UNAVAILABLE: tests not run")
        manifest["gradle"]["dependency_configurations"] = int(count[1])
        manifest["gradle"]["dependency_preflight"] = "passed" if int(count[1]) else "not_applicable"
        manifest["gradle"]["preflight"] = "passed"
    if "frontend" in manifest:
        _sandbox([str(node), "--version"], root, runtime, codex, frontend=True)
        _sandbox([str(node), str(frontend_check), str(project)], root, runtime, codex,
                 frontend=True)
        manifest["frontend"]["preflight"] = "passed"
        manifest["frontend"]["dependency_preflight"] = "passed"
    return manifest, runtime
