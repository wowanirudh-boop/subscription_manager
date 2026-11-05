import { strict as assert } from "node:assert";
import { test } from "node:test";

import { daysUntil, isValidIsoDate, ladderText, money, shortDate, sortRecords, stateTag, STATE_LABEL } from "../src/lib/format";

const f = (value: unknown, state: "confirmed" | "estimated" | "unknown" = "confirmed") => ({ value, state, evidence: null, derived_from: null });

test("money keeps the stated currency (no conversion, D30)", () => {
  assert.equal(money({ amount: f(283.2) as never, currency: f("EUR") as never }), "€283.20");
  assert.equal(money({ amount: f(450) as never, currency: f(null, "unknown") as never }), "450.00");
  assert.equal(money({ amount: f(null, "unknown") as never, currency: f(null, "unknown") as never }), "Amount unknown");
});

test("estimated and unknown values are tagged; confirmed are plain (6.2)", () => {
  assert.equal(stateTag(f(1)), null);
  assert.equal(stateTag(f(1, "estimated")), "Estimated");
  assert.equal(stateTag(f(null, "unknown")), "Unknown");
});

test("likely-cancelled label matches the PRD wording", () => {
  assert.equal(STATE_LABEL.likely_cancelled, "Likely cancelled — no charge seen");
});

test("dates", () => {
  assert.equal(shortDate("2026-12-04"), "4 Dec 2026");
  assert.equal(daysUntil("2026-11-16", new Date(2026, 10, 5)), 11);
  assert.ok(isValidIsoDate("2027-02-28") && !isValidIsoDate("2027-02-30") && !isValidIsoDate("16/11/2026"));
});

test("ladder text follows R7", () => {
  assert.match(ladderText("monthly", "subscription"), /1 day before/);
  assert.match(ladderText("monthly", "trial"), /7, 3, 1 and 0/);
  assert.match(ladderText(null, null), /7, 3, 1 and 0/);
});

test("list sorted by next date with unknowns last (R5)", () => {
  const r = (k: string, d: string | null) => ({ record_key: k, next_charge_date: f(d, d ? "confirmed" : "unknown") }) as never;
  assert.deepEqual(sortRecords([r("u", null), r("b", "2026-12-01"), r("a", "2026-11-16")]).map((x: { record_key: string }) => x.record_key), ["a", "b", "u"]);
});
