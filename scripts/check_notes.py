#!/usr/bin/env python3
"""formal-docs 自检：编码、配置规则、人称、标题编号、围栏、空行、引号、行尾空白。

用法：
    python check_notes.py path/to/doc.md [more.md ...]
    python check_notes.py doc.md --config .formal-docs.json
    python check_notes.py doc.md --space        # 强制开启中英文空格检查
    python check_notes.py doc.md --no-space     # 强制关闭配置中的空格检查

按 ERROR / WARN / INFO 分级输出并带行号；存在 ERROR 时退出码为 1。
只做机械可查项；文字围栏会扫描、代码围栏会跳过。语气、密钥、路径/链接有效性与内容自足性仍需人工判断。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---- 规则与 Markdown 结构 ---------------------------------------------------

RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "default-rules.json"
DEFAULT_ALLOW = [r"INSERT\s+INTO", r"VALUES\s*\("]
INLINE_CODE = re.compile(r"`[^`]*`")
HTML_TAG = re.compile(r"<[^>]+>")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
HEADING_2 = re.compile(r"^##\s+(\d+)\.\s")
HEADING_3 = re.compile(r"^###\s+(\d+)\.(\d+)\s")


def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


class Finding:
    def __init__(self, level, line, kind, detail):
        self.level, self.line, self.kind, self.detail = level, line, kind, detail


def load_config(path_arg, doc_path: Path) -> dict:
    if path_arg:
        candidates = [Path(path_arg)]
        if not candidates[0].is_file():
            raise FileNotFoundError(f"显式指定的配置文件不存在：{candidates[0]}")
    else:
        candidates = [parent / ".formal-docs.json" for parent in [doc_path.parent, *doc_path.parent.parents]]

    for config_path in candidates:
        if not config_path.is_file():
            continue
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("配置根节点必须是 JSON 对象")
            return config
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"配置文件读取失败 {config_path}: {exc}") from exc
    return {}


def strip_inline(line: str) -> str:
    return INLINE_CODE.sub("``", line)


def first_h2_heading(lines: list[str]):
    """Return the first level-2 heading outside fenced blocks, if any."""
    fence_char = ""
    fence_length = 0
    for line in lines:
        match = FENCE.match(line)
        if match:
            marker, rest = match.groups()
            if not fence_char:
                fence_char, fence_length = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length and not rest.strip():
                fence_char, fence_length = "", 0
            continue
        if fence_char:
            continue
        clean = HTML_TAG.sub("", line)
        if clean.startswith("## ") and not clean.startswith("### "):
            return HEADING_2.match(clean)
    return None


def check_file(path: Path, cfg: dict, space: bool | None, rules: dict | None = None) -> list[Finding]:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    findings: list[Finding] = []
    rules = rules or load_rules()

    if "\ufffd" in text:
        n = text.count("\ufffd")
        findings.append(Finding("ERROR", 0, "编码", f"发现 {n} 个替换字符 U+FFFD，文件可能被写坏"))

    banned_setting = cfg.get("banned", [])
    if not isinstance(banned_setting, list):
        findings.append(Finding("WARN", 0, "配置", "banned 必须是字符串数组；该项已忽略"))
        banned_setting = []
    elif any(not isinstance(item, str) for item in banned_setting):
        findings.append(Finding("WARN", 0, "配置", "banned 中的非字符串项已忽略"))
    project_banned = [b for b in banned_setting if isinstance(b, str) and b]

    allow_setting = cfg.get("allow_line_patterns", [])
    if not isinstance(allow_setting, list):
        findings.append(Finding("WARN", 0, "配置", "allow_line_patterns 必须是正则字符串数组；该项已忽略"))
        allow_setting = []
    elif any(not isinstance(item, str) for item in allow_setting):
        findings.append(Finding("WARN", 0, "配置", "allow_line_patterns 中的非字符串项已忽略"))
    allow = DEFAULT_ALLOW + [p for p in allow_setting if isinstance(p, str) and p]
    try:
        allow_re = re.compile("|".join(f"(?:{p})" for p in allow)) if allow else None
    except re.error as exc:
        allow_re = None
        findings.append(Finding("WARN", 0, "配置", f"allow_line_patterns 正则无效：{exc}"))

    if space is None:
        space_setting = cfg.get("space_check", False)
        if not isinstance(space_setting, bool):
            findings.append(Finding("WARN", 0, "配置", "space_check 必须是布尔值；按 false 处理"))
            space_setting = False
        space = space_setting

    try:
        hard_rules = [(re.compile(item["pattern"]), item.get("suggestion", "调整或删除")) for item in rules["internal_error"]]
        context_rules = [(re.compile(item["pattern"]), item.get("suggestion", "检查语境")) for item in rules["context_warn"]]
        spoken_rules = [re.compile(re.escape(word)) for word in rules["spoken_warn"]]
        filler_rules = [re.compile(re.escape(word)) for word in rules["filler_info"]]
        pronoun_re = re.compile(rules.get("pronoun_pattern", "[你我您]"))
    except (KeyError, TypeError, re.error) as exc:
        findings.append(Finding("ERROR", 0, "规则配置", f"default-rules.json 格式或正则无效：{exc}"))
        return findings

    # 自动模式只在文档采用编号标题时启用；片段可用 first_heading_number 指定起始号。
    numbering = cfg.get("numbered_headings", "auto")
    if numbering != "auto" and not isinstance(numbering, bool):
        findings.append(Finding("WARN", 0, "配置", "numbered_headings 仅接受 auto / true / false；按 auto 处理"))
        numbering = "auto"
    first_numbered = first_h2_heading(lines)
    if numbering == "auto":
        numbering = first_numbered is not None
    try:
        first_heading_setting = cfg.get("first_heading_number", 1)
        if isinstance(first_heading_setting, bool) or not isinstance(first_heading_setting, (int, str)):
            raise ValueError("必须是正整数")
        expected_first = int(first_heading_setting)
        if expected_first < 1:
            raise ValueError("必须大于等于 1")
    except (TypeError, ValueError) as exc:
        findings.append(Finding("WARN", 0, "配置", f"first_heading_number 无效：{exc}；按 1 处理"))
        expected_first = 1
    heading_main = expected_first - 1
    heading_sub = 0

    fence_char = ""
    fence_length = 0
    fence_open_line = 0
    scan_text_fence = False
    prose_languages = {lang.lower() for lang in rules.get("prose_fence_languages", [])}
    blank_run = 0
    quote_styles: dict[str, list[int]] = {"straight": [], "curly": [], "corner": []}

    def scan_prose(line: str, line_no: int, *, in_text_fence: bool = False) -> None:
        prose = HTML_TAG.sub("", strip_inline(line))
        for rx, suggestion in hard_rules:
            match = rx.search(prose)
            if match:
                findings.append(Finding("ERROR", line_no, "内部用语", f"“{match.group(0)}” → {suggestion}"))
        for rx, suggestion in context_rules:
            match = rx.search(prose)
            if match:
                findings.append(Finding("WARN", line_no, "语境用语", f"“{match.group(0)}”：{suggestion}"))
        for rx in spoken_rules:
            match = rx.search(prose)
            if match:
                findings.append(Finding("WARN", line_no, "口播腔", f"“{match.group(0)}”"))
                break
        for rx in filler_rules:
            match = rx.search(prose)
            if match:
                findings.append(Finding("INFO", line_no, "套话", f"检查“{match.group(0)}”是否必要"))
                break
        for word in project_banned:
            if word in prose:
                findings.append(Finding("ERROR", line_no, "项目禁用词", f"“{word}”（按项目配置）"))

        # 人称只做提示：引用块、示例数据和配置允许行不扫描。
        is_quote = line.lstrip().startswith(">")
        is_allowed = bool(allow_re and allow_re.search(line))
        if not is_quote and not is_allowed:
            match = pronoun_re.search(prose)
            if match:
                findings.append(Finding("WARN", line_no, "人称", f"“{match.group(0)}”（引用/数据除外）"))

        if '"' in prose:
            quote_styles["straight"].append(line_no)
        if "“" in prose or "”" in prose:
            quote_styles["curly"].append(line_no)
        if "「" in prose or "」" in prose:
            quote_styles["corner"].append(line_no)

        if space and not in_text_fence:
            if re.search(r"[\u4e00-\u9fff][A-Za-z0-9]|[A-Za-z0-9][\u4e00-\u9fff]", prose):
                findings.append(Finding("INFO", line_no, "空格", "中英文/数字间可能缺少空格"))

    for i, line in enumerate(lines, start=1):
        fence_match = FENCE.match(line)
        if fence_match:
            marker, rest = fence_match.groups()
            if not fence_char:
                fence_char, fence_length, fence_open_line = marker[0], len(marker), i
                info = rest.strip().split(maxsplit=1)[0].lower() if rest.strip() else ""
                scan_text_fence = info in prose_languages
                if not info:
                    findings.append(Finding("INFO", i, "代码围栏", "未标注语言；代码片段可补充语言，纯文本示意可标注 text"))
            elif marker[0] == fence_char and len(marker) >= fence_length and not rest.strip():
                fence_char, fence_length, scan_text_fence = "", 0, False
                blank_run = 0
            elif scan_text_fence:
                scan_prose(line, i, in_text_fence=True)
            continue

        if fence_char:
            if scan_text_fence and line.strip():
                scan_prose(line, i, in_text_fence=True)
            continue

        if not line.strip():
            blank_run += 1
            if blank_run >= 2:
                findings.append(Finding("WARN", i, "空行", "连续空行（建议不超过 1 行）"))
            continue
        blank_run = 0

        if line != line.rstrip():
            findings.append(Finding("INFO", i, "行尾空白", "行尾有多余空白"))

        scan_prose(line, i)

        if numbering:
            clean = HTML_TAG.sub("", line)
            if clean.startswith("## ") and not clean.startswith("### ") and not HEADING_2.match(clean):
                findings.append(Finding("WARN", i, "编号", "本篇使用编号标题，但该一级标题没有编号"))
            hm = HEADING_2.match(clean)
            if hm:
                num = int(hm.group(1))
                if num != heading_main + 1:
                    findings.append(Finding("WARN", i, "编号", f"标题编号跳到 {num}（期望 {heading_main + 1}）"))
                heading_main, heading_sub = num, 0
            hs = HEADING_3.match(clean)
            if hs:
                parent, sub = int(hs.group(1)), int(hs.group(2))
                if sub != heading_sub + 1 or parent != heading_main:
                    findings.append(Finding("WARN", i, "编号", f"子标题 {parent}.{sub} 与前序不一致"))
                heading_sub = sub

    if fence_char:
        findings.append(Finding("ERROR", fence_open_line, "围栏", "代码围栏未闭合"))

    used_quote_styles = [(name, locations[0]) for name, locations in quote_styles.items() if locations]
    if len(used_quote_styles) > 1:
        detail = "、".join(f"{name}(行 {line})" for name, line in used_quote_styles)
        findings.append(Finding("INFO", used_quote_styles[0][1], "引号", f"引号风格混用：{detail}"))

    return findings


def main() -> int:
    try:  # Windows 控制台默认可能是 GBK，统一按 UTF-8 输出
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="formal-docs 文档自检")
    ap.add_argument("files", nargs="+", help="待检查的 Markdown 文件")
    ap.add_argument("--config", help="项目配置 .formal-docs.json 路径")
    space_group = ap.add_mutually_exclusive_group()
    space_group.add_argument("--space", dest="space", action="store_true", help="强制启用中英文空格检查")
    space_group.add_argument("--no-space", dest="space", action="store_false", help="强制关闭中英文空格检查")
    ap.set_defaults(space=None)
    args = ap.parse_args()

    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    total: dict[str, int] = {"ERROR": 0, "WARN": 0, "INFO": 0}

    try:
        rules = load_rules()
    except Exception as exc:  # noqa: BLE001
        print(f"[error] 默认规则文件读取失败：{exc}", file=sys.stderr)
        return 1

    for f in args.files:
        p = Path(f)
        if p.is_dir():
            targets = sorted(p.rglob("*.md"))
            if not targets:
                print(f"[warn] 目录下没有 Markdown 文件：{p}", file=sys.stderr)
        else:
            targets = [p]
        for p in targets:
            if not p.is_file():
                print(f"[error] 文件不存在：{p}", file=sys.stderr)
                total["ERROR"] += 1
                continue
            try:
                cfg = load_config(args.config, p)
                findings = check_file(p, cfg, args.space, rules)
            except OSError as exc:
                findings = [Finding("ERROR", 0, "读取", f"无法读取文件：{exc}")]
            except ValueError as exc:
                findings = [Finding("ERROR", 0, "配置", str(exc))]
            findings.sort(key=lambda x: (order[x.level], x.line))
            print(f"\n=== {p} ===")
            if not findings:
                print("  通过：未发现机械问题")
            for x in findings:
                total[x.level] += 1
                loc = f"L{x.line:<4}" if x.line else "     "
                print(f"  {x.level:<5} {loc} [{x.kind}] {x.detail}")

    print(f"\n合计：ERROR {total['ERROR']} / WARN {total['WARN']} / INFO {total['INFO']}")
    return 1 if total["ERROR"] else 0


if __name__ == "__main__":
    sys.exit(main())
