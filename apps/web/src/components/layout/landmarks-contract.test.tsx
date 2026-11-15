import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AuthRouteLoading } from "@/components/layout/route-loading";
import { SkipToContentLink } from "@/components/layout/skip-to-content-link";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { SessionRichText } from "@/components/sessions/session-rich-text";
import { SetupFrame } from "@/components/setup/setup-frame";

// M8-E1-T3 (D-189, D-190, F-WEB-14): one <main> landmark per page, one <h1>
// per page, and a skip-link target on the auth routes.

const SRC = resolve(__dirname, "../..");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return entry.name.endsWith(".tsx") && !entry.name.includes(".test.") ? [path] : [];
  });
}

function read(path: string): string {
  return readFileSync(resolve(SRC, path), "utf8");
}

const MAIN_TAG = /<main[\s>]/;
const H1_TAG = /<h1[\s>]/;

// Every file allowed to render an <h1>. On routes that show the workspace
// topbar, its route title is the page's <h1>, so a page component under it
// uses <h2>; a new <h1> anywhere else fails this test.
const H1_ALLOWED = [
  // The route title on every route that shows the topbar.
  "components/layout/workspace-topbar.tsx",
  // Full-screen auth routes without the topbar.
  "components/auth/forgot-password-screen.tsx",
  "components/auth/insecure-transport-screen.tsx",
  "components/auth/login-screen.tsx",
  "components/setup/step-create-account.tsx",
  "components/setup/step-recovery-codes.tsx",
  // /sessions hides the topbar: a visually hidden route title.
  "components/features/sessions/sessions-page-client.tsx",
  // Not mounted on any route (no importers).
  "components/control-plane/shared/entity-header.tsx",
  "components/control-plane/system/integrations/integration-marketplace.tsx",
  "components/control-plane/system/mcp/mcp-server-catalog.tsx",
  "components/layout/header.tsx",
].sort();

describe("landmarks, headings and the skip link (M8-E1-T3)", () => {
  it("renders <main> only in the app shell and the full-screen auth frames", () => {
    const withMain = sourceFiles(SRC)
      .filter((path) => MAIN_TAG.test(readFileSync(path, "utf8")))
      .map((path) => relative(SRC, path))
      .sort();

    expect(withMain).toEqual([
      "components/layout/app-shell.tsx",
      "components/layout/route-loading.tsx",
      "components/setup/setup-frame.tsx",
    ]);
    // route-loading.tsx keeps a <main> only for AuthRouteLoading, which
    // renders outside the app shell.
    expect(read("components/layout/route-loading.tsx").match(/<main[\s>]/g)).toHaveLength(1);
  });

  it("renders <h1> only in the topbar and on routes without it", () => {
    const withH1 = sourceFiles(SRC)
      .filter((path) => H1_TAG.test(readFileSync(path, "utf8")))
      .map((path) => relative(SRC, path))
      .sort();
    expect(withH1).toEqual(H1_ALLOWED);
  });

  it("renders chat markdown headings one level below the page <h1>", () => {
    const { container } = render(
      <SessionRichText
        content={"# Release notes\n\n## Fixes\n\n###### Footnote\n\nEverything shipped correctly."}
      />,
    );
    expect(container.querySelectorAll("h1")).toHaveLength(0);
    expect(screen.getByRole("heading", { level: 2, name: "Release notes" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Fixes" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 6, name: "Footnote" })).toBeInTheDocument();
    // Each keeps the size of the markdown level it came from.
    expect(screen.getByRole("heading", { name: "Release notes" })).toHaveClass("session-richtext__h1");
    expect(screen.getByRole("heading", { name: "Fixes" })).toHaveClass("session-richtext__h2");
  });

  it("keeps the unmounted <h1> components unmounted", () => {
    const unmounted = [
      "entity-header",
      "integration-marketplace",
      "mcp-server-catalog",
      "layout/header",
    ];
    const importers = sourceFiles(SRC)
      .filter((path) =>
        unmounted.some((name) =>
          new RegExp(`from ["'][^"']*/${name}["']`).test(readFileSync(path, "utf8")),
        ),
      )
      .map((path) => relative(SRC, path));
    expect(importers).toEqual(["components/control-plane/control-plane-home.tsx"]);
    // control-plane-home.tsx (the only PageHeader user) is not mounted either.
    const homeImporters = sourceFiles(SRC).filter((path) =>
      /from ["'][^"']*\/control-plane-home["']/.test(readFileSync(path, "utf8")),
    );
    expect(homeImporters).toEqual([]);
  });

  it("gives the auth frame's <main> the skip-link target", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <SkipToContentLink />
        <SetupFrame>
          <p>form</p>
        </SetupFrame>
      </I18nProvider>,
    );
    const target = screen.getByRole("link").getAttribute("href");
    expect(target).toBe("#conteudo-principal");
    expect(screen.getByRole("main")).toHaveAttribute("id", "conteudo-principal");
  });

  it("gives the auth loading frame's <main> the skip-link target", () => {
    render(<AuthRouteLoading />);
    expect(screen.getByRole("main")).toHaveAttribute("id", "conteudo-principal");
  });
});
