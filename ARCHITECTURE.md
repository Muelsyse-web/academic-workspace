# 架构草案

状态：用户已于 2026-10-13 明确批准。

## 运行方式和模块边界

React + TypeScript + Vite 前端使用统一 UI 基础和 Markdown/KaTeX 渲染；FastAPI 生产模式提供静态构建和 `/api/v1`，开发模式通过 Vite 代理。SQLite 与文件仓库存于项目内 `var/`，可通过项目内配置改变数据目录。

后端分为 API 路由、应用服务、数据库仓储、文档解析、搜索、AI Provider、学习调度、备份与任务执行模块。路由只处理认证、校验和响应，不包含解析或模型逻辑。解析器返回标准内容单元，不直接修改数据库。Provider 不自行读取磁盘或数据库。

解析接口：`parse(file) -> iterator[SourceUnit]`。SourceUnit 包含文档版本、位置类型、序号、章节、文本及可选媒体。PDF 页码与 PPTX 幻灯片序号从 1 开始；DOCX 段落/表格位置不能标为页码。

检索接口：`search(query, scope, filters, mode, limit) -> SearchHit[]`。SearchHit 保存真实片段 ID、版本、摘录、得分及数据库构造的位置。AI 接口接受消息和受限证据包，返回文本与引用候选；应用服务验证后持久化。

## 数据实体

- semesters、courses、topics、tags：组织结构及受约束的关系。
- blobs：SHA-256、内部路径、大小、类型；documents 保存逻辑资料信息。
- document_courses、document_tags、document_links：多对多归属与关联。
- document_versions、source_units、chunks：不可变解析版本、真实位置、检索片段；active_version 确定当前索引。
- chunks_fts、notes_fts：可重建全文索引；embeddings 记录片段、model、维度和向量。
- jobs：状态、进度、错误、尝试次数与幂等键。
- notes、note_sources、note_links：Markdown 与文档引用、解析后的双向链接。
- conversations、messages、message_sources：问答历史与本次证据快照。
- flashcards、card_reviews：卡片、调度状态和不可变复习事件。
- quizzes、questions、attempts、answers：四类题目、作答、分数和自评来源。
- activities、settings、agent_tokens、schema_migrations：活动记录、配置、散列令牌和迁移版本。

数据库以顺序迁移初始化和升级，使用 sqlite3 参数化查询及清晰仓储方法；避免同时维护 ORM 与另一套原生数据访问层。所有跨表更新在服务层定义事务边界。

## 数据流与一致性

上传流式写入受限暂存区并计算哈希 → 校验格式 → 提交原件与导入任务 → 后台逐单元解析 → 生成 chunks 和 FTS → 原子切换 active_version → 可选 embedding 任务。

搜索限定 scope 后返回片段 → 问答构造 token 预算内证据包 → 本地模型推理 → 校验引用与摘录 → 保存响应和引用快照。引用定位基于片段版本，前端请求来源 API 后打开对应位置。

单进程部署限制有界后台并发，任务失败进入持久化错误状态。重启恢复 interrupted 状态，采用幂等处理；若未来需要独立 worker，在任务接口后替换实现，不先引入 Redis/Celery。

本轮向量规模采用 SQLite 持久化与分批计算，保持 embedding provider 和索引实现可替换。模型维度变化不能混用旧向量。

备份使用数据库一致性快照，在短暂维护窗口协调原件集合；恢复在暂存目录验证，再通过受控切换替换当前数据。备份不得以直接复制活动 WAL 数据库主文件实现。

## 资源和安全默认值

默认上传单文件上限 100 MiB，采用流式处理；ZIP 条目数、展开总大小和压缩比另设预算。解析并发初始为 1，embedding 小批量。请求具备超时和取消；日志轮换。

生产服务监听 127.0.0.1；固定同源前端、Host/Origin 校验、本地会话认证、Agent 散列令牌及权限范围共同控制访问。Provider 默认仅允许 loopback，禁止自动重定向到远程地址。外部访问代表本机 Agent 调用 API，不代表开放公网。

Markdown 禁止原始 HTML 执行，外链协议校验；导入归档不直接解压到最终目录；下载按数据库 ID 取文件。只记录诊断元数据，不记录资料正文和秘密。

## 后续实施规划约束

以 SPEC.md 的 M1–M10 为里程碑。批准后通过 writing-plans 制定每段的文件职责、测试先行任务、命令和验收证据，再实施。依赖版本以实际运行环境及官方文档为准，写入锁文件。每个里程碑完成后更新 PLAN.md 与 PROGRESS.md。
