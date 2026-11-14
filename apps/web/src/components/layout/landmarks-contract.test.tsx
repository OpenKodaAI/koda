import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AuthRouteLoading } from "@/components/layout/route-loading";
import { SkipToContentLink } from "@/components/layout/skip-to-content-link";
import { I18nProvider } from "@/components/providers/i18n-provider";
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

// Pages that render inside AppShell below the workspace topbar. The topbar's
// route title is their <h1>, so their own page title is an <h2>.
const UNDER_TOPBAR = [
  "components/features/overview/overview-page-client.tsx",
  "components/runtime/runtime-overview.tsx",
  "components/runtime/runtime-task-room.tsx",
  "components/control-plane/editor/agent-editor-shell.tsx",
  "components/control-plane/system/integrations/provider-grid.tsx",
  "app/settings/account/page.tsx",
];

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

  it("leaves the page <h1> to the topbar on routes that show it", () => {
    expect(read("components/layout/workspace-topbar.tsx")).toMatch(H1_TAG);
    for (const path of UNDER_TOPBAR) {
      expect(read(path), `${path} renders its own <h1>`).not.toMatch(H1_TAG);
    }
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
