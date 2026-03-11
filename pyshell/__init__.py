"""pyshell — A command-line shell with Python-like syntax.

Entry points: main() for CLI; Shell for programmatic REPL.
See docs/DESIGN.md for architecture and docs/API.md for function index.
"""

__version__ = "0.1.0"

from pyshell.shell import Shell, main

__all__ = ["Shell", "main", "__version__"]
