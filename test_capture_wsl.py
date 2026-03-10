#!/usr/bin/env python3
"""Run in WSL to verify command substitution capture (echo `ls|wc`)."""
import sys
sys.path.insert(0, ".")

from pyshell.shell import Shell

s = Shell()
s.executor.set_exit_callback(lambda c: None)

# Test 1: direct capture
try:
    out, code = s._run_and_capture("ls|wc")
    print("_run_and_capture(ls|wc) -> output:", repr(out[:50]), "..." if len(out) > 50 else "", "code:", code)
except Exception as e:
    import traceback
    print("FAIL:", type(e).__name__, e)
    traceback.print_exc()
    sys.exit(1)

# Test 2: full expansion (echo `ls|wc`)
try:
    expanded = s._expand_command_substitution("echo `ls|wc`")
    print("_expand_command_substitution('echo `ls|wc`') ->", repr(expanded[:60]), "..." if len(expanded) > 60 else "")
    if "echo" in expanded and any(c.isdigit() for c in expanded):
        print("OK: expansion contains echo and digits (wc output)")
    else:
        print("WARN: expansion looks wrong")
except Exception as e:
    import traceback
    print("FAIL:", type(e).__name__, e)
    traceback.print_exc()
    sys.exit(1)
print("All WSL capture tests passed.")
