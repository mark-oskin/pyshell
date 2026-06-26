"""Tests for subprocess environment handling."""

import os
import tempfile
import unittest
import unittest.mock

from pyshell.subprocess_env import subprocess_env


class TestSubprocessEnv(unittest.TestCase):
    def test_drops_mismatched_virtual_env(self):
        with tempfile.TemporaryDirectory() as pyshell_root, tempfile.TemporaryDirectory() as other_root:
            pyshell_venv = os.path.join(pyshell_root, ".venv")
            os.makedirs(pyshell_venv)
            with unittest.mock.patch.dict(os.environ, {"VIRTUAL_ENV": pyshell_venv}, clear=False):
                with unittest.mock.patch("os.getcwd", return_value=other_root):
                    env = subprocess_env()
            self.assertNotIn("VIRTUAL_ENV", env)

    def test_keeps_matching_virtual_env(self):
        with tempfile.TemporaryDirectory() as root:
            venv = os.path.join(root, ".venv")
            os.makedirs(venv)
            with unittest.mock.patch.dict(os.environ, {"VIRTUAL_ENV": venv}, clear=False):
                with unittest.mock.patch("os.getcwd", return_value=root):
                    env = subprocess_env()
            self.assertEqual(env["VIRTUAL_ENV"], venv)

    def test_no_virtual_env_unchanged(self):
        env = subprocess_env()
        self.assertEqual(env.get("VIRTUAL_ENV"), os.environ.get("VIRTUAL_ENV"))
