---
title: QALTAM Decisions Log
tags:
  - qaltam
  - decisions
status: active
---

# Decisions Log

## 2026-07-26

- Решено не писать в найденный личный Obsidian vault без явного разрешения пользователя.
- Для проектной памяти создан отдельный Obsidian-совместимый каталог внутри workspace.
- Базовый алгоритм сборки: backend-first, затем capture channels, затем Mini App, затем end-to-end verification.
- Утвержден local-only режим: SQLite, локальные импорты, локальные секреты.
- В схему добавлены `Goals`, `UserProfile`, `AccountDetails`, `ImportedStatements`, `MemoryNotes`, чтобы агент мог помнить контекст пользователя и реквизиты счетов.
- Фазы 1 и 2 реализованы: monorepo scaffold, backend foundation, ORM schema, onboarding memory entities и financial engine.
- Telegram bot token хранится в локальном `.env`; позже его нужно перевыпустить, потому что он уже был передан в чате.

## Next Entries

- Фиксировать здесь архитектурные развилки.
- Отмечать, почему выбран тот или иной contract или calculation rule.
