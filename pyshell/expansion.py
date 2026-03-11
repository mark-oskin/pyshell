"""Expand $VAR, ~, and globs in command arguments.

Used by the executor for command argv and redirect paths. Expansion order
in expand_command_argv: vars, then tilde, then glob.
"""

import glob as glob_module
import os
from typing import Any


def expand_vars_in_string(s: str, env: dict[str, Any]) -> str:
    """Replace $VAR and ${VAR} with values from env.

    Args:
        s: String possibly containing $VAR or ${VAR}.
        env: Dict used for lookup; falls back to os.environ for missing keys.

    Returns:
        New string with substitutions; unknown vars become empty.
    """
    result: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "$" and i + 1 < n:
            if s[i + 1] == "{":
                end = s.find("}", i + 2)
                if end != -1:
                    key = s[i + 2 : end]
                    result.append(str(env.get(key, os.environ.get(key, ""))))
                    i = end + 1
                    continue
            elif s[i + 1].isalnum() or s[i + 1] == "_":
                j = i + 1
                while j < n and (s[j].isalnum() or s[j] == "_"):
                    j += 1
                key = s[i + 1 : j]
                result.append(str(env.get(key, os.environ.get(key, ""))))
                i = j
                continue
        result.append(s[i])
        i += 1
    return "".join(result)


def expand_tilde(s: str) -> str:
    """Expand ~ and ~user to home directory.

    Args:
        s: Path that may start with ~ or ~username.

    Returns:
        Path with tilde expanded via os.path.expanduser.
    """
    return os.path.expanduser(s)


def expand_glob_argv(argv: list[str]) -> list[str]:
    """Expand tokens containing *, ?, or ** into matching file paths.

    Args:
        argv: List of tokens (e.g. command args).

    Returns:
        New list with glob patterns replaced by sorted matches; no match keeps token.
    """
    out: list[str] = []
    for token in argv:
        if "*" in token or "?" in token:
            if "**" in token:
                matches = glob_module.glob(token, recursive=True)
            else:
                matches = glob_module.glob(token)
            if matches:
                out.extend(sorted(matches))
            else:
                out.append(token)
        else:
            out.append(token)
    return out


def expand_command_argv(argv: list[str], env: dict[str, Any]) -> list[str]:
    """Apply variable, tilde, then glob expansion to command argv.

    Args:
        argv: List of raw tokens (before expansion).
        env: Environment for $VAR expansion.

    Returns:
        New argv with expand_vars_in_string, expand_tilde, then expand_glob_argv applied.
    """
    argv = [expand_vars_in_string(t, env) for t in argv]
    argv = [expand_tilde(t) for t in argv]
    argv = expand_glob_argv(argv)
    return argv


def expand_redirect_path(path: str | None, env: dict[str, Any]) -> str | None:
    """Expand $VAR and ~ in a redirect file path or here-string content.

    Args:
        path: Redirect path or <<< string content; None for 2>&1.
        env: Environment for $VAR expansion.

    Returns:
        Expanded string, or None if path is None.
    """
    if path is None:
        return None
    return expand_tilde(expand_vars_in_string(path, env))
