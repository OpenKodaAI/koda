"use client";

import { useEffect } from "react";

const KODA_CONSOLE_FLAG = "__kodaConsoleSignatureShown";

declare global {
  interface Window {
    [KODA_CONSOLE_FLAG]?: boolean;
  }
}

export function ConsoleSignature() {
  useEffect(() => {
    if (typeof window === "undefined" || window[KODA_CONSOLE_FLAG]) {
      return;
    }
    if (typeof console === "undefined" || typeof console.log !== "function") {
      return;
    }

    window[KODA_CONSOLE_FLAG] = true;

    console.log(
      "%cKODA%c  operational workspace for agent systems",
      [
        "color:#f5f5f5",
        "font-family:-apple-system,BlinkMacSystemFont,Inter,Segoe UI,sans-serif",
        "font-size:28px",
        "font-weight:600",
        "letter-spacing:.12em",
      ].join(";"),
      [
        "color:#9a9a9a",
        "font-family:JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, monospace",
        "font-size:12px",
        "letter-spacing:.02em",
      ].join(";"),
    );
  }, []);

  return null;
}
