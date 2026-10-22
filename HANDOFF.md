# Project Handoff — Prediction Market Intelligence Hub

**Written by**: Claude Code, on Erfanur's Mac, 2026-10-23, so a fresh
session (on a different PC, or just a different day) can pick this up
without redoing the conversation. This **replaces** the previous
Release-0-era handoff — that work is long done and merged. **Read this
file first in any new session on this project.**

---

## 1. What this project is (unchanged from Release 0/1)

**ASD 2026 (41026 Advanced Software Development)** group project, Group
29. Topic: Prediction Market Intelligence Hub — an Agentic AI
microservices app for prediction-market analysis. All market data is
seeded mock data, not a live feed.

- **Repo**: https://github.com/Erfanur1/ADVSD
- Full spec: `docs/reference/ASD_2026_Project_Specifications.pdf`
- The actual Release 2 brief (pasted into chat this session, not yet a
  file in the repo) is reproduced in full at the bottom of this doc under
  §7, since it's the authority for everything below.

| Member | Feature | Owns |
|---|---|---|
| Alex Choi | Market Watchlist & Discovery | `student-1/` |
| Christopher (Christian) Kumarelil Cherian | Portfolio & Position Tracker | `student-2/` |
| Humza Hussain | Market Research Notes & News Feed | `student-3/` |
| **Erfanur Rahman (Erfy) — the user** | AI Market Analyst Assistant | `student-4/` |

Release 2 (Multi-Agent Systems, Testing & Cloud Deployment, 30% +6
bonus) is **due Sunday 25 Oct 2026, 23:59 AEST** — i.e. very soon.

---

## 2. What happened this session

1. **Synced from a stale clone.** Local `main` was ~7 weeks and 64
   commits behind `origin/main`. Pulled everything; no conflicts, no
   unmerged branches — PRs #7–#22 had all already landed cleanly.

