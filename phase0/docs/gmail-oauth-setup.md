# Gmail OAuth setup for Phase 0

You need your own Google Cloud OAuth client (D8: our own OAuth app, `gmail.readonly` only). In **Testing** mode, Google allows up to 100 test users without verification, which covers Phase 0. CASA and verification are only needed for Phase 1/2 (PRD §10, §13).

> Google renames Cloud Console screens often. Recently the OAuth consent screen moved under **Google Auth Platform** (sections *Branding*, *Audience*, *Data access*, *Clients*). If your screens differ, the concepts below still apply. *Confidence: medium on exact menu names, high on the concepts.*

## Steps (about 15 minutes)

1. **Create a project.** In [console.cloud.google.com](https://console.cloud.google.com), create a new project (any name; the product name is deferred per D31).
2. **Enable the Gmail API.** Go to *APIs & Services → Library → Gmail API → Enable*.
3. **Consent screen / branding.** Choose user type **External**. Enter a placeholder app name, your email as the support and developer contact, and no logo. (A logo can trigger brand verification.)
4. **Audience.** Leave publishing status as **Testing**. Under *Test users*, add every Gmail address you'll connect.
5. **Data access (scopes).** Add `https://www.googleapis.com/auth/gmail.readonly` and nothing else.
6. **Create the client.** Go to *Clients → Create client → Application type: **Desktop app***. Note the **Client ID** and **Client secret**.
7. **Add them to the cloud environment**, not to chat. In the Claude app, open the environment menu in the session's title bar, then **Edit**. Add these under *Network secrets* (called *API credentials* in older app versions) if that section is offered, otherwise as environment variables:
   - `GOOGLE_OAUTH_CLIENT_ID`
   - `GOOGLE_OAUTH_CLIENT_SECRET`
   - `OPENROUTER_API_KEY`, `OPENROUTER_TRIAGE_MODEL`, `OPENROUTER_EXTRACT_MODEL` (when you have them)

   A **new session** picks these up.

## Connecting an account (headless, two steps)

```bash
srt-phase0 auth start --account you@gmail.com
```

1. Open the printed URL on any device and approve read-only access.
2. Google redirects to `http://localhost:8765/?state=…&code=…`. The page **fails to load**. That's expected: nothing listens there, because the code runs in a cloud container.
3. Copy that full URL from the address bar and finish:

```bash
srt-phase0 auth finish --account you@gmail.com --redirect-url '<pasted URL>'
```

**About pasting that URL:** it contains a one-time authorisation code. The code expires within minutes, can be redeemed only once, and is useless without the client secret plus the PKCE verifier stored in the container. It is still a credential-like value, and it will stay in the session transcript after use. If you want to avoid that, run `auth start` and `auth finish` from a terminal session on your own computer instead. (Google's device-code flow, which avoids the paste, doesn't support Gmail scopes, to my knowledge; *medium-high confidence*.)

`auth finish` refuses partial grants (flow sign-off #8 proposal) and refuses a different account than the one requested. In both cases it revokes the token.

## Known limits

- **Testing-mode refresh tokens expire after about 7 days** for an External app in Testing. Re-run the two auth steps when the pipeline reports an auth error. *(High confidence this policy exists; check Google's current OAuth docs for the exact duration.)*
- **Tokens are stored under `data/auth/` with 0600 file permissions**, not in a KMS/HSM. R10's encryption-at-rest requirement is therefore **not** met in Phase 0. That's acceptable for one founder inbox, not for beta users.
- **The container is ephemeral.** A new session needs a new `auth start`/`auth finish`.
- **To disconnect:** `srt-phase0 auth revoke --account you@gmail.com` revokes the token at Google and deletes it locally (R1).
