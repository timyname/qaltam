from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class StatementImportTextPayload(BaseModel):
    telegram_user_id: int
    telegram_chat_id: int
    raw_text: str
    language: str | None = None


class StatementClarificationPayload(BaseModel):
    telegram_user_id: int
    telegram_chat_id: int
    answer_text: str | None = None
    account_type: str | None = None
    life_sector: str | None = None
    language: str | None = None


class StatementImportResultRead(BaseModel):
    imported_statement_id: int
    parsed_count: int
    auto_count: int
    unclear_count: int
    summary_message: str
    prompt_message: str | None = None
    pending: "PendingStatementRead | None" = None
    latest_status: "StatementStatusSnapshotRead | None" = None
    history: list["StatementHistoryEntryRead"] = []


class MatchedClarificationRuleRead(BaseModel):
    match_key: str
    account_type: str
    life_sector: str
    explanation: str


class PendingStatementItemRead(BaseModel):
    index: int
    statement_date: str
    amount: Decimal
    transaction_type: str
    counterparty: str
    description: str
    reason: str
    suggested_account_type: str | None = None
    suggested_life_sector: str | None = None
    matched_rules: list[MatchedClarificationRuleRead] = []


class PendingStatementRead(BaseModel):
    statement_id: int
    parsed_count: int
    auto_count: int
    current_index: int
    total_count: int
    resolved_count: int
    remaining_count: int
    prompt_message: str
    current_item: PendingStatementItemRead | None = None
    items: list[PendingStatementItemRead]


class StatementStatusSnapshotRead(BaseModel):
    imported_statement_id: int
    source_name: str
    original_filename: str | None = None
    parse_status: str
    imported_at: str
    parsed_count: int | None = None
    auto_count: int | None = None
    unclear_count: int | None = None
    remaining_clarifications: int


class StatementHistoryEntryRead(BaseModel):
    imported_statement_id: int
    source_name: str
    original_filename: str | None = None
    parse_status: str
    imported_at: str
    parsed_count: int | None = None
    auto_count: int | None = None
    unclear_count: int | None = None
    remaining_clarifications: int


class StatementHistoryResponse(BaseModel):
    items: list[StatementHistoryEntryRead]


class StatementDetailRead(BaseModel):
    imported_statement_id: int
    source_name: str
    original_filename: str | None = None
    parse_status: str
    imported_at: str
    parsed_count: int | None = None
    auto_count: int | None = None
    unclear_count: int | None = None
    remaining_clarifications: int
    note: str | None = None
    storage_kind: str
    file_available: bool
    is_active: bool
    raw_line_count: int
    raw_preview: str
    raw_preview_truncated: bool
    pending: "PendingStatementRead | None" = None


class StatementWorkbenchStatusRead(BaseModel):
    latest_status: StatementStatusSnapshotRead | None = None
    pending: PendingStatementRead | None = None


class StatementWorkbenchRead(BaseModel):
    latest_status: StatementStatusSnapshotRead | None = None
    pending: PendingStatementRead | None = None
    history: list[StatementHistoryEntryRead] = []


class StatementClarificationResponse(BaseModel):
    message: str
    pending: PendingStatementRead | None = None
    latest_status: StatementStatusSnapshotRead | None = None
    history: list[StatementHistoryEntryRead] = []
