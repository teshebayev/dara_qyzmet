# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Dara Kyzmet — a SaaS for digital acceptance of supplier invoices (накладные). A store uploads a
delivery invoice (photo/PDF), a VLM (Qwen2.5-VL via vLLM) recognizes line items, the store edits
and confirms them, records discrepancies (shortage/surplus/misgrade/defect) which auto-recompute
the payable sum, generates a discrepancy act, and the supplier corrects their invoice. A LangGraph
support agent (chat bubble) answers stock/analytics questions, does catalog search, and drafts
supply orders. UI text, comments, and many identifiers are in Russian.

## Running

**Requires an NVIDIA GPU**: invoice recognition and the agent both use a real Qwen2.5-VL model via
vLLM (there is no mock mode). Start vLLM first, then the stack:
```bash
bash run_vllm.sh                   # separate terminal; serves Qwen2.5-VL, waits for model load
docker compose up --build          # db + qdrant + api + web
```
- Frontend (React/nginx): http://localhost:3000
- API + Swagger: http://localhost:8080/docs  (container port 8000 → host 8080)
- Qdrant (agent product search): http://localhost:6333/dashboard
- Demo logins: `store@dara.kz` (store) / `dist@dara.kz` (supplier), password `demo12345`
- DB and demo data are created automatically on startup (`SEED_DEMO=true`).
- Services: `db` (Postgres), `qdrant`, `api`, `web`. vLLM runs separately (see below).

Frontend dev without Docker:
```bash
cd frontend && npm install && npm run dev   # :5173, proxies /api and /health → :8080
```

Backend dependencies use **uv** (`pyproject.toml` + `uv.lock`). There is no migration tool —
`Base.metadata.create_all` builds the schema on startup (see `app/main.py` lifespan). There is
**no test suite** in this repo.

### vLLM (Qwen2.5-VL)

vLLM is intentionally NOT in docker-compose — `run_vllm.sh` starts it on the GPU host, and the API
reaches it via `host.docker.internal`. The script is parameterized by env vars (MODEL, GPU_DEVICE,
MAX_MODEL_LEN, etc.); the served model name must match `VLM_MODEL`/`LLM_MODEL` (default `qwen`).
The model must support tool-calling (for the agent) and vision (for invoice recognition).

## Models everywhere — no mock mode

There is **no `MOCK_VLM` / mock fallback** — both model-backed features require vLLM running:
- **Invoice recognition** (`app/vlm/client.py:recognize`): posts images to an OpenAI-compatible
  `/chat/completions` with vLLM `guided_json`.
- **Agent** (`app/agent/`): **function-calling** — the LLM picks and calls tools in a loop
  (`function_calling.py`). If vLLM is unreachable, `/agent/ask` returns 503.

The agent's **product search uses Qdrant + CLIP** (embeddings, not the LLM); Qdrant runs in every
`docker compose up`.

## Backend architecture (`backend/app/`)

FastAPI + SQLAlchemy 2 (sync engine) + PostgreSQL 16. All routers mount under `/api/v1`.

- **`main.py`** — entry point: `create_all` + `seed()` in the lifespan, registers all routers,
  serves `static/index.html` at `/`, exposes `/health`.
- **`models.py`** — full data model. Money is `Numeric(14,2)`, quantities `Numeric(14,3)`, PKs are
  UUIDs. Core chain: `Order → Invoice → InvoiceItem`, then `Acceptance → Discrepancy` /
  `DiscrepancyAct`. Multi-tenancy is by `organization_id` / `store_org_id` / `supplier_org_id`.
- **`security.py` + `deps.py`** — bcrypt + JWT (HS256). `Principal{user_id, role, org_id}` comes
  from the token. `require_role(...)` enforces RBAC (`admin` passes any check). Tenant isolation is
  enforced per-handler by comparing `p.org_id` to the row's org — there is no global filter, so
  every new query/handler must check ownership itself.
- **`services/recalc.py`** — `recompute(acceptance, invoice)` is the single source of truth for the
  corrected sum. All money is `Decimal` with `ROUND_HALF_EVEN`. Each discrepancy type has a
  specific delta formula in `compute_delta`. Recompute is called on every discrepancy mutation and
  when creating an act; never compute sums ad hoc elsewhere.
- **`vlm/`** — `pdf.normalize` (PDF/image → list of PNG pages, max 5, downscaled), `client.recognize`
  (VLM call), `domain` (Pydantic `Invoice` + JSON schema), `validate` (RK BIN check digit +
  total reconciliation, produces warnings).
- **`agent/`** — the support agent (LangGraph). See Agent section below.
- **`catalog.py`** — Qdrant product search (CLIP text+image embeddings via fastembed, ONNX/CPU).
  Tenant-isolated by `org_id` payload filter; resilient (returns `[]` if Qdrant is down). Indexed
  best-effort on startup in `main.py` lifespan.
