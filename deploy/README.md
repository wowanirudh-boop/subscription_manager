# Launch checklist (private beta, ≤ 100 users)

Items marked **you** need your accounts, money or legal identity; I can't do them from a build session. Everything else is scripted.

## 1. Accounts and decisions (you)
- [ ] **Google Cloud project** with billing.
- [ ] **Apple Developer** (paid, for iOS builds and TestFlight) and **Google Play Console** (one-time fee) accounts.
- [ ] **Expo account**, for EAS cloud builds and push notifications.
- [ ] **OpenRouter key**, and the triage and extraction models chosen after a Phase 0 run on your inbox (Q2). This also needs `openrouter.ai` allowed in the build environment.
- [ ] **E-mail sending provider** with SMTP credentials, for the T−1/T−0 e-mails (D13). Any provider that offers SMTP works.

## 2. Google OAuth (you, in the Cloud console)
1. **OAuth consent screen:** External, Testing mode, your beta testers added as test users (≤ 100 until verification), scope `gmail.readonly` only.
2. **Clients:**
   - **Web** client: the backend exchanges codes with it. Its id is `GOOGLE_OAUTH_CLIENT_ID` and `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`.
   - **Android** client: package name plus the SHA-1 of the EAS signing key (`npx eas-cli credentials`).
   - **iOS** client: bundle id. Its reversed client id is `GOOGLE_IOS_URL_SCHEME`.
3. **Verification:** submit for verification and start the **CASA** assessment as soon as the beta works (PRD §13). Above 100 users the app must be verified. This needs the domain, privacy policy and Limited Use statement (D31), which haven't been built.

## 3. Backend (scripted)
```bash
export PROJECT_ID=... GOOGLE_OAUTH_CLIENT_ID=... GOOGLE_OAUTH_CLIENT_SECRET=... \
       OPENROUTER_API_KEY=... OPENROUTER_TRIAGE_MODEL=... OPENROUTER_EXTRACT_MODEL=... \
       SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=... MAIL_FROM=alerts@yourdomain
./deploy/gcp-setup.sh
```
Everything is created in **asia-south1**:
- Cloud Run (the service)
- Cloud SQL Postgres 16 (the database)
- a Cloud KMS key for token encryption
- Pub/Sub topic `gmail-push`, with Gmail allowed to publish and an OIDC-authenticated push subscription
- Cloud Scheduler, calling `/internal/tick` every 5 minutes
- Secret Manager, holding the secrets

The script prints the service URL.

## 4. App (scripted, after 2 and 3)
```bash
cd mobile && npx eas-cli@latest init          # links the project; sets EAS_PROJECT_ID
# In EAS environment variables: EXPO_PUBLIC_API_URL, EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID, GOOGLE_IOS_URL_SCHEME,
# IOS_BUNDLE_ID, ANDROID_PACKAGE, EAS_PROJECT_ID
npx eas-cli@latest build --profile beta --platform all
```
Google Sign-In uses native code, so it **doesn't run in Expo Go**. Testers need the `beta` build: an APK link on Android, TestFlight on iOS.

## 5. Before inviting testers
- [ ] Phase 0 run with the chosen OpenRouter model, scored against your review (A3 gate).
- [ ] One end-to-end check on a real phone: connect Gmail → list appears → alert arrives at 09:00 IST, by push and by e-mail.
- [ ] Privacy policy and Limited Use statement published on your domain (R10, Google policy).
