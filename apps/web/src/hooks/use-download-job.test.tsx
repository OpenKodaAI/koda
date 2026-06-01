import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "@/hooks/use-toast";
import { useDownloadJob } from "@/hooks/use-download-job";
import { translateForLanguage } from "@/lib/i18n";

type FetchMock = ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  } as unknown as Response;
}

function mountHooks() {
  return renderHook(
    () => ({ download: useDownloadJob(), toast: useToast() }),
    {
      wrapper: ({ children }) => <ToastProvider>{children}</ToastProvider>,
    },
  );
}

describe("useDownloadJob", () => {
  let fetchMock: FetchMock;

  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("opens a sticky toast on start and morphs to success on completion", async () => {
    fetchMock
      // POST /start → returns running job
      .mockResolvedValueOnce(
        jsonResponse({
          id: "job-1",
          provider_id: "kokoro",
          asset_id: "model",
          status: "running",
          downloaded_bytes: 0,
          total_bytes: 1000,
          progress_percent: 0,
        }),
      )
      // first poll → still running, partial progress
      .mockResolvedValueOnce(
        jsonResponse({
          id: "job-1",
          provider_id: "kokoro",
          asset_id: "model",
          status: "running",
          downloaded_bytes: 500,
          total_bytes: 1000,
          progress_percent: 50,
        }),
      )
      // second poll → completed
      .mockResolvedValueOnce(
        jsonResponse({
          id: "job-1",
          provider_id: "kokoro",
          asset_id: "model",
          status: "completed",
          downloaded_bytes: 1000,
          total_bytes: 1000,
          progress_percent: 100,
        }),
      );

    const { result } = mountHooks();

    await act(async () => {
      await result.current.download.start({
        providerId: "kokoro",
        assetKey: "model",
        startEndpoint: "/api/start",
        toastTitle: "Baixando modelo Kokoro",
        successMessage: "Modelo Kokoro pronto.",
      });
    });

    // Sticky toast is up.
    expect(result.current.toast.toasts).toHaveLength(1);
    expect(result.current.toast.toasts[0].persistent).toBe(true);
    expect(result.current.toast.toasts[0].title).toBe("Baixando modelo Kokoro");

    // Advance to first poll → progress updates.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    expect(result.current.toast.toasts[0].progress).toEqual({
      downloaded: 500,
      total: 1000,
    });

    // Second poll → completed.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    expect(result.current.toast.toasts[0].type).toBe("success");
    expect(result.current.toast.toasts[0].persistent).toBe(false);
    expect(result.current.toast.toasts[0].message).toBe("Modelo Kokoro pronto.");
  });

  it("morphs to error toast when the job fails", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          id: "job-2",
          provider_id: "whispercpp",
          asset_id: "large-v3-turbo-q5_0",
          status: "running",
          downloaded_bytes: 0,
          total_bytes: 0,
          progress_percent: 0,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: "job-2",
          provider_id: "whispercpp",
          asset_id: "large-v3-turbo-q5_0",
          status: "error",
          downloaded_bytes: 0,
          total_bytes: 0,
          progress_percent: 0,
          details: { last_error: "404 not found" },
        }),
      );

    const { result } = mountHooks();

    await act(async () => {
      await result.current.download.start({
        providerId: "whispercpp",
        assetKey: "large-v3-turbo-q5_0",
        startEndpoint: "/api/start",
        toastTitle: "Baixando Whisper",
        successMessage: "Whisper pronto.",
      });
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });

    expect(result.current.toast.toasts[0].type).toBe("error");
    expect(result.current.toast.toasts[0].message).toBe("404 not found");
    expect(result.current.toast.toasts[0].persistent).toBe(false);
  });

  it("cancels an active download from the toast action", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          id: "job-5",
          provider_id: "kokoro",
          asset_id: "model",
          status: "running",
          downloaded_bytes: 0,
          total_bytes: 1000,
          progress_percent: 0,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: "job-5",
          provider_id: "kokoro",
          asset_id: "model",
          status: "cancelled",
          downloaded_bytes: 100,
          total_bytes: 1000,
          progress_percent: 10,
          details: { message: "Download cancelado." },
        }),
      );

    const { result } = mountHooks();

    await act(async () => {
      await result.current.download.start({
        providerId: "kokoro",
        assetKey: "model",
        startEndpoint: "/api/start",
        toastTitle: "Baixando modelo Kokoro",
        successMessage: "Modelo Kokoro pronto.",
      });
    });

    const action = result.current.toast.toasts[0].action;
    expect(action?.label).toBe(translateForLanguage("en-US", "downloads.cancelAction"));

    await act(async () => {
      action?.onClick();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/control-plane/providers/kokoro/downloads/job-5/cancel",
      {
        method: "POST",
        credentials: "same-origin",
      },
    );
    expect(result.current.toast.toasts[0].type).toBe("info");
    expect(result.current.toast.toasts[0].message).toBe(translateForLanguage("en-US", "downloads.canceled"));
    expect(result.current.toast.toasts[0].persistent).toBe(false);
    expect(result.current.toast.toasts[0].action).toBeUndefined();
  });

  it("treats a cancelled poll response as cancellation, not failure", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          id: "job-6",
          provider_id: "embedding",
          asset_id: "minilm-l6-v2",
          status: "running",
          downloaded_bytes: 0,
          total_bytes: 1000,
          progress_percent: 0,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: "job-6",
          provider_id: "embedding",
          asset_id: "minilm-l6-v2",
          status: "cancelled",
          downloaded_bytes: 250,
          total_bytes: 1000,
          progress_percent: 25,
          message: "Download cancelado.",
        }),
      );

    const { result } = mountHooks();

    await act(async () => {
      await result.current.download.start({
        providerId: "embedding",
        assetKey: "minilm-l6-v2",
        startEndpoint: "/api/start",
        toastTitle: "Baixando MiniLM",
        successMessage: "MiniLM pronto.",
      });
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });

    expect(result.current.toast.toasts[0].type).toBe("info");
    expect(result.current.toast.toasts[0].message).toBe("Download cancelado.");
    expect(result.current.toast.toasts[0].persistent).toBe(false);
    expect(result.current.toast.toasts[0].action).toBeUndefined();
  });

  it("keeps the toast persistent and surfaces a connection-loss message after repeated failures", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          id: "job-3",
          provider_id: "kokoro",
          asset_id: "model",
          status: "running",
          downloaded_bytes: 100,
          total_bytes: 1000,
          progress_percent: 10,
        }),
      )
      // Three polling attempts that all fail with network errors.
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"));

    const { result } = mountHooks();

    await act(async () => {
      await result.current.download.start({
        providerId: "kokoro",
        assetKey: "model",
        startEndpoint: "/api/start",
        toastTitle: "Baixando modelo Kokoro",
        successMessage: "Modelo Kokoro pronto.",
      });
    });

    // First poll fails.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    // Second failure → backoff to 2000ms.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    // Third failure → backoff to 4000ms; here we cross the 3-failure threshold.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4100);
    });

    expect(result.current.toast.toasts[0].persistent).toBe(true);
    expect(result.current.toast.toasts[0].message).toBe(
      translateForLanguage("en-US", "downloads.reconnecting"),
    );
  });

  it("short-circuits to success when the start endpoint returns an already-completed job", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "job-4",
        provider_id: "kokoro",
        asset_id: "model",
        status: "completed",
        downloaded_bytes: 100,
        total_bytes: 100,
        progress_percent: 100,
      }),
    );

    const onComplete = vi.fn();
    const { result } = mountHooks();

    await act(async () => {
      await result.current.download.start({
        providerId: "kokoro",
        assetKey: "model",
        startEndpoint: "/api/start",
        toastTitle: "Baixando modelo Kokoro",
        successMessage: "Já estava aqui.",
        onComplete,
      });
    });

    expect(result.current.toast.toasts[0].type).toBe("success");
    expect(result.current.toast.toasts[0].message).toBe("Já estava aqui.");
    expect(onComplete).toHaveBeenCalledOnce();
  });
});
