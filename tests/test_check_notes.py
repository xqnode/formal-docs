import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.check_notes import check_file, load_config, load_rules


class CheckNotesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.rules = load_rules()

    def tearDown(self):
        self.temp.cleanup()

    def write_note(self, text: str, relative: str = "note.md") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_scans_text_fences_but_skips_code_fences(self):
        note = self.write_note(
            "## 1. 标题\n"
            "```text\n讲解点：你可以运行这个例子。\n```\n"
            "```python\n# 讲解点：你\n```\n"
        )
        findings = check_file(note, {}, None, self.rules)
        categories = [item.kind for item in findings]
        self.assertIn("内部用语", categories)
        self.assertIn("人称", categories)
        self.assertEqual(sum(item.kind == "内部用语" for item in findings), 1)
        self.assertEqual(sum(item.kind == "人称" for item in findings), 1)

    def test_quote_and_data_exemptions_apply_to_pronouns(self):
        note = self.write_note(
            "## 1. 标题\n"
            "> 你和我来自引用内容。\n"
            "INSERT INTO `t` VALUES ('你');\n"
            "正文里避免你我称呼。\n"
        )
        findings = check_file(note, {}, None, self.rules)
        pronouns = [item for item in findings if item.kind == "人称"]
        self.assertEqual(len(pronouns), 1)
        self.assertEqual(pronouns[0].line, 4)

    def test_context_sensitive_terms_are_warnings_not_errors(self):
        note = self.write_note("## 1. 标题\n本集可敲可不敲。\n")
        findings = check_file(note, {}, None, self.rules)
        levels = [item.level for item in findings if item.kind == "语境用语"]
        self.assertEqual(levels, ["WARN", "WARN"])

    def test_lesson_sequencing_terms_are_warnings(self):
        note = self.write_note("## 1. 标题\n先讲第一个道理：只读是刻意的。\n")
        findings = check_file(note, {}, None, self.rules)
        hits = [item for item in findings if item.kind == "语境用语"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].level, "WARN")

    def test_plain_fence_is_treated_as_code_not_prose(self):
        note = self.write_note("## 1. 标题\n```plain\nDATABASE_URL=你的密码\n```\n")
        findings = check_file(note, {}, None, self.rules)
        self.assertNotIn("人称", [item.kind for item in findings])

    def test_html_attribute_quotes_are_ignored(self):
        note = self.write_note('## <font style="color:red">1. 标题</font>\n正文。\n')
        findings = check_file(note, {}, None, self.rules)
        self.assertNotIn("引号", [item.kind for item in findings])

    def test_finds_project_config_in_parent_directory(self):
        config = self.root / ".formal-docs.json"
        config.write_text(json.dumps({"banned": ["PRIVATE_TERM"]}), encoding="utf-8")
        note = self.write_note("## 1. 标题\nPRIVATE_TERM\n", "docs/note.md")
        cfg = load_config(None, note)
        findings = check_file(note, cfg, None, self.rules)
        self.assertIn("项目禁用词", [item.kind for item in findings])

    def test_explicit_missing_config_fails_loudly(self):
        note = self.write_note("## 1. 标题\n")
        with self.assertRaises(FileNotFoundError):
            load_config(self.root / "missing.json", note)

    def test_space_check_uses_config_and_cli_can_override(self):
        note = self.write_note("## 1. 标题\n中文API缺少空格。\n")
        cfg = {"space_check": True}
        enabled = check_file(note, cfg, None, self.rules)
        disabled = check_file(note, cfg, False, self.rules)
        self.assertIn("空格", [item.kind for item in enabled])
        self.assertNotIn("空格", [item.kind for item in disabled])

    def test_numbered_heading_auto_mode_handles_full_docs_and_fragments(self):
        full = self.write_note("## 1. 第一节\n## 3. 跳号\n")
        fragment = self.write_note("## 3. 摘录\n", "fragment.md")
        unnumbered = self.write_note("## Overview\n", "plain.md")
        full_findings = check_file(full, {}, None, self.rules)
        fragment_findings = check_file(fragment, {"first_heading_number": 3}, None, self.rules)
        plain_findings = check_file(unnumbered, {}, None, self.rules)
        self.assertIn("编号", [item.kind for item in full_findings])
        self.assertNotIn("编号", [item.kind for item in fragment_findings])
        self.assertNotIn("编号", [item.kind for item in plain_findings])

    def test_heading_examples_inside_fences_do_not_control_auto_mode(self):
        note = self.write_note("```markdown\n## 9. 示例\n```\n## Overview\n")
        findings = check_file(note, {}, None, self.rules)
        self.assertNotIn("编号", [item.kind for item in findings])

    def test_quote_style_check_includes_corner_quotes(self):
        note = self.write_note('## 1. 标题\n直引号 "文本" 与中文引号「文本」。\n')
        findings = check_file(note, {}, None, self.rules)
        self.assertIn("引号", [item.kind for item in findings])

    def test_unclosed_tilde_fence_is_reported(self):
        note = self.write_note("## 1. 标题\n~~~python\nprint('x')\n")
        findings = check_file(note, {}, None, self.rules)
        self.assertIn("围栏", [item.kind for item in findings])

    def test_instructional_style_keeps_reader_address_but_warns_first_person(self):
        note = self.write_note("你可以保存文件。\n您可以关闭窗口。\n我来演示。\n")
        findings = check_file(note, {"person_style": "instructional"}, None, self.rules)
        self.assertEqual([x.line for x in findings if x.kind == "人称"], [3])

    def test_preserve_style_does_not_disable_internal_term_checks(self):
        note = self.write_note("你和我保留原称呼。\n讲解点：复现步骤。\n")
        findings = check_file(note, {"person_style": "preserve"}, None, self.rules)
        self.assertNotIn("人称", [x.kind for x in findings])
        self.assertTrue(any(x.kind == "内部用语" and x.level == "ERROR" for x in findings))

    def test_invalid_person_style_warns_and_uses_neutral_default(self):
        note = self.write_note("你可以保存文件。\n")
        for value in ("unknown", [], None):
            with self.subTest(value=value):
                findings = check_file(note, {"person_style": value}, None, self.rules)
                self.assertIn("配置", [x.kind for x in findings])
                self.assertIn("人称", [x.kind for x in findings])

    def test_person_style_argument_overrides_project_config(self):
        note = self.write_note("你可以保存文件。\n")
        findings = check_file(note, {"person_style": "neutral"}, None, self.rules,
                              person_style="instructional")
        self.assertNotIn("人称", [x.kind for x in findings])

    def test_bad_allow_regex_preserves_other_valid_and_default_exemptions(self):
        note = self.write_note("INSERT INTO t VALUES ('你');\n引用原文：你\n正文：你\n")
        findings = check_file(note, {"allow_line_patterns": ["^引用原文：", "["]}, None, self.rules)
        self.assertEqual([x.line for x in findings if x.kind == "人称"], [3])
        self.assertTrue(any(x.kind == "配置" and x.level == "WARN" for x in findings))

    def test_multiple_backtick_inline_code_is_not_scanned_as_prose(self):
        note = self.write_note('使用 ``print("你"); value = `x` `` 中的表达式。\n')
        findings = check_file(note, {}, None, self.rules)
        self.assertNotIn("人称", [x.kind for x in findings])

    def test_unclosed_inline_code_does_not_hide_prose(self):
        note = self.write_note("未闭合的 `代码后面仍然有你。\n")
        findings = check_file(note, {}, None, self.rules)
        self.assertIn("人称", [x.kind for x in findings])

    def test_utf8_bom_does_not_break_heading_sequence_detection(self):
        note = self.write_note("\ufeff## 1. 开始\n## 2. 继续\n")
        findings = check_file(note, {}, None, self.rules)
        self.assertNotIn("编号", [x.kind for x in findings])

    def test_two_spaces_for_markdown_line_break_are_preserved(self):
        note = self.write_note("合法换行。  \n多余空白。 \n")
        findings = check_file(note, {}, None, self.rules)
        self.assertEqual([x.line for x in findings if x.kind == "行尾空白"], [2])

    def test_zero_based_heading_number_is_explicitly_supported(self):
        note = self.write_note("## 0. 前置说明\n## 1. 操作\n")
        findings = check_file(note, {"first_heading_number": 0}, None, self.rules)
        self.assertFalse(any(x.kind in {"编号", "配置"} for x in findings))

    def test_timeline_term_requires_context_instead_of_being_an_error(self):
        note = self.write_note("根据事件时间绘制时间轴。\n")
        findings = check_file(note, {}, None, self.rules)
        self.assertFalse(any(x.level == "ERROR" for x in findings))
        self.assertIn("语境用语", [x.kind for x in findings])


    def test_cli_person_style_overrides_discovered_config(self):
        note = self.write_note("你可以保存文件。\n")
        (self.root / ".formal-docs.json").write_text(
            json.dumps({"person_style": "neutral"}), encoding="utf-8",
        )
        command = [sys.executable, str(SKILL_ROOT / "scripts/check_notes.py"), str(note)]
        default = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=10)
        override = subprocess.run(command + ["--person-style", "instructional"],
                                  capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(default.returncode, 0)
        self.assertEqual(override.returncode, 0)
        self.assertIn("[人称]", default.stdout)
        self.assertNotIn("[人称]", override.stdout)


if __name__ == "__main__":
    unittest.main()
