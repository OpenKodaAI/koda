import type { Metadata } from "next";
import Script from "next/script";
import { cookies } from "next/headers";
import { Inter, JetBrains_Mono } from "next/font/google";
import { SkipToContentLink } from "@/components/layout/skip-to-content-link";
import { AppShell } from "@/components/layout/app-shell";
import { BotCatalogProvider } from "@/components/providers/bot-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { buildThemeBootstrapScript, normalizeThemePreference } from "@/components/providers/theme";
import { QueryProvider } from "@/components/providers/query-provider";
import { getCachedBotDisplays } from "@/lib/bot-catalog-cache";
import { DEFAULT_LANGUAGE } from "@/lib/i18n";
import { THEME_PREFERENCE_STORAGE_KEY } from "@/lib/storage-codecs";
import "@xterm/xterm/css/xterm.css";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  applicationName: "Koda",
  title: {
    default: "Koda",
    template: "%s | Koda",
  },
  icons: {
    icon: [{ url: "/koda-favicon.svg", type: "image/svg+xml", sizes: "any" }],
    shortcut: [{ url: "/koda-favicon.svg", type: "image/svg+xml", sizes: "any" }],
    apple: "/apple-icon.png",
  },
  description:
    "Koda is the operational workspace for monitoring agents, executions, costs, memory and routines in real time.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const initialBots = await getCachedBotDisplays();
  const initialLanguage = DEFAULT_LANGUAGE;
  const cookieStore = await cookies();
  const themePreferenceCookie = cookieStore.get(THEME_PREFERENCE_STORAGE_KEY)?.value;
  const initialThemePreference = normalizeThemePreference(themePreferenceCookie);
  const initialTheme =
    initialThemePreference === "system" ? undefined : initialThemePreference;

  return (
    <html
      lang={initialLanguage}
      data-scroll-behavior="smooth"
      suppressHydrationWarning
      className={initialTheme === "dark" ? "dark" : undefined}
      data-theme={initialTheme}
      style={initialTheme ? { colorScheme: initialTheme } : undefined}
    >
      <head>
        <Script
          id="theme-bootstrap"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: buildThemeBootstrapScript({
              storageKey: THEME_PREFERENCE_STORAGE_KEY,
              cookieKey: THEME_PREFERENCE_STORAGE_KEY,
            }),
          }}
        />
      </head>
      <body className={`${inter.variable} ${jetbrainsMono.variable} bg-background text-foreground`}>
        <QueryProvider>
          <ThemeProvider initialThemePreference={initialThemePreference}>
            <I18nProvider initialLanguage={initialLanguage}>
              <SkipToContentLink />
              <BotCatalogProvider initialBots={initialBots}>
                <AppShell>{children}</AppShell>
              </BotCatalogProvider>
            </I18nProvider>
          </ThemeProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
