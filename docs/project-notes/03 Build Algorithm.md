---
title: QALTAM Build Algorithm
tags:
  - qaltam
  - execution
status: active
---

# QALTAM Build Algorithm

## Principle

Строить проект от центра к краям: `data model -> financial logic -> API -> capture channels -> UI -> runtime verification`.

## Execution Order

1. `Project scaffold`
   Создать monorepo layout: `backend/`, `frontend/`, `infra/`, `.env.example`, `docker-compose.yml`, базовые README и package manifests.

2. `Backend foundation`
   Добавить settings, async SQLite session, base ORM, enums, models, migrations strategy, seed script.

3. `Financial engine`
   Реализовать:
   - safe-to-withdraw
   - cash gap date detection
   - 30-day rolling cashflow projection
   - hypothesis simulation on 30-90 day horizon
   - 11 gap scenarios generator

4. `API contracts`
   Поднять dashboard, transactions, obligations, hypotheses, quick-add, health routes.

5. `Capture layer`
   Подключить aiogram bot:
   - `/start`
   - WebApp button
   - text expense parser
   - voice capture pipeline
   - webhook endpoint

6. `Frontend TMA`
   Собрать SPA:
   - Macro view
   - Medium map nodes
   - Micro emergency panel
   - Hypothesis sandbox by role

7. `Local runtime`
   Docker Compose, startup guide, sample envs, local verification.

8. `End-to-end audit`
   Проверить, что каждая обязательная часть objective существует и связана.

## Anti-Confusion Rules

- Не писать UI-модель до фиксации backend response schemas.
- Не писать bot parser без единого transaction ingestion service.
- Не дублировать финансовую логику между bot, API и frontend.
- Каждую новую часть сначала заносить в [[04 Decisions Log]] и [[05 File Inventory]].
