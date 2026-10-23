## Python 教程的环境、依赖与 API 约定

在 Python 教程涉及环境、依赖、分层文件命名、logging 配置、API 模型命名、统一响应或增量代码时读取。示例版本不作为其他项目的固定要求。

### 依赖安装

- 编写 Python 教程的依赖安装步骤时，先交代项目根目录中的 `requirements.txt`，给出带明确版本号的完整内容，例如 `fastapi[standard]==0.124.4`。版本沿用项目约定或已核验的兼容版本，不把示例版本作为所有项目的固定要求，也不编造版本号。
- 再给出实际执行目录和虚拟环境激活命令，然后运行项目约定的安装命令。Windows PowerShell 示例：在虚拟环境所在目录执行 `.\.venv\Scripts\Activate.ps1`，确认当前终端已激活后执行 `pip install -r requirements.txt`。系列课程已有命令习惯时沿用；不以完整虚拟环境解释器路径代替激活步骤。
- 后续增加依赖时，说明对已有 `requirements.txt` 的追加或修改，保留仍需要的依赖，再执行同一安装命令；依赖文件、目录结构与运行说明同步更新。只安装当前章节需要的包，区分固定直接依赖版本与完整锁定传递依赖，不宣称仅用直接依赖列表实现完全相同的环境。

### 命令简写与惯用写法

- 编写和交付前主动审查示例代码的惯用写法：在语义等价且更易理解时，直接采用自然、简洁的表达，不等用户指出后再修改，也不为显得基础而保留冗余判断。必要时在首次出现处解释短路求值、真值判断等前置概念；不以缩短代码为目标引入难读的技巧。
- 简化前核对参数类型和边界值。只需排除 None、空字符串的可选字符串可用真值判断；纯空白仍需单独处理。需要保留有效的 0、False 或区分空容器与 None 时，保留显式的 `is not None`，不机械替换。同步核对代码、注释和验收结果。

- Python 教程每篇在首次安装依赖或运行程序前，先说明在虚拟环境所在目录激活一次。Windows PowerShell 使用 `.\.venv\Scripts\Activate.ps1`；当前终端已激活时跳过，新开终端后重新激活。后续命令用激活后的 `pip`、`python` 或课程已约定的简写，不反复写完整解释器路径。脚本名使用实际文件名，不固定为 `main.py`。
- macOS / Linux 在项目明确需要时用 `source .venv/bin/activate` 激活。说明执行目录与激活前提，不把 VS Code 选择解释器等同于终端已激活；激活失败时可给完整解释器路径作为备用，不要求修改系统策略。框架命令同样放在已激活的终端中运行，例如 `uvicorn app.main:app --reload`。
- 提供有助于当前知识点的代码技巧时，解释用途、与原写法的关系及必要限制，不用尚未讲解的复杂写法替代基础代码。依赖安装仍以 `requirements.txt` 为主线；所用命令与激活的环境、依赖文件及安装目标保持一致。

### 分层文件命名

适用于已采用 API、Service、Models、Schemas 分层的 Python Web API 教程；不为套用命名约定额外引入分层。新设计默认统一采用下表，已有项目规范或用户明确约定优先。这是项目命名约定，不是 Python 或框架的强制标准。

| 层 | 命名规则 | 示例 |
| --- | --- | --- |
| API | 资源名复数 | `api/products.py`、`api/categories.py` |
| Service | 实体名单数加 `_service` | `services/product_service.py`、`services/category_service.py` |
| Models | 实体名单数 | `models/product.py`、`models/category.py` |
| Schemas | 实体名单数 | `schemas/product.py`、`schemas/category.py` |

- 文件名统一使用小写与下划线；`services`、`models`、`schemas` 目录名使用复数。API 模块按资源集合命名，Service、Models、Schemas 模块按业务实体命名。资源 URL 默认用复数（如 `/products`），但 URL 的复数形式并不强制决定 Python 文件名。
- 一个 schema 文件可容纳同一实体的新增、修改、响应等多个模型，类名仍按下节的 `XxxCreateRequest`、`XxxUpdateRequest`、`XxxResponse` 约定，不因文件名单数而拆成每个类一个文件。
- 同一系列的目录树、正文路径、文件标题、导入语句和代码示例保持一致，不交替使用 `product.py` 与 `product_service.py` 表达同一个 Service 模块。更新本约定不自动重命名已交付项目；已授权迁移时同步相关引用。

### 首次使用 logging

