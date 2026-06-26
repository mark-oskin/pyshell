"""Environment passed to child processes."""

from __future__ import annotations

import os


def subprocess_env() -> dict[str, str]:
    """Return a copy of os.environ for child processes.

    Drops ``VIRTUAL_ENV`` when it does not match ``<cwd>/.venv`` (resolved), so
    tools like ``uv`` are not warned after ``cd`` into another project while
    pyshell still runs under a different activated venv.

    Returns:
        Environment dict for ``subprocess.run`` / ``Popen``.
    """
    env = os.environ.copy()
    venv = env.get("VIRTUAL_ENV")
    if not venv:
        return env
    try:
        local = os.path.realpath(os.path.join(os.getcwd(), ".venv"))
        if os.path.realpath(venv) != local:
            env.pop("VIRTUAL_ENV", None)
    except OSError:
        env.pop("VIRTUAL_ENV", None)
    return env
