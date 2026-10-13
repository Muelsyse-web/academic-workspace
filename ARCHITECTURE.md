# Scholar 架构与运行约束

用户于 2026-10-13 批准总体设计。本文说明当前代码结构；需求仍以 [SPEC.md](SPEC.md) 为准，验收证据单独记录在 [PROGRESS.md](PROGRESS.md) 与 [ACCEPTANCE.md](ACCEPTANCE.md)。

## 进程与模块

生产环境运行一个 FastAPI/Uvicorn 进程，监听 `127.0.0.1`，同时提供 React/Vite 静态构建和 `/api/v1`。开发环境由 Vite 代理 API。SQLite 是业务事实来源，原件与缓存位于同一数据目录；默认路径为项目内 `var/data`。

| 模块 | 职责 |
| --- | --- |
| `app.py`、`security.py`、`admission.py`、`limits.py` | 生命周期、路由注册、同源会话、Agent 权限、请求与维护窗口协调、请求字节预算 |
| `diagnostics.py` | 生命周期日志处理器、UTC 轮换日志、异常脱敏、通用 500 响应与浏览器安全响应头 |
| `db.py` 与 SQL 迁移 | 短连接事务、外键、WAL、15 秒忙等待、迁移及升级前快照 |
| `courses.py`、`documents.py` | 课程与资料管理、上传、原件下载、元数据与来源读取 |
| `parsing.py`、`jobs.py`、`previews.py` | 格式解析、持久化索引任务、版本切换、受限 PPTX 图片缓存 |
| `search.py`、`embeddings.py` | FTS/中文回退、向量构建、余弦排名、混合排序 |
| `providers.py`、`configuration.py` | 本机 OpenAI-compatible HTTP 传输、配置及独立密钥存储 |
| `ai.py`、`citations.py` | 会话范围、证据预算、取消、来源验证与消息快照 |
| `notes.py` | Markdown、来源校验、稳定双链、笔记检索与导出 |
| `learning.py`、`generation.py` | 手工练习、SM-2、判分和历史、待审核生成草稿 |
| `backup.py`、`portable.py` | 一致性备份、受控恢复、JSON 数据交换和关系重映射 |
| `frontend/src/pages`、`components` | 页面、安全 Markdown/KaTeX、来源选择、学习表单与数据管理 |

这些后端路径均相对于 `backend/workspace`。应用服务与路由目前位于各业务模块中；解析器不访问数据库，Provider 不自行读取文档或数据库。调用者负责范围、事务及来源校验。SQL 参数化，动态表名仅来自应用白名单。

## Schema 与存储

`Database.migrations` 注册所有迁移：基础字典包含 1、2、4，再扫描 `migrations/*.sql` 加载 3、5，最后按数字顺序应用。当前 schema 为 5。`PRAGMA user_version` 与 `schema_migrations` 共同记录版本；升级前使用 SQLite backup API 生成 `migration-backups/before-vN.sqlite3`。程序拒绝打开高于已注册版本的数据库。

| 版本 | 文件 | 实际数据结构 |
| --- | --- | --- |
| 1 | `schema.sql` | `courses`、`blobs`、`documents`、`document_courses`、`document_links`、`document_versions`、`source_units`、`chunks`、`chunks_fts`、`jobs`、`activities`、`settings`、`agent_tokens` |
| 2 | `notes_schema.sql` | `notes`、`note_sources`、`note_links`、`notes_fts` 及维护触发器 |
| 3 | `migrations/003_ai.sql` | `conversations`、`messages`、`embeddings`、`embedding_runs`、`embedding_staging` |
| 4 | `learning_schema.sql` | `flashcards`、`reviews`、`quizzes`、`quiz_questions`、`attempts`、`attempt_answers` |
| 5 | `migrations/005_metadata.sql` | 为 `documents` 增加 `relative_path` |

学期是课程字段，主题是资料/笔记/卡片字段，标签以 JSON 数组保存，不存在独立的 semester、topic 或 tag 表。消息来源、卡片来源与题目内容包含 JSON 快照；笔记来源单独保存在 `note_sources`。历史答题与复习保留当时的题目/调度快照，删除当前学习内容不会改写历史成绩。课程统计聚合资料、笔记、到期卡片和累计答题/正确数，正确率包含自评结果；复习与测验提交追加近期活动。

`originals/<sha256>` 存放不可变原件；文件名和文件夹相对路径仅作元数据。`workspace.sqlite3` 保存结构化数据、解析文本和向量。`logs/workspace.log` 保存轮换诊断日志，`media-cache` 保存可重建 PPTX PNG，`backup-tmp`、`portable-tmp` 用于验证和暂存，`recovery` 保留恢复前的数据。Python/npm 缓存、测试服务数据和临时目录位于项目 `.cache`。

## 导入与来源一致性

上传先受请求字节上限约束，再写入项目内暂存区，校验大小、扩展名及实际格式并计算 SHA-256。相同内容复用资料和原件，可追加课程关系。后台解析单并发；任务入库，进程重启时将 processing 任务重新排队。任务失败记录错误类型并提供重试。

解析器返回 `locator_type`、正整数 `locator`、`heading`、`text` 内容单元。PDF 使用物理页，PPTX 使用幻灯片，DOCX 使用段落/表格，文本使用块起始行。索引服务按 1,600 字符步长、最多 1,800 字符片段生成 chunks，然后在同一事务中写入版本、来源和 FTS，切换 `active_version`。失败保留旧版本；旧引用始终绑定原版本和摘录。

PPTX 预览先验证原件哈希与 Office 归档，按页提取受支持的位图并重新编码为 PNG，去掉嵌入元数据。服务按资料 ID 与图片序号提供缓存，不使用外部资源、不重建幻灯片排版。

