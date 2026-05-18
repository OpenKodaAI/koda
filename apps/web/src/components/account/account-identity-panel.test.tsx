import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AccountIdentityPanel } from "@/components/account/account-identity-panel";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { OPERATOR_AVATAR_STORAGE_KEY, avatarOptions } from "@/components/ui/avatar-picker";
import { ToastNotification } from "@/components/ui/toast-notification";
import { ToastProvider } from "@/hooks/use-toast";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

const authMock = vi.hoisted(() => {
  const signOut = vi.fn();
  const updateOperator = vi.fn();
  const baseOperator = {
    id: "op_1",
    email: "owner@koda.dev",
    username: "owner",
    display_name: "Owner",
    profile_photo_url: null,
    profile_photo_hash: null,
  };
  return {
    signOut,
    updateOperator,
    baseOperator,
    value: {
      operator: { ...baseOperator },
      isAuthenticated: true,
      signOut,
      updateOperator,
    },
  };
});

vi.mock("@/components/providers/auth-provider", () => ({
  useOptionalAuth: () => authMock.value,
}));

function renderPanel() {
  return render(
    <I18nProvider initialLanguage="en-US">
      <ToastProvider>
        <AccountIdentityPanel />
        <ToastNotification />
      </ToastProvider>
    </I18nProvider>,
  );
}

function jsonResponse(data: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(data), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
}