- **`routers/`** — `auth`, `orders`, `invoices`, `acceptance`, `supplier`, `products`, `agent`.

### Order status state machine

`orders.py` defines `TRANSITIONS` and `assert_transition`:
`new → shipped → receiving → {accepted | discrepancy} → act_created → invoice_corrected → closed`
(plus `cancelled`). Status is also advanced as a side effect inside other routers (e.g. uploading
an invoice or starting acceptance sets `receiving`; creating an act sets `act_created`; supplier
correction sets `invoice_corrected`). Keep status changes consistent with this machine.

### Acceptance / discrepancy flow

`POST /orders/{id}/acceptance` starts it; `accept` adds items to `Stock` and closes without
discrepancies; `add/delete discrepancy` recompute the sum live; `create act` snapshots
original/corrected/delta. `defect` requires a `photo_url`. Discrepancy delta depends on the
invoice item's price, so discrepancies reference `invoice_item_id`.

### Invoice check (OCR error detection)

`GET /invoices/{id}/check` (`services/invoice_check.py`) returns a read-only report flagging
arithmetic inconsistencies and suggesting fixes (it never mutates — the user applies fixes via the
existing PATCH endpoints). Key subtlety: stored `InvoiceItem.line_total` is *always* `qty*price`
(computed at upload), so per-line checks compare against the **OCR-declared** numbers in
`invoice.raw_ocr_json` (`items[].total`, `grand_total`), not the stored `line_total`. The
Acceptance UI shows the report banner, highlights bad rows, and renders suggestion buttons.

### Agent (`app/agent/`, LangGraph)

`routers/agent.py:ask` builds and invokes a compiled graph **per request** (it must NOT be cached
in a module global — the node closures capture that request's `db` session, which is closed by the
next request).

`supervisor_node` routes one of three ways: `confirm_draft` → `order`; image → `product`;
otherwise → `agent` (function-calling). Then one node → `END`.

- **`function_calling.py`** — `run()` runs the OpenAI tool-calling loop: the LLM is given
  `TOOL_SPECS` and picks/calls tools itself; `TOOL_FUNCS` execute them (adapters over `tools.py`),
  results go back to the model until it returns text. Tools cover stock, low_stock+supplier,
  discrepancy_report, supplier_quality, delivery_status, spend, top_products, find_product, photo
  search. **The LLM cannot write**: it gets `propose_order_draft` (read-only), not
  `create_order_draft`; a proposed draft is surfaced as `data.draft` for the confirm step.
- **`graph.py`** — the `agent` node (FC), `product` (Qdrant photo/text search, deterministic), and
  `order` (creates the order from a confirmed draft). Thin — most logic is in tools/FC.
- **`tools.py`** — read-only DB tools, all filtered by `org_id`; shared helpers `resolve_supplier`
  and `build_order_draft`; `create_order_draft` (the one write); Qdrant catalog wrappers.
- **`state.py`** — `AgentState` (pydantic): `message`, `org_id`, `user_id`, `image_b64`,
  `confirm_draft`, `route`, plus result fields (`answer`, `used_tools`, `data`).

**Order is propose→confirm (the key write-safety invariant).** A request with no `confirm_draft`
only *proposes* a draft via the read-only `propose_order_draft` tool (`data.draft`, nothing
written). The frontend (`AgentWidget.jsx`) shows a button that re-sends the reviewed draft as
`confirm_draft`; only then does the deterministic `order` node call `create_order_draft` to write
an `Order` (status `new`). The LLM never fabricates a write payload.

## Frontend (`frontend/src/`)

Plain React 18 + Vite, no router library and no state library. `App.jsx` switches views by the
logged-in role. `api.js` holds the bearer token in a module variable and exposes `api()`, the `fmt`
money formatter, and the `STATUS` label/color map (must stay in sync with backend statuses).
Views: `Login`, `Orders`, `Acceptance`, `Supplier`, plus the `AgentWidget` chat bubble. In Docker,
nginx (`nginx.conf`) serves the SPA and proxies `/api`, `/docs`, `/openapi.json`, `/health` to the
api service.

## Gotchas

- **Build the agent graph per request, never cache it globally** — node closures capture the
  request `db` session (see Agent section).
- **First `docker compose up` is slow**: the agent indexes the catalog into Qdrant on startup, which
  downloads the fastembed CLIP model (~350 MB). Needs internet once; wrapped best-effort so a
  failure logs and doesn't block startup.
- `Product.embedding` (JSONB, seeded from a SHA-256 hash) is **legacy/unused** now that catalog
  search goes through Qdrant (`catalog.py`). Don't rely on it.
- `spend` sums `Invoice.total_sum` of confirmed invoices (gross recognized total), not the
  act-corrected sum.
- CORS is wide open (`allow_origins=["*"]`) and `JWT_SECRET` defaults to a dev value — both are
  demo-grade, not production.
