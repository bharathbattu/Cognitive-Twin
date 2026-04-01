# Cognitive Twin Scaffold Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a clean, scalable full-stack starter for Cognitive Twin using FastAPI, React/Vite, Tailwind CSS, OpenRouter, and FAISS + JSON memory storage.

**Architecture:** Use a simple monorepo with `backend` and `frontend` applications plus shared root-level `data`, `docs`, and `scripts` folders. Keep FastAPI routes thin, place business logic in services, isolate memory adapters from higher-level AI/twin orchestration, and organize the frontend by features so new product areas can grow without rewrites.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic Settings, OpenAI SDK for OpenRouter compatibility, FAISS, React 18+, Vite, TypeScript, Tailwind CSS v4.

---

### Task 1: Create the project skeleton

**Files:**
- Create: `backend/`
- Create: `frontend/`
- Create: `data/faiss/`
- Create: `data/json/`
- Create: `docs/architecture/`
- Create: `docs/adr/`
- Create: `scripts/`
- Create: `.gitignore`
- Create: `README.md`

**Step 1: Create the root folders**

Run:
```powershell
New-Item -ItemType Directory -Force backend, frontend, data\faiss, data\json, docs\architecture, docs\adr, scripts
```

**Step 2: Add repository metadata**

Create a root `README.md` with quickstart instructions and a `.gitignore` for Python, Node, env files, build output, and vector data artifacts.

**Step 3: Verify the root structure**

Run:
```powershell
Get-ChildItem -Force
```

Expected: `backend`, `frontend`, `data`, `docs`, `scripts`, `.gitignore`, and `README.md` are present.

### Task 2: Scaffold the FastAPI backend

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/api/v1/router.py`
- Create: `backend/app/api/v1/routes/health.py`
- Create: `backend/app/api/v1/routes/chat.py`
- Create: `backend/app/api/v1/routes/memory.py`
- Create: `backend/app/api/v1/routes/twin.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/dependencies.py`
- Create: `backend/app/core/logging.py`
- Create: `backend/app/models/domain/`
- Create: `backend/app/models/schemas/chat.py`
- Create: `backend/app/models/schemas/memory.py`
- Create: `backend/app/models/schemas/twin.py`
- Create: `backend/app/services/ai/openrouter_service.py`
- Create: `backend/app/services/memory/memory_service.py`
- Create: `backend/app/services/twin/chat_service.py`
- Create: `backend/app/services/twin/profile_service.py`
- Create: `backend/app/memory/faiss_store.py`
- Create: `backend/app/memory/json_store.py`
- Create: `backend/app/memory/embedding_manager.py`
- Create: `backend/app/memory/retriever.py`
- Create: `backend/app/utils/file_helpers.py`
- Create: `backend/app/utils/validators.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`

**Step 1: Create package directories and `__init__.py` files**

Make all Python directories importable so future modules can be added cleanly.

**Step 2: Define configuration**

Implement `config.py` using `pydantic-settings` so environment variables control API host, OpenRouter credentials, model choice, and memory paths.

**Step 3: Define schemas**

Add Pydantic request/response models for chat, memory entries, and twin profile data.

**Step 4: Implement services**

Create adapter-style services:
- `openrouter_service.py` for model calls
- `memory_service.py` for save/search coordination
- `chat_service.py` for request orchestration
- `profile_service.py` for twin profile read/write logic

**Step 5: Implement memory adapters**

Add FAISS/JSON storage classes with minimal, non-production placeholder behavior that can be extended later.

**Step 6: Implement routes**

Expose:
- `/health`
- `/chat`
- `/memory`
- `/twin/profile`

**Step 7: Add a smoke test**

Run:
```powershell
pytest backend/tests/test_health.py -v
```

Expected: health endpoint returns `200`.

### Task 3: Scaffold the React frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/index.html`
- Create: `frontend/.env.example`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/index.css`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/twinApi.ts`
- Create: `frontend/src/app/providers/`
- Create: `frontend/src/components/common/`
- Create: `frontend/src/components/layout/AppShell.tsx`
- Create: `frontend/src/features/chat/ChatPanel.tsx`
- Create: `frontend/src/features/memory/MemoryPanel.tsx`
- Create: `frontend/src/features/twin/TwinProfileCard.tsx`
- Create: `frontend/src/hooks/`
- Create: `frontend/src/pages/HomePage.tsx`
- Create: `frontend/src/types/api.ts`
- Create: `frontend/src/utils/`

**Step 1: Create a minimal Vite + React + TS app**

Prefer the Vite React TypeScript template, then reshape it into the target feature-first structure.

**Step 2: Add Tailwind configuration**

Configure Tailwind for Vite and define the base stylesheet entrypoint in `src/index.css`.

**Step 3: Add API layer**

Create a small `fetch` wrapper and typed backend client functions so UI components do not talk to raw URLs directly.

**Step 4: Add starter UI**

Create a simple home page with sections for chat, memory, and twin profile to reflect the backend capabilities.

### Task 4: Add environment examples and developer docs

**Files:**
- Create: `backend/.env.example`
- Create: `frontend/.env.example`
- Modify: `README.md`

**Step 1: Add backend environment variables**

Include:
- `APP_NAME`
- `APP_ENV`
- `APP_HOST`
- `APP_PORT`
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `DEFAULT_MODEL`
- `MEMORY_JSON_PATH`
- `MEMORY_FAISS_PATH`

**Step 2: Add frontend environment variables**

Include:
- `VITE_API_BASE_URL`
- `VITE_APP_NAME`

**Step 3: Document startup**

Document backend and frontend install/run commands plus the expected local URLs.

### Task 5: Validate the scaffold

**Files:**
- Validate: `backend/**`
- Validate: `frontend/**`

**Step 1: Run Python validation**

Run:
```powershell
ruff check backend
mypy backend\app
pytest backend/tests -v
```

**Step 2: Run frontend validation**

Run:
```powershell
cd frontend
npm run build
npx tsc --noEmit
```

**Step 3: Fix issues and re-run**

Repeat validation until the scaffold is clean.
