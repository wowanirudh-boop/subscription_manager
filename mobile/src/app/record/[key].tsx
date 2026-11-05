import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { Button, C, Card, Note, Tag } from "@/components/ui";
import { api } from "@/lib/api";
import { isValidIsoDate, ladderText, money, shortDate, STATE_LABEL } from "@/lib/format";
import type { FieldValue, RecordView } from "@/lib/types";

type FieldName = "next_charge_date" | "amount" | "billing_period" | "last_charge_date" | "trial_end_date";

export default function RecordScreen() {
  const { key } = useLocalSearchParams<{ key: string }>();
  const [r, setR] = useState<RecordView | null>(null);
  const [open, setOpen] = useState<FieldName | null>(null);
  const [edit, setEdit] = useState("");

  useEffect(() => { api.record(key).then(setR).catch(() => router.back()); }, [key]);
  if (!r) return null;

  const update = (p: Promise<RecordView>) => p.then((v) => (v.removed ? router.back() : setR(v))).catch((e) => Alert.alert("Error", String(e.message)));

  function field(name: FieldName, label: string, f: FieldValue<unknown>, show: string) {
    return (
      <Pressable onPress={() => { setOpen(open === name ? null : name); setEdit(String(f.value ?? "")); }}>
        <View style={st.field}>
          <Text style={st.label}>{label}</Text>
          <View style={st.rowEnd}><Text style={st.value}>{show}</Text><Tag f={f} /></View>
        </View>
        {open === name && (
          // R5: tapping a field shows its evidence and allows correct / confirm.
          <View style={st.evidence}>
            {f.evidence ? <Text style={st.quote}>“{f.evidence.snippet}”</Text> : <Text style={st.sub}>No email evidence for this value.</Text>}
            {f.derived_from && <Text style={st.sub}>{f.state === "estimated" ? "Estimated from: " : "Source: "}{f.derived_from}</Text>}
            {f.state === "estimated" && <Button kind="secondary" title="This is correct" onPress={() => update(api.confirmField(r!.record_key, name))} />}
            {name !== "billing_period" && (
              <>
                <TextInput style={st.input} value={edit} onChangeText={setEdit}
                  placeholder={name.endsWith("date") ? "YYYY-MM-DD" : "Amount"} keyboardType={name === "amount" ? "decimal-pad" : "default"} />
                <Button kind="secondary" title="Save correction" onPress={() => {
                  if (name.endsWith("date") && !isValidIsoDate(edit)) return Alert.alert("Use the format YYYY-MM-DD");
                  update(api.correctField(r!.record_key, name, name === "amount" ? Number(edit) : edit));
                }} />
              </>
            )}
            {name === "billing_period" && (["monthly", "annual"] as const).map((p) => (
              <Button key={p} kind="secondary" title={p === "monthly" ? "Monthly" : "Yearly"} onPress={() => update(api.correctField(r!.record_key, name, p))} />
            ))}
          </View>
        )}
      </Pressable>
    );
  }

  const period = r.billing_period.value;
  return (
    <ScrollView style={{ backgroundColor: C.bg }} contentContainerStyle={{ padding: 16 }}>
      <Text style={st.title}>{r.merchant.value}</Text>
      <Text style={st.sub}>{STATE_LABEL[r.state]} · {r.source_accounts.join(", ")}</Text>

      {r.notices.includes("resubscribe_question") && (
        <Card>
          <Text style={st.q}>{r.merchant.value} charged you again. Did you re-subscribe?</Text>
          <Button title="Yes, I re-subscribed" onPress={() => update(api.resubscribe(r.record_key, true))} />
          <Button kind="danger" title="No, I didn't" onPress={async () => {
            const v = await api.resubscribe(r.record_key, false); setR(v);
            if (v.cancel_path.value) Alert.alert("How to cancel", v.cancel_path.value);
          }} />
        </Card>
      )}
      {r.notices.includes("charged_while_pending") && <Note>You said you cancelled, but {r.merchant.value} charged you again. Check the cancellation went through.</Note>}
      {r.notices.includes("no_receipt_seen") && r.missed_date && (
        <Note>No receipt seen for {shortDate(r.missed_date)}. Some merchants never email receipts, so we're still tracking it. The next date is estimated.</Note>
      )}

      <Card>
        {field("next_charge_date", "Next charge", r.next_charge_date, shortDate(r.next_charge_date.value))}
        {field("amount", "Amount", r.amount, money(r))}
        {field("billing_period", "Billing period", r.billing_period, period === "annual" ? "Yearly" : period === "monthly" ? "Monthly" : period === "other" ? `Every ${r.period_months ?? "?"} months` : "Unknown")}
        {field("last_charge_date", "Last charge", r.last_charge_date, shortDate(r.last_charge_date.value))}
        {r.kind.value === "trial" && field("trial_end_date", "Trial ends", r.trial_end_date, shortDate(r.trial_end_date.value))}
        <Text style={st.small}>{r.alerts_enabled ? ladderText(period, r.kind.value) : "No alerts for this item"}</Text>
      </Card>

      {r.cancel_path.value && (
        <Button kind="secondary" title="How to cancel" onPress={() =>
          r.cancel_path.value!.startsWith("http") ? Linking.openURL(r.cancel_path.value!) : Alert.alert("How to cancel", r.cancel_path.value!)} />
      )}
      {(r.state === "active" || r.state === "unknown_date") && (
        <Button title="I cancelled this" onPress={() => update(api.iCancelled(r.record_key))} />
      )}
      {r.state === "cancellation_pending" && (
        <>
          <Note>We'll keep warning you until {r.merchant.value} confirms the cancellation by email.</Note>
          <Button kind="secondary" title="Mark as cancelled anyway" onPress={() => Alert.alert(
            "No confirmation from the merchant",
            `${r.merchant.value} hasn't confirmed the cancellation. If it didn't go through, you won't be warned before the next charge.`,
            [{ text: "Keep warning me", style: "cancel" }, { text: "Mark cancelled", style: "destructive", onPress: () => update(api.forceConfirm(r.record_key)) }])} />
        </>
      )}
      {r.state === "likely_cancelled" && <Button title="Confirm it's cancelled" onPress={() => update(api.confirmCancelled(r.record_key))} />}
      <Button kind="secondary" title={r.muted ? "Unmute alerts" : "Mute alerts"} onPress={() => update(api.mute(r.record_key, !r.muted))} />
      <Button kind="danger" title="Not a subscription" onPress={() => update(api.notSubscription(r.record_key))} />
    </ScrollView>
  );
}

const st = StyleSheet.create({
  title: { fontSize: 24, fontWeight: "700", color: C.ink },
  sub: { color: C.sub, fontSize: 14, marginBottom: 12 },
  small: { color: C.sub, fontSize: 12, marginTop: 8 },
  q: { fontSize: 16, fontWeight: "600", color: C.ink, marginBottom: 8 },
  field: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.line },
  rowEnd: { flexDirection: "row", alignItems: "center" },
  label: { color: C.sub, fontSize: 15 },
  value: { color: C.ink, fontSize: 15, fontWeight: "500" },
  evidence: { paddingVertical: 8 },
  quote: { fontStyle: "italic", color: C.ink, marginBottom: 6 },
  input: { borderWidth: 1, borderColor: C.line, borderRadius: 8, padding: 10, marginVertical: 6, backgroundColor: "#fff" },
});
