---
title: QALTAM Goal and Scope
tags:
  - qaltam
  - scope
status: active
---

# Goal

Собрать локальную full-stack экосистему `QALTAM` для финансовой навигации казахстанского предпринимателя.

## Required Subsystems

1. FastAPI backend на Python 3.11 с SQLite, SQLAlchemy asyncio и Pydantic v2.
2. Финансовый движок для safe-to-withdraw, cash gap и short-term cashflow projection.
3. Telegram Bot на aiogram 3.x с text/voice capture.
4. Telegram Mini App на React + Tailwind + Framer Motion.
5. REST endpoint `POST /api/v1/quick-add` для Apple iOS Shortcuts.
6. Docker Compose и setup guide для локального запуска.

## Hard Requirements

- Порт локального запуска: `8000`.
- База данных: SQLite.
- Обязательные сущности: `Accounts`, `Transactions`, `Obligations`, `Hypotheses`.
- Обязательные расчеты: `get_safe_to_withdraw()`, `simulate_hypothesis()`, `get_gap_scenarios()`.
- Обязательные интерфейсы: Telegram bot, Telegram Mini App, REST API.

## Delivery Strategy

- Сначала делаем стабильное backend ядро и API-контракты.
- Потом подключаем ingestion channels: bot + iOS quick-add.
- Потом строим TMA поверх реальных response models.
- В конце собираем локальный runtime и прогоняем end-to-end.
