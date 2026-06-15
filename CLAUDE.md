# CLAUDE.md

Behavioral guidelines for Claude Code working on **Medical-AI** (HCI research platform). Four sections:

- **Common Commands** — build, test, lint, migrate, and other everyday commands.
- **Architecture** — high-level structure so you can find the right file quickly.
- **Part 1**: General coding behaviors (adapted from claude-code-bmad-foundation).
- **Part 2**: Project-specific invariants — non-obvious rules whose violation breaks the research design, not just code quality.

I am a beginner. When you ask me questions, explain them in plain language and explain what each option means.

---

## Common Commands

### Backend (Python / FastAPI)

```bash
# Run all tests
cd backend && python -m pytest -q

# Run a single test file
python -m pytest tests/test_llm.py -q

# Run a single test function
python -m pytest tests/test_llm.py::test_case_render_never_calls_llm_in_v4 -q

# Run tests with verbose output (shows each test name)
python -m pytest -q -v

# Create a new Alembic migration after editing models
cd backend && alembic revision --autogenerate -m "description_of_change"

# Apply pending migrations
cd backend && alembic upgrade head

# Validate seed data (case content + gold-action distribution)
cd backend && PYTHONIOENCODING=utf-8 python -m app.scripts.validate_data

# Check for dead imports only
cd backend && python -m ruff check app --select F401

# Full pre-commit check: lint + format + typecheck
cd backend && python -m ruff check app && python -m ruff format app --check && python -m mypy app
```

### Frontend (Next.js 14 / TypeScript)

```bash
# Typecheck
cd frontend && npm run typecheck

# Lint
cd frontend && npm run lint

# Run Playwright E2E tests
cd frontend && npx playwright test

# Dev server (proxies /api/* → localhost:8000)
cd frontend && npm run dev
```

### Docker

```bash
# Start dev stack (Postgres + backend)
docker compose up -d --build

# Start prod stack (Postgres + backend + frontend + Caddy + backup)
docker compose -f docker-compose.prod.yml up -d --build

# Clean Docker cache without destroying the Postgres volume
powershell -File docker/clean-cache.ps1
```

---

## Architecture

### Backend (FastAPI, async)

Three-layer design:

```
API layer (app/api/)        → Route handlers, request validation, HTTP concerns
Service layer (app/services/) → Business logic, cross-cutting orchestration
Repository layer (app/repositories/) → Database queries, one class per table
```

Key files and directories:

| Path | Role |
|---|---|
| `app/main.py` | `create_app()` factory — registers all routers, middleware, CORS |
| `app/api/deps.py` | FastAPI dependencies: `DBSession` (yields async DB session), `rate_limit_session`, `rate_limit_admin` |
| `app/core/config.py` | Pydantic `BaseSettings` — all config from env vars (loaded from `.env`) |
| `app/core/security.py` | `require_admin()` — validates `X-Admin-Token` header |
| `app/db/models.py` | **All 11 ORM models in one file** (~320 lines) |
| `app/db/session.py` | Async engine + session factory + `get_db()` generator |
| `app/llm/` | **Factory pattern**: `factory.py` picks a provider (`deepseek` / `dry_run` / `disabled`) based on `LLM_PROVIDER` env var. All providers implement the `LLMProvider` protocol in `base.py`. |
| `app/middleware/` | `RequestIdMiddleware` (adds `X-Request-ID` to every response) + `rate_limiter.py` (in-memory sliding-window) |
| `app/scripts/` | CLI utilities: `seed.py`, `validate_data.py`, `data_loader.py` |

**LLM rule (critical):** Every LLM call MUST go through `services/llm_audit.record_llm_call()` on both success AND failure paths. Skipping audit on the error path breaks research token accounting. The participant flow (V5) does NOT call the LLM at all — it returns seeded `aiDraft` verbatim.

### Frontend (Next.js 14 App Router)

