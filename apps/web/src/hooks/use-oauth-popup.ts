"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { requestJson } from "@/lib/http-client";

type OAuthPopupOptions = {
  agentId: string;
  onSuccess: () => void;
  onError: (error: string) => void;
};

type OAuthPopupReturn = {
  startOAuth: (connectionKey: string) => Promise<void>;
  isLoading: boolean;
  isPopupOpen: boolean;
};

export function useOAuthPopup({
  agentId,
  onSuccess,
  onError,
}: OAuthPopupOptions): OAuthPopupReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [isPopupOpen, setIsPopupOpen] = useState(false);
  const popupRef = useRef<Window | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Listen for postMessage from the popup callback page
  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type !== "koda:oauth:callback") return;

      setIsPopupOpen(false);
      setIsLoading(false);

      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }

      if (event.data.status === "success") {
        onSuccess();
      } else {
        onError(event.data.error || "OAuth failed");
      }
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [onSuccess, onError]);

  // Poll for popup closed (user cancelled)
  useEffect(() => {
    if (!isPopupOpen) return;

    const interval = setInterval(() => {
      if (popupRef.current && popupRef.current.closed) {
        setIsPopupOpen(false);
        setIsLoading(false);
        clearInterval(interval);
        // Only fire error if we haven't received a success message
        // (the message handler above handles success)
      }
    }, 500);

    return () => clearInterval(interval);
  }, [isPopupOpen]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (popupRef.current && !popupRef.current.closed) popupRef.current.close();
    };
  }, []);

  const startOAuth = useCallback(async (connectionKey: string) => {
    setIsLoading(true);

    try {
      const frontendCallbackUri = new URL("/oauth/callback", window.location.origin).toString();

      // Call backend to get authorization URL
      const response = await requestJson<{
        session_id: string;
        authorization_url: string;
      }>(
        `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(connectionKey)}/oauth/start`,
        {
          method: "POST",
          body: JSON.stringify({
            frontend_callback_uri: frontendCallbackUri,
            redirect_uri: frontendCallbackUri,
          }),
        },
      );

      // Open popup (600x700, centered)
      const width = 600;
      const height = 700;
      const left = Math.max(0, (window.screen.width - width) / 2);
      const top = Math.max(0, (window.screen.height - height) / 2);

      const popup = window.open(
        response.authorization_url,
        `koda-oauth:${connectionKey}`,
        `width=${width},height=${height},left=${left},top=${top},toolbar=no,menubar=no,scrollbars=yes,resizable=yes`,
      );

      if (!popup) {
        setIsLoading(false);
        onError("Popup blocked. Please allow popups for this site.");
        return;
      }

      popupRef.current = popup;
      setIsPopupOpen(true);

      // Timeout after 5 minutes
      timeoutRef.current = setTimeout(() => {
        if (popupRef.current && !popupRef.current.closed) {
          popupRef.current.close();
        }
        setIsPopupOpen(false);
        setIsLoading(false);
        onError("OAuth timeout — please try again.");
      }, 5 * 60 * 1000);
    } catch (err) {
      setIsLoading(false);
      onError(err instanceof Error ? err.message : "Failed to start OAuth flow");
    }
  }, [agentId, onError]);

  return { startOAuth, isLoading, isPopupOpen };
}
