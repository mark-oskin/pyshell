# pyshell documentation

- **[DESIGN.md](DESIGN.md)** — Architecture, data flow, parsing vs execution, and extension points. Update when behavior or structure changes.
- **[API.md](API.md)** — Index of modules and functions for quick lookup. Keep in sync when adding or changing public APIs.

Code docstrings (in `pyshell/*.py`) are the source of truth for each function; use Args/Returns/Raises where useful so docs stay indexable.

To keep docs current: see `.cursor/rules/maintain-docs.mdc` (and update DESIGN + API when you change the codebase).
