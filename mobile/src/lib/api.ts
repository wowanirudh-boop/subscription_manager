import Constants from "expo-constants";
import * as SecureStore from "expo-secure-store";

import type { Me, Period, RecordView } from "./types";

const API = (Constants.expoConfig?.extra as { apiUrl: string } | undefined)?.apiUrl ?? "http://localhost:8000";
const KEY = "srt.session";
export const DISCLOSURE_VERSION = "mail-disclosure-v2"; // v2: Outlook + bank/card alert e-mails

// One app session id: a skipped unknowns card returns no sooner than the next session (R6).
export const SESSION_ID = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(KEY);
}
export async function setToken(t: string | null): Promise<void> {
  if (t) await SecureStore.setItemAsync(KEY, t);
  else await SecureStore.deleteItemAsync(KEY);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const tok = auth ? await getToken() : null;
  if (tok) headers.Authorization = `Bearer ${tok}`;
  const res = await fetch(`${API}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail ?? msg; } catch { /* not JSON */ }
    throw new ApiError(res.status, String(msg));
  }
  return res.json() as Promise<T>;
}

export const api = {
  connectGmail: (serverAuthCode: string) =>
    call<{ session_token: string; account_id: number; email: string }>("POST", "/v1/auth/google", {
      server_auth_code: serverAuthCode, disclosure_version: DISCLOSURE_VERSION, disclosure_accepted: true,
    }),
  connectOutlook: (code: string, codeVerifier: string, redirectUri: string) =>
    call<{ session_token: string; account_id: number; email: string }>("POST", "/v1/auth/microsoft", {
      code, code_verifier: codeVerifier, redirect_uri: redirectUri,
      disclosure_version: DISCLOSURE_VERSION, disclosure_accepted: true,
    }),
  me: () => call<Me>("GET", "/v1/me"),
  records: () => call<{ records: RecordView[]; unknowns: number }>("GET", "/v1/records"),
  record: (key: string) => call<RecordView>("GET", `/v1/records/${key}`),
  confirmField: (key: string, field: string) => call<RecordView>("POST", `/v1/records/${key}/fields/${field}`, { action: "confirm" }),
  correctField: (key: string, field: string, value: unknown) =>
    call<RecordView>("POST", `/v1/records/${key}/fields/${field}`, { action: "correct", value }),
  iCancelled: (key: string) => call<RecordView>("POST", `/v1/records/${key}/cancelled`),
  forceConfirm: (key: string) =>
    call<RecordView>("POST", `/v1/records/${key}/force-confirm-cancel`, { acknowledged_no_merchant_confirmation: true }),
  confirmCancelled: (key: string) => call<RecordView>("POST", `/v1/records/${key}/confirm-cancelled`),
  resubscribe: (key: string, resubscribed: boolean) =>
    call<RecordView & { show_cancel_path: boolean }>("POST", `/v1/records/${key}/resubscribe`, { resubscribed }),
  notSubscription: (key: string) => call<RecordView>("POST", `/v1/records/${key}/not-subscription`),
  mute: (key: string, muted: boolean) => call<RecordView>("POST", `/v1/records/${key}/mute`, { muted }),
  addManual: (r: { merchant: string; amount: number | null; currency: string; billing_period: Period; next_charge_date: string | null }) =>
    call<RecordView>("POST", "/v1/records/manual", r),
  nextUnknown: () =>
    call<{ card: RecordView | null; remaining: number; prompt: string }>("GET", `/v1/unknowns/next?session_id=${SESSION_ID}`),
  answerUnknown: (key: string, answer: "monthly" | "annual" | "not_subscription" | "skip" | "date", date?: string) =>
    call<{ needs_date: boolean; record: RecordView }>("POST", `/v1/unknowns/${key}/answer`, { answer, session_id: SESSION_ID, date }),
  pushToken: (token: string, platform: "ios" | "android") => call<{ ok: boolean }>("POST", "/v1/push-tokens", { token, platform }),
  alertOpened: (id: number) => call<{ ok: boolean }>("POST", `/v1/alerts/${id}/opened`),
  disconnect: (accountId: number) => call<{ disconnected: boolean }>("POST", `/v1/accounts/${accountId}/disconnect`),
  deleteEverything: () => call<{ deleted: boolean }>("DELETE", "/v1/me"),
};
