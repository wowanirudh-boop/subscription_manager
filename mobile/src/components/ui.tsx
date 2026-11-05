import { Pressable, StyleSheet, Text, View } from "react-native";

import { stateTag } from "@/lib/format";
import type { FieldValue } from "@/lib/types";

export const C = { ink: "#14171a", sub: "#5b6470", line: "#e3e6ea", bg: "#f6f7f9", card: "#ffffff",
  accent: "#1f6feb", warn: "#b54708", warnBg: "#fff4e5", danger: "#c4320a", ok: "#067647" };

export function Button({ title, onPress, kind = "primary", disabled }: {
  title: string; onPress: () => void; kind?: "primary" | "secondary" | "danger"; disabled?: boolean;
}) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} disabled={disabled}
      style={({ pressed }) => [s.btn, s[kind], (pressed || disabled) && { opacity: 0.6 }]}>
      <Text style={[s.btnText, kind !== "primary" && { color: kind === "danger" ? C.danger : C.accent }]}>{title}</Text>
    </Pressable>
  );
}

export function Tag({ f }: { f: FieldValue<unknown> }) {
  const t = stateTag(f);
  if (!t) return null;
  return <Text style={[s.tag, t === "Unknown" && { backgroundColor: C.line, color: C.sub }]}>{t}</Text>;
}

export function Card({ children }: { children: React.ReactNode }) {
  return <View style={s.card}>{children}</View>;
}

export function Note({ children }: { children: React.ReactNode }) {
  return <View style={s.note}><Text style={{ color: C.warn }}>{children}</Text></View>;
}

const s = StyleSheet.create({
  btn: { paddingVertical: 12, paddingHorizontal: 16, borderRadius: 10, alignItems: "center", marginVertical: 4 },
  primary: { backgroundColor: C.accent },
  secondary: { backgroundColor: "transparent", borderWidth: 1, borderColor: C.line },
  danger: { backgroundColor: "transparent", borderWidth: 1, borderColor: C.danger },
  btnText: { color: "#fff", fontWeight: "600", fontSize: 16 },
  tag: { fontSize: 12, color: C.warn, backgroundColor: C.warnBg, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, overflow: "hidden", marginLeft: 6 },
  card: { backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: C.line },
  note: { backgroundColor: C.warnBg, borderRadius: 10, padding: 12, marginBottom: 10 },
});
