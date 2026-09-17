export type StatementHistorySelectionEntry = {
  imported_statement_id: number;
};

type ResolveStatementHistorySelectionArgs = {
  statementHistory: StatementHistorySelectionEntry[];
  selectedStatementId: number | null;
  initialStatementId: number | null;
};

export type StatementHistorySelectionDecision = {
  nextSelectedStatementId: number | null;
  consumeInitialStatementId: boolean;
};

export function resolveStatementHistorySelection({
  statementHistory,
  selectedStatementId,
  initialStatementId,
}: ResolveStatementHistorySelectionArgs): StatementHistorySelectionDecision {
  const availableStatementIds = new Set(statementHistory.map((item) => item.imported_statement_id));

  if (selectedStatementId !== null && availableStatementIds.has(selectedStatementId)) {
    return {
      nextSelectedStatementId: selectedStatementId,
      consumeInitialStatementId: initialStatementId !== null,
    };
  }

  if (initialStatementId !== null && availableStatementIds.has(initialStatementId)) {
    return {
      nextSelectedStatementId: initialStatementId,
      consumeInitialStatementId: true,
    };
  }

  return {
    nextSelectedStatementId: statementHistory[0]?.imported_statement_id ?? null,
    consumeInitialStatementId: initialStatementId !== null,
  };
}
