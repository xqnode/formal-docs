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

    def test_scans_markdown_fences_but_skips_code_fences(self):
        note = self.write_note(
            "## 1. 标题\n"
            "```markdown\n讲解点：你可以运行这个例子。\n```\n"
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



    def test_h1_forms_are_errors_with_source_lines(self):
        for text, line in [("# 标题\n", 1), ("  # 标题\n", 1), ("#\n", 1),
                           ("<H1 class='title'>标题</H1>\n", 1),
                           ("标题\n====\n", 2), ("> # 引用标题\n", 1),
                           ("<h1\nclass='title'>标题</h1>\n", 1)]:
            with self.subTest(text=text):
                hits = [f for f in check_file(self.write_note(text), {}, None, self.rules) if f.kind == "H1"]
                self.assertTrue(hits)
                self.assertEqual(hits[0].level, "ERROR")
                self.assertEqual(hits[0].line, line)

    def test_heading_examples_and_comments_do_not_trigger_h1(self):
        text = ("```markdown\n# 示例\n<h1>示例</h1>\n标题\n====\n```\n"
                "~~~text\n# 原始输出\n~~~\n"
                "使用 `<h1>` 和 `# 标题` 描述语法。\n"
                "<!--\n<h1>注释</h1>\n-->\n"
                "    # 缩进代码\n## 正常标题\n#没有空格\n")
        self.assertFalse(any(f.kind == "H1" for f in check_file(self.write_note(text), {}, None, self.rules)))

    def test_setext_does_not_bridge_fences_or_blank_lines(self):
        for text in ["正文\n\n====\n", "正文\n```text\n输出\n```\n====\n", "## 标题\n====\n"]:
            with self.subTest(text=text):
                self.assertFalse(any(f.kind == "H1" for f in check_file(self.write_note(text), {}, None, self.rules)))

    def test_raw_output_is_preserved_without_prose_findings(self):
        for language in ["text", "txt", "output", "plain", "prompt"]:
            with self.subTest(language=language):
                note = self.write_note(f"```{language}\n我的商品\n其实\n讲解点\n<h1>日志</h1>\n```\n")
                self.assertEqual(check_file(note, {}, None, self.rules), [])
        unclosed = self.write_note("```text\n我的输出\n")
        self.assertTrue(any(f.kind == "围栏" and f.level == "ERROR" for f in check_file(unclosed, {}, None, self.rules)))

    def test_review_hints_are_opt_in_and_non_authoritative(self):
        text = ("## 操作\n```bash\nGET catalog:known\n```\n"
                "[命令说明](https://example.com/docs)\n"
                "## 排错\n检查 `GET`、`catalog:known` 和 `catalog:new`。\n"
                "`WRONGTYPE` 是本段新介绍的错误示例。\n"
                "第一篇的 `catalog:previous`。\n")
        note = self.write_note(text)
        self.assertFalse(any(f.kind in {"排错引用", "外链标注"} for f in check_file(note, {}, None, self.rules)))
        findings = check_file(note, {"check_link_labels": True, "check_troubleshooting_identifiers": True}, None, self.rules)
        review = [f for f in findings if f.kind in {"排错引用", "外链标注"}]
        self.assertEqual(len(review), 3)
        self.assertTrue(all(f.level == "INFO" for f in review))
        self.assertFalse(any('catalog:known' in f.detail or 'catalog:previous' in f.detail for f in review))

    def test_external_link_hint_skips_code_and_labelled_sources(self):
        note = self.write_note("[官方说明（英文）](https://example.com/docs)\n```text\n[原始输出](https://example.com/)\n```\n")
        self.assertFalse(any(f.kind == "外链标注" for f in check_file(note, {"check_link_labels": True}, None, self.rules)))

    def test_cli_returns_nonzero_for_h1(self):
        note = self.write_note("# 标题\n")
        result = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts/check_notes.py"), str(note)], capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[H1]", result.stdout)



    def test_h1_inside_list_containers_is_detected(self):
        for text in ["- # 步骤\n", "1. # 步骤\n", "- 条目\n  # 步骤\n", "- 条目\n  - 子条目\n    # 步骤\n", "- 标题\n  ====\n"]:
            with self.subTest(text=text):
                self.assertTrue(any(f.kind == "H1" for f in check_file(self.write_note(text), {}, None, self.rules)))

    def test_indented_list_code_and_root_underline_are_not_h1(self):
        for text in ["- 条目\n\n      # 缩进代码\n", "-     # 缩进代码\n", "- 条目\n====\n", "> 引用\n====\n"]:
            with self.subTest(text=text):
                self.assertFalse(any(f.kind == "H1" for f in check_file(self.write_note(text), {}, None, self.rules)))



    def test_quoted_fenced_examples_do_not_trigger_h1(self):
        text = "> ```html\n> <h1>示例</h1>\n> ```\n> ```text\n> 我的商品\n> 其实\n> ```\n"
        self.assertEqual(check_file(self.write_note(text), {}, None, self.rules), [])

    def test_list_state_does_not_leak_into_a_new_quote_container(self):
        note = self.write_note("- 条目\n>     # 引用中的缩进代码\n")
        self.assertFalse(any(f.kind == "H1" for f in check_file(note, {}, None, self.rules)))


if __name__ == "__main__":
    unittest.main()
