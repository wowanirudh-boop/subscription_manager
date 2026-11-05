import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, StyleSheet, Text, TextInput, View } from "react-native";

import { Button, C } from "@/components/ui";
import { api } from "@/lib/api";
import { isValidIsoDate, money } from "@/lib/format";
import type { RecordView } from "@/lib/types";

// R6 / D22: bottom sheet - merchant, evidence, "We couldn't find a renewal date in this email",
// Monthly / Annual / Not a subscription / Skip; "Enter a date" is secondary.
export default function UnknownSheet() {
  const { key } = useLocalSearchParams<{ key: string }>();
  const [r, setR] = useState<RecordView | null>(null);
  const [askDate, setAskDate] = useState(false);
  const [date, setDate] = useState("");
  useEffect(() => { api.record(key).then(setR).catch(() => router.back()); }, [key]);
  if (!r) return null;

  async function answer(a: "monthly" | "annual" | "not_subscription" | "skip" | "date") {
    if (a === "date" && !isValidIsoDate(date)) return Alert.alert("Use the format YYYY-MM-DD");
    const out = await api.answerUnknown(r!.record_key, a, a === "date" ? date : undefined);
    if (out.needs_date) { setAskDate(true); return; } // period kept; we still need one date
    router.back();
  }
  const evidence = r.merchant.evidence?.snippet ?? r.amount.evidence?.snippet ?? r.last_charge_date.evidence?.snippet;

  return (
    <View style={st.wrap}>
      <Text style={st.title}>{r.merchant.value}</Text>
      {r.amount.value != null && <Text style={st.sub}>{money(r)}</Text>}
      {evidence && <Text style={st.quote}>“{evidence}”</Text>}
      <Text style={st.sub}>We couldn't find a renewal date in this email</Text>
      {!askDate ? (
        <>
          <Text style={st.q}>How often does it charge?</Text>
          <Button title="Monthly" onPress={() => answer("monthly")} />
          <Button title="Yearly" onPress={() => answer("annual")} />
          <Button kind="secondary" title="Not a subscription" onPress={() => answer("not_subscription")} />
          <Button kind="secondary" title="Skip for now" onPress={() => answer("skip")} />
          <Button kind="secondary" title="Enter a date instead" onPress={() => setAskDate(true)} />
        </>
      ) : (
        <>
          <Text style={st.q}>When is the next charge?</Text>
          <TextInput style={st.input} value={date} onChangeText={setDate} placeholder="YYYY-MM-DD" autoFocus />
          <Button title="Save" onPress={() => answer("date")} />
        </>
      )}
    </View>
  );
}

const st = StyleSheet.create({
  wrap: { padding: 20, backgroundColor: C.card, flex: 1 },
  title: { fontSize: 22, fontWeight: "700", color: C.ink },
  sub: { color: C.sub, marginVertical: 6 },
  quote: { fontStyle: "italic", color: C.ink, marginVertical: 8 },
  q: { fontSize: 16, fontWeight: "600", color: C.ink, marginTop: 12, marginBottom: 6 },
  input: { borderWidth: 1, borderColor: C.line, borderRadius: 8, padding: 12, marginVertical: 8 },
});
