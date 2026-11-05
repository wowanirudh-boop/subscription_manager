import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { Alert, ScrollView, StyleSheet, Text } from "react-native";

import { Button, C, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { connectGmail, signOutLocal } from "@/lib/auth";
import type { Me } from "@/lib/types";

export default function Settings() {
  const [me, setMe] = useState<Me | null>(null);
  useFocusEffect(useCallback(() => { api.me().then(setMe).catch(() => null); }, []));

  return (
    <ScrollView style={{ backgroundColor: C.bg }} contentContainerStyle={{ padding: 16 }}>
      <Text style={st.h}>Connected Gmail accounts</Text>
      {me?.accounts.map((a) => (
        <Card key={a.id}>
          <Text style={st.email}>{a.email}</Text>
          <Text style={st.sub}>{a.sync_status === "done" ? `${a.processed} emails checked` : `Sync: ${a.sync_status}`}</Text>
          <Button kind="danger" title="Disconnect" onPress={() => Alert.alert(
            "Disconnect this account?",
            "We revoke access and delete everything found in this account. Subscriptions also seen in another account stay.",
            [{ text: "Cancel", style: "cancel" }, { text: "Disconnect", style: "destructive",
              onPress: async () => { await api.disconnect(a.id); setMe(await api.me()); } }])} />
        </Card>
      ))}
      <Button kind="secondary" title="Add another Gmail account" onPress={() => router.push("/disclosure")} />
      <Text style={[st.h, { marginTop: 24 }]}>Your data</Text>
      <Button kind="danger" title="Delete everything" onPress={() => Alert.alert(
        "Delete everything?",
        "All subscriptions, evidence and Gmail access are deleted and can't be recovered. You'll get a confirmation email.",
        [{ text: "Cancel", style: "cancel" }, { text: "Delete", style: "destructive",
          onPress: async () => { await api.deleteEverything(); await signOutLocal(); router.replace("/disclosure"); } }])} />
      <Button kind="secondary" title="Sign out on this phone" onPress={async () => { await signOutLocal(); router.replace("/disclosure"); }} />
    </ScrollView>
  );
}

const st = StyleSheet.create({
  h: { fontSize: 17, fontWeight: "700", color: C.ink, marginBottom: 8 },
  email: { fontSize: 16, fontWeight: "600", color: C.ink },
  sub: { color: C.sub, marginBottom: 6 },
});
