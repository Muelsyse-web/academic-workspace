# Scholar · Local Academic Workspace

React + FastAPI + SQLite 的本地学术工作空间，面向中英文课程资料。当前已实现课程、五种文档导入、原文定位、关键词搜索与 Dashboard；AI、笔记、复习与备份仍在开发。完整范围见 SPEC.md，真实进度见 PROGRESS.md。

## macOS 安装与启动

需要 Python 3.11+、Node.js 22.12+ 和 npm。首次安装需要网络下载依赖，日常基础功能无需联网或 AI 模型。命令均在本项目目录运行。

```sh
mkdir -p .cache/tmp .cache/pip .cache/npm
python3 -m venv .venv
PIP_CACHE_DIR="$PWD/.cache/pip" TMPDIR="$PWD/.cache/tmp" .venv/bin/pip install -r requirements.lock
npm --prefix frontend --cache "$PWD/.cache/npm" ci
npm --prefix frontend run build
./scripts/start.sh
```

浏览器打开 http://127.0.0.1:8765。服务只监听本机，Ctrl+C 停止。再次运行启动脚本即可读取原有数据。默认数据目录 `var/data`，通过 `WORKSPACE_DATA_DIR` 指定项目内另一个目录，端口通过 `WORKSPACE_PORT` 配置。不要同时启动两个后端操作同一个目录。

## 资料与搜索

1. 在“我的课程”创建课程和学期，进入课程后选择或拖入资料。
2. PDF、PPTX、DOCX、TXT、Markdown 会保留原件并在后台解析。单文件上限 100 MiB，每批请求上限 256 MiB；大批资料分批导入。
3. 在资料页可查看状态、重新索引、编辑标签/主题/课程、收藏及下载原件。
4. 在“知识搜索”输入中英文关键词并筛选课程/格式。点击结果打开实际来源位置。

PDF 定位到物理页，PPTX 定位到幻灯片，DOCX 定位到段落/表格，文本文件定位到起始行。Office 在线内容预览不重建原始排版。扫描 PDF 需要 OCR，当前会显示缺少文本提示。重新索引保留旧版本供引用使用。

重复内容按 SHA-256 去重，可关联多个课程。误用扩展名导致失败时，可改正扩展名后重新导入。未指定课程的资料仍在全库中。

## 本地 Agent API

所有业务接口位于 `/api/v1`；浏览器本地会话或 Agent Bearer 令牌验证后可读取 `/api/v1/openapi.json`。只读令牌不能写入；设置、令牌管理和数据恢复仅浏览器管理员会话可操作。管理 UI 随后续里程碑提供，现阶段可用已认证 API 创建令牌。

默认 LM Studio 地址为 http://127.0.0.1:1234/v1。本轮初次探测返回连接拒绝，真实推理尚未验证；不得将测试 Mock 视为本机模型可用。

## 测试资料与验证

模拟数据只包含虚构课程，不会读取项目外的个人学习文件。

```sh
.venv/bin/python scripts/generate_fixtures.py
TMPDIR="$PWD/.cache/tmp" .venv/bin/python -m pytest
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

当前 Playwright 配置使用已安装的 Google Chrome，测试服务端口 8766，数据存于 `.cache/e2e-data`。测试报告在 `frontend/playwright-report`，截图与失败跟踪在 `frontend/test-results`。这些测试资料不进入日常 `var/data` 数据库。

开发可分别运行后端和 `npm --prefix frontend run dev`；前端开发代理连接本机 8765。所有依赖缓存和测试数据应留在项目内。