## 检索与模型

关键词检索使用 SQLite FTS5，另做中文字符片段处理和短查询回退，限定课程、资料、类型、标签与当前版本。笔记保存时维护 `notes_fts`，当前列表检索使用标题/正文的大小写无关子串匹配。单页资料结果上限 100。

Embedding worker 单并发，每批最多 16 个片段。向量按 Provider 地址、模型与维度区分，先写 staging，确认资料集合未改变后原子替换该模型索引。失败保留旧向量；重启时清理 staging 并标记中断任务失败。语义搜索分批读取 64 个向量，计算余弦相似度并维护当前结果窗口；混合搜索对关键词和语义各取最多 100 个候选，用倒数排名融合，候选总数最多 200。当前实现适合小型本地资料库，没有专用向量数据库。

聊天检索最多选取 6 个证据片段，总证据预算固定为 12,000 字符；这不是可配置 token 计数。Provider 配置提供服务地址、聊天/Embedding 模型、3–180 秒超时和可选密钥。调用模型列表、聊天及 embedding 兼容端点时禁用环境代理和重定向，仅接受 loopback 地址；单次响应最多 8 MiB。

模型得到问题、受限证据及会话上下文，没有工具执行能力。后端核对返回引用属于本次证据，且引文是对应正文中的非空片段；位置和标题从数据库生成。缺失或伪造引用标为未验证，证据不足单独标识。取消请求设置会话取消标志并关闭正在进行的 HTTP 传输，最终消息保留取消状态。

生成服务返回经来源和题型校验的草稿，由前端展示并在用户确认后调用笔记/学习持久化 API。单次生成最多 10 张卡片或 10 道题。确定性 Mock 仅验证业务契约，不能证明真实模型质量。

## 笔记与学习规则

笔记保存时验证每个引文在指定资料版本、位置中存在。`[[标题]]` 的原文本与解析出的目标 ID 分开保存；唯一匹配可自动关联，同名目标需显式选择，删除目标后保留失效关系，避免误连到新建同名笔记。Markdown 渲染不执行原始 HTML，外链协议受限。

单选、多选题根据所选选项集合判分，简答与数学题使用用户自评。`sm2-v1` 将 Again/Hard/Good/Easy 映射为 0/3/4/5；初次成功间隔 1 天、第二次 6 天，后续按旧 ease 计算，ease 下限 1.3。Again 重置连续次数并安排 1 天后复习。复习和测验提交支持幂等键，记录 UTC 时间；界面按 Asia/Shanghai 划分学习日。

## 备份与恢复

备份在维护锁内使用 SQLite backup API 创建一致性快照，校验并归档原件和 manifest，不复制正在活动的 WAL 主文件。导出删除 Agent 令牌数据，不包含模型密钥、缓存和日志。

恢复先在数据目录内验证 ZIP 路径、元数据预算、校验和、SQLite 完整性与注册 schema，旧版受支持 schema 经过迁移后再核对。写入维护窗口协调活动请求，并拒绝正在索引或问答时替换。切换前保留 recovery，数据库、原件与模型密钥协调移动；失败尝试回滚，如回滚也失败则保留恢复点和暂存区供人工恢复。成功后清空浏览器会话及 Agent 令牌，模型凭据需重配。

便携导出用白名单字段生成 `data.json`，要求相同 schema，排除配置、凭据、任务、向量和日志。导入先给出冲突预览，确认后在事务中重映射 ID、追加关系和历史、重建 FTS。相同原件资料沿用目标元数据及当前版本；同名课程/笔记/测验生成新记录。省略原件的包要求目标库已有对应原件。导入失败回滚数据库，并仅清理该次导入创建的原件。

## 固定资源边界与安全

| 对象 | 上限 |
| --- | --- |
| 资料上传 | 单文件 100 MiB，普通请求 256 MiB；UI 每批最多 200 MiB、100 个文件 |
| Office 归档 | 10,000 条目，展开 256 MiB；大条目压缩比最多 1,000 |
| PPTX 图片 | 每页 50 张（含组合内图片），单图 16 MiB、2,000 万像素，仅 PNG/JPEG/WebP |
| 备份/便携归档 | 展开 4 GiB，20,000 条目，manifest 8 MiB，中央目录 16 MiB |
| 便携 JSON | 128 MiB |
| 归档上传 | 文件 4 GiB + 32 MiB，请求 4 GiB + 33 MiB，为归档及 multipart 留余量 |

生产只绑定 loopback；Host、Origin、客户端地址校验阻止跨站及远程访问。浏览器会话使用 HttpOnly、SameSite=Strict Cookie，写操作要求 CSRF token；本机 Agent 使用独立 Bearer 令牌，数据库只存 SHA-256 散列，read 权限不能写。设置、凭据、备份及导入导出仅浏览器管理员会话可用。

模型密钥单独以明文保存为权限 `0600` 的 `provider-secret.json`，不在 SQLite/导出中；本机文件权限是其保护边界。`diagnostics.py` 随应用生命周期安装并关闭文件处理器，日志写入数据目录的 `logs/workspace.log`，使用 UTC 时间、1 MiB 轮换阈值和 3 个备份。请求异常只记录已注册路由模板和异常类名，不记录异常参数、原始 URL 或输入；未发送响应时返回通用 500。解析诊断记录任务 ID 和异常类型，不输出正文；生产脚本关闭访问日志。CSP 仅允许同源脚本、字体和连接，样式允许 KaTeX/React 所需内联内容，图片/PDF 预览使用受限 data/blob 来源，`frame-ancestors` 限定同源。当前部署不提供磁盘加密、OCR、Office 排版还原、云同步、远程访问或多进程 worker。
