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
  SKILL.md                        # 核心约束、工作流与按需读取入口
  references/
    banned-phrases.md             # 禁用词分组与替换建议
    default-rules.json            # 检查器的通用扫描规则
    structure-template.md         # 文档骨架
    examples.md                   # before → after 对照
    course-notes.md               # 初学者系列实操课约定
    python-tutorials.md           # Python 环境与命令
    command-validation.md         # Redis / SQL / shell 验证流程
    diagrams.md                   # 图解细节
  scripts/
    check_notes.py                # 自检脚本
    extract_blocks.py             # 只读抽取命令与输出，不执行
  tests/
    test_check_notes.py           # 回归测试
    test_extract_blocks.py        # 抽取工具回归测试
```

## 安装

把 `formal-docs/` 放到助手的技能目录。通用位置：

* `~/.agents/skills/formal-docs/`
* `~/.claude/skills/formal-docs/`
* `~/.config/opencode/skills/formal-docs/`（OpenCode）
* 项目内：`.opencode/skills/formal-docs/`

技能 ID 取目录名 `formal-docs`。

本机同时保留 `~/.agents/skills/formal-docs/` 与 `~/.codex/skills/formal-docs/` 时，以前者为维护主副本；规则、README、脚本、参考资料和测试修改后同步两处，避免同名技能执行不同版本。

## 使用

在对话里直接描述任务（会自动触发），或显式点名：

```
@formal-docs 审一下 docs/某笔记.md
```

完整新稿（包括系列续篇）交付前及整篇审稿，在 Codex 中执行三轮：第一轮由主代理运行检查器并做机械核对；第二轮使用不继承写作上下文的 `gpt-6-astra`、`low` 独立审查技术准确性和读者操作；第三轮使用独立的 `gpt-6-luna`、`high` 专检图解与代码注释。第二、三轮可并行，均不预先接收其他审稿者的候选问题或结论。主代理核实并汇总，不按写稿档位提高 Codex 审稿档位。Claude Code 与其他宿主保留原有两轮流程和档位规则，Claude Code 图解与注释专检继续默认用 Haiku。指定模型或档位不可用时说明未完成，不静默替换。详见 `SKILL.md` 的“审稿分工”。

局部补充、单句与格式等小修改只做局部自检和必要验证，修后不反复启动整篇审稿。已有记录与当前内容和相关环境一致时可以复用，注明来源；只对变化、证据不足或相互矛盾的行为重跑必要验证。替代写法仅在常见误用、关键边界或选型有教学意义时比较，不固定试验数量。

审稿允许没有发现问题；每条问题说明原文位置、触发条件、影响和依据，区分已确认错误、解释不足、可选增强与未能验证。仅要求审稿时不自动修改正文；已授权修改按既有范围处理，教学或业务方案的未定取舍单独交由作者决定。

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

检查项：H1（ATX / Setext / HTML，ERROR）、编码损坏、配置用语、人称、可选标题编号、代码围栏配对与语言、连续空行、引号风格混用、行尾空白、可选的中英文空格。`markdown` / `md` 围栏扫描文风；`text` / `txt` / `output`、代码与提示词围栏跳过文风，保留原始输出，仍检查编码与围栏闭合。围栏和行内代码中的示例 H1 不会触发禁令。密钥、路径/链接有效性、语气仍需人工判断。

## 项目配置

在项目根放 `.formal-docs.json`，脚本会从文档目录向上自动查找：

```json
{
  "banned": ["仅内部使用的模块名", "对照版"],
  "allow_line_patterns": ["INSERT INTO", "VALUES \\("],
  "person_style": "neutral",
  "space_check": false,
  "numbered_headings": "auto",
  "first_heading_number": 1,
  "check_link_labels": false,
  "check_troubleshooting_identifiers": false
}
```

人称策略可用 `--person-style neutral|instructional|preserve` 覆盖项目配置；默认保持中性文风，操作教程可允许第二人称。详细配置见 `references/banned-phrases.md`。结构按受众和项目约定选择，不强制套固定骨架。

## 命令块抽取

```bash
python scripts/extract_blocks.py docs/note.md --language bash
```

只输出 JSON，不运行文档里的命令。保留行号、原始输入和空行；未找到紧随的输出围栏时返回 null。执行器选择、隔离环境、结果比较与验证记录见 `references/command-validation.md`。

课程时长和 Python 安装细节按需读取，不用于所有技术文档。可选 `check_link_labels` 与 `check_troubleshooting_identifiers` 只生成 INFO 提醒，不确认语言、官方性或语义错误，也不访问网络。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 许可

MIT
