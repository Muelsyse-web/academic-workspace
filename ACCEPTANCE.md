# 核心验收记录

日期：2026-10-13（Asia/Shanghai）。核心实现和本地验收完成。真实 LM Studio 推理未验证；按照原始目标明确允许的替代方式，AI 业务使用 Mock Provider 和真实 HTTP 兼容服务测试，不将其称为真实模型结果。

## 最终执行结果

`./scripts/verify.sh` 完整执行成功：pytest **307 passed**，Vitest **23 passed**，TypeScript/Vite 生产构建通过，Playwright/Google Chrome **3 passed**，实际进程重启恢复脚本通过，搜索基准通过。没有跳过后端用例。日常启动默认端口改为 8767 后再次构建成功，并实测 `/api/v1/health` 返回 schema 5、首页 HTTP 200。

- [完整验证输出](docs/verification/final-verification.log)
- [后端 JUnit 报告](docs/verification/pytest.xml)
- [前端测试 JSON](docs/verification/vitest.json)
- [生产构建输出](docs/verification/production-build.log)
- [实际进程验证](docs/verification/process-lod2skbg.json)
- [搜索基准](docs/verification/search-benchmark-8g6tdxbu.json)
- 浏览器 HTML 报告：`frontend/playwright-report/index.html`；截图：`frontend/test-results/`。

## 原始 13 项场景

| # | 场景 | 状态及实际证据 |
|---|---|---|
| 1 | 按 README 在 Mac 启动 | 通过。本机 macOS/Apple Silicon，Python 3.13.7，安装锁定依赖、构建；`scripts/start.sh` 启动到 127.0.0.1:8767，健康检查与首页 200。8765 已被其他进程占用，因此同步改了日常端口和开发代理。 |
| 2 | 创建课程 | 通过。三个浏览器流程均实际提交课程；后端验证课程字段、修改、删除和重启读回。 |
| 3 | 导入 PDF/PPTX/DOCX | 通过。真实生成的三种文件经浏览器上传；另验证 Markdown/TXT、整文件夹和 DataTransfer 拖拽。 |
| 4 | 正确解析并保留位置 | 通过。解析夹具与原件比对；PDF 物理页、PPTX 幻灯片、DOCX 段落/表格、文本行。原件 SHA-256 保留，文件夹路径作为元数据。 |
| 5 | 中英文检索 | 通过。单字/双字/完整中文问句、英文、多条件筛选、分页和大候选集合回归；语义同义词及混合排序用受控向量验证。 |
| 6 | 从结果定位原文 | 通过。搜索链接包含实际文档/版本/位置；浏览器分别打开 PDF 第 2 页、PPTX 第 1 张与图片、DOCX 第 2 段，并验证 Markdown 来源跳转。 |
| 7 | 配置本地模型并问答 | 本地兼容 HTTP 与 Mock 业务通过；真实 LM Studio 未验证。浏览器在设置中连接 127.0.0.1:18765 的测试服务、选择模型、构建索引并提问。真实 LM Studio CLI 确认服务未运行、无已加载模型。 |
| 8 | 引用追溯 | 通过（受控模型）。验证 ID 属于本次检索、摘录确实存在、来源范围与版本正确；伪造 ID/摘录被拒绝，证据不足和离线状态明确。浏览器展开引用并打开实际来源。 |
| 9 | Markdown 笔记及关联 | 通过。公式、表格、代码渲染；保存/重开；多文档真实摘录；双向链接及同名目标选择；删除目标不静默改连；单篇/批量导出。 |
| 10 | Quiz/Flashcards 与复习 | 通过。浏览器手工建卡并评分；完成单选、多选、简答、数学题；保存模型生成的卡片/测验草稿和学习总结；SM-2、历史、错题、薄弱主题有后端回归。简答/数学题明确自评。 |
| 11 | 关闭、重启后保留数据 | 通过。三次真实 uvicorn 进程启动/关闭，比较所有逻辑表、API 结果、原件哈希、来源单位、笔记、会话与学习历史；没有用重新创建对象代替进程测试。 |
| 12 | 备份恢复全部核心数据 | 通过。浏览器下载备份、添加额外数据、恢复并确认额外状态消失；真实进程脚本恢复后再次重启比对。损坏/越界/异构 schema/并发恢复均有失败保护；凭据与令牌失效，保留恢复点。便携导出预览无写入，合并重映射关系并保留原数据。 |
| 13 | 自动化测试、构建及 E2E | 通过。307 后端、23 前端、3 条完整浏览器流程及生产构建；原始输出与机器可读报告见上。 |

## 模块覆盖与交付文件

| 模块 | 交付范围 | 主要证据 |
|---|---|---|
| A 资料管理 | 五格式、批量/拖放/文件夹、标题/章节位置/元数据、学期/课程/主题、标签/收藏/关联、预览、原件/去重/增量任务/重建 | parsing/documents/previews 测试与浏览器流程 1、3 |
| B 搜索 | FTS5、中文字符片段、语义与混合、范围/文件/类型/标签、笔记入口、原文链接、无模型回退 | search/embeddings 测试，完整中文问句回归，浏览器流程 1、3 |
| C AI | LM Studio/Ollama 兼容服务、独立模型设置、全库/课程/文件、多轮记录、引用验证、实际传输取消、本地 Agent API | providers/provider_cancel/ai/generation/core 测试，浏览器流程 2、3 |
| D 笔记 | Markdown/数学/代码/表格、课程/主题/多文档、摘录、双链/歧义/删除目标、检索和导出 | notes 与 SourcePicker 测试，浏览器流程 2、3 |
| E 复习 | 手工与生成草稿、四类题目、SM-2、记录/错题/进度、弱项练习、无模型使用 | learning/generation 测试，浏览器流程 2、3 |
| F Dashboard | 实际课程/资料/笔记/到期数、学习活动、各课程答题/正确/笔记/复习统计、全局入口、主题和窄屏 | core 统计回归，Dashboard/Courses UI，桌面与移动端截图 |
| G 基础设施 | SQLite 外键/WAL/事务、schema 1–5 迁移及升级恢复点、持久任务、错误重试、脱敏轮换日志、备份/恢复/便携合并、安装文档及测试 | db/core/backup/portable 回归，真实进程验证，README 与 ARCHITECTURE |

要求的 `SPEC.md`、`ARCHITECTURE.md`、`PLAN.md`、`PROGRESS.md`、`AGENTS.md`、`README.md` 均存在并已维护。独立规格、质量、安全审查及修复记录见 [审查报告](docs/REVIEW.md) 与 [安全报告](docs/security_best_practices_report.md)。

## 验证边界

- AI 的真实模型质量、推理速度和真实多语言 Embedding 效果未验证。不会把 Mock 输出冒充真实推理。
- OCR、复杂公式重建和 Office 原始排版不属于本轮可靠交付；扫描件显示缺少文本，DOCX 不虚构页码。
- 单文件 100 MiB；浏览器自动按 200 MiB/100 文件分批；备份/恢复有 4 GiB 与条目数预算，便携 JSON 128 MiB，具体限制见 README。
- 搜索基准为 200 个模拟原件、10,000 个预索引片段、30 次查询：p50 18.109 ms、p95 22.716 ms、测试进程峰值 RSS 53.91 MiB。不是整应用/模型/批量解析性能承诺。
- 引用验证证明来源和摘录存在，不证明模型推导的每个结论正确。用户可逐条回到原文核对。
