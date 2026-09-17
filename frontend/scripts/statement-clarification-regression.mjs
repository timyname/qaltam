import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const helperPath = path.resolve(scriptDir, "../src/lib/statementClarification.ts");
const helperSource = await readFile(helperPath, "utf8");
const transpiled = ts.transpileModule(helperSource, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
});
const helperModuleUrl = `data:text/javascript;base64,${Buffer.from(transpiled.outputText, "utf8").toString("base64")}`;
const { findMatchingStatementRuleForChoice, prioritizeStatementQuickChoices } = await import(helperModuleUrl);

const choices = [
  { account_type: "personal", life_sector: "family_living", label: "Family living" },
  { account_type: "business", life_sector: "sales_income", label: "Sales income" },
  { account_type: "business", life_sector: "inventory_parts", label: "Inventory" },
];

const item = {
  suggested_account_type: "business",
  suggested_life_sector: "inventory_parts",
  matched_rules: [
    {
      account_type: "business",
      life_sector: "sales_income",
      explanation: "Client payments from this counterparty usually land here.",
    },
  ],
};

assert.deepStrictEqual(
  prioritizeStatementQuickChoices(choices, item).map((choice) => `${choice.account_type}:${choice.life_sector}`),
  ["business:sales_income", "business:inventory_parts", "personal:family_living"],
);

assert.deepStrictEqual(prioritizeStatementQuickChoices(choices, null), choices);

assert.deepStrictEqual(findMatchingStatementRuleForChoice(item, choices[1]), item.matched_rules[0]);
assert.equal(findMatchingStatementRuleForChoice(item, choices[2]), null);

console.log("statement-clarification regression checks passed");
