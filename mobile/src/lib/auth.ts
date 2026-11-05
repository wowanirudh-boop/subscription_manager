import { GoogleSignin, isSuccessResponse } from "@react-native-google-signin/google-signin";
import Constants from "expo-constants";

import { api, setToken } from "./api";

// D8: gmail.readonly only. offlineAccess makes Google return a server auth code that the
// backend exchanges (with its client secret) for a refresh token. The app never holds Gmail tokens.
const GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly";

let configured = false;
function configure() {
  if (configured) return;
  const webClientId = (Constants.expoConfig?.extra as { googleWebClientId?: string } | undefined)?.googleWebClientId;
  GoogleSignin.configure({ webClientId, offlineAccess: true, forceCodeForRefreshToken: true, scopes: [GMAIL_SCOPE] });
  configured = true;
}

/** Call only after the user tapped "Agree and connect" on the disclosure screen (R1). */
export async function connectGmail(): Promise<{ email: string } | null> {
  configure();
  await GoogleSignin.hasPlayServices();
  await GoogleSignin.signOut().catch(() => null); // always show the account picker (D16: several accounts)
  const res = await GoogleSignin.signIn();
  if (!isSuccessResponse(res)) return null; // user cancelled
  const code = res.data.serverAuthCode;
  if (!code) throw new Error("Google did not return an authorization code. Check the web client id.");
  const out = await api.connectGmail(code); // backend rejects partial grants (flow #8)
  await setToken(out.session_token);
  return { email: out.email };
}

export async function signOutLocal(): Promise<void> {
  await setToken(null);
  configure();
  await GoogleSignin.signOut().catch(() => null);
}
