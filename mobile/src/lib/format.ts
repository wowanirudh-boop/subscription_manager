// Pure presentation helpers (unit-tested in tests/format.test.ts).
import type { FieldValue, Period, RecordView, State } from "./types";

export const STATE_LABEL: Record<State, string> = {
  active: "Active",
  cancellation_pending: "Cancellation pending",
  cancelled_confirmed: "Cancelled (confirmed by merchant)",
  likely_cancelled: "Likely cancelled — no charge seen", // PRD 6.3 wording
  cancelled_user_confirmed: "Cancelled (confirmed by you)",
  unknown_date: "Renewal date unknown",
};

export function stateTag(f: FieldValue<unknown>): string | null {
  return f.state === "estimated" ? "Estimated" : f.state === "unknown" ? "Unknown" : null;
}

export function money(r: Pick<RecordView, "amount" | "currency">): string {
  if (r.amount.value == null) return "Amount unknown";
  const n = r.amount.value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sym: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£" };
  const c = r.currency.value;
  return c ? `${sym[c] ?? c + " "}${n}` : n; // stated currency, never converted (D30)
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function shortDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export function daysUntil(iso: string, today: Date): number {
  const [y, m, d] = iso.split("-").map(Number);
  const t = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((Date.UTC(y, m - 1, d) - t) / 86_400_000);
}

export function ladderText(period: Period | null, kind: string | null): string {
  if (kind === "trial") return "Alerts 7, 3, 1 and 0 days before";
  return period === "monthly" ? "Alerts 1 day before and on the day" : "Alerts 7, 3, 1 and 0 days before";
}

export function isValidIsoDate(s: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const [y, m, d] = s.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

// R5: next charge date ascending, unknowns last (server already sorts; kept for optimistic updates).
export function sortRecords(rs: RecordView[]): RecordView[] {
  return [...rs].sort((a, b) => {
    const x = a.next_charge_date.value, y = b.next_charge_date.value;
    if (!x && !y) return 0;
    if (!x) return 1;
    if (!y) return -1;
    return x < y ? -1 : x > y ? 1 : 0;
  });
}

export function isClosed(s: State): boolean {
  return s === "cancelled_confirmed" || s === "cancelled_user_confirmed";
}
