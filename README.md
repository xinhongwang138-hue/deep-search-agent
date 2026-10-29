---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 2ef7930562d418b0a12963f90da05d53_faf21d1ed34011f1a301525400cd780f
    ReservedCode1: o9qJ3mOu77OwiONabVoH5nrNSDSxrh6MB42bNS5c/oQ/WUN2xUNbPHXiID0FQ5PZh2Ui1Mz0fbGEX8pmLfXx+MM/K5q4u9fD4QExj3dIhtTGn93NcHePsKeTInjFqIKxJWAt502xyMr3x5b6HFw9F/a8IwhOMoiq5+PPxYvdS4RjbcmbGj1Y3wRd2PY=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 2ef7930562d418b0a12963f90da05d53_faf21d1ed34011f1a301525400cd780f
    ReservedCode2: o9qJ3mOu77OwiONabVoH5nrNSDSxrh6MB42bNS5c/oQ/WUN2xUNbPHXiID0FQ5PZh2Ui1Mz0fbGEX8pmLfXx+MM/K5q4u9fD4QExj3dIhtTGn93NcHePsKeTInjFqIKxJWAt502xyMr3x5b6HFw9F/a8IwhOMoiq5+PPxYvdS4RjbcmbGj1Y3wRd2PY=
---



# Deep Search Agent（deepagents 深度搜索框架）

基于 `deepagents` 的"主智能体 + 三路检索子智能体"深度搜索框架，提示词方案见配套文档 `deepagents-multi-agent-prompts.md`。

核心设计原则：

- **信息获取下沉到子智能体，文档生成收口到主智能体**：子智能体不写文件，主智能体不做检索。
- **描述即路由**：子智能体的 `description` 是主智能体委派决策的唯一依据，适用 / 不适用边界写在同一段里。
- **执行层兜底**：提示词只做声明，SQL 只读、路径穿越、检索次数预算全部在执行层硬校验。

---

## 一、目录结构

```
deep-search-agent/
├── config/settings.py             # 全局配置（阈值、模型、外部服务凭据）
├── prompt/
│   ├── prompts.yml                # 全部提示词（L1 / L3 统一装配）
│   └── loader.py                  # 加载 + 变量注入
├── tools/
│   ├── path_guard.py              # 会话工作目录沙箱（防路径穿越）
│   ├── internet_search.py         # Tavily 检索 + 次数预算
│   ├── sql_tools.py               # 只读 SQL（list / preview / query）
│   ├── ragflow_tools.py           # RAGFlow 助手列表与问答
│   ├── doc_readers.py             # PDF / DOCX / XLSX 解析后端（异常收敛 + 三重上限）
│   └── file_tools.py              # generate_markdown / convert_md_to_pdf / read_file_content
├── agent/
│   ├── workspace.py               # 会话工作目录与上传文件清单
│   ├── sub_agents/
│   │   ├── internet_sub_agent.py  # L2 网络搜索
│   │   ├── db_sub_agent.py        # L2 数据库查询
│   │   └── rag_sub_agent.py       # L2 RAGFlow 知识库
│   └── main_agent.py              # create_deep_agent 装配
├── api/                           # 服务端（线程级会话 + 定向推送）
│   ├── context.py                 # ContextVar 会话上下文（避免并发串台）
│   ├── monitor.py                 # ConnectionManager：事件按 thread_id 定向推送
│   └── server.py                  # /api/task /upload /download /files + /ws/{thread_id}
├── ui/                            # Vue3 + Vite 前端
│   ├── src/App.vue                # 执行轨迹 / 产物列表 / 上传下载
│   ├── src/api.ts                 # 接口封装
│   └── vite.config.ts             # /api、/ws 代理到 8000
├── sql/
│   ├── db.sql                     # 建表：drugs / inventory / sales_orders
│   ├── seed.sql                   # 示例数据（10 药品 / 22 库存 / 56 流水）
│   └── schema.yml                 # 表与指标语义说明
├── server/app.py                  # 旧版单文件服务端（保留参考，不再推荐）
├── main.py                        # 后端统一入口
├── pyproject.toml                 # uv 依赖管理（与 requirements.txt 等价）
├── run_cli.py                     # 命令行入口
└── tests/
    ├── test_guards.py             # 沙箱与只读 SQL 单测
    └── test_doc_tools.py          # PDF / DOCX / XLSX 读取与异常收敛单测
```

## 二、装配关系

