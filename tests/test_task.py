import json
from pathlib import Path
import tempfile
import unittest

from pipeline.task import BenchmarkTask


class TaskTests(unittest.TestCase):
    def test_loads_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "spec.md").write_text("specification", encoding="utf-8")
            config = {
                "name": "double",
                "specification": "spec.md",
                "reference": {
                    "command": ["python3", "blackbox.py"],
                    "cwd": ".",
                },
                "input_format": "one integer",
                "output_format": "one integer",
                "timeout_seconds": 1.5,
            }
            path = root / "task.json"
            path.write_text(json.dumps(config), encoding="utf-8")

            task = BenchmarkTask.from_json(path)

            self.assertEqual(task.name, "double")
            self.assertEqual(task.specification_path, (root / "spec.md").resolve())
            self.assertEqual(task.reference_cwd, root.resolve())
            self.assertEqual(task.reference_command, ("python3", "blackbox.py"))
            self.assertEqual(task.read_specification(), "specification")
            self.assertEqual(task.timeout_seconds, 1.5)

    def test_rejects_unsafe_task_name(self):
        with self.assertRaises(ValueError):
            BenchmarkTask(
                name="../bad",
                specification_path=Path("spec.md"),
                reference_command=("program",),
                reference_cwd=Path("."),
                input_format="input",
                output_format="output",
            )


if __name__ == "__main__":
    unittest.main()
