import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))
from scripts.extract_blocks import extract


class ExtractBlocksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def note(self, text):
        path = self.root / "note.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_preserves_empty_output_lines_and_reports_positions(self):
        path = self.note("```bash\nHGET catalog:item name\n```\n预期输出：\n```text\n\nPONG\n```\n")
        case = extract(path, {"bash"})[0]
        self.assertEqual(case["input_line"], 2)
        self.assertEqual(case["output_line"], 6)
        self.assertEqual(case["input"], "HGET catalog:item name\n")
        self.assertEqual(case["expected_output"], "\nPONG\n")

    def test_does_not_cross_an_intervening_fence(self):
        path = self.note("```bash\nPING\n```\n```python\nprint(1)\n```\n```text\n1\n```\n")
        self.assertIsNone(extract(path, {"bash"})[0]["expected_output"])

    def test_long_and_tilde_fences_keep_shorter_markers_as_content(self):
        path = self.note("````bash\n```\nPING\n````\n~~~txt\nPONG\n~~~\n")
        self.assertEqual(extract(path, {"bash"})[0]["input"], "```\nPING\n")
        self.assertEqual(extract(path, {"bash"})[0]["expected_output"], "PONG\n")

    def test_unclosed_fence_fails_instead_of_returning_partial_cases(self):
        with self.assertRaises(ValueError):
            extract(self.note("```sql\nSELECT 1;\n"), {"sql"})

    def test_only_selected_languages_are_extracted(self):
        path = self.note("```bash\nPING\n```\n```text\nPONG\n```\n```sql\nSELECT 1;\n```\n")
        cases = extract(path, {"sql"})
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["language"], "sql")
        self.assertIsNone(cases[0]["expected_output"])

    def test_cli_requires_explicit_language_and_never_executes(self):
        target = self.root / "must-not-exist"
        path = self.note(f"```bash\ntouch {target}\n```\n```text\n\n```\n")
        command = [sys.executable, str(SKILL_ROOT / "scripts/extract_blocks.py"), str(path)]
        missing = subprocess.run(command, capture_output=True, timeout=10)
        self.assertNotEqual(missing.returncode, 0)
        result = subprocess.run(command + ["--language", "bash"], capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)), 1)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
