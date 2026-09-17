---
title: QALTAM Open Questions
tags:
  - qaltam
  - questions
status: active
---

# Open Questions

- Будем ли мы держать bot как webhook-only или добавим fallback polling mode для локальной отладки?
- Нужно ли сразу закладывать Alembic или для локального ecosystem достаточно bootstrap create-all + seed script на первом этапе?
- Каким сервисом будем транскрибировать voice: локальный stub/adaptor или OpenAI-compatible API?
- Нужны ли отдельные dashboard endpoints под каждый zoom level или один aggregated endpoint?
- Нужно ли хранить `Goals` как отдельную таблицу, раз они упоминаются в objective, хотя детальная схема дана только для 4 сущностей?
