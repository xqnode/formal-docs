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

    def test_instructional_we_is_not_spoken_or_person_warning(self):
        note = self.write_note("从这一篇开始，我们来学习 MySQL。\n我来演示。\n讲解点：操作步骤。\n")
        findings = check_file(note, {"person_style": "instructional"}, None, self.rules)
        self.assertFalse(any(x.line == 1 and x.kind in {"人称", "口播腔"} for x in findings))
        self.assertTrue(any(x.line == 2 and x.kind == "人称" for x in findings))
        self.assertTrue(any(x.line == 3 and x.level == "ERROR" for x in findings))

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

    def test_list_fenced_examples_preserve_code_and_source_lines(self):
        for text in [
            "- ```html\n  <h1>示例</h1>\n  ```\n",
            "1. ~~~html\n   <h1>示例</h1>\n   ~~~\n",
            "- 条目\n  - ```html\n    <h1>示例</h1>\n    ```\n",
            "> - ```html\n>   <h1>示例</h1>\n>   ```\n",
            "- > ```html\n  > <h1>示例</h1>\n  > ```\n",
        ]:
            with self.subTest(text=text):
                findings = check_file(self.write_note(text + "# 正文标题\n"), {}, None, self.rules)
                self.assertEqual([(f.kind, f.line) for f in findings],
                                 [("H1", len(text.splitlines()) + 1)])

    def test_list_markdown_fences_still_scan_prose_but_not_headings(self):
        note = self.write_note("- ```markdown\n  # 示例标题\n  讲解点：你\n  ```\n")
        findings = check_file(note, {}, None, self.rules)
        self.assertTrue(any(f.kind == "内部用语" and f.line == 3 for f in findings))
        self.assertTrue(any(f.kind == "人称" and f.line == 3 for f in findings))
        self.assertFalse(any(f.kind in {"H1", "围栏"} for f in findings))

    def test_unclosed_list_fence_reports_actual_opening_line(self):
        note = self.write_note("## 操作\n- ```html\n  <h1>示例</h1>\n")
        findings = check_file(note, {}, None, self.rules)
        self.assertEqual([(f.kind, f.line) for f in findings], [("围栏", 2)])

    def test_list_markers_inside_code_do_not_close_fence(self):
        note = self.write_note("- ```text\n  - ```\n  <h1>示例</h1>\n  ```\n")
        self.assertEqual(check_file(note, {}, None, self.rules), [])

    def test_list_fences_do_not_enable_numbering_or_link_hints(self):
        note = self.write_note(
            "- ```text\n  ## 99. 示例\n  [示例](https://example.com/)\n  ```\n## Overview\n"
        )
        findings = check_file(note, {"check_link_labels": True}, None, self.rules)
        self.assertEqual(findings, [])

    def test_cli_relative_document_discovers_parent_project_config(self):
        note = self.write_note("PRIVATE_TERM\n你可以操作。\n", "docs/note.md")
        (self.root / ".formal-docs.json").write_text(
            json.dumps({"banned": ["PRIVATE_TERM"], "person_style": "instructional"}),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-B", str(SKILL_ROOT / "scripts/check_notes.py"), "note.md"],
            cwd=note.parent, capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("[项目禁用词]", result.stdout)
        self.assertNotIn("[人称]", result.stdout)

    def test_quote_markers_inside_root_fences_are_literal(self):
        for text in [
            "```text\n> ```\n# literal title\n讲解点：原始输出\n```\n",
            "~~~text\n> ~~~\n<h1>示例</h1>\n~~~\n",
        ]:
            with self.subTest(text=text):
                self.assertEqual(check_file(self.write_note(text), {}, None, self.rules), [])

    def test_container_exit_ends_fence_without_swallowing_prose(self):
        for prefix in ["> ```text\n> literal\n", "- ```text\n  literal\n",
                       "> - ```text\n>   literal\n"]:
            with self.subTest(prefix=prefix):
                findings = check_file(
                    self.write_note(prefix + "# Real title\n讲解点：正文\n"), {}, None, self.rules,
                )
                self.assertTrue(any(f.kind == "H1" and f.line == 3 for f in findings))
                self.assertTrue(any(f.kind == "内部用语" and f.line == 4 for f in findings))
                self.assertFalse(any(f.kind == "围栏" for f in findings))

    def test_indented_fence_markers_do_not_swallow_following_prose(self):
        for indent in ["    ", "\t"]:
            with self.subTest(indent=repr(indent)):
                note = self.write_note(indent + "```text\n\n# Real title\n讲解点：正文\n")
                findings = check_file(note, {}, None, self.rules)
                self.assertTrue(any(f.kind == "H1" and f.line == 3 for f in findings))
                self.assertTrue(any(f.kind == "内部用语" and f.line == 4 for f in findings))
                self.assertFalse(any(f.kind == "围栏" for f in findings))

    def test_three_space_fences_and_list_continuation_remain_supported(self):
        for text in ["   ```html\n<h1>示例</h1>\n   ```\n",
                     "- 操作\n\n  ```html\n  <h1>示例</h1>\n  ```\n"]:
            with self.subTest(text=text):
                self.assertEqual(check_file(self.write_note(text), {}, None, self.rules), [])

    def test_literal_quote_fence_does_not_leak_numbering_or_link_hints(self):
        note = self.write_note(
            "```text\n> ```\n## 99. 示例\n[示例](https://example.com/)\n```\n## Overview\n"
        )
        self.assertEqual(check_file(note, {"check_link_labels": True}, None, self.rules), [])

    def test_empty_list_item_retains_fence_container(self):
        for marker, indent in [("-", "  "), ("1.", "   ")]:
            with self.subTest(marker=marker):
                text = f"{marker}\n{indent}```text\n{indent}output\n# Real title\n讲解点：正文\n"
                findings = check_file(self.write_note(text), {}, None, self.rules)
                self.assertTrue(any(f.kind == "H1" and f.line == 4 for f in findings))
                self.assertTrue(any(f.kind == "内部用语" and f.line == 5 for f in findings))
                self.assertFalse(any(f.kind == "围栏" for f in findings))

    def test_indentation_cannot_interrupt_an_existing_paragraph(self):
        continuation = self.write_note("正文。\n    讲解点：你\n")
        findings = check_file(continuation, {}, None, self.rules)
        self.assertTrue(any(f.kind == "内部用语" and f.line == 2 for f in findings))
        self.assertTrue(any(f.kind == "人称" and f.line == 2 for f in findings))
        separated = self.write_note("正文。\n\n    讲解点：你\n")
        self.assertEqual(check_file(separated, {}, None, self.rules), [])

    def test_heading_underlines_and_thematic_breaks_end_paragraphs(self):
        for prefix in ["---\n", "* * *\n", "___\n", "标题\n---\n", "标题\n====\n"]:
            with self.subTest(prefix=prefix):
                text = prefix + "    讲解点：你\n"
                findings = check_file(self.write_note(text), {}, None, self.rules)
                self.assertFalse(any(f.kind in {"内部用语", "人称"} for f in findings))

    def test_h1_in_mixed_list_and_quote_containers_is_detected(self):
        for text, expected_line in [
            ("- > # Real title\n", 1),
            ("1. > # Real title\n", 1),
            ("> - > <h1>标题</h1>\n", 1),
            ("- > 标题\n  > ====\n", 2),
        ]:
            with self.subTest(text=text):
                findings = check_file(self.write_note(text), {}, None, self.rules)
                self.assertEqual([(f.kind, f.line) for f in findings], [("H1", expected_line)])

    def test_mixed_container_code_is_not_misreported_as_h1(self):
        for text in ["- >     # literal title\n", "- > ```html\n  > <h1>示例</h1>\n  > ```\n",
                     "- > 标题\n====\n"]:
            with self.subTest(text=text):
                self.assertFalse(any(f.kind == "H1" for f in check_file(self.write_note(text), {}, None, self.rules)))

    def test_comment_fences_cannot_swallow_following_prose(self):
        for comment in ["<!--\n```text\n# hidden title\n-->\n",
                        "<!--\n~~~markdown\n讲解点：隐藏内容\n-->\n",
                        "<!-- ```text -->\n"]:
            with self.subTest(comment=comment):
                note = self.write_note(comment + "# Real title\n讲解点：正文\n")
                findings = check_file(note, {}, None, self.rules)
                next_line = len(comment.splitlines()) + 1
                self.assertEqual([(f.kind, f.line) for f in findings],
                                 [("H1", next_line), ("内部用语", next_line + 1)])

    def test_comment_blocks_in_containers_end_with_their_container(self):
        for prefix in ["- <!--\n  ```text\n", "> <!--\n> ```text\n",
                       "- > <!--\n  > ```text\n"]:
            with self.subTest(prefix=prefix):
                note = self.write_note(prefix + "# Real title\n讲解点：正文\n")
                findings = check_file(note, {}, None, self.rules)
                self.assertEqual([(f.kind, f.line) for f in findings],
                                 [("H1", 3), ("内部用语", 4)])

    def test_comment_examples_in_code_are_literal(self):
        for text in ["```text\n<!--\n```\n# Real title\n",
                     "    <!--\n\n# Real title\n",
                     "`<!--`\n# Real title\n"]:
            with self.subTest(text=text):
                findings = check_file(self.write_note(text), {}, None, self.rules)
                self.assertTrue(any(f.kind == "H1" and f.line == len(text.splitlines()) for f in findings))
                self.assertFalse(any(f.kind == "围栏" for f in findings))

    def test_comments_do_not_enable_numbering_or_link_hints(self):
        text = "<!--\n```text\n## 99. 隐藏标题\n[示例](https://example.com/)\n-->\n## Overview\n"
        findings = check_file(self.write_note(text), {"check_link_labels": True}, None, self.rules)
        self.assertEqual(findings, [])

    def test_unclosed_html_comment_does_not_open_a_fence(self):
        note = self.write_note("<!--\n```text\n# hidden title\n讲解点：隐藏内容\n")
        self.assertEqual(check_file(note, {}, None, self.rules), [])

    def test_comment_block_terminator_clears_prior_inline_comment_state(self):
        note = self.write_note("说明 <!--\n<!-- 注释 -->\n# Real title\n")
        findings = check_file(note, {}, None, self.rules)
        self.assertEqual([(f.kind, f.line) for f in findings], [("H1", 3)])

    def test_setext_cannot_cross_distinct_list_items_with_identical_shapes(self):
        for text in ["- > title\n- > ====\n", "1. > title\n2. > ====\n",
                     "- title\n- ====\n"]:
            with self.subTest(text=text):
                self.assertFalse(any(f.kind == "H1" for f in check_file(self.write_note(text), {}, None, self.rules)))
        continuation = self.write_note("- > title\n  > ====\n")
        findings = check_file(continuation, {}, None, self.rules)
        self.assertEqual([(f.kind, f.line) for f in findings], [("H1", 2)])


if __name__ == "__main__":
    unittest.main()
