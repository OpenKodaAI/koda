"use client";

import { useCallback, useEffect, useState } from "react";
import {
  hexToRgb,
  rgbToHex,
  validateColor,
} from "@/lib/control-plane-editor";
import { AnimatedColorPicker } from "./animated-color-picker";
import { FormField } from "./form-field";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface ColorPickerFieldProps {
  label?: string;
  hex: string;
  rgb: string;
  onHexChange: (hex: string) => void;
  onRgbChange: (rgb: string) => void;
}

export function ColorPickerField({
  label = "Cor",
  hex,
  rgb,
  onHexChange,
  onRgbChange,
}: ColorPickerFieldProps) {
  const { tl } = useAppI18n();
  const [internalHex, setInternalHex] = useState(hex);

  useEffect(() => {
    setInternalHex(hex);
  }, [hex]);

  const handleHexChange = useCallback(
    (nextHex: string) => {
      setInternalHex(nextHex);
      onHexChange(nextHex);

      if (!validateColor(nextHex)) {
        return;
      }

      const components = hexToRgb(nextHex);
      if (!components) {
        return;
      }

      const normalized = rgbToHex(
        components.r,
        components.g,
        components.b,
      );
      if (normalized !== nextHex.toUpperCase()) {
        // Defensive normalization for consistency.
        onHexChange(normalized);
      }
      const rgbText = `${components.r}, ${components.g}, ${components.b}`;
      if (rgbText !== rgb) {
        onRgbChange(rgbText);
      }
    },
    [onHexChange, onRgbChange, rgb],
  );

  return (
    <FormField label={label}>
      <div className="space-y-3">
        <AnimatedColorPicker
          value={internalHex}
          onChange={handleHexChange}
          label=""
          presets={[
            "#7A8799",
            "#2F80ED",
            "#2F9E44",
            "#F59F00",
            "#F03E3E",
            "#845EF7",
            "#15AABF",
            "#12B886",
          ]}
        />

        <div className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_auto] md:items-end">
          <div>
            <p className="eyebrow mb-1.5">{tl("Valor RGB")}</p>
            <input
              type="text"
              readOnly
              value={rgb || ""}
              className="field-shell w-full px-3 py-2 text-sm text-[var(--text-primary)] font-mono tabular-nums"
              aria-label={tl("Cor em formato RGB")}
            />
          </div>
          <span className="h-10 text-xs text-[var(--text-quaternary)] flex items-end">
            {validateColor(internalHex) ? tl("Hex válido") : tl("Hex inválido")}
          </span>
        </div>
      </div>
    </FormField>
  );
}
