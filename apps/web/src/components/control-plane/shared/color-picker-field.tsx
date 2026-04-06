"use client";

import { useCallback, useEffect, useState } from "react";
import {
  hexToRgb,
  rgbToHex,
  validateColor,
} from "@/lib/control-plane-editor";
import { AnimatedColorPicker } from "./animated-color-picker";
import { FormField } from "./form-field";

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

      </div>
    </FormField>
  );
}
