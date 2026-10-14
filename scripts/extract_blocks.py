#!/usr/bin/env python3
"""Extract explicitly selected fenced inputs and following raw outputs; never execute."""
import argparse
import json
import re
import sys
from pathlib import Path

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def fenced_blocks(path):
    """Read closed Markdown fences and preserve content whitespace and line numbers."""
    blocks, opened, content = [], None, []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(keepends=True), 1):
        match = FENCE.match(line.rstrip("\r\n"))
        if opened is None:
            if match:
                marker, info = match.groups()
                opened = {"marker": marker[0], "length": len(marker), "fence_line": number,
                          "line": number + 1, "language": info.strip().split(maxsplit=1)[0].lower() if info.strip() else ""}
                content = []
        elif match and match.group(1)[0] == opened["marker"] and len(match.group(1)) >= opened["length"] and not match.group(2).strip():
            blocks.append({"line": opened["line"], "language": opened["language"], "content": "".join(content)})
            opened = None
        else:
            content.append(line)
    if opened is not None:
        raise ValueError(f"{path}:{opened['fence_line']}: 代码围栏未闭合")
    return blocks


def extract(path, languages, output_languages=("text", "txt", "output")):
    """Pair only the next fence; do not cross an intervening code or prose fence."""
    blocks, cases = fenced_blocks(path), []
    for index, block in enumerate(blocks):
        if block["language"] not in languages:
            continue
        following = blocks[index + 1] if index + 1 < len(blocks) else None
        output = following if following and following["language"] in output_languages else None
        cases.append({"source": str(path), "input_line": block["line"], "language": block["language"],
                      "input": block["content"], "output_line": output["line"] if output else None,
                      "expected_output": output["content"] if output else None})
    return cases


def main():
    """Print extraction results as JSON; errors exit nonzero without partial output."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description="抽取命令与预期输出（只读，不执行）")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--language", action="append", required=True, help="显式选择输入围栏语言，可重复")
    parser.add_argument("--output-language", action="append", help="输出围栏语言，默认 text/txt/output")
    args = parser.parse_args()
    try:
        cases = []
        for file in args.files:
            cases.extend(extract(Path(file), {v.lower() for v in args.language},
                                 {v.lower() for v in args.output_language} if args.output_language else ("text", "txt", "output")))
        print(json.dumps(cases, ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