**State management:** A single Zustand store (`src/lib/store.ts`) persisted to `localStorage` drives the entire study flow. It holds `session`, `step`, `caseIndex`, `completionCode`, and `performance`.

**Study flow (route progression):**

```
/ → /consent → /pre-survey → /practice → /case/[order] (× N cases) → /post-survey → /completion
```

The Zustand `step` field controls which page renders; `caseIndex` drives which case within the `case` step.

Key directories:

| Path | Role |
|---|---|
| `src/app/` | Next.js App Router pages — one directory per route |
| `src/components/` | Shared components: `Likert`, `ProgressBar`, `VoiceInputButton`, plus `case/CasePage.tsx` (most complex component, ~8.6KB) |
| `src/lib/api/client.ts` | Fetch wrapper (base URL, error handling) |
| `src/lib/api/types.ts` | TypeScript interfaces for API DTOs (~227 lines) |
| `src/lib/store.ts` | Zustand store — the single source of truth for study state |
| `src/lib/i18n/zh-CN.ts` | Chinese UI dictionary (single file, ~168 lines; English not supported) |
| `src/lib/forms/` | Pre-survey and post-survey form field configs |

**V5 is single-condition.** The guardrail UI panel is intentionally not rendered (`guardrail: None` in `case_service.py`). There is no experimental/control group split — every participant sees the same UI.

### Database (11 tables)

All models in **one file** (`app/db/models.py`). Primary keys are UUID hex strings (`uuid.uuid4().hex`).

Key relationships:
- `Session` → `CasePresentation` ← `Case` (junction with `order_index` and timing)
- `CasePresentation` → `Action` (one-to-one, unique FK)
- `Session` → `UiEvent` (fire-and-forget telemetry)
- `Participant` → `Session` (one participant per session)

Migrations via Alembic (5 revisions in `backend/alembic/versions/`).

### API routes summary

| Route | Method | Purpose |
|---|---|---|
| `/healthz` | GET | Health check |
| `/api/session` | POST | Create participant + session, return case order |
| `/api/case/{id}` | GET | Fetch a case with seeded AI draft |
| `/api/case/open` | POST | Create / return in-progress CasePresentation |
| `/api/action` | POST | Submit decision (action + survey + client stats) |
| `/api/pre-survey` | POST | Submit pre-study survey |
| `/api/post-survey` | POST | Submit post-study survey (marks session complete) |
| `/api/ui-event` | POST | Log UI interaction (fire-and-forget) |
| `/api/voice-recording` | POST | Upload audio recording (multipart) |
| `/api/admin/summary` | GET | Aggregated study statistics |
| `/api/admin/export/*` | GET | CSV / JSON / ZIP data exports |
| `/api/admin/dashboard/*` | GET | Dashboard overview + health + timeseries |
| `/api/admin/llm/*` | POST | LLM-powered cohort / participant summaries |

---

## Part 1 — General behaviors

### 1. Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First
**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

### 3. Surgical Changes
**Touch only what you must. Clean up only your own mess.**

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.
- Remove imports/variables/functions that YOUR changes made unused; don't remove pre-existing dead code unless asked.

### 4. Goal-Driven Execution
**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

### 5. Use Installed Tools Before Going to Memory
**Tools compensate for training-data drift. Use them before relying on memory.**

- **Context7 MCP** (wired in `.mcp.json`): before writing code that uses any library, framework, or SDK (FastAPI, Next.js, SQLAlchemy, recharts, Pydantic, Tailwind, etc.), fetch current docs via `mcp__context7__resolve-library-id` then `mcp__context7__get-library-docs`. Do this even for libraries you recognize — APIs drift.
- **Sequential Thinking MCP**: for complex multi-step reasoning (e.g. designing a new aggregation function, planning a refactor across many files), use `mcp__sequential-thinking__sequentialthinking` to externalize the steps.

---

## Part 2 — Medical-AI project invariants

These are easy to break by accident and break the research, not just the code.

### A. LLM call rules (research validity)

