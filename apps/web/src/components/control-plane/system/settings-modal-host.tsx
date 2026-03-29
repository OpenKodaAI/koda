"use client";

import { useSystemSettings } from "@/hooks/use-system-settings";
import { VariableEditorModal } from "@/components/control-plane/system/shared/variable-editor-modal";

export function SettingsModalHost() {
  const { editingVariable, setEditingVariable, confirmVariable } = useSystemSettings();

  if (!editingVariable) return null;

  return (
    <VariableEditorModal
      draft={editingVariable}
      onChange={setEditingVariable}
      onCancel={() => setEditingVariable(null)}
      onConfirm={confirmVariable}
    />
  );
}