| 层 | 角色 | 工具 | 装配位置 |
| --- | --- | --- | --- |
| L1 | 主智能体 | `generate_markdown` / `convert_md_to_pdf` / `read_file_content` + 框架内置 `task` 委派能力 | `agent/main_agent.py` |
| L2 | 网络搜索助手 | `internet_search` | `subagents=[...]` 中的 tavily 项 |
| L2 | 数据库查询助手 | `list_sql_tables` / `get_table_data` / `execute_sql_query` | db 项 |
| L2 | RAGFlow 助手 | `ragflow_list_assistants` / `ragflow_ask` | ragflow 项 |
| L3 | 原子工具 | `tools/*.py` | 由提示词约束调用顺序 |

## 三、安装与配置

```bash
cd deep-search-agent
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    # 填入真实凭据
```

`.env` 关键项：

| 变量 | 说明 |
| --- | --- |
| `DS_AGENT_MODEL` | 模型标识，如 `openai:gpt-4o-mini`、`anthropic:claude-sonnet-4-5` |
| `DS_AGENT_MODEL_BASE_URL` | 走 OpenAI 兼容网关时填 base_url（如自建 DeepSeek 代理），留空则用原生 provider |
| `TAVILY_API_KEY` | 网络检索 |
| `DS_AGENT_DB_URL` | SQLAlchemy 连接串，如 `mysql+pymysql://user:pwd@host:3306/db` |
| `RAGFLOW_BASE_URL` / `RAGFLOW_API_KEY` | 内部知识库 |

PDF 导出依赖任选其一即可：`weasyprint`、`pandoc`（`pypandoc`）。都缺失时 `convert_md_to_pdf` 会明确报错而不是静默产出空文件。

## 四、运行

```bash
# 方式一：uv（推荐）
uv sync                     # 或 uv sync --extra pdf
uv run python main.py

# 方式二：pip
pip install -r requirements.txt
python main.py
```

后端起来后：

```bash
cd ui
npm install
npm run dev          # http://localhost:5173，/api 与 /ws 自动代理到 8000
npm run build        # 产物在 ui/dist，可直接挂到 nginx
```

数据库示例（MySQL 8）：

```bash
mysql -u root -p < sql/db.sql
mysql -u root -p cps_demo < sql/seed.sql
# 再把只读账号写入 .env：DS_AGENT_DB_URL=mysql+pymysql://readonly:pwd@127.0.0.1:3306/cps_demo
```

每次会话自动创建独立工作目录 `workspaces/session_{id}/{uploads,output}`，主智能体写入的 Markdown / PDF 均落在 `output/` 下，接口返回相对路径，不下发绝对路径。

## 五、阈值配置（不要硬编码进提示词）

`config/settings.py` 中可调：

| 配置 | 默认 | 作用 |
| --- | --- | --- |
| `MAX_SEARCHES_PER_QUESTION` | 3 | 子智能体单问题的检索上限，超限工具直接拒绝并提示停止重搜 |
| `SQL_MAX_ROWS` | 200 | 明细查询行数上限 |
| `SQL_TABLE_PREVIEW_ROWS` | 100 | 表结构预览行数 |
| `MAX_SQL_FIX_ATTEMPTS` | 1 | 同一 SQL 允许的纠错次数 |
| `MAX_FILE_READ_BYTES` | 2 MB | `read_file_content` 单文件读取上限 |

## 六、二次开发

1. **新增子智能体**（如文件解析助手）：在 `agent/sub_agents/` 加一个构建函数，返回 `{name, description, prompt, tools}` 并注册到 `main_agent.build_agent()` 的 `subagents` 列表，主智能体代码不动。
2. **改路由效果**：优先改 `prompts.yml → sub_agents.*.description`，它对委派行为的影响大于 `system_prompt`。
3. **换模型**：主智能体与子智能体可分别指定 `model` 字段，检索型子智能体用便宜模型、汇总用强模型是常见组合。

## 七、已知失效模式与对策

| 失效模式 | 对策 |
| --- | --- |
| 信息未到齐就生成文档 | 提示词"必须先取数 / 禁止占位符"+ 主智能体工具集中不含检索工具，结构上无法自行补数 |
| 子智能体被要求写文件 | 子智能体工具集里根本没有文件工具，硬件隔离 |
| SQL 越权写库 | `assert_read_only()` 双层校验：语句白名单 + 关键字黑名单 + 单语句限制 |
| 路径穿越 | `resolve_in_workspace()` 做 resolve 后的父子关系校验，拒绝 `../` 逃逸 |
| 反复换词重搜 | `internet_search` 内部按会话计数，超预算直接返回拒绝信息 |

## 八、接口协议（`api/`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/task?query=&thread_id=` | 提交检索任务，立即返回 `{status, thread_id}`；同 thread 已有任务在跑返回 409 |
| POST | `/api/upload?thread_id=` | multipart 上传，多文件字段名 `files`，落 `session_{id}/uploads/` |
| GET | `/api/files?thread_id=&path=output` | 列出产物，返回相对路径 + 大小 + mtime |
| GET | `/api/download?thread_id=&path=` | 下载单个文件，路径经 `resolve_in_workspace()` 校验 |
| WS | `/ws/{thread_id}` | 订阅该会话事件，客户端可发 `ping` 保活 |
| GET | `/health` | 存活探针 |

