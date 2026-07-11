# Prody — Team integration handoff

> **Branch:** `feat/prody-team-integration`  
> **This is the only branch you need.** It combines engine + dashboard + MCP deploy agent + IDE extension + landing.

Give this file (and root `AGENTS.md`) to your coding agent at the start of every session.

---

## What was done (already on this branch)

| Area | Path | Status |
|------|------|--------|
| Security gate | `pentest/` | Merged, runs on `:8900` |
| Engine orchestrator | `engine/orchestrator.py` | Full pipeline wired |
| FastAPI + SSE backend | `backend/main.py` | Runs on `:8000` |
| Modular agents | `agents/` | architect, devops, sre |
| Gcloud fallback | `tools/gcloud.py` | Legacy deploy path |
| **MCP deploy agent** | `deploy_agent/` | Teammate's `managed_deploy.py` + `runner.py` wired into orchestrator |
| Web dashboard | `dashboard/` | Intake, SSE session view, approval panel (scaffold UI) |
| **IDE extension** | `extension/` | VS Code / Cursor / Antigravity — security loop + fix MD |
| Cursor agent rules | `.cursor/rules/` | Prody workflow + security fix guide |
| Landing | `landing/` | Pipeline narrative, CTAs → dashboard |
| Demo app | `demo_app/` | Secure Flask app for E2E |
| Agent instructions | `AGENTS.md` | Root-level for Antigravity / IDE agents |

### Superseded branches (do not branch off these)

- `feat/integrated-deploy-mcp` — merged in
- `feat/prody-ide-extension` — merged in

---

## End-to-end workflow (what we integrated)

```
intake
  → functional_gate (functest on :8900 — HARD GATE, blocks deploy on FAIL)
  → security_scan (pentest gate on :8900 — HARD GATE, blocks deploy on FAIL)
  → architect (Managed Agent + architecture.jpg if MCP available)
  → [human approval] (dashboard or IDE extension)
  → deploy (Google Cloud MCP via deploy_agent/runner.py, or gcloud fallback)
  → sre (health check + handoff)
  → deploy URL + readiness score
```

**Merged from `feat/pentest-agent`:** functional testing gate (`pentest/functest/`), dashboard `GatePanel` (Works? / Secure?), extension dual-gate fix loop.

**Local Gemma (Ollama):** when `PRODY_GEMMA_ENABLED=1` and Ollama is running, gate findings and executive summaries are narrated on-device via `engine/gemma_local.py` before falling back to cloud Gemini. Check: `GET /api/gemma/status`.

**Security fail loop (IDE):**

1. User runs **Prody: Ship to Production**
2. Findings stream to Prody sidebar
3. Engine writes **`PRODY_SECURITY_FIXES.md`** in workspace root
4. User/agent implements fixes
5. User runs **Prody: Retry After Fixes**
6. When gate = `PASS` or `PASS_WITH_WARNINGS` → pipeline continues

---

## How to run the full stack locally

```bash
# 1. Dependencies
pip install -r requirements.txt
cd dashboard && npm install && cd ..
cd extension && npm install && npm run compile && cd ..

# 2. Env (engine + MCP deploy)
# GEMINI_API_KEY=...
# gcloud auth login
# optional: GOOGLE_CLOUD_MCP_PROJECT=your-project-id

# Terminal 1 — security gate
uvicorn pentest.main:app --host 127.0.0.1 --port 8900

# Terminal 2 — Prody engine
uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Terminal 3 — landing (optional)
cd landing && npm run dev          # :3000

# Terminal 4 — dashboard
cd dashboard && npm run dev        # :3001
```

**Quick E2E test path:**

```text
Dashboard: http://localhost:3001
Local path: <absolute path>/demo_app
```

Or POST:

```bash
curl -s -X POST http://127.0.0.1:8000/api/session/start \
  -H "Content-Type: application/json" \
  -d "{\"source\":\"dashboard\",\"project_path\":\"<abs>/demo_app\"}"
```

Then open: `http://localhost:3001/session/<session_id>`

---

## How to integrate / test the IDE extension

