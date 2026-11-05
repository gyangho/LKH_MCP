"""Explicit local registration/refresh of private Agent verification assets.

Queued tasks cannot invoke this command. Project installation and Gradle code run
only after the local operator supplies --allow-project-code, inside the managed
workspace sandbox. Network access remains subject to that sandbox's policy.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import json
import ntpath
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from urllib.parse import unquote, urlsplit

import verification_environment as verification


class AssetError(RuntimeError):
    """Fixed non-sensitive error codes suitable for terminal output."""


def _read(path: Path) -> dict:
    verification._checked(path)
    if path.stat().st_size > 1024 * 1024:
        raise AssetError("ASSETS_CONFIG_TOO_LARGE")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise AssetError("ASSETS_INVALID_CONFIG")
    return data


def _write(path: Path, data: dict, expected: bytes) -> None:
    """Do not clobber edits made after the command read its private config."""
    verification._checked(path)
    if path.read_bytes() != expected:
        raise AssetError("ASSETS_CONFIG_CHANGED")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".verification-", suffix=".tmp", delete=False) as out:
            temporary = Path(out.name)
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        if path.read_bytes() != expected:
            raise AssetError("ASSETS_CONFIG_CHANGED")
        _replace_config(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _replace_config(source: Path, target: Path) -> None:
    if sys.platform == "win32":
        _windows_replace_config(source, target)
    else:
        os.chmod(source, stat.S_IMODE(target.stat().st_mode))
        os.replace(source, target)


def _windows_replace_config(source: Path, target: Path) -> None:
    # ReplaceFileW preserves the target DACL; os.replace would replace it with
    # the temporary file's inherited ACL and discard the enrolled Agent's ACE.
    # Never use IGNORE_ACL_ERRORS or fall back to weaker permissions.
    # https://learn.microsoft.com/windows/win32/api/winbase/nf-winbase-replacefilew
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    replace = kernel.ReplaceFileW
    replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                        wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
    replace.restype = wintypes.BOOL
    backup = target.parent / (".verification-backup-" + uuid.uuid4().hex + ".json")
    if os.path.lexists(backup):
        raise AssetError("ASSETS_CONFIG_BACKUP_COLLISION")
    if not replace(str(target), str(source), str(backup), 0, None, None):
        # Some documented partial failures can leave the original under the
        # backup name. Restore that same file/ACL if the target disappeared.
        if not os.path.lexists(target) and os.path.lexists(backup):
            verification._checked(backup)
            os.replace(backup, target)
        raise AssetError("ASSETS_CONFIG_REPLACE_FAILED")
    try:
        backup.unlink(missing_ok=True)
    except OSError:
        # The new configuration is already published. A sharing/AV lock on
        # the private backup must not turn successful registration into failure.
        print("ASSETS_CONFIG_BACKUP_CLEANUP_PENDING", file=sys.stderr)


def _binding(config: dict, project: str, profile: dict) -> None:
    configured = config.get("projects", {}).get(project)
    if (not isinstance(configured, dict)
            or configured.get("repository") != profile.get("repository")
            or Path(configured.get("path", "")).resolve() != Path(profile.get("path", "")).resolve()):
        raise AssetError("ASSETS_PROJECT_BINDING_MISMATCH")


def register(config_path: Path, project: str, profile: dict, *, bind_project: bool = False) -> dict:
    """Register explicit installed paths; missing caches may be refreshed later."""
    config_path = verification._absolute(str(config_path))
    config = _read(config_path)
    before = config_path.read_bytes()
    profiles = dict(config.get("verification_environments", {}))
    profiles[project] = profile
    verification.validate_profiles(profiles)
    if bind_project:
        projects = dict(config.get("projects", {}))
        projects[project] = {"repository": profile["repository"], "path": profile["path"]}
        if len(projects) > 10:
            raise AssetError("ASSETS_INVALID_PROJECT_BINDINGS")
        for alias, binding in projects.items():
            if (not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", alias)
                    or not isinstance(binding, dict)
                    or not isinstance(binding.get("repository"), str)
                    or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", binding["repository"])):
                raise AssetError("ASSETS_INVALID_PROJECT_BINDINGS")
            verification._absolute(binding.get("path"))
        config["projects"] = projects
    _binding(config, project, profile)
    config["verification_environments"] = profiles
    _write(config_path, config, before)
    return {"status": "registered", "project": project}


def _profile(config_path: Path, project: str) -> tuple[dict, dict]:
    config = _read(config_path)
    profiles = config.get("verification_environments", {})
    verification.validate_profiles(profiles)
    if project not in profiles:
        raise AssetError("ASSETS_PROJECT_NOT_REGISTERED")
    profile = profiles[project]
    _binding(config, project, profile)
    return config, profile


def plan(config_path: Path, project: str, sha: str, output: Path) -> dict:
    _, profile = _profile(config_path, project)
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise AssetError("ASSETS_EXACT_SHA_REQUIRED")
    output = verification._absolute(str(output))
    verification._checked(output.parent)
    if os.path.lexists(output):
        raise AssetError("ASSETS_OUTPUT_EXISTS")
    root = verification._checked(Path(profile["path"]))
    if output.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(output.resolve()):
        raise AssetError("ASSETS_OUTPUT_OVERLAPS_REPOSITORY")
    return {"status": "planned", "project": project, "sha": sha,
            "steps": (["Gradle dependency resolution and testClasses (downloads and compiles; does not run tests)"] if "gradle" in profile else [])
                     + (["npm ci (may execute dependency lifecycle scripts)"] if "frontend" in profile else []),
            "requires": "--allow-project-code; managed sandbox network permission; installed Gradle/JDK/Node",
            "tests_executed": 0}


def _run(command: list[str], root: Path, env: dict | None = None) -> str:
    completed = subprocess.run(command, cwd=root, env=env, shell=False,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace", timeout=1200, check=False)
    if completed.returncode:
        raise AssetError("ASSETS_COMMAND_FAILED")
    return completed.stdout.strip()


def _sandbox(command: list[str], root: Path, env: dict, codex: str) -> None:
    if any(re.search(r'[&|<>^()%!"\r\n]', value) for value in (codex, str(root), *command)):
        raise AssetError("ASSETS_UNSAFE_LAUNCH_ARGUMENT")
    completed = subprocess.run(
        [codex, "sandbox", "--include-managed-config", "--permission-profile", ":workspace",
         "--cd", str(root), "--", *command], cwd=root, env=env, shell=False,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", timeout=1200, check=False)
    if completed.returncode:
        text = completed.stdout.lower()
        if "getsockopt" in text and "permission denied" in text:
            raise AssetError("ASSETS_LOOPBACK_DENIED")
        if any(value in text for value in ("unknownhostexception", "eai_again", "enotfound", "name resolution")):
            raise AssetError("ASSETS_NETWORK_UNAVAILABLE_OR_DENIED")
        raise AssetError("ASSETS_SANDBOX_REFRESH_BLOCKED_OR_FAILED")


def _git(root: Path, *args: str) -> str:
    return _run(["git", "-c", "core.hooksPath=NUL", *args], root)


def _repository(root: Path, repository: str, sha: str) -> None:
    if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root.resolve():
        raise AssetError("ASSETS_REPOSITORY_ROOT_MISMATCH")
    accepted = {f"https://github.com/{repository}", f"https://github.com/{repository}.git",
                f"git@github.com:{repository}", f"git@github.com:{repository}.git",
                f"ssh://git@github.com/{repository}", f"ssh://git@github.com/{repository}.git"}
    if _git(root, "remote", "get-url", "origin").lower() not in {x.lower() for x in accepted}:
        raise AssetError("ASSETS_REPOSITORY_ORIGIN_MISMATCH")
    if _git(root, "rev-parse", "--verify", sha + "^{commit}").lower() != sha:
        raise AssetError("ASSETS_SHA_UNAVAILABLE")


def _runtime(output: Path) -> dict:
    # Do not pass Agent tokens, private registry settings or arbitrary build env.
    keep = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
            "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "CODEX_HOME"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    if sys.platform == "win32":
        value = lambda name: next((v for k, v in env.items() if k.upper() == name), "")
        drive = value("SYSTEMDRIVE")
        if not re.fullmatch(r"[A-Za-z]:", drive):
            drive = ntpath.splitdrive(value("SYSTEMROOT") or value("WINDIR"))[0]
        if not re.fullmatch(r"[A-Za-z]:", drive):
            raise AssetError("ASSETS_WINDOWS_SYSTEM_DRIVE_UNAVAILABLE")
        env = {k: v for k, v in env.items() if k.upper() != "SYSTEMDRIVE"}
        env["SystemDrive"] = drive.upper()
    env.update(TEMP=str(output / "tmp"), TMP=str(output / "tmp"),
               GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    return env


def _refresh(profile: dict, sha: str, output: Path, codex: str) -> dict:
    root = verification._checked(Path(profile["path"]))
    _repository(root, profile["repository"], sha)
    output.mkdir()  # Never overwrite earlier assets or reuse a failed directory.
    worktree = output / "worktree"
    _git(root, "worktree", "add", "--detach", "--", str(worktree), sha)
    try:
        staging = worktree / ".lkh-refresh"
        staging.mkdir()
        (staging / "tmp").mkdir()
        env = _runtime(staging)
        copier = verification._Copier()
        updated = copy.deepcopy(profile)
        commands = []
        if "gradle" in profile:
            settings = profile["gradle"]
            project = verification._inside(worktree, settings["project_dir"])
            wrapper = verification._checked(project / "gradle/wrapper/gradle-wrapper.properties")
            if wrapper.stat().st_size > 65536:
                raise AssetError("ASSETS_WRAPPER_TOO_LARGE")
            match = re.search(r"^distributionUrl\s*=\s*(\S+)\s*$", wrapper.read_text(encoding="utf-8"), re.M)
            filename = unquote(urlsplit(match[1].replace("\\:", ":")).path).rsplit("/", 1)[-1] if match else ""
            version = re.fullmatch(r"gradle-(\d+(?:\.\d+){1,2})-(?:bin|all)\.zip", filename)
            if version is None:
                raise AssetError("ASSETS_WRAPPER_VERSION_UNSUPPORTED")
            distribution = verification._asset(settings["distribution"], "GRADLE_DISTRIBUTION")
            cli = f"lib/gradle-gradle-cli-main-{version[1]}.jar"
            instrumentation = f"lib/agents/gradle-instrumentation-agent-{version[1]}.jar"
            for item in (cli, instrumentation):
                verification._checked(distribution / item)
            java = verification._asset(settings["java_executable"], "JAVA", directory=False)
            copier.copy(distribution, staging / "gradle")
            home = staging / "gradle-home"
            (home / "caches").mkdir(parents=True)
            cache = Path(settings["dependency_cache"])
            if os.path.lexists(cache):
                verification._dependency_cache(verification._checked(cache))
                copier.copy(cache, home / "caches/modules-2", cache=True)
            env.update(JAVA_HOME=str(java.parent.parent), GRADLE_USER_HOME=str(home))
            properties = ["org.gradle.java.installations.auto-download=false"]
            toolchains = verification._java_toolchains(settings)
            if toolchains:
                escaped = [json.dumps(Path(item["home"]).as_posix(), ensure_ascii=True)[1:-1]
                           for item in toolchains]
                properties += ["org.gradle.java.installations.auto-detect=false",
                               "org.gradle.java.installations.paths=" + ",".join(escaped)]
            (home / "gradle.properties").write_text("\n".join(properties) + "\n", encoding="ascii")
            dependency_check = staging / "dependency-preflight.gradle"
            dependency_check.write_text(verification._GRADLE_DEPENDENCY_PREFLIGHT, encoding="utf-8")
            command = [str(java), f"-javaagent:{staging / 'gradle' / instrumentation}",
                       "-Dorg.gradle.appname=gradle", "-jar", str(staging / "gradle" / cli),
                       "--gradle-user-home", str(home), "-p", str(project),
                       "--no-daemon", "--stacktrace", "--no-problems-report"]
            commands.append(command + ["--no-configuration-cache", "--init-script", str(dependency_check),
                                       "lkhVerificationDependencies", "testClasses"])
            updated["gradle"]["dependency_cache"] = str(output / "modules-2")
        if "frontend" in profile:
            settings = profile["frontend"]
            project = verification._inside(worktree, settings["project_dir"])
            node = verification._asset(settings["node_executable"], "NODE", directory=False)
            npm = verification._asset(str(node.parent / "node_modules/npm/bin/npm-cli.js"), "NPM", directory=False)
            for filename in ("package.json", "package-lock.json"):
                verification._checked(project / filename)
            (staging / "npm-cache").mkdir()
            for filename in ("npm-user.conf", "npm-global.conf"):
                (staging / filename).write_text("", encoding="utf-8")
            env.update(NPM_CONFIG_USERCONFIG=str(staging / "npm-user.conf"),
                       NPM_CONFIG_GLOBALCONFIG=str(staging / "npm-global.conf"),
                       NPM_CONFIG_CACHE=str(staging / "npm-cache"), NPM_CONFIG_AUDIT="false",
                       NPM_CONFIG_FUND="false", NPM_CONFIG_UPDATE_NOTIFIER="false",
                       PATH=str(node.parent) + os.pathsep + env.get("PATH", ""))
            commands.append([str(node), str(npm), "--prefix", str(project), "ci", "--no-audit", "--no-fund"])
            updated["frontend"]["snapshot"] = str(output / "frontend")
        # All host-side setup finishes before any untrusted project executes.
        for command in commands:
            _sandbox(command, worktree, env, codex)
        verification._checked(worktree)
        if _git(worktree, "rev-parse", "HEAD").lower() != sha:
            raise AssetError("ASSETS_WORKTREE_HEAD_CHANGED")
        _git(worktree, "diff", "--quiet", "--no-ext-diff", "--no-textconv", "HEAD", "--")
        verification._checked(output)
        copier = verification._Copier()
        if "gradle" in profile:
            cache = staging / "gradle-home/caches/modules-2"
            verification._dependency_cache(verification._checked(cache))
            copier.copy(cache, output / "modules-2", cache=True)
        if "frontend" in profile:
            project = verification._inside(worktree, profile["frontend"]["project_dir"])
            verification._frontend_locks(project, project)
            snapshot = output / "frontend"
            snapshot.mkdir()
            for filename in ("package.json", "package-lock.json", "node_modules"):
                copier.copy(project / filename, snapshot / filename)
            verification._frontend_locks(project, snapshot)
        return updated
    finally:
        # Git cleans only this explicitly created detached worktree. Keep failed
        # output directories for inspection; never recursively delete asset roots.
        if worktree.exists():
            verification._checked(worktree)
            try:
                _git(root, "worktree", "remove", "--force", "--", str(worktree))
            except (AssetError, OSError, subprocess.TimeoutExpired):
                pass


def refresh(config_path: Path, project: str, sha: str, output: Path, *,
            allow_project_code: bool = False, codex: str | None = None) -> dict:
    planned = plan(config_path, project, sha, output)
    if not allow_project_code:
        return planned
    before = config_path.read_bytes()
    config, profile = _profile(config_path, project)
    codex = codex or shutil.which("codex")
    if not codex:
        raise AssetError("ASSETS_CODEX_UNAVAILABLE")
    try:
        updated = _refresh(profile, sha, output, codex)
        config["verification_environments"][project] = updated
        _write(config_path, config, before)
    except AssetError:
        raise
    except (OSError, ValueError, KeyError, TypeError, verification.PreparationError, subprocess.TimeoutExpired):
        raise AssetError("ASSETS_REFRESH_FAILED") from None
    return {"status": "refreshed", "project": project, "sha": sha, "tests_executed": 0,
            "summary": "New assets registered; previous assets retained. Native build and tests were not run."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    registration = commands.add_parser("register", help="Register an explicit profile JSON in private agent.json")
    registration.add_argument("--config", type=Path, required=True)
    registration.add_argument("--project", required=True)
    registration.add_argument("--profile", type=Path, required=True)
    registration.add_argument("--bind-project", action="store_true",
                              help="Explicitly register/update this alias's local repository/path binding too")
    for name in ("plan", "refresh"):
        action = commands.add_parser(name, help="Plan or explicitly execute isolated dependency refresh")
        action.add_argument("--config", type=Path, required=True)
        action.add_argument("--project", required=True)
        action.add_argument("--sha", required=True, help="Exact commit already present in the approved checkout; no fetch")
        action.add_argument("--output", type=Path, required=True, help="New absolute directory outside the repository")
        if name == "refresh":
            action.add_argument("--allow-project-code", action="store_true",
                                help="Execute Gradle compilation and npm lifecycle scripts in the managed sandbox")
    args = parser.parse_args(argv)
    try:
        config = args.config.absolute()
        if args.command == "register":
            result = register(config, args.project, _read(args.profile.absolute()), bind_project=args.bind_project)
        elif args.command == "plan":
            result = plan(config, args.project, args.sha, args.output)
        else:
            result = refresh(config, args.project, args.sha, args.output,
                             allow_project_code=args.allow_project_code)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (AssetError, verification.PreparationError) as exc:
        print(json.dumps({"status": "environment_blocked", "code": str(exc), "tests_executed": 0}))
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired):
        print(json.dumps({"status": "environment_blocked", "code": "ASSETS_INVALID_OR_UNAVAILABLE", "tests_executed": 0}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
