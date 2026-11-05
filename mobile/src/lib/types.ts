// Mirrors backend RecordView (srt_backend.domain.lifecycle). Field states per PRD 6.2 (D5-D7).
export type FieldState = "confirmed" | "estimated" | "unknown";
export interface Evidence { message_id: string; account: string; snippet: string }
export interface FieldValue<T> { value: T | null; state: FieldState; evidence: Evidence | null; derived_from: string | null }

export type State =
  | "active" | "cancellation_pending" | "cancelled_confirmed"
  | "likely_cancelled" | "cancelled_user_confirmed" | "unknown_date";

export type Notice = "resubscribe_question" | "charged_while_pending" | "no_receipt_seen" | "no_merchant_confirmation";
export type Period = "monthly" | "annual" | "other" | "unknown";

export interface RecordView {
  record_key: string;
  merchant: FieldValue<string>;
  kind: FieldValue<"trial" | "subscription" | "renewal">;
  billing_period: FieldValue<Period>;
  period_months: number | null;
  amount: FieldValue<number>;
  currency: FieldValue<string>;
  last_charge_date: FieldValue<string>;
  next_charge_date: FieldValue<string>;
  trial_end_date: FieldValue<string>;
  cancel_path: FieldValue<string>;
  state: State;
  alerts_enabled: boolean;
  notices: Notice[];
  missed_date: string | null;
  source_accounts: string[];
  reference: string | null;
  sources: ("merchant" | "bank")[];
  flags: string[];
  muted: boolean;
  removed?: boolean;
}

export interface Me {
  email: string;
  accounts: { id: number; email: string; provider: "gmail" | "outlook"; sync_status: string; matched: number; processed: number; last_synced_at: string | null }[];
  unknowns: number;
}
