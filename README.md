# AI Plan Issue

AI Plan Issue is a standalone, local-first planning board for AI-assisted software development. It turns a large goal or development plan into parent issues, child issues, priorities, dependencies, comments, activity records, and a realtime board that humans and AI agents can share.

中文说明在前，English version follows.

---

## 中文版

### 这是什么

AI Plan Issue 让用户和 AI 不再只依赖聊天上下文开发项目，而是围绕一组可追踪 issue 协作。用户可以提出大目标，AI 将目标拆成父单、子单、模块、优先级、验收标准和执行顺序；随后 Codex、Claude Code 或其他 agent 可以 claim 具体 issue、评论、更新状态，并把实现记录写回项目。

这是独立项目。默认运行不依赖 Spec Kit、`specify_cli` 或 `.specify/extensions`。

### 核心能力

- 从 `tasks.md` 生成父子 issue。
- 支持手动新增父单和子单。
- SQLite 作为实时状态源。
- Markdown/JSONL 持续导出，方便审阅、留档和版本管理。
- 本地或局域网 Web 看板。
- REST 写入，Server-Sent Events 实时同步。
- 项目 token 保护写入；LAN 模式下读写都需要 token。
- Codex 插件包装，支持 AI 按 issue 协作开发。
- 可选 Spec Kit 兼容层，放在 `compat/spec-kit-extension/`。

### 快速开始

准备一个任务文件：

```markdown
# Tasks

## Phase 1: Board foundation

- [ ] T001 Create issue data model
- [ ] T002 Build local board server
- [ ] T003 Render issue cards

## Phase 2: Agent workflow

- [ ] T004 Add claim command
- [ ] T005 Append comments and activity
```

生成 issue：

```bash
scripts/ai-plan-issue generate --tasks tasks.md --force
```

启动看板：

```bash
scripts/ai-plan-issue-board --port 8768
```

服务会打印：

```text
AI Plan Issue board: http://127.0.0.1:8768
Authenticated URL: http://127.0.0.1:8768/?token=<project-token>
Realtime store: .ai-plan-issue/ai-plan-issue.db
```

用 CLI 更新 issue：

```bash
scripts/ai-plan-issue claim --agent codex-local AI-001-01
scripts/ai-plan-issue status --author codex-local AI-001-01 in_review
scripts/ai-plan-issue comment --author codex-local AI-001-01 "Ready for review."
```

### 数据目录

默认数据在项目根目录的 `.ai-plan-issue/`：

```text
.ai-plan-issue/
├── ai-plan-issue.db
├── ai-plan-issue.token
├── index.json
├── board.md
├── 001-board-foundation/
│   ├── issue.md
│   ├── comments.jsonl
│   ├── activity.jsonl
│   └── implementation.md
└── 001-01-create-issue-data-model/
    ├── issue.md
    ├── comments.jsonl
    ├── activity.jsonl
    └── implementation.md
```

可以用 `AI_PLAN_ISSUE_DIR` 改变存储目录：

```bash
AI_PLAN_ISSUE_DIR=.project/issues scripts/ai-plan-issue generate --tasks tasks.md
```

不要把 `.ai-plan-issue/ai-plan-issue.db` 或 `.ai-plan-issue/ai-plan-issue.token` 发布到公开仓库。

### Codex 插件

Codex 插件在：

```text
plugins/codex/
├── .codex-plugin/plugin.json
├── skills/ai-plan-issue/SKILL.md
├── scripts/
└── assets/
```

插件要求 AI：

- 先读取 issue、父单、依赖、评论、活动记录和项目文档。
- 执行前 claim 一个具体 issue。
- 只实现当前 issue 范围内的工作。
- 执行后更新状态、评论/活动和 implementation notes。

### 可选 Spec Kit 兼容

`compat/spec-kit-extension/ai-plan-issue/` 保留旧的 Spec Kit extension 包装。需要和 Spec Kit 的 `/speckit.ai-plan-issue.*` 命令一起使用时，可以从这里复制或安装兼容层。

主线功能不依赖这个目录。

---

## English Version

### What is this?

AI Plan Issue is a standalone collaboration board for AI-assisted development. It turns a broad goal into a durable issue tree with parent issues, child issues, priorities, dependencies, comments, activity records, and a realtime board shared by humans and agents.

It does not require Spec Kit, `specify_cli`, or `.specify/extensions` for normal use.

### Features

- Generate parent and child issues from `tasks.md`.
- Create parent or child issues manually.
- Use SQLite as the realtime source of truth.
- Export Markdown and JSONL for review, archival, and version control.
- Run a local or LAN web board.
- Use REST for writes and Server-Sent Events for realtime updates.
- Protect writes with a project token; LAN mode requires token access for reads and writes.
- Ship a Codex plugin wrapper for issue-driven agent work.
- Keep optional Spec Kit compatibility under `compat/spec-kit-extension/`.

### Quick Start

Create a task file:

```markdown
# Tasks

## Phase 1: Board foundation

- [ ] T001 Create issue data model
- [ ] T002 Build local board server
- [ ] T003 Render issue cards
```

Generate issues:

```bash
scripts/ai-plan-issue generate --tasks tasks.md --force
```

Start the board:

```bash
scripts/ai-plan-issue-board --port 8768
```

Update issues from CLI:

```bash
scripts/ai-plan-issue claim --agent codex-local AI-001-01
scripts/ai-plan-issue status --author codex-local AI-001-01 in_review
scripts/ai-plan-issue comment --author codex-local AI-001-01 "Ready for review."
```

### Runtime Data

The default project-local data directory is `.ai-plan-issue/`:

```text
.ai-plan-issue/
├── ai-plan-issue.db
├── ai-plan-issue.token
├── index.json
├── board.md
└── issue folders...
```

Override it with:

```bash
AI_PLAN_ISSUE_DIR=.project/issues scripts/ai-plan-issue generate --tasks tasks.md
```

Do not publish runtime databases, token files, local paths, or private project records.

### API

The board exposes:

- `GET /api/v1/session`
- `GET /api/v1/issues`
- `GET /api/v1/issues/{id}`
- `POST /api/v1/issues`
- `PATCH /api/v1/issues/{id}`
- `POST /api/v1/issues/{id}/comments`
- `POST /api/v1/issues/{id}/claim`
- `POST /api/v1/issues/{id}/assign`
- `GET /api/v1/events`
- `POST /api/v1/import`
- `POST /api/v1/export`

SSE event types:

- `issue.created`
- `issue.updated`
- `comment.created`
- `activity.created`
- `presence.updated`
- `board.exported`

### Reference Repositories / 参考仓库

| Repository | How it was referenced |
| --- | --- |
| [github/spec-kit](https://github.com/github/spec-kit) | Referenced for the original extension workflow, task file conventions, and optional compatibility layer. The standalone runtime does not require Spec Kit. |
| [multica-ai/multica](https://github.com/multica-ai/multica) | Referenced for the product direction of human-agent collaboration around issue boards, agent ownership, comments, and status transitions. No direct source code from Multica is copied. |