- 教程首次引入 `logging` 时，在第一次日志调用前给出可运行的初始化配置，明确日志级别与输出格式，不能只给 `logger.error(...)` 或 `logging.exception(...)`。默认将配置放在应用入口 `main.py` 的初始化位置，在业务日志产生前执行；项目已有统一日志配置时沿用，并说明配置位置与生效方式，不重复配置。
- 入门示例可采用以下配置，并解释 `INFO` 会输出 INFO 及以上级别，格式依次包含时间、级别、logger 名称与消息；级别和格式有项目约定时以项目为准。

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
```

- 其他模块使用 `logger = logging.getLogger(__name__)` 获取 logger，复用入口配置，不在每个模块或请求中重复调用 `basicConfig()`。若运行环境已有 root handler，`basicConfig()` 默认可能不生效；核对启动方式和实际输出，沿用现有配置或在统一入口调整，不无条件使用 `force=True` 覆盖配置。

### API 请求模型与统一响应

适用于 Python Web API 教程与项目笔记；普通脚本、命令行程序不套 API 响应封装。用户已确定的接口契约和项目规范优先；下面是新设计时的默认约定，不因修订 skill 自动改写已交付课程的模型名或接口格式。已授权迁移时同步相关章节、代码、导入、调用方、示例与验证。

- **模型命名**：新增请求用 `XxxCreateRequest`，修改请求用 `XxxUpdateRequest`，业务响应用 `XxxResponse`，例如 `CategoryCreateRequest`、`CategoryUpdateRequest`、`CategoryResponse`。`Xxx` 是实际业务对象名，其他请求按用途命名（如 `LoginRequest`）；不要把示例类名固定到所有项目，也不要在同一系列混用 `Create`、`CreateRequest`、`Read`、`Response` 等后缀表达相同角色。请求模型只接收允许客户端提交的字段，响应模型显式声明允许返回的字段及序列化规则。
- **全局响应**：为普通 JSON API 定义并复用一份 `Response`，统一外层 `code`、`message`、`data`。`code` 表达结果代码，`message` 提供可理解的提示，`data` 承载业务响应模型、列表、分页数据或 `None`；业务 `XxxResponse` 定义 `data` 内的结构，不重复外层字段。通过共用的 `Response.success(...)`、`Response.error(...)` 或既有等价构造方法返回，避免每个接口手写一份封装；分页结构沿用已定字段，放在 `data` 内，不因统一封装更换分页契约。引用框架同名 `Response` 时使用明确别名，避免覆盖项目的响应模型。
- **业务序列化**：ORM 结果显式转换为业务响应 schema 后封装，或由具有明确 `data` 类型的完整响应模型统一完成校验、字段过滤和序列化，不要求路由提前手动转换 JSON；不能把未经处理的 ORM 对象塞进 `Any` 就当作已完成字段过滤。金额、时间等输出格式放在 schema 中，保持路由简洁。
- **统一异常处理**：FastAPI 使用框架提供的自定义异常处理器机制，集中定义异常与处理函数，在应用入口注册；例如把共用代码放在 `common/exceptions.py`、`common/response.py`，由 `main.py` 调用 `app.add_exception_handler()`，不要把这套目录说成官方强制结构。业务错误统一使用 `BusinessError` 携带提示和代码，例如 `BusinessError("名称已存在", code=409)`；未另定业务码时，普通输入业务错误可用 `code=400`、HTTP400，本例重名用 `code=409`、HTTP409，不为重名、库存不足等不同提示逐项新建异常子类或专用处理器，也不注册整个 `ValueError` 来替代明确的业务异常。业务代码与 HTTP 状态的关系按下条约定说明，不能直接把任意业务码作为 HTTP 状态。共用处理器覆盖业务错误、数据库故障、HTTP 异常、请求校验失败和未知故障，统一输出 `Response`；HTTP 处理器注册到 Starlette 的 `HTTPException` 基类并保留响应头，校验错误保留可定位字段的信息。数据库事务回滚仍由业务层负责；处理器将异常转换成响应，不替业务函数提交事务。服务端保留可定位日志，跨线程的同步兜底处理器显式传入异常（如 `exc_info=exc`），不能依赖已丢失的异常上下文，也不能把原始数据库错误或堆栈返回客户端。
- **代码与协议语义**：区分响应体的 `code` 与 HTTP 状态码，沿用明确的成功码、业务码及错误状态约定；未另作约定时，示例可用 `code=200` 表示成功，错误仍使用对应的 HTTP 错误状态，不能因采用统一格式就把所有错误改成 HTTP 200。若有自定义业务码，明确它与 HTTP 状态码的关系。没有返回体的响应、文件下载及流式响应按其协议处理，不强塞 JSON 封装；普通新增、查询、修改、删除 JSON 接口保持契约一致。
- **按定位讲清与核对**：入门教程先让读者分清请求 schema、业务响应 schema 和外层 `Response` 的职责，结合一个成功与一个失败过程说明数据怎样转换，再让其他接口复用；不为封装本身提前堆泛型、装饰器或自动包装中间件。进阶教程承接已有机制，重点解释契约、边界与扩展。验证外层结构、实际 `data` 字段过滤及格式、列表/分页/删除结果、HTTP 状态与响应头、错误分支和 OpenAPI 描述，而不只检查代码能运行。

### 增量示例验证

按正文的新增、替换、追加顺序拼装完整文件。可用 `ast` 检查缺少的导入、常量和函数名，再在隔离虚拟环境中整体运行；语法检查不证明名字已定义，也不证明运行结果正确。固定直接依赖不等于完整锁定传递依赖。修改版本要求前，用目标版本验证，并记录实际版本与结果。
