import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


@unittest.skipUnless(os.name == "nt", "Windows launcher integration")
class WindowsLauncherTests(unittest.TestCase):
    def run_launcher(self, shortcut_script):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="megasweep launcher ") as folder:
            root = Path(folder)
            scripts = root / ".venv" / "Scripts"
            scripts.mkdir(parents=True)
            (scripts / "activate.bat").write_text("@exit /b 0\n")
            for name in ("python.exe", "pythonw.exe"):
                (scripts / name).touch()
            (root / "requirements.txt").touch()
            (root / "assets").mkdir()
            (root / "assets" / "megasweep.ico").touch()
            (root / "main.py").write_text(
                "from pathlib import Path\nPath(__file__).with_name('started').write_text('ok')\n"
            )
            (root / "Create_Megasweep_Shortcut.ps1").write_text(shortcut_script)
            # Exercise the real batch flow with a harmless child instead of the GUI.
            launcher = (source / "Megasweep Analysis.bat").read_text()
            launcher = launcher.replace(
                'set "VENV_PYTHONW=%VENV_DIR%\\Scripts\\pythonw.exe"',
                f'set "VENV_PYTHONW={sys.executable}"',
            )
            (root / "launch.bat").write_text(launcher)
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "launch.bat"], cwd=root,
                input="\n", capture_output=True, text=True, timeout=20,
            )
            deadline = time.monotonic() + 5
            while not (root / "started").exists() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue((root / "started").exists(), result.stdout + result.stderr)
            return result, (root / "Megasweep Analysis.lnk").exists()

    def test_shortcut_creation_handles_directory_with_spaces(self):
        script = (Path(__file__).resolve().parents[1] / "Create_Megasweep_Shortcut.ps1").read_text()
        result, shortcut_exists = self.run_launcher(script)
        self.assertTrue(shortcut_exists, result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_optional_shortcut_failure_does_not_report_launch_failure(self):
        result, _ = self.run_launcher('throw "Simulated optional shortcut failure"')
        self.assertIn("[WARNING]", result.stdout)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("[ERROR] Failed to start", result.stdout)
