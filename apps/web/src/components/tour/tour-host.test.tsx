import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as browserStorage from "@/lib/browser-storage";
import { AppTourProvider } from "@/components/providers/app-tour-provider";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { safeLocalStorageGetValue, safeLocalStorageRemoveValue } from "@/lib/browser-storage";
import { appTourStorageCodec } from "@/lib/storage-codecs";

const pushMock = vi.fn();

function installLocalStorageMock() {
  const storageState = new Map<string, string>();
  const storage = {
    getItem: vi.fn((key: string) => storageState.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      storageState.set(key, String(value));
    }),
    removeItem: vi.fn((key: string) => {
      storageState.delete(key);
    }),
    clear: vi.fn(() => {
      storageState.clear();
    }),
  };

  Object.defineProperty(window, "localStorage", {
    value: storage,
    writable: true,
    configurable: true,
  });

  return storage;
}

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: { href: string; children: ReactNode } & Record<string, unknown>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

function HomeShell() {
  return (
    <>
      <div {...tourRoute("overview", "default")}>
        <div {...tourAnchor("overview.bot-switcher")}>Bot switcher</div>
        <div {...tourAnchor("overview.stats")}>Overview stats</div>
        <div {...tourAnchor("overview.runtime-control")}>Runtime control</div>
        <div {...tourAnchor("overview.live-plan")}>Live plan</div>
      </div>
      <aside {...tourRoute("shell.sidebar")} {...tourAnchor("shell.sidebar.brand")}>
        <span {...tourAnchor("shell.sidebar.nav.home")}>
          Home
        </span>
      </aside>
      <header {...tourRoute("shell.topbar")}>
        <div {...tourAnchor("shell.topbar.actions")}>Topbar actions</div>
        <button type="button" {...tourAnchor("shell.topbar.language-switcher.trigger")}>
          Language
        </button>
      </header>
    </>
  );
}

function ControlPlaneShell() {
  return (
    <>
      <section {...tourRoute("control-plane.catalog", "empty")}>
        <button type="button" {...tourAnchor("catalog.create-bot")}>
          Create bot
        </button>
        <div {...tourAnchor("catalog.board")}>Catalog board</div>
        <div {...tourAnchor("catalog.empty")}>Empty catalog</div>
      </section>
      <aside {...tourRoute("shell.sidebar")} {...tourAnchor("shell.sidebar.brand")}>
        <span {...tourAnchor("shell.sidebar.nav.control-plane")}>
          Agents
        </span>
      </aside>
      <header {...tourRoute("shell.topbar")}>
        <div {...tourAnchor("shell.topbar.actions")}>Topbar actions</div>
      </header>
    </>
  );
}

function renderTour({
  pathname,
  shell,
}: {
  pathname: string;
  shell: React.ReactNode;
}) {
  return render(
    <I18nProvider initialLanguage="en-US">
      <AppTourProvider
        pathname={pathname}
        mobileNavOpen={false}
        onMobileNavOpenChange={() => undefined}
      >
        {shell}
      </AppTourProvider>
    </I18nProvider>,
  );
}

function setViewportSize(width: number, height: number) {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    writable: true,
    value: height,
  });
  window.dispatchEvent(new Event("resize"));
}

function mockElementRect(
  element: Element,
  rect: {
    top: number;
    left: number;
    width: number;
    height: number;
  },
) {
  const right = rect.left + rect.width;
  const bottom = rect.top + rect.height;

  Object.defineProperty(element, "getBoundingClientRect", {
    configurable: true,
    value: vi.fn(() => ({
      x: rect.left,
      y: rect.top,
      top: rect.top,
      left: rect.left,
      right,
      bottom,
      width: rect.width,
      height: rect.height,
      toJSON: () => undefined,
    })),
  });
}

describe("TourHost", () => {
  const setValueSpy = vi.spyOn(browserStorage, "safeLocalStorageSetValue");

  beforeEach(() => {
    installLocalStorageMock();
    pushMock.mockReset();
    setValueSpy.mockClear();
    safeLocalStorageRemoveValue(appTourStorageCodec);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    setViewportSize(1280, 900);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("auto-opens on first eligible load and supports continue, back and skip", async () => {
    const user = userEvent.setup();
    const view = renderTour({ pathname: "/", shell: <HomeShell /> });

    expect(
      await screen.findByRole("heading", {
        name: "Start with a quick guided tour",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Start tour" }));
    expect(
      await screen.findByRole("heading", {
        name: "This sidebar is your main map",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(
      await screen.findByRole("heading", {
        name: "The topbar keeps route context close",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(
      await screen.findByRole("heading", {
        name: "This sidebar is your main map",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Skip tour" }));

    await waitFor(() => {
      expect(
        within(document.body).queryByRole("heading", {
          name: "This sidebar is your main map",
        }),
      ).not.toBeInTheDocument();
    });
    expect(setValueSpy).toHaveBeenCalled();
    expect(safeLocalStorageGetValue(appTourStorageCodec).status).toBe("skipped");

    view.unmount();
    renderTour({ pathname: "/", shell: <HomeShell /> });

    await waitFor(() => {
      expect(within(document.body).queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("skips the optional editor chapter and navigates to runtime when no bot editor route exists", async () => {
    const user = userEvent.setup();
    renderTour({ pathname: "/control-plane", shell: <ControlPlaneShell /> });

    expect(
      await screen.findByRole("heading", {
        name: "The catalog is your first stop on a fresh install",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(
      await screen.findByRole("heading", {
        name: "The board grows with the catalog",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/runtime", { scroll: false });
    });
  });

  it("uses a bottom-sheet coachmark on mobile and falls back to the visible anchor", async () => {
    setViewportSize(390, 844);
    const user = userEvent.setup();

    renderTour({ pathname: "/", shell: <HomeShell /> });

    mockElementRect(screen.getByText("Home"), {
      top: 112,
      left: 20,
      width: 220,
      height: 56,
    });
    mockElementRect(screen.getByText("Topbar actions"), {
      top: 0,
      left: -120,
      width: 0,
      height: 0,
    });
    mockElementRect(screen.getByRole("button", { name: "Language" }), {
      top: 18,
      left: 286,
      width: 82,
      height: 42,
    });

    await user.click(
      await screen.findByRole("button", {
        name: "Start tour",
      }),
    );

    await screen.findByRole("heading", {
      name: "This sidebar is your main map",
    });

    const sidebarDialog = screen.getByRole("dialog");
    expect(sidebarDialog.className).toContain("tour-coachmark--mobile-sheet");
    expect(sidebarDialog.getAttribute("style")).toContain("top: auto");
    expect(sidebarDialog.getAttribute("style")).toContain("max-height:");

    await user.click(screen.getByRole("button", { name: "Continue" }));

    await screen.findByRole("heading", {
      name: "The topbar keeps route context close",
    });

    await waitFor(() => {
      const spotlight = document.querySelector<HTMLElement>(".tour-spotlight");
      expect(spotlight).not.toBeNull();
      const style = spotlight?.getAttribute("style") ?? "";
      const left = Number(style.match(/left: ([0-9.]+)px/)?.[1] ?? Number.NaN);
      const top = Number(style.match(/top: ([0-9.]+)px/)?.[1] ?? Number.NaN);
      expect(Number.isFinite(left)).toBe(true);
      expect(Number.isFinite(top)).toBe(true);
      expect(left).toBeGreaterThan(240);
      expect(top).toBeLessThan(24);
    });
  });
});
