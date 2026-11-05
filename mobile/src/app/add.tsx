import { router } from "expo-router";
import { useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, TextInput } from "react-native";

import { Button, C } from "@/components/ui";
import { api } from "@/lib/api";
import { isValidIsoDate } from "@/lib/format";

// R5 manual add: everything entered here is confirmed (user-entered). Covers merchants that never email (R1 risk).
export default function Add() {
  const [merchant, setMerchant] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [period, setPeriod] = useState<"monthly" | "annual">("monthly");
  const [next, setNext] = useState("");

  async function save() {
    if (!merchant.trim()) return Alert.alert("Enter the merchant name");
    if (next && !isValidIsoDate(next)) return Alert.alert("Use the format YYYY-MM-DD for the date");
    await api.addManual({ merchant: merchant.trim(), amount: amount ? Number(amount) : null, currency: currency.trim().toUpperCase(),
      billing_period: period, next_charge_date: next || null });
    router.back();
  }
  return (
    <ScrollView contentContainerStyle={st.wrap}>
      <Text style={st.l}>Merchant</Text><TextInput style={st.i} value={merchant} onChangeText={setMerchant} placeholder="e.g. YouTube Premium" />
      <Text style={st.l}>Amount</Text><TextInput style={st.i} value={amount} onChangeText={setAmount} keyboardType="decimal-pad" />
      <Text style={st.l}>Currency</Text><TextInput style={st.i} value={currency} onChangeText={setCurrency} autoCapitalize="characters" />
      <Text style={st.l}>Billing period</Text>
      <Button kind={period === "monthly" ? "primary" : "secondary"} title="Monthly" onPress={() => setPeriod("monthly")} />
      <Button kind={period === "annual" ? "primary" : "secondary"} title="Yearly" onPress={() => setPeriod("annual")} />
      <Text style={st.l}>Next charge (YYYY-MM-DD)</Text><TextInput style={st.i} value={next} onChangeText={setNext} placeholder="2026-12-08" />
      <Button title="Add" onPress={save} />
    </ScrollView>
  );
}

const st = StyleSheet.create({
  wrap: { padding: 20 },
  l: { color: C.sub, marginTop: 12 },
  i: { borderWidth: 1, borderColor: C.line, borderRadius: 8, padding: 12, marginTop: 4, backgroundColor: "#fff" },
});
