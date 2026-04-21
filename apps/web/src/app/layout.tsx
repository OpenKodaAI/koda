import type { Metadata } from "next";
import Script from "next/script";
import { cookies, headers } from "next/headers";
import { Inter, JetBrains_Mono } from "next/font/google";
import { SkipToContentLink } from "@/components/layout/skip-to-content-link";
import { AppShell } from "@/components/layout/app-shell";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { buildThemeBootstrapScript, normalizeThemePreference } from "@/components/providers/theme";
import { QueryProvider } from "@/components/providers/query-provider";
import { getCachedAgentDisplays } from "@/lib/agent-catalog-cache";
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
  const initialAgents = await getCachedAgentDisplays();
  const initialLanguage = DEFAULT_LANGUAGE;
  const cookieStore = await cookies();
  const themePreferenceCookie = cookieStore.get(THEME_PREFERENCE_STORAGE_KEY)?.value;
  const initialThemePreference = normalizeThemePreference(themePreferenceCookie);
  const initialTheme =
    initialThemePreference === "system" ? undefined : initialThemePreference;
  const headerStore = await headers();
  // The middleware sets `x-koda-pathname` on every forwarded request, so the
  // layout can branch on the route deterministically during SSR even though
  // `usePathname()` is client-only.
  const serverPathname = headerStore.get("x-koda-pathname") || "";

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
              <AgentCatalogProvider initialAgents={initialAgents}>
                <AppShell serverPathname={serverPathname}>{children}</AppShell>
              </AgentCatalogProvider>
            </I18nProvider>
          </ThemeProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
