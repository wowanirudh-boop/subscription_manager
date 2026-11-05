import type { ExpoConfig } from "expo/config";

// Placeholder name until Phase 0 succeeds and naming is done (D31).
// Values that differ per environment come from EAS environment variables.
const config: ExpoConfig = {
  name: "Renewal Tracker",
  slug: "renewal-tracker",
  scheme: "renewaltracker",
  version: "0.1.0",
  orientation: "portrait",
  icon: "./assets/icon.png",
  userInterfaceStyle: "automatic",
  ios: { supportsTablet: false, bundleIdentifier: process.env.IOS_BUNDLE_ID ?? "app.renewaltracker.dev" },
  android: {
    package: process.env.ANDROID_PACKAGE ?? "app.renewaltracker.dev",
    adaptiveIcon: {
      backgroundColor: "#E6F4FE",
      foregroundImage: "./assets/android-icon-foreground.png",
      backgroundImage: "./assets/android-icon-background.png",
      monochromeImage: "./assets/android-icon-monochrome.png",
    },
  },
  plugins: [
    "expo-router",
    "expo-secure-store",
    "expo-notifications",
    // iosUrlScheme = reversed iOS OAuth client id from Google Cloud (com.googleusercontent.apps.<id>).
    ["@react-native-google-signin/google-signin", { iosUrlScheme: process.env.GOOGLE_IOS_URL_SCHEME ?? "com.googleusercontent.apps.placeholder" }],
  ],
  extra: {
    apiUrl: process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000",
    googleWebClientId: process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID ?? "",
    // Azure app registration ("Mobile and desktop" platform, redirect renewaltracker://auth), personal + work accounts.
    microsoftClientId: process.env.EXPO_PUBLIC_MICROSOFT_CLIENT_ID ?? "",
    eas: { projectId: process.env.EAS_PROJECT_ID },
  },
};

export default config;
