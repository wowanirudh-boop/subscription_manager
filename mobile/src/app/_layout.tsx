import * as Notifications from "expo-notifications";
import { router, Stack } from "expo-router";
import { useEffect } from "react";

import { api } from "@/lib/api";

export default function Layout() {
  useEffect(() => {
    // Tapping an alert opens its record and records the open (M5).
    const sub = Notifications.addNotificationResponseReceivedListener((resp) => {
      const data = resp.notification.request.content.data as { record_key?: string; alert_id?: number };
      if (data.alert_id) api.alertOpened(data.alert_id).catch(() => null);
      if (data.record_key) router.push(`/record/${data.record_key}`);
    });
    return () => sub.remove();
  }, []);
  return (
    <Stack screenOptions={{ headerTitleStyle: { fontWeight: "600" } }}>
      <Stack.Screen name="index" options={{ title: "Upcoming charges" }} />
      <Stack.Screen name="disclosure" options={{ title: "Connect email" }} />
      <Stack.Screen name="record/[key]" options={{ title: "Subscription" }} />
      <Stack.Screen name="unknown/[key]" options={{ title: "Missing renewal date", presentation: "formSheet" }} />
      <Stack.Screen name="add" options={{ title: "Add manually", presentation: "modal" }} />
      <Stack.Screen name="settings" options={{ title: "Accounts & data" }} />
    </Stack>
  );
}
