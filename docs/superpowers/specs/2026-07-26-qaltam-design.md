# QALTAM Design Spec

**Date:** 2026-07-26  
**Status:** Approved for implementation  
**Mode:** Local-only ecosystem

## Goal

Build a complete local financial navigator ecosystem named `QALTAM` for Kazakhstani entrepreneurs. The system includes a FastAPI backend with SQLite and a financial engine, a Telegram bot for transaction capture, a Telegram Mini App for financial navigation, and REST endpoints for iOS Shortcuts.

## Product Shape

QALTAM is a local-first financial operating layer that helps an owner answer four questions:

1. How much money is really available right now?
2. When will a cash gap happen if nothing changes?
3. How much can the owner safely withdraw without harming business continuity?
4. Which actions can close the upcoming gap fastest?

## Local-Only Data Policy

- Sensitive user data stays on the local machine.
- SQLite is the system of record.
- Imported files such as statements and payment extracts are stored only under the project workspace.
- Secrets such as Telegram bot token and API keys live only in local `.env` files.
- No third-party data export is enabled by default.
- Future integrations must be explicit opt-ins.

## Subsystems

### 1. Backend Core

- FastAPI on Python 3.11
- SQLAlchemy asyncio with SQLite
- Pydantic v2 for request and response contracts
- Service layer for financial logic and onboarding memory

### 2. Capture Layer

- aiogram 3.x Telegram bot
- Text transaction parser
- Voice transaction ingestion pipeline with a local adapter boundary
- Webhook-ready integration with local development fallback
- iOS Shortcuts ingestion through `POST /api/v1/quick-add`

### 3. Mini App

- React + Vite + Tailwind CSS
- Framer Motion for guided interaction
- Telegram WebApps SDK
- Three focus levels: Macro, Medium, Micro

### 4. Local Runtime

- Docker Compose for local startup
- Port `8000` for backend
- Local storage folders for database and uploaded statements

## Data Model

### Required Tables

- `accounts`
  - id
  - name
  - type (`personal`, `business`)
  - balance

- `transactions`
  - id
  - account_id
  - amount
  - category
  - type (`income`, `expense`)
  - role_tag (`CFO`, `CMO`, `COO`, `CEO`)
  - note
  - created_at

- `obligations`
  - id
  - title
  - amount
  - due_date
  - priority (`1_critical`, `2_regular`)
  - target_type (`personal`, `business`)

- `hypotheses`
  - id
  - title
  - role_perspective
  - required_investment
  - time_lag_days
  - expected_roi
  - risk_level
  - status (`draft`, `active`, `completed`)

### Extended Tables Added For Real Use

- `goals`
  Stores owner financial goals and horizon.

- `user_profiles`
  Stores client type, risk profile, operating mode, and communication preferences.

- `account_details`
  Stores optional bank name, IBAN or account number, currency, owner label, and extra notes.

- `memory_notes`
  Stores persistent agent memory about the user, business, and constraints.

- `imported_statements`
  Stores metadata about locally imported statements or payment files.

## Onboarding

The first-run flow must gather enough data to make the engine useful.

### Required Questions

1. Is this personal, business, or mixed mode?
2. What accounts exist right now?
3. What are the current balances?
4. What obligations recur monthly or on fixed dates?
5. What recent statements or payment extracts can be imported?
6. What are the owner goals?
7. What is the acceptable risk level?

### UX Rules

- User should not be forced to type account numbers in every message.
- Accounts use short aliases for everyday interaction.
- Detailed requisites are optional and stored separately.
- When ambiguity exists, the system should ask a short follow-up question.
- After a batch of inputs, the system should ask whether there is more data or whether it should move to the next onboarding step.

## Financial Engine

### `get_safe_to_withdraw()`

Calculate the maximum amount that can be taken by the owner for personal use without causing a projected business cash gap over the next 30 days.

The result must account for:

- current balances by account type
- future obligations
- planned income and expenses from recent transaction trend
- a configurable reserve buffer

### `simulate_hypothesis(hypothesis_id)`

Project a 30-90 day cash curve for a hypothesis that consumes capital now and returns value only after a lag.

The result must include:

- baseline projection
- hypothesis projection
- delta by date
- payback date if reached
- qualitative risk marker

### `get_gap_scenarios()`

Generate 11 tactical gap-closing options ranked by urgency and reversibility, such as:

1. Freeze non-critical expenses
2. Delay owner withdrawal
3. Renegotiate payment due date
4. Accelerate receivables
5. Shift spend from business to personal pocket
6. Convert planned investment to phased spend
7. Pause low-conversion marketing
8. Split supplier payment
9. Use reserve pocket
10. Re-sequence payroll or contractor dates
11. Activate short-term bridge financing

## API Surface

### Immediate Endpoints

- `GET /health`
- `POST /api/v1/onboarding/profile`
- `POST /api/v1/accounts`
- `POST /api/v1/transactions`
- `POST /api/v1/quick-add`
- `GET /api/v1/dashboard/macro`
- `GET /api/v1/dashboard/medium`
- `GET /api/v1/dashboard/micro`
- `GET /api/v1/hypotheses/{id}/simulate`

### `POST /api/v1/quick-add`

- Header: `X-API-KEY`
- Body:

```json
{
  "amount": 1500,
  "category": "Такси",
  "account_type": "personal",
  "note": "Яндекс"
}
```

## Telegram Bot

- `/start` sends greeting and inline WebApp button labeled `Open Qaltam Map`
- Text parser understands shorthand messages like:
  - `17000 kassa`
  - `5000 eda`
  - `250000 client`
- If account is ambiguous, bot asks a short clarifying question.
- Voice messages go through a transcription adapter and then the same parser pipeline.

## Mini App

### Macro

- Pocket state summary
- Safe-to-withdraw widget
- Current net liquidity and top warnings

### Medium

- Obligation and cash flow node map
- Corridor style visualization of upcoming pressure windows

### Micro

- Emergency gap panel
- 11 action roadmap
- Hypothesis sandbox by role view: CFO, CMO, COO, Owner

## Brand Direction

- Name: `QALTAM`
- Description: Local financial navigator for entrepreneurs
- First-pass identity: minimal compass mark with finance line motif
- Default theme: dark slate `#0f172a`

## Verification Scope

Implementation is not complete until there is evidence for:

- monorepo scaffold
- local runtime files
- database models
- financial engine logic
- onboarding memory layer
- bot entrypoint and handlers
- quick-add endpoint
- Mini App shell and zoom UI
- working setup documentation
