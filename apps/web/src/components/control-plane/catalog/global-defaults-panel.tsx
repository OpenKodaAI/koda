"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useToast } from "@/hooks/use-toast";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { prettyJson } from "@/lib/control-plane-editor";

async function requestJson(path: string, init: RequestInit = {}) {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      payload && typeof payload === "object" && "error" in payload
        ? String(payload.error)
        : `Request failed with status ${response.status}`,
    );
  }
  return payload;
}

interface GlobalDefaultsPanelProps {
  sections: Record<string, Record<string, unknown>>;
  version: number;
}

export function GlobalDefaultsPanel({
  sections,
  version,
}: GlobalDefaultsPanelProps) {
  const router = useRouter();
  const { showToast } = useToast();
  const { tl } = useAppI18n();

  const [expanded, setExpanded] = useState(false);
  const [json, setJson] = useState(() => prettyJson(sections));
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      const parsed = JSON.parse(json);
      await requestJson("/api/control-plane/global-defaults", {
        method: "PATCH",
        body: JSON.stringify({ sections: parsed }),
      });
      showToast(tl("Defaults globais salvos com sucesso."), "success");
      router.refresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao salvar defaults."),
        "error",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <button
        type="button"
        className="eyebrow flex items-center gap-2 py-2 w-full text-left hover:text-[var(--text-secondary)] transition-colors"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <ChevronRight
          className="h-3.5 w-3.5 transition-transform duration-200"
          style={{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)" }}
        />
        {tl("Defaults globais")} v{version}
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="pt-3 space-y-3">
              <textarea
                className="field-shell min-h-[360px] font-mono text-sm leading-relaxed"
                value={json}
                onChange={(e) => setJson(e.target.value)}
                spellCheck={false}
              />
              <div className="flex justify-end">
                <button
                  type="button"
                  className="button-shell button-shell--primary button-shell--sm"
                  disabled={saving}
                  onClick={handleSave}
                >
                  {saving ? tl("Salvando...") : tl("Salvar defaults")}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