- **V4 rule: the participant flow MUST NOT invoke the LLM at all.** Every participant must see the same seeded `aiDraft` for every case, otherwise the AI text becomes an uncontrolled experimental variable. [`app/api/case.py`](backend/app/api/case.py) returns `case.ai_draft` verbatim with no provider call. Regression: [`test_case_render_never_calls_llm_in_v4`](backend/tests/test_llm.py) asserts `llm_calls` stays empty across both defect and non-defect case loads.
- **Admin-side LLM endpoints still exist** (`/api/admin/llm/cohort-summary`, `/api/admin/llm/participant-summary`, `/api/admin/llm/case-draft`) for researcher-side report generation. These remain bound by: **every LLM call must go through `services/llm_audit.record_llm_call`** on both success and failure paths. Skipping audit on the error path is the bug I fixed in [bc933f9](https://github.com/lordrance/Medical-AI/commit/bc933f9); don't reintroduce it.
- If a future revision re-enables live LLM drafting on the participant side, recover the implementation from the V3 tag at [`backend/app/api/case.py`](https://github.com/lordrance/Medical-AI/blob/V3/backend/app/api/case.py) — don't reinvent it.

### B. Questionnaire 7.0 field naming

- Survey-related columns and JSON keys use **snake_case** to align with the PDF codebook: `pre_specialty`, `case_action_choice`, `log_final_action`, `post_qual_l1_ehr_pain_ai_substitution`, etc.
- DB metadata columns and frontend API DTOs use **camelCase** (e.g. `sessionId`, `casePresentationId`, `payloadJson`).
- Don't "normalize" the naming. The split is intentional and matches the published research instrument.

### C. Case data integrity

- `backend/data/cases.json` defines the 8 formal cases + 1 practice case. The gold-action distribution is locked at **1 send_as_is / 3 edit_then_send / 3 discard_and_rewrite / 1 escalate** per the V3 PDF brief — tested by [`test_v3_gold_action_distribution`](backend/tests/test_seed.py).
- Each case must carry at least one entry in `goldActionAlternates` (the "secondary acceptable action").
- After editing case content, run `python -m app.scripts.validate_data` before committing — it checks order-template constraints (the sole non-defect case must appear in the first half).

### D. Auth / secrets

- The admin UI authenticates via `ADMIN_TOKEN` stored in `sessionStorage` (key: `medai_admin_token`). **Never put the token back in URLs** — it leaks via history / referer / screenshots. The previous behaviour was fixed in [49785cf](https://github.com/lordrance/Medical-AI/commit/49785cf).
- File downloads from `/admin` use `downloadWithToken()` (fetch + Blob + synthetic `<a download>`) so the token only travels in the `X-Admin-Token` header.
- Never read `.env` (blocked by the safety hook). Use `.env.example` to find variable names.

### E. Tests & validation before committing

For any change touching the backend, the minimum verification is:

```bash
cd backend
python -m pytest -q                                # full suite
PYTHONIOENCODING=utf-8 python -m app.scripts.validate_data   # data integrity
python -m ruff check app --select F401             # no dead imports
```

For frontend changes:

```bash
cd frontend
npm run typecheck
```

### F. Commit hygiene

- One commit per logical change. Don't bundle unrelated work.
- Use conventional commit prefixes already in the repo's history: `feat(...)`, `fix(...)`, `chore(...)`, `test(...)`, `docs(...)`, `refactor(...)`.
- Don't skip hooks (`--no-verify`) or amend pushed commits.
- All commits should include `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` per existing convention.

### G. Docker

- The backend Dockerfile defaults to **aliyun** mirrors (apt + PyPI) — tuna mirrors are unstable on the Chinese education network. Don't switch back without testing.
- For Docker disk bloat, use [`docker/clean-cache.ps1`](docker/clean-cache.ps1) instead of running `docker system prune -a -f` blindly (the latter kills the postgres volume too if pgdata is the only volume around).

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
