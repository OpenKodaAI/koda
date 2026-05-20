import type { Metadata } from "next";
import Script from "next/script";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { Inter, Fraunces, JetBrains_Mono } from "next/font/google";
import { SkipToContentLink } from "@/components/layout/skip-to-content-link";
import { AppShell } from "@/components/layout/app-shell";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { ConsoleSignature } from "@/components/providers/console-signature";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { buildThemeBootstrapScript, normalizeThemePreference } from "@/components/providers/theme";
import { QueryProvider } from "@/components/providers/query-provider";
import { getCachedAgentDisplays } from "@/lib/agent-catalog-cache";
import { resolveOptionalAuthStatus } from "@/lib/auth-guard";
import { DEFAULT_LANGUAGE } from "@/lib/i18n";
import { isSafeRedirectTarget } from "@/lib/safe-redirect";
import { THEME_PREFERENCE_STORAGE_KEY } from "@/lib/storage-codecs";
import { PENDING_RECOVERY_COOKIE } from "@/lib/web-operator-session-constants";
import "@xterm/xterm/css/xterm.css";
import "./globals.css";

const PUBLIC_AUTH_PATH_PATTERN = /^\/(login|setup|forgot-password|oauth)(\/|$)/;
const PUBLIC_AUTH_PATH_EXACT = new Set(["/login", "/setup", "/forgot-password"]);

function isPublicAuthRoute(pathname: string): boolean {
  if (!pathname) return false;
  return PUBLIC_AUTH_PATH_EXACT.has(pathname) || PUBLIC_AUTH_PATH_PATTERN.test(pathname);
}

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
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
  const initialLanguage = DEFAULT_LANGUAGE;
  const cookieStore = await cookies();
  const themePreferenceCookie = cookieStore.get(THEME_PREFERENCE_STORAGE_KEY)?.value;
  const initialThemePreference = normalizeThemePreference(themePreferenceCookie);
  const initialTheme =
    initialThemePreference === "system" ? undefined : initialThemePreference;
  const headerStore = await headers();
  // The proxy (Next 16) sets `x-koda-pathname` on every forwarded request, so
  // the layout can branch on the route deterministically during SSR even
  // though `usePathname()` is client-only.
  const serverPathname = headerStore.get("x-koda-pathname") || "";

  // Skip the agent-catalog hydration for public auth routes — /login, /setup
  // and /forgot-password don't render anything that depends on the catalog,
  // and skipping the upstream call means a slow control plane never makes
  // the login form take 6s to paint. Also skip when the proxy header is
  // missing entirely (Next 16 occasionally drops it): we'd rather hydrate
  // an empty catalog client-side than block SSR for everyone.
  const initialAgents =
    !serverPathname || isPublicAuthRoute(serverPathname)
      ? []
      : await getCachedAgentDisplays();

  // Defense-in-depth gate. The proxy already redirects unauthenticated traffic
  // away from protected routes; this layer additionally validates the sealed
  // cookie against the control plane (so revoked-but-decryptable tokens are
  // caught). Auth screens (/login, /setup, /forgot-password, /oauth/*) skip
  // this check — they own their own auth-status flow.
  // If the proxy header hasn't propagated (Next.js 16 sometimes drops custom
  // request headers between middleware and server components), trust the proxy
  // and skip the secondary check — otherwise we redirect /login → /login.
  let initialAuth = null;
  if (serverPathname && !isPublicAuthRoute(serverPathname)) {
    const resolution = await resolveOptionalAuthStatus();
    // - `ok` + authenticated → use the resolved operator on first paint
    // - `ok` + unauthenticated (false) → cookie revoked server-side, redirect
    // - `unauthenticated`              → explicit 401 from upstream, redirect
    // - `unreachable`                  → backend hiccup; trust the proxy's
    //                                    cookie validation and KEEP rendering
    //                                    so a transient 503 doesn't feel like
    //                                    a logout. Client-side AuthProvider
    //                                    retries on focus / next mutation.
    if (resolution.kind === "ok") {
      initialAuth = resolution.status;
    }
    const shouldRedirect =
      (resolution.kind === "ok" && !resolution.status.authenticated) ||
      resolution.kind === "unauthenticated";
    if (shouldRedirect) {
      const hasPendingRecovery =
        cookieStore.get(PENDING_RECOVERY_COOKIE)?.value === "1";
      // The proxy normally catches this earlier, but a race (cookie revoked
      // server-side after proxy passed) can land us here. Single safe redirect
      // to /login with `?next=`.
      if (!hasPendingRecovery) {
        const safeNext = isSafeRedirectTarget(serverPathname) ? serverPathname : null;
        const target = safeNext
          ? `/login?next=${encodeURIComponent(safeNext)}`
          : "/login";
        redirect(target);
      }
    }
  }

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
      <body className={`${inter.variable} ${fraunces.variable} ${jetbrainsMono.variable} bg-background text-foreground`}>
        <QueryProvider>
          <ThemeProvider initialThemePreference={initialThemePreference}>
            <I18nProvider initialLanguage={initialLanguage}>
              <ConsoleSignature />
              <SkipToContentLink />
              <AgentCatalogProvider initialAgents={initialAgents}>
                <AppShell serverPathname={serverPathname} initialAuth={initialAuth}>
                  {children}
                </AppShell>
              </AgentCatalogProvider>
            </I18nProvider>
          </ThemeProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
