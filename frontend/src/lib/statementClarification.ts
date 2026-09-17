export type StatementClarificationRule = {
  account_type: string;
  life_sector: string;
  explanation: string;
};

export type StatementClarificationChoice = {
  account_type: string;
  life_sector: string;
};

export type StatementClarificationItem = {
  suggested_account_type: string | null;
  suggested_life_sector: string | null;
  matched_rules: StatementClarificationRule[];
};

export function findMatchingStatementRuleForChoice(
  item: StatementClarificationItem | null,
  choice: StatementClarificationChoice,
) {
  return (
    item?.matched_rules.find(
      (rule) => rule.account_type === choice.account_type && rule.life_sector === choice.life_sector,
    ) ?? null
  );
}

export function prioritizeStatementQuickChoices<T extends StatementClarificationChoice>(
  choices: readonly T[],
  item: StatementClarificationItem | null,
): T[] {
  if (!item) {
    return [...choices];
  }

  const learnedKeys = new Set(item.matched_rules.map((rule) => `${rule.account_type}:${rule.life_sector}`));
  const suggestedKey =
    item.suggested_account_type && item.suggested_life_sector
      ? `${item.suggested_account_type}:${item.suggested_life_sector}`
      : null;

  return [...choices].sort((left, right) => {
    const leftKey = `${left.account_type}:${left.life_sector}`;
    const rightKey = `${right.account_type}:${right.life_sector}`;
    const leftScore =
      Number(learnedKeys.has(leftKey)) * 4 +
      Number(suggestedKey === leftKey) * 3 +
      Number(item.suggested_account_type === left.account_type) +
      Number(item.suggested_life_sector === left.life_sector);
    const rightScore =
      Number(learnedKeys.has(rightKey)) * 4 +
      Number(suggestedKey === rightKey) * 3 +
      Number(item.suggested_account_type === right.account_type) +
      Number(item.suggested_life_sector === right.life_sector);
    return rightScore - leftScore;
  });
}
