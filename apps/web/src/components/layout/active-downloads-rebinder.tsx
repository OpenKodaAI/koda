"use client";

import { useActiveDownloads } from "@/hooks/use-active-downloads";

/**
 * Side-effect-only component mounted next to `<ToastNotification />`.
 *
 * On mount, queries the backend for any download jobs still running
 * server-side and reattaches sticky toasts to them. Without this, a hard
 * refresh during a long Whisper download would lose the progress toast even
 * though the download itself keeps running on the server.
 */
export function ActiveDownloadsRebinder() {
  useActiveDownloads();
  return null;
}
