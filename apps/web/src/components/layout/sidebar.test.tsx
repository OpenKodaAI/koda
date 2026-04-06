import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/layout/sidebar";
import { isSidebarItemActive, type SidebarNavItem } from "@/components/layout/sidebar-nav";
import { AppTourProvider } from "@/components/providers/app-tour-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";

const prefetchMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    prefetch,
    scroll,
    ...props
  }: { href: string; children: ReactNode } & Record<string, unknown>) => {
    void prefetch;
    void scroll;

    return (
      <a href={href} {...props}>
        {children}
      </a>
    );
  },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/control-plane/system",
  useRouter: () => ({ prefetch: prefetchMock }),
}));

describe("Sidebar", () => {
  beforeEach(() => {
    prefetchMock.mockReset();
    if (typeof window.localStorage?.clear === "function") {
      window.localStorage.clear();
    } else if (typeof window.localStorage?.removeItem === "function") {
      window.localStorage.removeItem("atlas.locale");
    }
  });

  it("renders general settings as a separated footer navigation item", () => {
    render(
      <I18nProvider initialLanguage="pt-BR">
        <AppTourProvider
          pathname="/control-plane/system"
          mobileNavOpen={false}
          onMobileNavOpenChange={() => {}}
        >
          <Sidebar mobileOpen={false} onMobileOpenChange={() => {}} collapsed={false} />
        </AppTourProvider>
      </I18nProvider>,
    );

    expect(screen.getByRole("link", { name: /Configurações gerais/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Agentes/i })).toBeInTheDocument();
  });

  it("does not keep Agents active when General settings is selected", () => {
    const agentsItem: SidebarNavItem = {
      href: "/control-plane",
      label: "Agentes",
      icon: (() => null) as SidebarNavItem["icon"],
      kind: "primary",
      freshnessTier: "catalog",
      prefetchStrategy: "intent",
      loadingLabel: "Carregando agentes",
      match: "startsWith",
    };

    const generalSettingsItem: SidebarNavItem = {
      href: "/control-plane/system",
      label: "Configurações gerais",
      icon: (() => null) as SidebarNavItem["icon"],
      kind: "footer",
      freshnessTier: "catalog",
      prefetchStrategy: "intent",
      loadingLabel: "Carregando configurações",
      match: "startsWith",
    };

    expect(isSidebarItemActive("/control-plane/system", agentsItem)).toBe(false);
    expect(isSidebarItemActive("/control-plane/system", generalSettingsItem)).toBe(true);
  });

  it("prefetches heavy routes on intent and shows pending feedback on click", () => {
    vi.useFakeTimers();

    render(
      <I18nProvider initialLanguage="pt-BR">
        <AppTourProvider
          pathname="/control-plane/system"
          mobileNavOpen={false}
          onMobileNavOpenChange={() => {}}
        >
          <Sidebar mobileOpen={false} onMobileOpenChange={() => {}} collapsed={false} />
        </AppTourProvider>
      </I18nProvider>,
    );

    const agentsLink = screen.getByRole("link", { name: /Agentes/i });
    fireEvent.mouseEnter(agentsLink);

    vi.advanceTimersByTime(150);

    expect(prefetchMock).toHaveBeenCalledWith("/control-plane");

    const homeLink = screen.getByRole("link", { name: /Início/i });
    fireEvent.click(homeLink);

    expect(homeLink).toHaveAttribute("aria-busy", "true");

    vi.useRealTimers();
  });

  it("hides section labels when the sidebar is collapsed", () => {
    render(
      <I18nProvider initialLanguage="pt-BR">
        <AppTourProvider
          pathname="/control-plane/system"
          mobileNavOpen={false}
          onMobileNavOpenChange={() => {}}
        >
          <Sidebar mobileOpen={false} onMobileOpenChange={() => {}} collapsed />
        </AppTourProvider>
      </I18nProvider>,
    );

    expect(screen.queryByText("Operação")).not.toBeInTheDocument();
    expect(screen.queryByText("Análise")).not.toBeInTheDocument();
    expect(screen.queryByText("Sistema")).not.toBeInTheDocument();
  });
});
