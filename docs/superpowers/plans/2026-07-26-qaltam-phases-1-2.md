# QALTAM Phases 1-2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the local QALTAM scaffold plus the backend foundation and financial engine needed for phases 1 and 2.

**Architecture:** Use a monorepo with `backend`, `frontend`, `infra`, `storage`, and `docs`. Keep a strict backend-first flow: define settings, storage, database schema, and engine contracts first, then expose them through API and later plug bot and Mini App into the same ingestion and projection services.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy asyncio, SQLite, Pydantic v2, pytest, React, Vite, Tailwind CSS, Docker Compose

---

### Task 1: Scaffold The Monorepo

**Files:**
- Create: `backend/app/`
- Create: `backend/tests/`
- Create: `frontend/src/`
- Create: `infra/`
- Create: `storage/`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `requirements.txt`
- Create: `frontend/package.json`

- [ ] Create the project directories and placeholder files.
- [ ] Add a local-only environment template.
- [ ] Add backend and frontend dependency manifests.
- [ ] Add Docker Compose for local backend runtime.

### Task 2: Build Backend Foundation

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/security.py`
- Create: `backend/app/db/database.py`
- Create: `backend/app/db/base.py`
- Create: `backend/app/models/*.py`
- Create: `backend/app/schemas/*.py`

- [ ] Create application settings and secret loading from `.env`.
- [ ] Create async SQLAlchemy engine and session factory.
- [ ] Create ORM enums and tables, including user memory entities.
- [ ] Create Pydantic schemas for onboarding, accounts, transactions, obligations, and hypotheses.

### Task 3: Build Tests For Financial Engine

**Files:**
- Create: `backend/tests/services/test_financial_engine.py`

- [ ] Write tests for safe-to-withdraw using obligations and reserve buffer.
- [ ] Write tests for first cash gap date detection.
- [ ] Write tests for 30-day projection shape.
- [ ] Write tests for hypothesis simulation.
- [ ] Write tests for 11 tactical scenarios output.

### Task 4: Implement Financial Engine

**Files:**
- Create: `backend/app/services/financial_engine.py`

- [ ] Run the financial engine tests and verify they fail.
- [ ] Implement the minimal engine to make the tests pass.
- [ ] Refine for readability after green.

### Task 5: Add Setup Documentation

**Files:**
- Create: `README.md`

- [ ] Document local startup, env setup, storage behavior, and phase status.
- [ ] Document that the Telegram token should live only in local `.env` and should be rotated because it was shared in chat.

### Task 6: Verify Phases 1-2

**Files:**
- Verify: scaffold files
- Verify: backend importability
- Verify: tests

- [ ] Run backend tests.
- [ ] Verify the required files exist.
- [ ] Report remaining gaps before phases 3 and 4.
