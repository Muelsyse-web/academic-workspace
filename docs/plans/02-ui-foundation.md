# Connected library UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Expose the verified course, import, source and search APIs through a usable responsive interface.
**Architecture:** HashRouter avoids server history fallback; typed API client centralizes local session/CSRF. Shared Radix dialogs and semantic form controls provide consistent interaction.
**Tech Stack:** React, TypeScript, Vite, Radix Dialog, Lucide, react-markdown, KaTeX, Vitest and Playwright.

- [x] Markdown test first: assert heading/table/code/math visible, HTML scripts and javascript links cannot execute; implement safe renderer. 2 passed.
- [x] Course form test first: submit named course and verify typed API payload; implement create/edit/remove form and course cards. 1 passed.
- [x] Add Library test that chooses files, submits multipart files/course, displays saved title and opens actual source locator.
- [x] Implement `pages/Library.tsx` list/filter/import/jobs and `pages/DocumentView.tsx` version-aware source viewer. PDF original uses iframe with page fragment; DOCX/PPTX text view explicitly labeled as extracted preview.
- [x] Add Search test that submits query, verifies hit and source URL containing version and locator.
- [x] Implement `pages/Search.tsx`, `pages/Dashboard.tsx`, `App.tsx`, `styles.css`; overview uses only API counts; no invented activity.
- [x] Run Vitest, TypeScript/build, then Playwright against actual application and synthetic fixtures. Verify narrow viewport, dark mode and error/empty states.

API contracts come from PLAN.md. Source links use `/documents/:id?version=:version&locator=:n`; original download is authenticated cookie fetch. Browser folder picker uploads files, never server filesystem paths. Form submission awaits HTTP outcome, records errors, disables repeat submit while busy. Preserve selected course in import and search filters.

实施核对：核心实现及最终验证已完成，实际结果与限制以根目录 ACCEPTANCE.md 为准。真实 LM Studio 推理仍未验证；条件性真实模型检查由环境状态记录完成，不能视为真实推理通过。
