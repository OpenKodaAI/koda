"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { SetupFrame } from "@/components/setup/setup-frame";
import { StepCreateAccount, type RegisterOwnerResponse } from "@/components/setup/step-create-account";
import { StepRecoveryCodes } from "@/components/setup/step-recovery-codes";
import type { ControlPlaneAuthStatus } from "@/lib/control-plane";
import { requestJson } from "@/lib/http-client";

export interface SetupScreenProps {
  authStatus: ControlPlaneAuthStatus | null;
}

// Short-lived session-scoped cache so the operator can survive an accidental F5
// on the recovery-codes screen without losing the one-time plaintext. Clears on
// explicit acknowledgement and is tab-scoped (sessionStorage).
const RECOVERY_CODES_STORAGE_KEY = "koda.setup.pending_recovery_codes.v1";
const RECOVERY_CODES_EXPIRES_MS = 1000 * 60 * 15;

type StoredRecovery = {
  codes: string[];
  storedAt: number;
};

function parseStoredRecoveryCodes(raw: string | null): string[] | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as StoredRecovery;
    if (!parsed || !Array.isArray(parsed.codes) || typeof parsed.storedAt !== "number") return null;
    return parsed.codes.length > 0 ? parsed.codes : null;
  } catch {
    return null;
  }
}

function storedRecoveryIsFresh(raw: string | null, nowMs: number): boolean {
  if (!raw) return false;
  try {
    const parsed = JSON.parse(raw) as StoredRecovery;
    if (typeof parsed?.storedAt !== "number") return false;
    return nowMs - parsed.storedAt <= RECOVERY_CODES_EXPIRES_MS;
  } catch {
    return false;
  }
}

function writeStoredRecoveryCodes(codes: string[]) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      RECOVERY_CODES_STORAGE_KEY,
      JSON.stringify({ codes, storedAt: Date.now() } satisfies StoredRecovery),
    );
  } catch {
    // Best-effort — ignore quota or incognito failures.
  }
}

function clearStoredRecoveryCodes() {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(RECOVERY_CODES_STORAGE_KEY);
  } catch {
    // Best-effort.
  }
}

function subscribeToRecoveryStorage(notify: () => void) {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener("storage", notify);
  return () => window.removeEventListener("storage", notify);
}

// useSyncExternalStore requires snapshot identity stability between calls when
// the underlying data hasn't changed. We return the raw JSON string so that
// identical payloads compare equal, then parse in a useMemo in the component.
function recoveryCodesRawSnapshot(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(RECOVERY_CODES_STORAGE_KEY);
  } catch {
    return null;
  }
}

function recoveryCodesServerSnapshot(): string | null {
  return null;
}

export function SetupScreen({ authStatus }: SetupScreenProps) {
  const router = useRouter();
  const persistedRaw = useSyncExternalStore(
    subscribeToRecoveryStorage,
    recoveryCodesRawSnapshot,
    recoveryCodesServerSnapshot,
  );
  const persisted = useMemo<string[] | null>(() => parseStoredRecoveryCodes(persistedRaw), [persistedRaw]);
  // Clean up stale entries on mount (beyond the 15-minute window). This runs
  // after render so Date.now() is not called during the pure render phase.
  useEffect(() => {
    const raw = recoveryCodesRawSnapshot();
    if (raw && !storedRecoveryIsFresh(raw, Date.now())) {
      clearStoredRecoveryCodes();
    }
  }, []);
  const [localRecoveryCodes, setLocalRecoveryCodes] = useState<string[] | null>(null);
  const recoveryCodes = localRecoveryCodes ?? persisted;
  const loopbackTrustEnabled = Boolean(authStatus?.loopback_trust_enabled);
  const bootstrapFilePath = authStatus?.bootstrap_file_path || null;

  // Warn the operator before they reload / close the tab while unconfirmed
  // recovery codes are on screen.
  useEffect(() => {
    if (!recoveryCodes || recoveryCodes.length === 0) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
      return "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [recoveryCodes]);

  const handleRegistered = useCallback((result: RegisterOwnerResponse) => {
    const codes = result.recovery_codes || [];
    writeStoredRecoveryCodes(codes);
    setLocalRecoveryCodes(codes);
  }, []);

  const handleRecoveryConfirmed = useCallback(async () => {
    clearStoredRecoveryCodes();
    setLocalRecoveryCodes(null);
    try {
      await requestJson("/api/control-plane/auth/recovery-codes/acknowledge", {
        method: "POST",
        body: "{}",
      });
    } catch {
      // Best-effort — the cookie will expire on its own if the POST failed.
    }
    router.replace("/");
    router.refresh();
  }, [router]);

  return (
    <SetupFrame>
      <div
        key={recoveryCodes === null ? "create" : "recovery"}
        className="animate-in fade-in slide-in-from-bottom-2 duration-[280ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
      >
        {recoveryCodes === null ? (
          <StepCreateAccount
            loopbackTrustEnabled={loopbackTrustEnabled}
            bootstrapFilePath={bootstrapFilePath}
            onRegistered={handleRegistered}
          />
        ) : (
          <StepRecoveryCodes codes={recoveryCodes} onConfirmed={handleRecoveryConfirmed} />
        )}
      </div>
    </SetupFrame>
  );
}
