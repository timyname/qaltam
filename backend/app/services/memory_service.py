from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.profile import MemoryNote, UserProfile
from backend.app.services.deepseek_client import DeepSeekClient


class MemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.client = DeepSeekClient()

    async def add_note(self, *, kind: str, title: str, content: str, importance: int = 1) -> MemoryNote:
        note = MemoryNote(kind=kind, title=title, content=content, importance=importance)
        self.session.add(note)
        await self.session.flush()
        return note

    async def summarize_profile(self, profile: UserProfile) -> str | None:
        if not self.client.api_key:
            return None
        prompt = (
            "Return a concise JSON object with keys summary, risk_level, goals, constraints, "
            "and account_aliases based on this user profile."
        )
        user_prompt = f"""
display_name: {profile.display_name}
client_mode: {profile.client_mode}
risk_level: {profile.risk_level}
communication_style: {profile.communication_style}
owner_priority: {profile.owner_priority}
privacy_policy_note: {profile.privacy_policy_note}
"""
        result = await self.client.extract_json(prompt, user_prompt)
        return result.raw_text if result else None

    async def attach_summary_to_profile(self, profile: UserProfile) -> UserProfile:
        summary = await self.summarize_profile(profile)
        if summary:
            profile.memory_summary = summary
        return profile

    async def last_notes(self, limit: int = 20) -> list[MemoryNote]:
        result = await self.session.execute(select(MemoryNote).order_by(MemoryNote.created_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def save_pending_statement(self, telegram_user_id: int, payload: dict) -> MemoryNote:
        note = await self._find_pending_statement_note(telegram_user_id)
        content = json.dumps(payload, ensure_ascii=False)
        title = f"user:{telegram_user_id}|statement_pending"
        if note:
            note.content = content
            note.title = title
            note.importance = 3
            await self.session.flush()
            return note
        return await self.add_note(
            kind="statement_pending",
            title=title,
            content=content,
            importance=3,
        )

    async def get_pending_statement(self, telegram_user_id: int) -> dict | None:
        note = await self._find_pending_statement_note(telegram_user_id)
        if not note:
            return None
        try:
            return json.loads(note.content)
        except json.JSONDecodeError:
            return None

    async def clear_pending_statement(self, telegram_user_id: int) -> None:
        note = await self._find_pending_statement_note(telegram_user_id)
        if note:
            await self.session.delete(note)
            await self.session.flush()

    async def save_clarification_rule(
        self,
        telegram_user_id: int,
        *,
        match_key: str,
        account_type: str,
        life_sector: str,
        explanation: str,
    ) -> MemoryNote:
        payload = {
            "match_key": match_key,
            "account_type": account_type,
            "life_sector": life_sector,
            "explanation": explanation,
        }
        return await self.add_note(
            kind="clarification_rule",
            title=f"user:{telegram_user_id}|rule:{match_key}",
            content=json.dumps(payload, ensure_ascii=False),
            importance=4,
        )

    async def get_clarification_rules(self, telegram_user_id: int, limit: int = 200) -> list[dict]:
        result = await self.session.execute(
            select(MemoryNote)
            .where(MemoryNote.kind == "clarification_rule")
            .order_by(MemoryNote.created_at.desc())
            .limit(limit)
        )
        rules: list[dict] = []
        prefix = f"user:{telegram_user_id}|rule:"
        for note in result.scalars().all():
            if not note.title.startswith(prefix):
                continue
            try:
                payload = json.loads(note.content)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rules.append(payload)
        return rules

    async def _find_pending_statement_note(self, telegram_user_id: int) -> MemoryNote | None:
        result = await self.session.execute(
            select(MemoryNote)
            .where(
                MemoryNote.kind == "statement_pending",
                MemoryNote.title == f"user:{telegram_user_id}|statement_pending",
            )
            .order_by(MemoryNote.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()
