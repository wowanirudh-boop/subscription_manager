import { makeRedirectUri, useAuthRequest, type DiscoveryDocument } from "expo-auth-session";
import Constants from "expo-constants";
import * as WebBrowser from "expo-web-browser";

import { api, setToken } from "./api";

WebBrowser.maybeCompleteAuthSession();

// Microsoft identity platform, "common" = personal (Outlook.com / Hotmail) and work/school accounts.
const discovery: DiscoveryDocument = {
  authorizationEndpoint: "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
  tokenEndpoint: "https://login.microsoftonline.com/common/oauth2/v2.0/token",
};
// Read-only mail (mirrors D8). offline_access lets the backend keep syncing.
const SCOPES = ["openid", "email", "offline_access", "Mail.Read", "User.Read"];

export function useOutlookSignIn() {
  const clientId = (Constants.expoConfig?.extra as { microsoftClientId?: string } | undefined)?.microsoftClientId ?? "";
  const redirectUri = makeRedirectUri({ scheme: "renewaltracker", path: "auth" });
  const [request, , promptAsync] = useAuthRequest(
    { clientId, scopes: SCOPES, redirectUri, usePKCE: true, extraParams: { prompt: "select_account" } },
    discovery,
  );

  /** Call only after the user tapped "Agree and connect" on the disclosure screen (R1). */
  async function connect(): Promise<{ email: string } | null> {
    if (!request) throw new Error("Outlook sign-in is still loading");
    if (!clientId) throw new Error("Outlook sign-in isn't configured (EXPO_PUBLIC_MICROSOFT_CLIENT_ID).");
    const res = await promptAsync();
    if (res.type !== "success") return null;
    // The phone never redeems the code: the backend does, with the PKCE verifier (no secret on device).
    const out = await api.connectOutlook(res.params.code, request.codeVerifier ?? "", redirectUri);
    await setToken(out.session_token);
    return { email: out.email };
  }
  return { ready: !!request, connect };
}