The extension is a **thin client** to the same engine API as the dashboard. It does not run deploy itself.

### Install (development)

```bash
cd extension
npm install
npm run compile
```

**Cursor / VS Code:**

1. Open the `extension/` folder in the editor
2. Press **F5** → Extension Development Host opens
3. In that window, open the target app (e.g. `demo_app/`)
4. Command Palette → **Prody: Ship to Production**

**Docs:**

- `extension/README.md` — extension commands and settings
- `cursor/README.md` — Cursor-specific setup

### Extension settings

| Setting | Default |
|---------|---------|
| `prody.engineUrl` | `http://127.0.0.1:8000` |
| `prody.dashboardUrl` | `http://localhost:3001` |
| `prody.fixesFileName` | `PRODY_SECURITY_FIXES.md` |

### Extension commands

| Command | When to use |
|---------|-------------|
| **Prody: Ship to Production** | Start full pipeline from workspace root |
| **Prody: Retry After Fixes** | After implementing security fixes |
| **Prody: Open Security Fixes Guide** | Opens `PRODY_SECURITY_FIXES.md` |
| **Prody: Approve & Deploy** | When architecture approval is pending |
| **Prody: Open Web Dashboard** | Same session in browser |

### For your coding agent (Cursor / Claude / Antigravity)

Point the agent at these files:

1. **`INTEGRATION.md`** (this file) — system context
2. **`AGENTS.md`** — security-first loop rules
3. **`.cursor/rules/prody-workflow.mdc`** — always-on Prody context in Cursor
4. **`.cursor/rules/prody-security-fixes.mdc`** — applies when `PRODY_SECURITY_FIXES.md` is open

When security fails, tell the agent:

> Read `PRODY_SECURITY_FIXES.md` and implement every fix under **Open issues**. Then I'll run **Prody: Retry After Fixes**.

---

## Engine API contract (do not break without updating TASKS.md)

```
POST /api/session/start
  { source: "ide"|"dashboard", project_path?, repo_url?, project_id?, region?, service_name? }
  → { session_id }

GET  /api/session/{id}/events     → SSE (type, agent, message, data?)
POST /api/session/{id}/approve    → { step_id, approved: true|false }
GET  /api/session/{id}/status     → phase, deploy_url, pending_approval, readiness_score
GET  /api/session/{id}/architecture.jpg
GET  /api/session/{id}/report
```

**Key SSE event types:** `finding`, `gate`, `approval_required`, `architecture_image`, `deploy_url`, `finished`, `error`

**Phases:** `intake` → `security_scan` → `architect` → `deploy` → `sre`

---

## What still needs work (your integration tasks)

| Priority | Task | Owner hint |
|----------|------|------------|
| P0 | Dashboard rich UI — finding cards, gate badge, deploy checklist (not plain log) | Teammate |
| P0 | E2E live test: pentest + engine + dashboard on `demo_app` | Teammate |
| P1 | MCP deploy path: SRE handoff should pass `deploy_url` into `deploy_result` for MCP sessions | Small engine fix |
| P1 | `DEMO.md` — 3-minute judge rehearsal script | Either |
| P2 | Root README runbook | Either |

**Do all new work on `feat/prody-team-integration`.** One PR when ready.

---

## Git workflow for teammate

```bash
git fetch origin
git checkout feat/prody-team-integration
git pull

# If you have commits on another branch:
git merge origin/your-branch    # resolve conflicts once here

# Commit with prefix: teammate: or cursor: or claude:
git push origin feat/prody-team-integration
```

**Open one PR:** `feat/prody-team-integration` → `main`

---

## Architecture map (quick reference)

```
landing (:3000) ──CTA──► dashboard (:3001)
                              │
                              ▼ SSE / REST
IDE extension ──────────► backend (:8000) ──► engine/orchestrator.py
                              │
                              ├──► pentest gate (:8900)
                              └──► deploy_agent/runner.py ──► GCP MCP + Managed Agents
```

---

## Questions?

- Coordination log: `TASKS.md` → Agent Log (append, don't delete)
- Product vision: `context.md`, `hackathon.md`
