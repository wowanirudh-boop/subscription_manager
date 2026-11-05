# Mobile app — Expo (iOS + Android)

Expo SDK 58, Expo Router, TypeScript. Screens live in `src/app/`, client code in `src/lib/`.

| Screen | PRD |
|---|---|
| `disclosure.tsx`: what is read, stored, never stored, who sees it, India region; "Agree and connect Gmail" | R1 |
| `index.tsx`: list sorted by next charge (unknowns last), one unknown card, sync progress, notices | R2, R5, R6 |
| `record/[key].tsx`: fields with Estimated/Unknown tags, evidence on tap, confirm/correct, I cancelled, force-confirm warning, confirm likely cancelled, re-subscribe question, mute, not a subscription | R5, R8 |
| `unknown/[key].tsx`: bottom sheet: Monthly / Yearly / Not a subscription / Skip, "Enter a date instead" | R6, D22 |
| `add.tsx`: manual add (all values confirmed) | R5 |
| `settings.tsx`: accounts (add, disconnect), delete everything, sign out | R1, R9 |

```bash
npm install
npm run typecheck     # tsc --noEmit
npm test              # pure helpers (node:test)
npx expo export --platform android   # bundles the whole app (checked in the build session)
```

Google Sign-In is native, so run a development build (`npx eas-cli build --profile development`), not Expo Go. Configuration comes from environment variables; see `app.config.ts` and `../deploy/README.md`.

**Note:** in the build session `docs.expo.dev` and the Expo API were blocked. Package versions came from Expo's offline `bundledNativeModules.json`, and APIs were checked against the installed type definitions. Re-run `npx expo-doctor` and `npx expo install --check` with network access.