推送体统一为 `{type:"monitor_event", event, message, data, timestamp}`：

| event | 触发点 | 前端用途 |
| --- | --- | --- |
| `session_created` | 工作目录就绪 | 显示会话路径 |
| `assistant_call` | 主智能体调用 `task` 工具 | 显示委派给了哪个子智能体、子任务是什么 |
| `tool_start` / `tool_end` | 任意工具调用 | 执行轨迹、排查卡点 |
| `token` | 模型增量输出 | 打字机效果 |
| `task_result` | 任务结束 | 渲染最终回答并刷新产物列表 |
| `error` | 异常 | 红色告警 |

关键设计：`thread_id` 与工作目录存在 `ContextVar` 里，而不是全局变量或 `threading.local`——FastAPI 下同一线程并发多个请求时，全局变量会串台，`threading.local` 又会因为协程共用线程而失效。

## 九、与 deepagents-framework 仓库的差异

| 维度 | 本工程 | 仓库 |
| --- | --- | --- |
| 执行层防护 | SQL 只读双层校验、路径沙箱、检索次数预算、主子工具集物理隔离 | 无，全部依赖提示词约束 |
| 模型接入 | `provider:model` 可配，主/子智能体可分层 | 锁定单一厂商 |
| 目录结构 | `api/` 分包（context / monitor / server） | 单文件服务端 |
| 接口 | `/api/task` `/upload` `/download` `/files` `/ws/{thread_id}` | 同左 |
| 前端 | Vue3 + Vite，轨迹 + 产物 + 上传下载 | Vue3 + TS + Vite |
| 依赖管理 | `pyproject.toml` + `uv` | 同左 |
| 示例数据 | `sql/db.sql` + `seed.sql` + `schema.yml` | `sql/db.sql` + `cps.yml` |
| 上传文件读取 | 文本 / PDF（按页打标）/ DOCX（含表格转 Markdown）/ XLSX（列名 + 前 N 行 + 数值列统计），读取前过沙箱与字节上限，解析异常收敛为文本 | 支持 md/txt/docx/pdf/xlsx（pypdf + python-docx + pandas），无大小与页数上限，异常直接抛给模型 |
| PDF 导出 | `weasyprint` → `pandoc` 依次尝试，全缺时明确报错 | 依赖 Word COM（`converter_utils`），须装 Office + pywin32 |

## 十、注意

- `prompts.yml` 中的提示词与配套文档保持一致，仅把阈值替换成 `${...}` 变量，由 `loader.render()` 注入实际值，避免提示词与配置漂移。
- 框架内置 `task` 工具负责子智能体调度，无需自行实现委派工具。
- deepagents 0.7.32 上已验证：子智能体字典的字段名为 `prompt`，`create_deep_agent(model=..., tools=..., subagents=[...])` 可直接编译成 `CompiledStateGraph`；若升版后字段改为 `system_prompt`，只需改 `agent/sub_agents/*.py` 的字典键。

## 十一、借鉴上游的取舍

| 上游做法 | 是否采纳 | 说明 |
| --- | --- | --- |
| 多格式文件读取（PDF / DOCX / XLSX） | 采纳 | 新增 `tools/doc_readers.py`，补齐本项目最明显的短板；但保留沙箱校验、字节/页数/字符三重上限，解析异常收敛为文本而非抛给模型 |
| Excel 附统计描述 | 采纳（轻量实现） | 上游用 `pandas.describe`，本项目用 `openpyxl` 自行统计数值列，避免为一次读取引入 pandas 这层重依赖 |
| Word COM 生成 PDF | 未采纳 | 需本机装 Office + pywin32，COM 进程易残留；本项目 `weasyprint` / `pandoc` 链路已够用，且失败时明确报错 |
| `sql/cps.yml` | 无需借鉴 | 实为 MySQL 8.0 的 docker-compose 配置（非 SQL 脚本），本项目 `docker-compose.demo.yml` 已做端口避让与只读账号 |
| `test/` 调试页 | 未采纳 | `scripts/verify_offline.py` 已用命令行复现同样能力，避免维护第二套 UI |
| 模块级全局 LLM 单例 | 未采纳 | 上游 `agent/llm.py` 将模型名与 provider 写死在模块级；本项目按角色分档并从 `settings` 读取 |

## 十二、实测记录

环境：Windows 11 / Python 3.12.9（系统解释器）/ Node v22.12.0 / uv 0.12.23 / deepagents 0.7.32。

