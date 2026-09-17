import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const helperPath = path.resolve(scriptDir, "../src/lib/statementSelection.ts");
const helperSource = await readFile(helperPath, "utf8");
const transpiled = ts.transpileModule(helperSource, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
});
const helperModuleUrl = `data:text/javascript;base64,${Buffer.from(transpiled.outputText, "utf8").toString("base64")}`;
const { resolveStatementHistorySelection } = await import(helperModuleUrl);

assert.deepStrictEqual(
  resolveStatementHistorySelection({
    statementHistory: [
      { imported_statement_id: 41 },
      { imported_statement_id: 40 },
    ],
    selectedStatementId: 17,
    initialStatementId: 17,
  }),
  {
    nextSelectedStatementId: 41,
    consumeInitialStatementId: true,
  },
);

assert.deepStrictEqual(
  resolveStatementHistorySelection({
    statementHistory: [
      { imported_statement_id: 41 },
      { imported_statement_id: 40 },
    ],
    selectedStatementId: 40,
    initialStatementId: 17,
  }),
  {
    nextSelectedStatementId: 40,
    consumeInitialStatementId: true,
  },
);

assert.deepStrictEqual(
  resolveStatementHistorySelection({
    statementHistory: [
      { imported_statement_id: 41 },
      { imported_statement_id: 40 },
    ],
    selectedStatementId: 17,
    initialStatementId: 40,
  }),
  {
    nextSelectedStatementId: 40,
    consumeInitialStatementId: true,
  },
);

assert.deepStrictEqual(
  resolveStatementHistorySelection({
    statementHistory: [
      { imported_statement_id: 41 },
      { imported_statement_id: 40 },
    ],
    selectedStatementId: 17,
    initialStatementId: 18,
  }),
  {
    nextSelectedStatementId: 41,
    consumeInitialStatementId: true,
  },
);

assert.deepStrictEqual(
  resolveStatementHistorySelection({
    statementHistory: [
      { imported_statement_id: 41 },
      { imported_statement_id: 40 },
    ],
    selectedStatementId: null,
    initialStatementId: null,
  }),
  {
    nextSelectedStatementId: 41,
    consumeInitialStatementId: false,
  },
);

console.log("statement-selection regression checks passed");
