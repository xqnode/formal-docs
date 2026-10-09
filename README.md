# formal-docs

一个给 AI 编码助手用的中文文档写作与审稿技能：把**面向内部或口播**的内容，改写成**面向读者**的正式中文文档，并带一个可自动运行的检查器。

## 它解决什么

内部讲稿、录制脚本、口播整理稿里常带着读者看不懂的东西：

* 内部流程用语（“讲解点”“带敲提示”“不敲”“本集”“讲解 3~5 分钟”）；
* 口播腔（“我们来看一下”“很简单”“你会发现”）；
* 人称代词（你 / 我 / 您 / 大家）；
* 对内部产物的称呼（各项目自定义）；
* 排版问题（中英文空格、引号混用、连续空行）。

本技能把这些整理成一套可复用的规则，并提供脚本机械校验。

## 组成

```
formal-docs/
  SKILL.md                        # 触发条件、工作流、八组规则
  references/
    banned-phrases.md             # 禁用词分组与替换建议
    default-rules.json            # 检查器的通用扫描规则
    structure-template.md         # 文档骨架
    examples.md                   # before → after 对照
  scripts/
    check_notes.py                # 自检脚本
  tests/
    test_check_notes.py           # 回归测试
```

## 安装

把 `formal-docs/` 放到助手的技能目录。通用位置：

* `~/.agents/skills/formal-docs/`
* `~/.claude/skills/formal-docs/`
* `~/.config/opencode/skills/formal-docs/`（OpenCode）
* 项目内：`.opencode/skills/formal-docs/`

技能 ID 取目录名 `formal-docs`。

## 使用

在对话里直接描述任务（会自动触发），或显式点名：

```
@formal-docs 审一下 docs/某笔记.md
```

## 自检脚本

```bash
python scripts/check_notes.py docs/note.md
```

输出按 `ERROR / WARN / INFO` 分级并带行号，有 ERROR 时退出码为 1。

常用参数：

```bash
python scripts/check_notes.py docs/          # 目录内所有 .md
python scripts/check_notes.py docs/note.md --space      # 强制检查中英文空格
python scripts/check_notes.py docs/note.md --no-space   # 强制关闭
python scripts/check_notes.py docs/note.md --config .formal-docs.json
```

检查项：编码损坏、配置用语、人称、可选标题编号、代码围栏配对与语言、连续空行、引号风格混用、行尾空白、可选的中英文空格。文字围栏（`text` / `markdown`）会扫描，代码围栏会跳过。密钥、路径/链接有效性、语气仍需人工判断。

## 项目配置

在项目根放 `.formal-docs.json`，脚本会从文档目录向上自动查找：

```json
{
  "banned": ["仅内部使用的模块名", "对照版"],
  "allow_line_patterns": ["INSERT INTO", "VALUES \\("],
  "person_style": "neutral",
  "space_check": false,
  "numbered_headings": "auto",
  "first_heading_number": 1
}
```

人称策略可用 `--person-style neutral|instructional|preserve` 覆盖项目配置；默认保持中性文风，操作教程可允许第二人称。详细配置见 `references/banned-phrases.md`。结构按受众和项目约定选择，不强制套固定骨架。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 许可

MIT
