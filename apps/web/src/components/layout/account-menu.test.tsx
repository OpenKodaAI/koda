import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccountMenu } from "@/components/layout/account-menu";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { OPERATOR_AVATAR_STORAGE_KEY } from "@/components/ui/avatar-picker";

const authMock = vi.hoisted(() => ({
  value: {
    operator: {
      id: "op_1",
      email: "owner@koda.dev",
      username: "owner",
      display_name: "Owner",
      profile_photo_url: null as string | null,
      profile_photo_hash: null as string | null,
    },
    isAuthenticated: true,
    signOut: vi.fn(),
    updateOperator: vi.fn(),
  },
}));

vi.mock("@/components/providers/auth-provider", () => ({
  useOptionalAuth: () => authMock.value,
}));

function renderMenu() {
  return render(
    <I18nProvider initialLanguage="en-US">
      <AccountMenu />
    </I18nProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  authMock.value.operator = {
    id: "op_1",
    email: "owner@koda.dev",
    username: "owner",
    display_name: "Owner",
    profile_photo_url: null,
    profile_photo_hash: null,
  };
});

describe("AccountMenu", () => {
  it("uses the selected colored avatar when the operator has no profile photo", () => {
    window.localStorage.setItem(OPERATOR_AVATAR_STORAGE_KEY, "mint");
    renderMenu();

    expect(
      within(screen.getByTestId("account-menu-trigger")).getByRole("img", {
        name: "Mint animated avatar",
      }),
    ).toBeInTheDocument();
  });

  it("renders the persisted profile photo when available", () => {
    authMock.value.operator.profile_photo_url = "/api/control-plane/auth/profile/photo?v=abc123";

    renderMenu();

    const image = screen.getByTestId("account-menu-trigger").querySelector("img");
    expect(image).toHaveAttribute("src", "/api/control-plane/auth/profile/photo?v=abc123");
  });
});
