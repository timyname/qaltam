# QALTAM / FOCUS

QALTAM / FOCUS is a local-first financial navigator for entrepreneurs in Kazakhstan. It combines a FastAPI backend, a Telegram bot, and a React Telegram Mini App for balance control, statements, receipts, cashflow, safe withdrawal, and financial hypotheses.

## Stack

- Python 3.11, FastAPI, SQLAlchemy asyncio, SQLite, Pydantic v2;
- aiogram Telegram bot;
- React 19, TypeScript, Vite, Telegram Apps SDK, Axios, Framer Motion;
- pandas, openpyxl, pdfplumber for statement ingestion;
- Docker Compose for the local stack;
- pytest, pytest-asyncio, and Playwright-based frontend checks.

## Main capabilities

- PDF, CSV, XLSX, and XLS statement ingestion;
- transaction clarification and classification;
- receipt OCR and SKU inflation analysis;
- cashflow analytics and forecasting;
- Safe-to-Withdraw calculation;
- hypothesis scoring and financial sandbox workflows;
- Telegram and Quick Add capture flows;
- Russian, Kazakh, English, and Ukrainian interface copy.

## Repository layout

- `backend/` — API, models, schemas, bot handlers, ingestion, financial engines, and services;
- `frontend/` — React Telegram Mini App;
- `infra/` — Docker and static frontend deployment assets;
- `tests/` and `backend/tests/` — backend and integration coverage;
- `docs/` — product decisions, architecture notes, and verification records.

## Reconstructed archive history

This repository was assembled from the QALTAM workspaces created during July and August 2026. The commits are organized by implementation phase so the project history is readable, while preserving the working source snapshot.

## Local data policy

Runtime databases, imported statements, receipt files, `.env` files, virtual environments, package caches, build output, and test artifacts are intentionally excluded. Use `.env.example` for local configuration.

## Verification snapshot

The August 15, 2026 workspace recorded 149 passing backend tests and a successful Vite production build.
