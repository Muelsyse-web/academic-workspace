# Scholar · Local Academic Workspace

面向中英文课程资料的本地学习工作空间。你可以管理课程，导入 PDF、PPTX、DOCX、TXT、Markdown，检索并返回原文，保存引用笔记，创建 Quiz 和复习卡片。连接本机模型后，可使用有来源的问答、语义搜索和学习草稿生成。数据保存在项目内的 SQLite 和原件目录中。

完整需求见 [SPEC.md](SPEC.md)，实现结构见 [ARCHITECTURE.md](ARCHITECTURE.md)。实际验证结果与待办见 [PROGRESS.md](PROGRESS.md) 和 [ACCEPTANCE.md](ACCEPTANCE.md)；功能存在不等于所有验收已经完成。

## macOS 安装与启动

目标环境为 Apple Silicon Mac，需预先安装 Python 3.11+、Node.js 22.12+ 和 npm。首次安装下载依赖；日常资料、关键词搜索、笔记和手工练习无需 AI 模型。以下命令在项目根目录运行，依赖与缓存留在项目内。

```sh
mkdir -p .cache/tmp .cache/pip .cache/npm
python3 -m venv .venv
PIP_CACHE_DIR="$PWD/.cache/pip" TMPDIR="$PWD/.cache/tmp" .venv/bin/python -m pip install -r requirements.lock
npm --prefix frontend --cache "$PWD/.cache/npm" ci
npm --prefix frontend run build
./scripts/start.sh
```

