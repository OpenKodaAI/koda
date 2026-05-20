"use client";

import { useState } from "react";
import { Plus, Trash2, Edit3, ChevronDown, ChevronUp } from "lucide-react";
import { InlineSpinner } from "@/components/ui/async-feedback";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface CollectionManagerProps {
  label: string;
  items: Array<Record<string, unknown>>;
  onSave: (items: Array<Record<string, unknown>>) => void;
  onDelete: (id: number) => void;
  busy: boolean;
  busyKey: string | null;
  busyPrefix: string;
  getItemLabel: (item: Record<string, unknown>) => string;
  getItemId: (item: Record<string, unknown>) => number;
}

export function CollectionManager({
  label,
  items,
  onSave,
  onDelete,
  busy,
  busyKey,
  busyPrefix,
  getItemLabel,
  getItemId,
}: CollectionManagerProps) {
  const { t } = useAppI18n();
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [addMode, setAddMode] = useState(false);
  const [newItemJson, setNewItemJson] = useState("{\n  \n}");
  const [editJsonMap, setEditJsonMap] = useState<Record<number, string>>({});
  const [showAllJson, setShowAllJson] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleExpand = (id: number) => {
    if (expandedId === id) {
      setExpandedId(null);
    } else {
      setExpandedId(id);
      // Initialize edit JSON for this item if not already set
      const item = items.find((i) => getItemId(i) === id);
      if (item && !editJsonMap[id]) {
        setEditJsonMap((prev) => ({
          ...prev,
          [id]: JSON.stringify(item, null, 2),
        }));
      }
    }
  };

  const handleAddSave = () => {
    setError(null);
    try {
      const parsed = JSON.parse(newItemJson.trim());
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        setError(t("generated.controlPlane.value_must_be_a_json_object_093e2ad3"));
        return;
      }
      onSave([...items, parsed as Record<string, unknown>]);
      setNewItemJson("{\n  \n}");
      setAddMode(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("generated.controlPlane.invalid_json_9abee6af"));
    }
  };

  const handleAddCancel = () => {
    setAddMode(false);
    setNewItemJson("{\n  \n}");
    setError(null);
  };

  const handleEditSave = (id: number) => {
    setError(null);
    const json = editJsonMap[id];
    if (!json) return;

    try {
      const parsed = JSON.parse(json.trim());
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        setError(t("generated.controlPlane.value_must_be_a_json_object_093e2ad3"));
        return;
      }
      const updated = items.map((item) =>
        getItemId(item) === id ? (parsed as Record<string, unknown>) : item,
      );
      onSave(updated);
      setExpandedId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("generated.controlPlane.invalid_json_9abee6af"));
    }
  };

  const isBusyFor = (id: number) =>
    busy && busyKey === `${busyPrefix}:${id}`;

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="eyebrow">{label}</span>
        <span className="text-xs text-[var(--text-quaternary)]">
          {t("generated.controlPlane.count_item_s_6ee20be0", { count: items.length })}
        </span>
      </div>

      {/* Item list */}
      <div className="flex flex-col gap-2">
        {items.map((item) => {
          const id = getItemId(item);
          const isExpanded = expandedId === id;
          const itemBusy = isBusyFor(id);

          return (
            <div
              key={id}
              className="glass-card-sm overflow-hidden"
            >
              {/* Item header */}
              <div className="flex items-center gap-3 px-4 py-3">
                <span className="flex-1 text-sm text-[var(--text-primary)] font-medium truncate">
                  {getItemLabel(item)}
                </span>

                <button
                  type="button"
                  onClick={() => toggleExpand(id)}
                  className="shrink-0 p-1 text-[var(--text-quaternary)] hover:text-[var(--text-secondary)] transition-colors"
                  aria-label={isExpanded ? t("generated.controlPlane.collapse_aa817030") : t("generated.controlPlane.expand_9e31313d")}
                >
                  {isExpanded ? (
                    <ChevronUp size={14} />
                  ) : (
                    <ChevronDown size={14} />
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => onDelete(id)}
                  disabled={itemBusy || busy}
                  className="shrink-0 p-1 text-[var(--text-quaternary)] hover:text-[var(--tone-danger-dot)] transition-colors disabled:opacity-40"
                  aria-label={t("generated.controlPlane.delete_c4aab121")}
                >
                  <Trash2 size={14} />
                </button>
              </div>

              {/* Expanded edit view */}
              {isExpanded && (
                <div className="border-t border-[var(--border-subtle)] px-4 py-3 flex flex-col gap-3">
                  <textarea
                    value={editJsonMap[id] ?? JSON.stringify(item, null, 2)}
                    onChange={(e) =>
                      setEditJsonMap((prev) => ({
                        ...prev,
                        [id]: e.target.value,
                      }))
                    }
                    className="field-shell resize-y min-h-[160px] font-mono text-xs text-[var(--text-primary)]"
                    spellCheck={false}
                  />
                  {error && expandedId === id && (
                    <p className="text-xs text-[var(--tone-danger-text)]">
                      {error}
                    </p>
                  )}
                  <div className="flex items-center gap-2 justify-end">
                    <button
                      type="button"
                      onClick={() => setExpandedId(null)}
                      className="button-shell button-shell--secondary button-shell--sm"
                    >
                      <span>{t("generated.controlPlane.cancel_6b55a126")}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleEditSave(id)}
                      disabled={itemBusy}
                      aria-label={itemBusy ? t("generated.controlPlane.saving_97489820") : undefined}
                      aria-busy={itemBusy || undefined}
                      className="button-shell button-shell--primary button-shell--sm"
                    >
                      {itemBusy ? <InlineSpinner className="h-3.5 w-3.5" /> : <Edit3 size={12} />}
                      <span>{t("generated.controlPlane.save_b83e7d1a")}</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Add new item */}
      {addMode ? (
        <div className="glass-card-sm px-4 py-4 flex flex-col gap-3">
          <span className="eyebrow">{t("generated.controlPlane.new_item_7a05789b")}</span>
          <textarea
            value={newItemJson}
            onChange={(e) => setNewItemJson(e.target.value)}
            className="field-shell resize-y min-h-[160px] font-mono text-xs text-[var(--text-primary)]"
            spellCheck={false}
          />
          {error && !expandedId && (
            <p className="text-xs text-[var(--tone-danger-text)]">{error}</p>
          )}
          <div className="flex items-center gap-2 justify-end">
            <button
              type="button"
              onClick={handleAddCancel}
              className="button-shell button-shell--secondary button-shell--sm"
            >
              <span>{t("generated.controlPlane.cancel_6b55a126")}</span>
            </button>
            <button
              type="button"
              onClick={handleAddSave}
              disabled={busy}
              aria-label={busy ? t("generated.controlPlane.saving_97489820") : undefined}
              aria-busy={busy || undefined}
              className="button-shell button-shell--primary button-shell--sm"
            >
              {busy ? <InlineSpinner className="h-3.5 w-3.5" /> : null}
              <span>{t("generated.controlPlane.save_b83e7d1a")}</span>
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => {
            setAddMode(true);
            setError(null);
          }}
          disabled={busy}
          className="flex items-center justify-center gap-2 py-3 border border-dashed border-[var(--border-subtle)] text-sm text-[var(--text-quaternary)] hover:text-[var(--text-secondary)] hover:border-[var(--border-strong)] transition-colors disabled:opacity-40"
        >
          <Plus size={14} />
          <span>{t("generated.controlPlane.add_new_5de667ac")}</span>
        </button>
      )}

      {/* Collapsible raw JSON view */}
      <div className="mt-2">
        <button
          type="button"
          onClick={() => setShowAllJson((prev) => !prev)}
          className="flex items-center gap-1.5 text-xs text-[var(--text-quaternary)] hover:text-[var(--text-secondary)] transition-colors"
        >
          {showAllJson ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          <span>{t("generated.controlPlane.raw_json_count_items_b1b73e72", { count: items.length })}</span>
        </button>

        {showAllJson && (
          <textarea
            value={JSON.stringify(items, null, 2)}
            readOnly
            className="field-shell resize-y min-h-[200px] mt-2 font-mono text-xs text-[var(--text-primary)]"
            spellCheck={false}
          />
        )}
      </div>
    </div>
  );
}
