# Local Academic Workspace Implementation Plan

用户于 2026-10-13 批准完整范围并授权持续实施。需求见 [SPEC.md](SPEC.md)，实际结果见 [PROGRESS.md](PROGRESS.md) 与 [ACCEPTANCE.md](ACCEPTANCE.md)。以下勾选记录已存在的实现，不代替最终验收；测试数量和性能数字只在证据文档记录。

## 实现清单

- [x] M1：批准需求与总体架构，建立项目边界和生成式测试资料规则。
- [x] M2–M3：FastAPI/React 工程、SQLite 顺序迁移、会话与 Agent 权限、课程管理、Dashboard、锁文件和本地启动脚本。
- [x] M4：五种格式、多文件/文件夹/拖放导入、哈希去重、持久化任务、版本索引、来源定位、PDF/Office 内容预览、PPTX 受限图片与资料关联。
- [x] M5：中英文关键词检索、范围过滤、分页、原文入口、语义索引和混合搜索及失败回退。
- [x] M6：本机 Provider 配置、会话与范围、证据验证、HTTP 传输取消、令牌管理及 OpenAPI。
- [x] M7：Markdown/LaTeX 笔记、引用选择、稳定双链及歧义选择、笔记搜索和单篇/批量导出。
- [x] M8：手工卡片与四类 Quiz、SM-2、判分/自评、历史与错题、薄弱主题及带来源生成草稿。
- [x] M9 实现：Dashboard、课程、资料、搜索、问答、笔记、复习、设置页面；主题、窄屏导航和共享状态组件；课程学习统计与复习/测验近期活动。
- [x] M10 诊断能力：本地 UTC 轮换日志、请求异常脱敏与通用 500、CSP 及浏览器安全响应头。
- [x] M10 数据能力：一致性备份、受控恢复、恢复点、便携导出/预览/事务合并、导出排除凭据。
- [x] M10 使用文档：安装、启动、模型配置、使用流程、API 示例、迁移策略和实际限制。

## 最终集成与证据

- [x] 完成最终浏览器集成验证，核对课程统计、来源预览与失败状态。
- [x] 对最终集成代码运行完整 pytest、Vitest、生产构建和 Playwright，并记录实际结果。
- [x] 完成独立进程重启、恢复持久化和失败保护验证。
- [x] 完成独立审查，修复发现的问题并记录相应复测。
- [x] 逐项填写原始验收场景的证据、限制及实际性能规模。
- [x] 由主任务根据全部证据判断交付状态，不能用实现清单代替 Goal 完成条件。

LM Studio 环境探测结果为服务未运行、无已加载模型。真实推理暂未验证；如用户现有环境就绪，再使用虚构资料记录模型 ID、真实问答与 Embedding 结果。不得将 Mock 测试记作真实推理，不自动启动或下载项目之外的模型。

## 文件职责与验证入口

| 范围 | 核心文件 | 回归入口 |
| --- | --- | --- |
| 初始化/权限 | `backend/workspace/{app,db,security,admission,limits,diagnostics,courses}.py`、SQL 迁移 | `test_core.py`、`test_db.py` |
| 资料与检索 | `documents.py`、`parsing.py`、`jobs.py`、`previews.py`、`search.py` | `test_documents.py`、`test_parsing.py`、`test_previews.py`、`test_search.py` |
| 模型与生成 | `providers.py`、`configuration.py`、`ai.py`、`citations.py`、`embeddings.py`、`generation.py` | `test_providers.py`、`test_provider_cancel.py`、`test_ai.py`、`test_embeddings.py`、`test_generation.py` |
| 学习 | `notes.py`、`learning.py` | `test_notes.py`、`test_learning.py` |
| 迁移 | `backup.py`、`portable.py` | `test_backup.py`、`test_portable.py` |
| UI | `frontend/src/` | Vitest、`frontend/e2e/workspace.spec.ts` |

上述后端测试位于 `backend/tests`，缩写业务文件位于 `backend/workspace`。原始基础子计划保留在 `docs/plans/01-foundation.md`，后续实现以当前接口和批准范围为准。

```sh
TMPDIR="$PWD/.cache/tmp" .venv/bin/python -m pytest
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

运行端到端测试前先构建前端，使用已安装 Google Chrome。测试端口为 8766/18765，隔离数据为 `.cache/e2e-runs`；真实日常数据为 `var/data`。新增业务逻辑采用有意义的失败测试、实现、相关回归及审查；文档小改不追加镜像测试。依赖改动同时更新锁文件，禁止伪造测试、模型或性能证据。