打开 [本地工作空间](http://127.0.0.1:8767)。服务只监听 `127.0.0.1`，终端按 Ctrl+C 停止；有正在处理的任务时，正常关闭可能需要等待。下次运行启动脚本会继续使用 `var/data`。不要启动多个后端同时操作同一数据目录。

可用 `WORKSPACE_PORT` 改端口，用 `WORKSPACE_DATA_DIR` 指向项目内另一个数据目录：

```sh
WORKSPACE_DATA_DIR="$PWD/var/demo-data" WORKSPACE_PORT=8767 ./scripts/start.sh
```

升级时先从设置下载完整备份，停止旧进程，按锁文件安装依赖并重新构建前端，再启动。程序按顺序迁移旧数据库，并在 `var/data/migration-backups` 保存升级前的数据库快照；这些快照不包含原件，不能代替完整备份。旧版程序会拒绝打开更新版本的数据库。

## 导入、阅读与搜索

1. 在“我的课程”创建课程和学期，进入课程导入文件；也可在“资料库”选择多个文件、文件夹或拖放文件。
2. 查看排队、解析进度和错误。完成后可编辑标题、课程归属、主题、标签、收藏以及关联资料。文件夹相对路径仅作元数据保存。
3. 在“知识搜索”选择资料或笔记，输入中英文词句。资料结果可按课程和格式筛选；点击来源返回对应位置。
4. 资料页可下载原件、重新索引，或把来源加入笔记。重复原件按 SHA-256 去重，可同时关联多个课程。

单文件最多 100 MiB，普通上传请求最多 256 MiB（含 multipart 开销）；界面按每批最多 200 MiB、100 个文件分批上传，并在发出请求前拒绝超大的单文件。Office 压缩包还受 10,000 条目、256 MiB 展开大小及压缩比限制。

| 格式 | 来源位置与预览 |
| --- | --- |
| PDF | 从 1 开始的物理页；浏览器 PDF 预览支持跳页，不采用印刷页码 |
| PPTX | 从 1 开始的幻灯片；提取文本及可支持的图片 |
| DOCX | 段落或表格位置；不生成页码 |
| TXT / Markdown | 文本块起始行 |

PPTX、DOCX 提供内容预览，不重建 Office 布局。PPTX 图片支持 PNG、JPEG、WebP，转为本地 PNG 缓存；每张图片最多 16 MiB、2,000 万像素，每页最多 50 张（包含组合形状中的图片）。图表、矢量图或不支持的图片可能无法预览，可下载原件查看。

程序不做 OCR 或复杂公式重建。没有可提取文本的扫描 PDF 会提示需要处理，不能用于可靠的文本检索。重新索引成功后才切换当前版本；旧版本继续支持已有引用，重建失败也不会删除旧索引。

关键词搜索无需模型，支持中文短词和英文术语。语义检索需要先建立 Embedding 索引；混合检索融合关键词和语义排名，最多使用 200 个候选片段。模型不可用或当前范围没有向量时，页面显示关键词回退提示。笔记搜索使用全文/关键词检索。

## 连接本地模型

默认地址为 `http://127.0.0.1:1234/v1`。项目接受本机 OpenAI-compatible 服务，包括 LM Studio、Ollama 的兼容接口；不自动下载模型，也不调用付费 API 或公网模型服务。

若你已有 LM Studio 和本地模型，可自行在 Developer 页面启动服务，并加载已有模型。已配置 `lms` CLI 时，可执行 `lms load` 选择已有模型，再执行 `lms server start`。操作依据：[LM Studio 本地服务文档](https://lmstudio.ai/docs/developer/core/server)、[加载已有模型文档](https://lmstudio.ai/docs/cli/local-models/load)。这会启动项目之外的 LM Studio；应用本身不会替你启动它。

在“设置”填写服务地址、聊天模型 ID、Embedding 模型 ID，以及服务要求的可选密钥，点击“保存并检测连接”。聊天和 Embedding 模型分别配置；模型列表可访问不代表所选模型已经完成推理验证。然后点击“构建 / 重建 Embedding 索引”。更换 Embedding 模型或导入、重建资料后，应重建语义索引。

在“AI 问答”选择全库、课程或资料范围。回答保存本次证据快照，可展开摘录并返回原文，也可取消正在生成的回答，取消会关闭正在进行的模型 HTTP 传输。后端核对引用 ID 和引文，未通过校验的回答会标为未验证；来源可定位并不能证明模型推导正确，仍应核对摘录。

本轮环境探测中，LM Studio 已安装，但服务未运行、没有已加载模型。因此真实问答及 Embedding 推理尚未验证。`scripts/mock_model_server.py` 是确定性测试服务，不代表真实模型能力；最新状态以 [PROGRESS.md](PROGRESS.md) 为准。

## 笔记与复习

笔记支持 Markdown、表格、代码和 LaTeX 预览，可关联课程、主题、标签及多个来源。引用保留原文摘录、版本和位置。写入 `[[笔记标题]]` 可建立双向链接：唯一同名笔记可自动解析；同名目标需在链接列表中选择，找不到目标会显示未解析。已解析链接使用笔记 ID，重命名后仍保留关系。可单篇导出 Markdown，或批量导出带引用清单的 ZIP。

在“复习”手工创建或编辑卡片与测验。单选、多选按答案集合判分；简答和数学题显示参考答案，由你自评。答题后可查看历史、错题和按主题统计的薄弱项。卡片先显示问题，再显示答案，选择 Again / Hard / Good / Easy 后按 `sm2-v1` 安排下次复习；系统用 UTC 保存时间，按 Asia/Shanghai 展示学习日期。

课程列表显示资料、笔记、到期卡片、已答题数与答题正确率；正确率包含简答和数学题的自评结果。卡片复习与测验提交也会出现在近期活动中。

本地模型可生成卡片、四类 Quiz 及总结草稿。你核对内容和来源后再保存；生成接口本身不把草稿写入学习库。没有模型时仍可完成手工创建、答题与复习。

## 备份、恢复与便携合并

在“设置 → 备份与数据迁移”选择操作：

| 操作 | 内容与行为 |
| --- | --- |
| 完整备份 | 一致性 SQLite 快照、原件和校验清单；包含普通配置，排除模型密钥、Agent 令牌、缓存与日志 |
| 完整恢复 | 验证路径、校验和与 schema 后替换当前库；需输入 `RESTORE`，等待索引和问答结束 |
| 便携导出 | 版本化 JSON、关系、引用、对话、练习和复习历史，以及原件；排除配置、凭据、任务和向量 |
| 便携导入 | 先预览数量与冲突，再确认合并；要求相同应用 schema 版本 |

完整备份和便携包最多 4 GiB 展开数据、20,000 个 ZIP 条目，清单最多 8 MiB、ZIP 中央目录最多 16 MiB。便携 `data.json` 最多 128 MiB。两种归档上传均预留 ZIP 与 multipart 开销，归档文件上限为 4 GiB + 32 MiB。

合并会为课程、笔记、测验和历史生成新 ID，同名记录分别保留。相同原件复用现有资料，保留目标库标题、元数据和当前解析版本，并追加导入的历史来源及课程关系。重复导入同一包会再次追加学习记录。导入不覆盖目标库的模型设置；需重新建立向量索引。API 可用 `include_originals=false` 导出不带原件的包，此类包只能导入到已包含全部对应原件的库。

恢复前的原库保存在数据目录下的 `recovery/<id>`。成功恢复会使现有浏览器会话和 Agent 令牌失效，并移走当前模型密钥；刷新页面后重新填写密钥、创建 Agent 令牌。恢复点可能包含旧模型密钥，按私密数据管理，不要当作分享包。若程序提示需人工恢复，停止服务，保留报告中的 recovery 和暂存目录，不要手动覆盖仍在运行的数据库。

## 本地 Agent API

在设置中创建“只读”或“读写”令牌，完整令牌仅在创建时显示。业务 API 前缀为 `/api/v1`，通过已登录浏览器或 Bearer 令牌读取 [OpenAPI](http://127.0.0.1:8767/api/v1/openapi.json)。Agent 不直接操作 SQLite。

以下示例使用占位令牌；用设置中创建的令牌替换变量值。只读令牌可搜索和读取，创建笔记需要读写令牌。

```sh
WORKSPACE_AGENT_TOKEN='替换为你的本地令牌'
curl -H "Authorization: Bearer $WORKSPACE_AGENT_TOKEN" \
  'http://127.0.0.1:8767/api/v1/search?q=probability&mode=keyword&limit=5'
curl -X POST -H "Authorization: Bearer $WORKSPACE_AGENT_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"复习计划","body":"复习条件概率与贝叶斯公式"}' \
  'http://127.0.0.1:8767/api/v1/notes'
unset WORKSPACE_AGENT_TOKEN
```

设置、令牌管理、备份、恢复和便携导入导出仅允许浏览器管理员会话。撤销令牌后立即失效。数据库只存 Agent 令牌散列；可选模型密钥以明文 JSON 保存在数据目录的 `provider-secret.json`，文件权限为 `0600`，不进入备份或便携导出。

## 故障排查

- **启动失败或端口占用**：确认虚拟环境与 `frontend/dist/index.html` 存在；先停止之前的启动终端，或设置另一个 `WORKSPACE_PORT`。健康检查为 `/api/v1/health`。
- **页面显示旧内容**：重新构建前端、重启后端并刷新浏览器。浏览器会话在重启后重新建立。
- **AI 连接失败**：检查本地模型服务是否运行、端口及 `/v1` 地址是否正确、模型 ID 和密钥是否匹配。连接检测成功后再试真实提问；超时可在设置中调整为 3–180 秒。
- **语义搜索回退**：查看设置中的索引错误，确认 Embedding 模型支持向量接口，再重建。失败的重建保留旧向量；模型维度不匹配时不能混用旧索引。
- **解析失败**：查看资料任务错误，确认文件没有损坏、加密或超限。修正扩展名后可重新导入。原件校验失败需从可靠备份恢复，不要编辑 `originals` 中的文件。
- **重启后的任务**：文档解析任务会重新排队；中断的 Embedding 任务标为失败，需手动重建。恢复/合并得到的中断资料可能需要手动重新索引。
- **意外服务器错误**：页面返回通用错误信息；查看数据目录下的 `logs/workspace.log`，默认路径为 `var/data/logs/workspace.log`。日志使用 UTC 时间，每个文件最多 1 MiB，保留 3 个轮换备份。请求异常只记录路由模板与异常类型，不包含参数、正文或密钥。
- **恢复被拒绝**：等后台任务结束，确认 ZIP 来自本应用且未损坏。新版本备份不能交给旧版程序恢复；便携包要求相同 schema。

## 开发与验证

测试仅使用生成的虚构课程，不读取项目外的个人学习文件。锁定 Python 依赖位于 `requirements.lock`，前端依赖位于 `frontend/package-lock.json`。在项目根目录运行：

```sh
.venv/bin/python scripts/generate_fixtures.py
TMPDIR="$PWD/.cache/tmp" .venv/bin/python -m pytest
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Playwright 使用已安装的 Google Chrome（`channel: "chrome"`），不要求下载额外浏览器。测试自动启动 8766 端口应用和 18765 端口 Mock 模型服务；数据在 `.cache/e2e-runs`，报告在 `frontend/playwright-report`，失败跟踪在 `frontend/test-results`。运行前确保两个端口空闲。独立后端开发仍可使用启动脚本，另开终端运行 `npm --prefix frontend run dev`，Vite 默认代理到本机 8767。

本应用面向单用户、单进程、本机访问。无云同步、协作编辑或公网部署；原件、正文和本地密钥没有磁盘加密，拥有本机文件权限的程序仍可访问。模型只接收本次任务的内容和证据，Provider 拒绝公网地址及重定向。生产脚本关闭访问日志；应用将受限诊断写入数据目录的轮换日志，解析失败记录任务 ID 与错误类型，不记录正文。浏览器安全策略限制脚本、字体和连接来自同源，允许 KaTeX/React 所需的内联样式及本地图片/PDF 预览，禁止外站嵌入页面。

## 已执行的交付验证

2026-10-13：307 项后端、23 项前端、3 条完整浏览器流程和生产构建通过；真实进程重启/备份恢复验证通过。完整范围、原始证据和限制见 [ACCEPTANCE.md](ACCEPTANCE.md)。可用 `./scripts/verify.sh` 复现整套验证（包含生成虚构资料、测试、构建、浏览器、进程持久化和搜索基准）。日常本地实例使用 8767。
