import { router } from "expo-router";
import { useState } from "react";
import { Alert, ScrollView, StyleSheet, Text } from "react-native";

import { Button, C } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { connectGmail } from "@/lib/auth";
import { useOutlookSignIn } from "@/lib/outlook";
import { registerForPush } from "@/lib/push";

// R1: in-app disclosure immediately before the OAuth handoff; affirmative tap required.
export default function Disclosure() {
  const [busy, setBusy] = useState(false);
  const outlook = useOutlookSignIn();
  async function agree(provider: "gmail" | "outlook") {
    setBusy(true);
    try {
      const out = provider === "gmail" ? await connectGmail() : await outlook.connect();
      if (!out) return;
      await registerForPush().catch(() => false);
      router.replace("/");
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 403
        ? "Read access to your mail wasn't granted, so nothing was connected. The app only works with read access."
        : String((e as Error).message ?? e);
      Alert.alert("Couldn't connect Gmail", msg);
    } finally {
      setBusy(false);
    }
  }
  return (
    <ScrollView contentContainerStyle={st.wrap}>
      <Text style={st.h}>Before you connect your email</Text>
      <Text style={st.b}>We warn you before a subscription or free trial charges you. To find them, we need read-only access to your Gmail or Outlook inbox. You can connect several accounts.</Text>
      <Text style={st.s}>What we read</Text>
      <Text style={st.b}>Only emails that look like receipts, invoices, trials, renewals or cancellations, and card or bank transaction alerts (to spot charges that repeat). Other mail is never downloaded.</Text>
      <Text style={st.s}>What we store</Text>
      <Text style={st.b}>The merchant, amount, dates and billing period we find, plus the one sentence each value came from, so you can check it. From bank alerts we keep only charges that repeat; one-off purchases are discarded.</Text>
      <Text style={st.s}>What we never store</Text>
      <Text style={st.b}>The emails themselves. They are processed and discarded.</Text>
      <Text style={st.s}>Who sees it</Text>
      <Text style={st.b}>Email content is sent to an AI provider solely to extract those fields, under zero-retention, no-training terms. No human reads your email. Support can see your data only if you allow it for a specific request.</Text>
      <Text style={st.s}>Where it lives</Text>
      <Text style={st.b}>On servers in India. You can disconnect an account or delete everything at any time, in one tap.</Text>
      <Text style={st.s}>What we can't see</Text>
      <Text style={st.b}>Subscriptions that never send email (some billed only by SMS or UPI apps) are invisible to us. You can add those manually.</Text>
      <Button title={busy ? "Connecting…" : "Agree and connect Gmail"} onPress={() => agree("gmail")} disabled={busy} />
      <Button kind="secondary" title="Agree and connect Outlook / Hotmail" onPress={() => agree("outlook")} disabled={busy || !outlook.ready} />
    </ScrollView>
  );
}

const st = StyleSheet.create({
  wrap: { padding: 20, backgroundColor: C.bg },
  h: { fontSize: 24, fontWeight: "700", color: C.ink, marginBottom: 10 },
  s: { fontSize: 15, fontWeight: "700", color: C.ink, marginTop: 14 },
  b: { fontSize: 15, color: C.sub, marginTop: 4, lineHeight: 21 },
});
