import { Link, router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { Button, C, Card, Tag } from "@/components/ui";
import { api, ApiError, getToken } from "@/lib/api";
import { daysUntil, isClosed, money, shortDate, STATE_LABEL } from "@/lib/format";
import type { Me, RecordView } from "@/lib/types";

export default function Home() {
  const [records, setRecords] = useState<RecordView[]>([]);
  const [card, setCard] = useState<RecordView | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!(await getToken())) { router.replace("/disclosure"); return; }
    setLoading(true);
    try {
      const [r, u, m] = await Promise.all([api.records(), api.nextUnknown(), api.me()]);
      setRecords(r.records); setCard(u.card); setRemaining(u.remaining); setMe(m);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.replace("/disclosure");
    } finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const syncing = me?.accounts.some((a) => a.sync_status === "running" || a.sync_status === "pending");
  const upcoming = records.filter((r) => !isClosed(r.state));
  const closed = records.filter((r) => isClosed(r.state));

  return (
    <FlatList
      style={{ backgroundColor: C.bg }} contentContainerStyle={{ padding: 16 }}
      data={[...upcoming, ...closed]} keyExtractor={(r) => r.record_key}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
      ListHeaderComponent={
        <View>
          {syncing && (
            <Card><Text style={st.sub}>
              Scanning your inbox… {me?.accounts.reduce((n, a) => n + a.processed, 0)} emails checked so far.
              Results appear as they're found; large inboxes take longer.
            </Text></Card>
          )}
          {card && (
            // R6: one unknown at a time, as a single card; never a list by default.
            <Pressable onPress={() => router.push(`/unknown/${card.record_key}`)}>
              <Card>
                <Text style={st.cardTitle}>When does {card.merchant.value} renew?</Text>
                <Text style={st.sub}>One tap turns on alerts for it.</Text>
                {remaining > 1 && <Text style={st.small}>{remaining - 1} more to check later</Text>}
              </Card>
            </Pressable>
          )}
          <View style={st.row}>
            <Link href="/add" style={st.link}>+ Add manually</Link>
            <Link href="/settings" style={st.link}>Accounts & data</Link>
          </View>
        </View>
      }
      ListEmptyComponent={!loading && !syncing ? <Text style={st.sub}>No subscriptions found yet.</Text> : undefined}
      renderItem={({ item: r }) => <Row r={r} />}
    />
  );
}

function Row({ r }: { r: RecordView }) {
  const next = r.next_charge_date.value;
  const days = next ? daysUntil(next, new Date()) : null;
  return (
    <Pressable onPress={() => router.push(`/record/${r.record_key}`)}>
      <Card>
        <View style={st.between}>
          <Text style={st.merchant} numberOfLines={1}>{r.merchant.value ?? "Unknown merchant"}</Text>
          <Text style={st.amount}>{money(r)}</Text>
        </View>
        <View style={[st.row, { marginTop: 4 }]}>
          <Text style={st.sub}>{next ? `Next charge ${shortDate(next)}${days !== null && days >= 0 ? ` · in ${days} d` : ""}` : "Next charge unknown"}</Text>
          <Tag f={r.next_charge_date} />
        </View>
        <Text style={st.small}>
          {STATE_LABEL[r.state]}{r.muted ? " · muted" : ""} · {r.source_accounts.join(", ")}
        </Text>
        {r.notices.includes("resubscribe_question") && <Text style={st.warn}>Charged again — did you re-subscribe?</Text>}
        {r.notices.includes("charged_while_pending") && <Text style={st.warn}>Charged although you cancelled</Text>}
      </Card>
    </Pressable>
  );
}

const st = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 12, flexWrap: "wrap" },
  between: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  merchant: { fontSize: 17, fontWeight: "600", color: C.ink, flexShrink: 1 },
  amount: { fontSize: 16, color: C.ink, fontVariant: ["tabular-nums"] },
  sub: { color: C.sub, fontSize: 14 },
  small: { color: C.sub, fontSize: 12, marginTop: 4 },
  warn: { color: C.warn, marginTop: 6, fontWeight: "600" },
  cardTitle: { fontSize: 16, fontWeight: "600", color: C.ink },
  link: { color: C.accent, fontSize: 15, marginBottom: 10 },
});
