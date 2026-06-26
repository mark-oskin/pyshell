"""Resolve shell command names to executables, including ``.py`` scripts on PATH."""

from __future__ import annotations

import os
import shutil
import sys


def path_lookup_names(name: str) -> list[str]:
    """Return command names to try on PATH, in order.

    ``program`` tries ``program`` then ``program.py``. ``program.`` tries
    ``program.py`` only (trailing dot with no extension).

    Args:
        name: Command token from argv[0] (no path separators).

    Returns:
        Ordered lookup names for ``shutil.which`` / PATH scan.
    """
    if name.endswith(".") and not name.endswith(".."):
        base = name[:-1]
        if base:
            return [base + ".py"]
        return [name]
    names = [name]
    if not os.path.splitext(name)[1]:
        names.append(name + ".py")
    return names


def _path_file_candidates(name: str) -> list[str]:
    """Return filesystem paths to try for a path-qualified command."""
    if name.endswith(".") and not name.endswith(".."):
        base = name[:-1]
        if base:
            return [base + ".py", base]
        return [name]
    candidates = [name]
    root, ext = os.path.splitext(name)
    if not ext:
        candidates.append(name + ".py")
    if os.name == "nt":
        candidates.append(name + ".exe")
    return candidates


def _find_py_on_path(py_name: str, path_env: str) -> str | None:
    """Find ``name.py`` on PATH even when the file is not executable."""
    if not py_name.endswith(".py"):
        py_name = py_name + ".py"
    for d in path_env.split(os.pathsep):
        if not d:
            continue
        candidate = os.path.join(d, py_name)
        if os.path.isfile(candidate):
            return candidate
    return None


def _argv_for_script(path: str) -> list[str]:
    """Build argv prefix to run a script (direct exec or via Python)."""
    if os.access(path, os.X_OK):
        return [path]
    return [sys.executable, path]


def _resolve_on_path(name: str, path_env: str) -> list[str] | None:
    for lookup in path_lookup_names(name):
        resolved = shutil.which(lookup, path=path_env)
        if resolved is not None:
            return [resolved]
    for lookup in path_lookup_names(name):
        if not lookup.endswith(".py"):
            continue
        found = _find_py_on_path(lookup, path_env)
        if found is not None:
            return _argv_for_script(found)
    return None


def _resolve_path_qualified(name: str) -> list[str] | None:
    for path in _path_file_candidates(name):
        if os.path.isfile(path):
            if path.endswith(".py"):
                return _argv_for_script(path)
            return [path]
    return None


def resolve_command_argv(
    argv: list[str],
    *,
    path_env: str | None = None,
) -> list[str] | None:
    """Resolve argv[0] to an executable; return full argv or None.

    Unqualified names use PATH (``program`` then ``program.py``). A trailing
    dot (``program.``) resolves to ``program.py``. Non-executable ``.py``
    scripts on PATH run via ``sys.executable``.

    Args:
        argv: Command vector ``[name, arg1, ...]``.
        path_env: PATH override (default: ``os.environ["PATH"]``).

    Returns:
        Resolved argv, or None if the command was not found.
    """
    if not argv:
        return argv
    name = argv[0]
    path_env = path_env if path_env is not None else os.environ.get("PATH", "")

    if os.path.isabs(name) or os.path.sep in name or (
        os.path.altsep and os.path.altsep in name
    ):
        prefix = _resolve_path_qualified(name)
    else:
        prefix = _resolve_on_path(name, path_env)

    if prefix is None:
        return None
    return prefix + argv[1:]


def lookup_command(name: str, *, path_env: str | None = None) -> str | None:
    """Return the path shown by ``which`` / ``type`` for ``name``.

    Args:
        name: Command name.
        path_env: PATH override (default: ``os.environ["PATH"]``).

    Returns:
        Resolved script path, or None if not found.
    """
    resolved = resolve_command_argv([name], path_env=path_env)
    if resolved is None:
        return None
    if len(resolved) >= 2 and resolved[0] == sys.executable:
        return resolved[1]
    return resolved[0]
