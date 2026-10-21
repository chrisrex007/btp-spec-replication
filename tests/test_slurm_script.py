"""Exercise preflight guards without invoking modules, GPUs, or inference."""
from pathlib import Path
import os
import shutil
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "hpc/paramshakti/run_offline_batch.sh"
BASH = ("C:/Program Files/Git/bin/bash.exe" if os.name == "nt"
        and Path("C:/Program Files/Git/bin/bash.exe").exists() else shutil.which("bash"))


@unittest.skipUnless(BASH, "bash unavailable")
class SlurmPreflightTests(unittest.TestCase):
    def test_shell_syntax(self):
        result = subprocess.run([BASH, "-n"], input=SCRIPT.read_text(),
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def run_guard(self, values):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("SLURM_", "BTP_")) and k != "SCRATCH"}
        env.update(values)
        return subprocess.run([BASH, "-s"], input=SCRIPT.read_text(), env=env,
                              text=True, capture_output=True, timeout=15)

    def test_rejects_login_node(self):
        result = self.run_guard({})
        self.assertEqual(result.returncode, 2)
        self.assertIn("Slurm GPU batch allocation", result.stderr)

    def test_rejects_cpu_allocation(self):
        result = self.run_guard({"SLURM_JOB_ID": "fixture"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("No Slurm GPU allocation", result.stderr)

    def test_rejects_missing_scratch(self):
        result = self.run_guard({"SLURM_JOB_ID": "fixture", "SLURM_JOB_GPUS": "0"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("absolute scratch directory", result.stderr)

    def test_submission_and_resume_guards(self):
        # All directories are shell-local; guards stop before any external service.
        prefix = 'd=$(mktemp -d); trap \'rm -rf -- "$d"\' EXIT\n'
        base = 'export SLURM_JOB_ID=fixture SLURM_JOB_GPUS=0 BTP_EXPERIMENT_ID=fixture\n'
        for settings, expected in [
            ('mkdir "$d/scratch" "$d/other"; export BTP_SCRATCH_ROOT="$d/scratch" SLURM_SUBMIT_DIR="$d/other"', "Submit only from scratch"),
            ('export BTP_SCRATCH_ROOT="$d" SLURM_SUBMIT_DIR="$d" BTP_RESUME=no', "BTP_RESUME must be 0 or 1"),
            ('export BTP_SCRATCH_ROOT="$d" SLURM_SUBMIT_DIR="$d" BTP_RESUME=0 BTP_RESULTS_ROOT="$d/results"', "persistent home/project storage"),
        ]:
            with self.subTest(expected=expected):
                result = subprocess.run([BASH, "-s"], text=True, capture_output=True,
                    input=prefix + base + settings + "\n" + SCRIPT.read_text(), timeout=15)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(expected, result.stderr)