beforeEach(() => {
  authMock.signOut.mockReset();
  authMock.updateOperator.mockReset();
  authMock.value.operator = { ...authMock.baseOperator };
  fetchMock.mockReset();
  window.localStorage.clear();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("AccountIdentityPanel", () => {
  it("renders operator profile data with photo controls and color avatars", () => {
    renderPanel();

    expect(screen.getByLabelText("Choose profile photo")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Owner")).toBeInTheDocument();
    expect(screen.getByText("owner@koda.dev")).toBeInTheDocument();
    expect(screen.getByText("owner")).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(avatarOptions.length);
    expect(screen.getByRole("radio", { name: "Select Ember" })).toHaveAttribute("aria-checked", "true");
  });

  it("keeps the local colored avatar picker as an image fallback", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("radio", { name: "Select Mint" }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(OPERATOR_AVATAR_STORAGE_KEY)).toBe("mint");
    expect(await screen.findByText("Avatar atualizado.")).toBeInTheDocument();
  });

  it("updates the display name through the profile API", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        operator: {
          ...authMock.baseOperator,
          display_name: "Avery Stone",
        },
      }),
    );
    renderPanel();

    const input = screen.getByLabelText("Display name");
    await user.clear(input);
    await user.type(input, "Avery Stone");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/control-plane/auth/profile",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ display_name: "Avery Stone" }),
      }),
    );
    expect(authMock.updateOperator).toHaveBeenCalledWith(
      expect.objectContaining({ display_name: "Avery Stone" }),
    );
    expect(await screen.findByText("Nome atualizado.")).toBeInTheDocument();
  });

  it("blocks invalid display names before making a request", async () => {
    const user = userEvent.setup();
    renderPanel();

    const input = screen.getByLabelText("Display name");
    await user.clear(input);
    await user.type(input, "   ");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(await screen.findByText("Display name is required.")).toBeInTheDocument();
    expect(await screen.findByText("Informe um nome de exibição válido.")).toBeInTheDocument();
  });

  it("removes the persisted profile photo", async () => {
    const user = userEvent.setup();
    authMock.value.operator = {
      ...authMock.baseOperator,
      profile_photo_url: "/api/control-plane/auth/profile/photo?v=abc123",
      profile_photo_hash: "abc123",
    };
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        removed: true,
        operator: { ...authMock.baseOperator },
      }),
    );
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove profile photo" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/control-plane/auth/profile/photo",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(authMock.updateOperator).toHaveBeenCalledWith(
      expect.objectContaining({ profile_photo_hash: null }),
    );
    expect(await screen.findByText("Foto removida.")).toBeInTheDocument();
  });

  it("uploads a cropped profile photo", async () => {
    const user = userEvent.setup();
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:profile");
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    Object.defineProperty(HTMLImageElement.prototype, "decode", {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    });
    Object.defineProperty(HTMLImageElement.prototype, "naturalWidth", { configurable: true, get: () => 80 });
    Object.defineProperty(HTMLImageElement.prototype, "naturalHeight", { configurable: true, get: () => 80 });
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
      save: vi.fn(),
      fillRect: vi.fn(),
      drawImage: vi.fn(),
      restore: vi.fn(),
      imageSmoothingEnabled: true,
      imageSmoothingQuality: "high",
      fillStyle: "#000",
    })) as unknown as HTMLCanvasElement["getContext"];
    HTMLCanvasElement.prototype.toBlob = vi.fn((callback: BlobCallback) => {
      callback(new Blob(["jpeg"], { type: "image/jpeg" }));
    }) as unknown as HTMLCanvasElement["toBlob"];
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        photoUrl: "/api/control-plane/auth/profile/photo?v=abc123",
        photoHash: "abc123",
        byteSize: 4,
        operator: {
          ...authMock.baseOperator,
          profile_photo_url: "/api/control-plane/auth/profile/photo?v=abc123",
          profile_photo_hash: "abc123",
        },
      }),
    );
    const { container } = renderPanel();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(input, new File(["image"], "profile.png", { type: "image/png" }));
    const saveButtons = screen.getAllByRole("button", { name: "Save" });
    await user.click(saveButtons[0]);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/control-plane/auth/profile/photo",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData),
      }),
    );
    expect(authMock.updateOperator).toHaveBeenCalledWith(
      expect.objectContaining({ profile_photo_hash: "abc123" }),
    );
    expect(await screen.findByText("Foto atualizada.")).toBeInTheDocument();

    createObjectUrl.mockRestore();
    revokeObjectUrl.mockRestore();
  });

  it("shows busy feedback while a profile photo upload is in flight", async () => {
    const user = userEvent.setup();
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:profile");
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    let resolveUpload: (response: Response) => void = () => {};
    Object.defineProperty(HTMLImageElement.prototype, "decode", {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    });
    Object.defineProperty(HTMLImageElement.prototype, "naturalWidth", { configurable: true, get: () => 80 });
    Object.defineProperty(HTMLImageElement.prototype, "naturalHeight", { configurable: true, get: () => 80 });
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
      save: vi.fn(),
      fillRect: vi.fn(),
      drawImage: vi.fn(),
      restore: vi.fn(),
      imageSmoothingEnabled: true,
      imageSmoothingQuality: "high",
      fillStyle: "#000",
    })) as unknown as HTMLCanvasElement["getContext"];
    HTMLCanvasElement.prototype.toBlob = vi.fn((callback: BlobCallback) => {
      callback(new Blob(["jpeg"], { type: "image/jpeg" }));
    }) as unknown as HTMLCanvasElement["toBlob"];
    fetchMock.mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        resolveUpload = resolve;
      }),
    );
    const { container } = renderPanel();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(input, new File(["image"], "profile.png", { type: "image/png" }));
    await user.click(screen.getAllByRole("button", { name: "Save" })[0]);

    const busySave = await screen.findByRole("button", { name: /^(Preparing|Saving) profile photo$/ });
    expect(busySave).toHaveAttribute("aria-busy", "true");
    expect(busySave).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(/profile photo/i);
    expect(screen.getByLabelText("Zoom")).toBeDisabled();

    resolveUpload(
      jsonResponse({
        ok: true,
        photoUrl: "/api/control-plane/auth/profile/photo?v=abc123",
        photoHash: "abc123",
        byteSize: 4,
        operator: {
          ...authMock.baseOperator,
          profile_photo_url: "/api/control-plane/auth/profile/photo?v=abc123",
          profile_photo_hash: "abc123",
        },
      }),
    );

    await waitFor(() => expect(authMock.updateOperator).toHaveBeenCalledWith(expect.objectContaining({ profile_photo_hash: "abc123" })));

    createObjectUrl.mockRestore();
    revokeObjectUrl.mockRestore();
  });

  it("uses the authenticated sign-out action", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Sign out" }));

    expect(authMock.signOut).toHaveBeenCalledTimes(1);
  });
});
