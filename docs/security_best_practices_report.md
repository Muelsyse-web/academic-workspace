# 安全审查报告

2026-10-13。范围为本地单用户 React/TypeScript + FastAPI 应用。独立审查确认两项低风险问题，均已修复并复核；未确认认证绕过、服务端路径穿越、SQL 注入、远程 Provider 逃逸或 XSS。最终综合测试不代替渗透测试或解析器模糊测试。

## 已修复发现

### SEC-01：模型响应先缓冲后检查预算（Low，已修复）

- 位置：`backend/workspace/providers.py:30`、`:53`、`:106`。
- 复现：合成分块响应超过 8 MiB 时，旧实现读取完整 12 MiB 后才拒绝。异常本机模型服务可能消耗过多内存。
- 修复：同步/异步均流式读取解码后的数据，在首个越界块停止累积并关闭传输。取消会取消并等待 HTTP 任务结束，关闭 socket。
- 证据：`test_providers.py`、`test_provider_cancel.py` 覆盖分块、压缩响应、首部/正文阶段取消及完整响应。独立复核通过。

### SEC-02：恢复后的任意笔记 ID 进入导出文件名（Low，已修复）

- 位置：`backend/workspace/notes.py:66`、`:194`、`:256`。
- 复现：合成数据库笔记 ID 为 `../../outside`，合法备份恢复后，旧版 ZIP 导出生成穿越成员名；单篇下载头也直接使用原 ID。风险发生在下游不安全解压器或下载客户端。
- 修复：正常生成的 UUID 文件名保持稳定；其他 ID 使用 SHA-256 安全基名。ZIP 路径与 Content-Disposition 都使用此规则，manifest 保留逻辑身份。
- 证据：`test_notes.py` 实际备份→恢复→恶意 ID 导出的回归，包含特殊字符下载头。独立复核通过。

## 已检查控制

- loopback 监听、Host/Origin/Fetch Metadata、HttpOnly/SameSite 会话、CSRF、Bearer 范围与撤销；本地 HTTP 不错误启用 Secure cookie。
- 请求体预算、上传流、原件哈希与路径、Office 归档预算、PPTX 图片/像素/缓存边界。
- ZIP 路径/重复条目/哈希/schema/外键校验；恢复与已入场请求互斥；失败回滚、恢复点及凭据失效。
- 模型 URL 仅 loopback、禁用环境代理及跳转；API 密钥 0600 本地文件且不进入备份/便携包。
- SQL 参数化，服务端控制引用 ID/位置，模型与文档不能执行工具。
- Markdown 禁用原始 HTML 和远端图像自动加载；KaTeX 安全默认值；本地 CSP、nosniff、同源框架及 referrer 策略。
- 通用 500 与日志只记录路由模板/异常类别；不记录请求体、资料正文或密钥。

## 复核边界

独立安全复核运行了 106 项相关 provider、取消、笔记、预览和解析测试；之后主任务完整验证 307 项后端测试。未进行真实模型推理、依赖漏洞公告全量扫描、穷尽浏览器攻击或解析器 fuzzing。项目内置 100 MiB 原件、图片/归档和备份资源上限，超限内容会明确拒绝。
