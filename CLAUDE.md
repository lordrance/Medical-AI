# CLAUDE.md

Behavioral guidelines for Claude Code working on **Medical-AI** (HCI research platform). Two sections:

- **Part 1**: General coding behaviors (adapted from claude-code-bmad-foundation).
- **Part 2**: Project-specific invariants — these are non-obvious rules whose violation breaks the research design, not just code quality.

I am a beginner. When you ask me questions, explain them in plain language and explain what each option means.

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

- **Never call the LLM on a `defect_present=True` case for `case_draft`.** The seeded `aiDraft` for these cases contains an intentional flaw — the experiment depends on showing it as-is to the participant. Letting the LLM rewrite it silently "fixes" the flaw and invalidates that case. Enforced by [`app/api/case.py:_generate_case_draft`](backend/app/api/case.py); regression test [`test_defect_case_skips_case_draft_llm_call`](backend/tests/test_llm.py).
- **Every LLM call must go through `services/llm_audit.record_llm_call`**, on both success and failure paths. This populates `llm_calls` so researchers can audit token usage, error rate, and provider behaviour. Skipping audit on the error path is the bug I fixed in [bc933f9](https://github.com/lordrance/Medical-AI/commit/bc933f9); don't reintroduce it.

### B. Questionnaire 7.0 field naming

- Survey-related columns and JSON keys use **snake_case** to align with the PDF codebook: `pre_specialty`, `case_action_choice`, `log_final_action`, `post_qual_ehr_redesign`, etc.
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