2. **Synopsis of what the team did while this clone was stale:**
   - **Alex** (Release 1, Sept 22–29): shared live market-data layer,
     shared MCP server, shared RAG server, shared agentic validation
     loop; wired MCP/RAG into Student 1.
   - **Alex** (Release 2, Oct 14–16, PR #20): the shared **Multi-Agent
     Server** (`ai-services/multi-agent-server/` — Planner/Worker/
     Reviewer + mandatory human review, port 8300, HTTP + `cli.py`);
     the shared pre-commit security config (Ruff `S` rules,
     detect-secrets, pip-audit); Azure Container Apps Bicep IaC + deploy
     scripts; the `cloud-deployment.yml` workflow; Student 1's Release 2
     endpoint tests/CI.
   - **Christopher** (PR #21, merged 22 Oct): integrated Student 2 with
     Alex's Multi-Agent Server (`review_portfolio` task type, routes, UI
     review panel), endpoint tests for `/positions` and `/trade-history`.
   - **Humza** (PR #22, merged overnight 22→23 Oct, pulled in *this*
     session): Student 3's Release 2 work — multi-agent integration,
     security scanning, endpoint tests (`student-3/tests/`).
   - **Erfanur (you)**: Student 4 cross-exchange mispricing feature,
     Kalshi data-layer swap, UI refresh (shared sidebar/theme).

3. **Actually ran the whole thing and verified it, not just read it:**
   - Started the 3 shared non-containerised AI services locally (venv at
     `/tmp/advsd-aiservices-venv` on *this* Mac — **does not survive a
     machine switch**, recreate per §4 on the new PC):
     MCP `:8100` (7 tools incl. `compare_markets`, `validate_portfolio`,
     `get_exposure_summary`), RAG `:8200`, Multi-Agent `:8300`.
   - Brought up the full `docker compose` stack (11 containers: ollama,
     ai-mode, home, 4× student backend+frontend). All `/health` checks
     green; Student 2 and Student 4 backends confirmed `mcp_enabled`/
     `rag_enabled`/`multi_agent_enabled` all `true`.
   - Directly exercised the new Multi-Agent Server: ran a real
     `review_portfolio` task (portfolio 2) through
     `POST localhost:8300/multi-agent/run` — full Planner → Worker →
     Reviewer cycle executed for real, landed correctly in
     `pending_human_review` with a genuine finding (one position at 52%
     concentration, over the 50% warning threshold).

4. **Found and fixed a real compliance bug** before any cloud money got
   spent on it — see §3.

5. **Alex posted this ask** (paraphrased from the team chat): his PR #20
   is merged; the `cloud-deployment` GitHub Actions workflow is red only
   because the `AZURE_CREDENTIALS` secret is missing. He asked Erfanur to:
   - `az group create --name group29-r2-rg --location australiaeast`
   - `az ad sp create-for-rbac --name group29-r2-github --role contributor --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/group29-r2-rg --sdk-auth`
   - Add that JSON as a GitHub secret named `AZURE_CREDENTIALS` (repo
     Settings → Secrets and variables → Actions)
   - Run the `cloud-deployment` workflow by hand (Actions tab, on `main`)
   - Send Alex the smoke-test URLs
   - **Delete the resource group afterward** so it doesn't keep costing
     money

6. **Erfanur had no Azure access.** Chose to sign up for **Azure for
   Students** (UTS email, no credit card) rather than use Alex's or a
   shared subscription — this was a deliberate choice so the
   service-principal credential never has to travel through chat: the
   same person who creates it also pastes it straight into the GitHub
   secret. **The account now exists**, but `az login` was never actually
   completed — both attempts (via `az login --use-device-code`, printing
   a URL + one-time code) were cut off when Erfanur stepped away mid-flow.
   `az account show` currently still errors "please run az login".

7. **This handoff doc** was requested so the above doesn't have to be
   re-explained on a different machine.

---

## 3. ⚠️ Compliance bug found + fixed (pushed, needs a PR + merge)

**The Release 2 brief's Cloud Baseline rule** (quoted exactly): *"AI-Mode,
MCP, RAG, and the Multi-Agent Server must be disabled by default in the
required cloud deployment."* Rubric item 7 — "Integrated Cloud
Application – CRUD" — grades on this directly (3 pts), and Bonus B1
assumes you're deliberately *enabling* a baseline that's otherwise off.

**What was actually wrong**, as merged in PR #20: `scripts/deploy/azure/
main.bicep` correctly never deployed MCP/RAG/Multi-Agent, but **AI-Mode +
Ollama were always deployed** as live Container Apps, wired into every
student backend's `AI_MODE_URL` — directly contradicting both the brief
and the file's own header comment, which claimed AI-Mode was "deliberately
NOT deployed."

**Fix** (committed, pushed to branch `fix/cloud-ai-disabled-by-default`,
**NOT yet a PR, NOT yet merged to `main`**):
- Added `param enableCloudAi bool = false` to `main.bicep`.
- Ollama, its Azure Files share/mount, and the AI-Mode Container App are
  now `if (enableCloudAi)`.
- `aiModeUrl` passed into each student module is `''` when disabled (the
  default — every backend already falls back gracefully on a
  missing/unreachable `AI_MODE_URL`), the real FQDN only when
  `enableCloudAi=true` is explicitly passed.
- Verified with `az bicep build --file scripts/deploy/azure/main.bicep`
  — compiles clean, zero errors.
- `scripts/deploy/README.md` updated to document the default vs. the
  deliberate Bonus-B1 opt-in path.

**⚠️ Critical ordering**: this fix must be **merged into `main` before**
the `cloud-deployment.yml` workflow is actually triggered for real,
because that workflow checks out `main` from GitHub, not whatever's on
anyone's laptop. Open the PR, merge it, *then* do the Azure setup in §4 —
doing it in the other order deploys the non-compliant version.

---

## 4. Exact next steps to finish Alex's ask

In order:

1. **Open and merge the PR** for `fix/cloud-ai-disabled-by-default` →
   `main`. (Branch is already pushed; just needs
   `gh pr create --base main --head fix/cloud-ai-disabled-by-default` or
   the GitHub web UI, then merge.)
2. **Finish `az login`**: run `az login --use-device-code`, open the
   printed URL, enter the code, sign in with the **Azure-for-Students
   account** (UTS email), not Erfanur's personal Gmail.
3. `az account show --query id -o tsv` → note the subscription ID.
4. `az group create --name group29-r2-rg --location australiaeast`
5. `az ad sp create-for-rbac --name group29-r2-github --role contributor --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/group29-r2-rg --sdk-auth`
   → copy the full JSON output.
6. Add it as a GitHub Actions secret named exactly `AZURE_CREDENTIALS`
   (repo Settings → Secrets and variables → Actions → New repository
   secret). `gh` CLI is installed locally if `gh secret set
   AZURE_CREDENTIALS < creds.json` is easier than the web UI — but **run
   `gh auth login` first**, it was never authenticated this session.
7. Trigger the workflow: Actions tab → `cloud-deployment` → Run workflow
   (on `main`), or `gh workflow run cloud-deployment.yml`.
8. Watch it run — `deploy.sh` does two passes (first pass's Container
   Apps show a failed/pending revision before images exist in ACR; that's
   expected, not a bug, per `scripts/deploy/README.md`).
9. Grab the smoke-test URLs from the workflow output, **send them to
   Alex**.
10. Once Alex/the team have what they need from it: **delete the resource
    group** — `az group delete --name group29-r2-rg` or
    `scripts/deploy/azure/teardown.sh` (asks you to type the RG name to
    confirm) — so it stops costing money. Don't skip this step.

If claiming **Bonus B1** (Cloud AI-Mode) separately: redeploy with
`enableCloudAi=true` passed to `az deployment group create`, capture the
demo evidence, then redeploy again with it back to `false` (or just tear
the whole group down per step 10) so the baseline requirement isn't
quietly violated again afterward.

---

## 5. Environment state / gotchas (this Mac — recreate fresh on a new PC)

- **Docker Desktop got stuck** this session — process running, but
  `docker ps`/`docker info` hang indefinitely. Needs a manual quit +
  reopen (`open -a Docker`, then poll `docker info` until it responds —
  took ~10s the first time this session). Not yet re-verified working
  after the hang; check this first on whichever machine you're on.
- **`az` CLI, `gh` CLI, Bicep CLI**: all installed via Homebrew
  (`brew install azure-cli gh`, `az bicep install`) on this Mac this
  session. Not installed yet on a fresh PC — same commands.
- **`gh` is not authenticated** anywhere yet — run `gh auth login` before
  trying `gh pr create` / `gh secret set` / `gh workflow run`.
- **The 3 local AI services** (MCP/RAG/multi-agent) were started from a
  venv at `/tmp/advsd-aiservices-venv` — temp directory, won't survive a
  reboot or a machine switch. Recreate:
  ```bash
  python3 -m venv /tmp/advsd-aiservices-venv
  /tmp/advsd-aiservices-venv/bin/pip install -r ai-services/mcp-server/requirements.txt \
    -r ai-services/rag-server/requirements.txt \
    -r ai-services/multi-agent-server/requirements.txt \
    -r ai-services/shared/requirements.txt
  # then, one per terminal (or background + disown):
  cd ai-services/mcp-server && /tmp/advsd-aiservices-venv/bin/python app.py      # :8100
  cd ai-services/rag-server && /tmp/advsd-aiservices-venv/bin/python app.py      # :8200
  cd ai-services/multi-agent-server && /tmp/advsd-aiservices-venv/bin/python app.py  # :8300
  ```
- **Ollama model** (`llama3.2:3b`) was already cached in the `ollama`
  docker volume from a prior session on this Mac — a fresh PC will need
  `docker compose up -d ollama && docker compose exec ollama ollama pull llama3.2:3b`
  once, per the original §7 instructions (now superseded by just
  `docker compose up -d --build` for everything else).
- Local git state when this was written: `main` is up to date with
  `origin/main` (`da7c989`, includes Humza's PR #22). The compliance fix
  lives on pushed-but-unmerged branch `fix/cloud-ai-disabled-by-default`.
  This doc itself is on branch `docs/handoff-notes-r2`.

---

## 6. A note on how Erfanur likes to work (carried forward, still true)

- Wants things **actually verified**, not just read/assumed — this
  session ran the real stack and hit a real multi-agent endpoint rather
  than trusting the code read alone. Match that standard.
- Prefers being asked before consequential/costly/outward-facing actions
  (creating billable cloud resources, service principals, GitHub secrets,
  merging to `main`) but moves fast once a plan is clear.
- Appreciates a teammate's claim ("everything should work") being
  independently checked against the actual spec before spending time or
  money on it — that's exactly how the AI-Mode bug in §3 got caught.

---

## 7. Release 2 brief, for reference (pasted in chat, not previously in-repo)

The brief itself is long (rubric, bonus marks, per-item descriptions in
full) — rather than duplicate several hundred lines here, the authoritative
copy is the message Erfanur pasted into the Claude Code session on
2026-10-22. If this file is being read without that conversation history
available, ask Erfanur for the brief PDF/text again, or check whether it's
since been added to `docs/reference/`. The load-bearing points already
extracted into this doc:

- Cloud Baseline: AI-Mode, MCP, RAG, Multi-Agent **disabled by default**
  in the required cloud deployment (§3 above).
- Bonus B1–B6: enabling each AI service / adding cloud security controls
  in the cloud, each worth +1 (max +4 combined for AI services via the
  rubric's tiered bonus row, +2 for security).
- Each student needs 2 tested endpoint functions in their own
  `student-x.yml` CI workflow (already true for all 4 per the PRs merged
  so far).
- One group PDF report, `group-<number>.pdf`, due 25 Oct 2026 23:59 AEST,
  max 3000 words, with a ≤10-minute showcase video URL included.
