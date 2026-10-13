# Local Academic Workspace

本地优先学术资料、检索、问答、笔记与复习应用。当前正在实现，尚未达到交付状态。

已批准需求见 SPEC.md；架构见 ARCHITECTURE.md；任务与验收见 PLAN.md、ACCEPTANCE.md；实际结果见 PROGRESS.md。

开发环境：macOS Apple Silicon、Python 3.11+、Node.js 22.12+。所有命令在本项目目录运行。

```sh
mkdir -p .cache/tmp .cache/pip
python3 -m venv .venv
PIP_CACHE_DIR="$PWD/.cache/pip" TMPDIR="$PWD/.cache/tmp" .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
```

应用启动及最终操作说明将随实际可运行功能更新。不要将项目目录之外的个人资料用于自动化测试。