| 验证项 | 做法 | 结果 |
| --- | --- | --- |
| 依赖解析 | `uv lock` | 解析 93 个包成功，生成 `uv.lock` |
| 依赖安装 | `uv sync --extra dev` | 成功，`deepagents==0.7.32` 就位 |
| 后端装配 | `import api.server` | 路由齐全：`/api/task`、`/api/upload`、`/api/files`、`/api/download`、`/ws/{thread_id}`、`/health` |
| 离线单测 | `uv run pytest -q` | 18 passed（沙箱路径逃逸 + SQL 只读防护 + PDF/DOCX/XLSX 读取与异常收敛） |
| 上传文件解析 | `/api/upload` 上传 `.docx`/`.xlsx` 后调 `read_file_content` | 中文段落与表格正确转 Markdown；XLSX 输出列名与前 2 行、`amount` 合计 1783682；`../../etc/passwd` 越界被拒 |
| 智能体装配 | `build_agent()` | 返回 `CompiledStateGraph`，三子智能体注册成功 |
| SQL 取数链路 | SQLite 复刻 `drugs/inventory/sales_orders` = 10/22/56 行 | 表清单、表预览、Top5 GMV、低库存 9 行均正确 |
| SQL 防护 | DELETE / 多语句 / 注释 / SET / 超量 LIMIT | 前 4 类被拒，`LIMIT 9999` 自动压回 `sql_max_rows` |
| HTTP 链路 | `DS_AGENT_PORT=51937 python main.py` + curl | health、upload、files、download(200, 56B) 全通；`../../../../Windows/win.ini` 返回 404 |
| 前端 | `npm install` + `npm run build` | `vue-tsc --noEmit` 无错，`dist` 产出 JS 73.73 kB |
| 真实 MySQL 取数 | `docker compose -f docker-compose.demo.yml up -d` + `uv run python scripts/verify_mysql.py` | MySQL 8.0.46 / `cps_demo`：drugs 10 行、inventory 22 行、sales_orders 56 行；表清单、表预览、Top5 GMV（复方丹参滴丸 572860）、低库存 9 行、区域排名 4 行、近效期 10 行全部正确，中文正常 |
| 真实库只读边界 | 同一脚本对只读账号执行 INSERT/UPDATE/DELETE/DDL | 4 类写操作全部被库侧拒绝（MySQL 1142）；执行层 5 类绕过用例全部拦截，`LIMIT 9999` 压回上限 |

上表的 SQL 链路与防护可随时复现（无需 MySQL、无需模型 key）：`uv run python scripts/verify_offline.py`，脚本会用 SQLite 复刻三表并逐项打印结果。

未验证项（缺外部条件，不影响交付）：

- 真实大模型推理：需 `OPENAI_API_KEY` 或网关 `DS_AGENT_MODEL_BASE_URL` / `DS_AGENT_MODEL_API_KEY`。
- ~~MySQL 实库~~：已用 `docker-compose.demo.yml` 起独立演示库完成验证（见上表），无需本机 MySQL80；接自己的库时把只读账号写入 `.env` 的 `DS_AGENT_DB_URL` 即可。
- Tavily 检索与 RAGFlow 知识库：需各自 `TAVILY_API_KEY` 与 RAGFlow 服务地址、key。

四个环境坑（本机已遇到并规避）：

1. 8000 端口可能被其它服务占用（`bind` 报 `WinError 10048`），用 `DS_AGENT_PORT` 换端口即可。
2. `uv sync` 若报 “virtual environment directory ... is not a valid Python environment”，是 uv 下载托管 CPython 失败所致；改用系统解释器重建：`uv venv --force --clear --python "C:\Program Files\Python312\python.exe"`，再 `uv sync`。
3. 容器端口映射“假成功”：Docker 显示 `127.0.0.1:3307->3306/tcp`，但 WSL2 的 localhost 转发已抢占 3307/13307，实际连到的是 WSL 里的另一个 MySQL，报 `Access denied`（客户端 IP 显示 `172.21.0.1` 即为信号）。先用 `wsl -d Ubuntu -u root -- ss -lnt | grep :端口` 确认未被占用，再选 23306 这类冷门端口；连接必须写 `127.0.0.1`，写 `localhost` 可能解析到 `::1` 而走错通道。
4. 初始化数据中文乱码：`sql/db.sql`、`sql/seed.sql` 缺 `SET NAMES utf8mb4` 时，中文字面量会按 latin1 双写进库（`HEX(drug_name)` 出现 `C3A5C2B8` 类字节），读出来是 `å¸ƒæ´›èŠ¬`。已在两个脚本开头补 `SET NAMES utf8mb4`，同时在 `tools/sql_tools.py` 的 engine 上强制 `charset=utf8mb4`，双层兜底。

*（内容由AI生成，仅供参考）*
