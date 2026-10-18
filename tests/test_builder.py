import shutil
import tempfile
import unittest

from pipeline.builder import build_candidate
from pipeline.candidate import CandidateSource
from pipeline.execution import run_program


class CandidateTests(unittest.TestCase):
    def test_defaults_filename(self):
        candidate = CandidateSource(language="python", source="print('ok')")
        self.assertEqual(candidate.filename, "main.py")

    def test_rejects_unsupported_language(self):
        with self.assertRaises(ValueError):
            CandidateSource(language="java", source="class Main {}")

    def test_rejects_path_traversal_filename(self):
        with self.assertRaises(ValueError):
            CandidateSource(
                language="python",
                filename="../main.py",
                source="print('x')",
            )


class BuilderTests(unittest.TestCase):
    def test_python_candidate_is_runnable(self):
        candidate = CandidateSource(
            language="python",
            source="import sys\nx=int(sys.stdin.read())\nprint(x*2)\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            build = build_candidate(candidate, tmp)
            self.assertTrue(build.success)
            self.assertIsNotNone(build.run_command)
            result = run_program(build.run_command, "4\n")
            self.assertTrue(result.succeeded)
            self.assertEqual(result.stdout, "8\n")

    @unittest.skipUnless(shutil.which("g++"), "g++ not installed")
    def test_cpp_candidate_builds_and_runs(self):
        candidate = CandidateSource(
            language="cpp",
            source=(
                "#include <iostream>\n"
                "int main(){ long long x; if(!(std::cin>>x)) return 1; "
                "std::cout << x*2 << '\\n'; }\n"
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            build = build_candidate(candidate, tmp)
            self.assertTrue(build.success, build.build_stderr)
            result = run_program(build.run_command, "7\n")
            self.assertTrue(result.succeeded)
            self.assertEqual(result.stdout, "14\n")

    @unittest.skipUnless(shutil.which("g++"), "g++ not installed")
    def test_cpp_compile_error_is_returned(self):
        candidate = CandidateSource(
            language="cpp",
            source="int main( { broken",
        )
        with tempfile.TemporaryDirectory() as tmp:
            build = build_candidate(candidate, tmp)
            self.assertFalse(build.success)
            self.assertIsNone(build.run_command)
            self.assertNotEqual(build.exit_code, 0)
            self.assertTrue(build.build_stderr)


if __name__ == "__main__":
    unittest.main()
