"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { AsyncActionButton } from "@/components/ui/async-feedback";

interface SaveBarProps {
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  onDiscard?: () => void;
}

export function SaveBar({ dirty, saving, onSave, onDiscard }: SaveBarProps) {
  const { t } = useAppI18n();
  const [showSuccess, setShowSuccess] = useState(false);
  const wasSavingRef = useRef(saving);

  // Flash success when saving completes
  useEffect(() => {
    const saveCompleted = wasSavingRef.current && !saving && !dirty;
    wasSavingRef.current = saving;

    if (saveCompleted) {
      const showTimer = window.setTimeout(() => setShowSuccess(true), 0);
      const hideTimer = window.setTimeout(() => setShowSuccess(false), 2000);
      return () => {
        window.clearTimeout(showTimer);
        window.clearTimeout(hideTimer);
      };
    }

    const resetTimer = window.setTimeout(() => setShowSuccess(false), 0);
    return () => window.clearTimeout(resetTimer);
  }, [saving, dirty]);

  return (
    <AnimatePresence>
      {(dirty || showSuccess) && (
        <motion.div
          initial={{ y: 60, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 60, opacity: 0 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex items-end justify-center px-4 pb-4 sm:px-5 sm:pb-5 lg:pl-[calc(var(--shell-sidebar-width)+1.5rem)] lg:pr-6"
          style={{ bottom: "var(--editor-footer-offset, 0px)" }}
        >
          <div
            className="pointer-events-auto flex w-full max-w-[680px] items-center gap-4 rounded-2xl border px-5 py-3.5 transition-colors duration-500"
            style={{
              borderColor: showSuccess
                ? "var(--tone-success-border)"
                : "var(--border-subtle)",
              backgroundColor: "rgba(10, 10, 11, 0.82)",
              backdropFilter: "blur(20px) saturate(1.05)",
              boxShadow: showSuccess
                ? "0 10px 40px rgba(77, 137, 100, 0.12), 0 0 0 1px rgba(255,255,255,0.02)"
                : "0 18px 44px rgba(0,0,0,0.34), 0 0 0 1px rgba(255,255,255,0.02)",
            }}
          >
            {showSuccess ? (
              <span className="flex items-center gap-2 text-sm text-[var(--tone-success-text)]">
                <Check size={16} />
                {t("controlPlane.shared.saveBar.saved", { defaultValue: "Saved successfully" })}
              </span>
            ) : (
              <>
                <span className="text-sm text-[var(--tone-warning-text)]">
                  {t("controlPlane.shared.saveBar.unsaved", { defaultValue: "Unsaved changes" })}
                </span>

                <div className="flex items-center gap-2">
                  {onDiscard && (
                    <AsyncActionButton
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={onDiscard}
                      disabled={saving}
                    >
                      {t("controlPlane.shared.saveBar.discard", { defaultValue: "Discard" })}
                    </AsyncActionButton>
                  )}

                  <AsyncActionButton
                    type="button"
                    variant="primary"
                    size="sm"
                    onClick={onSave}
                    loading={saving}
                    loadingLabel={t("controlPlane.shared.saveBar.saving", { defaultValue: "Saving" })}
                  >
                    {t("common.save")}
                  </AsyncActionButton>
                </div>
              </>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
