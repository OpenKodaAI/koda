"use client";

import { createPortal } from "react-dom";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { motion } from "framer-motion";
import { ChevronDown, Palette } from "lucide-react";
import { FormField } from "./form-field";
import { hexToRgb, validateColor } from "@/lib/control-plane-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface AnimatedColorPickerProps {
  label?: string;
  value: string;
  onChange: (color: string) => void;
  disabled?: boolean;
  presets?: string[];
}

const DEFAULT_PRESETS = [
  "#7A8799",
  "#A26AD3",
  "#4F86F7",
  "#37B24D",
  "#F59F00",
  "#FA5252",
  "#0F7BFF",
  "#1EA7A7",
];

const DEFAULT_HUE = 208;
const DEFAULT_SAT = 55;
const DEFAULT_LIGHT = 52;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function rgbToHsl(rgb: [number, number, number]): [number, number, number] {
  const [r, g, b] = rgb.map((channel) => channel / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;

  let hue = 0;
  if (delta > 0) {
    if (max === r) {
      hue = ((g - b) / delta) % 6;
    } else if (max === g) {
      hue = (b - r) / delta + 2;
    } else {
      hue = (r - g) / delta + 4;
    }
  }

  const h = Math.round((hue * 60 + 360) % 360);
  const l = (max + min) / 2;
  const s = delta === 0 ? 0 : delta / (1 - Math.abs(2 * l - 1));

  return [h, Math.round(clamp(s * 100, 0, 100)), Math.round(l * 100)];
}

function hueToRgb(p: number, q: number, t: number): number {
  let ratio = t;
  if (ratio < 0) ratio += 1;
  if (ratio > 1) ratio -= 1;

  if (ratio * 6 < 1) {
    return p + (q - p) * 6 * ratio;
  }
  if (ratio * 2 < 1) {
    return q;
  }
  if (ratio * 3 < 2) {
    return p + (q - p) * (2 / 3 - ratio) * 6;
  }
  return p;
}

function hslToHex(hue: number, saturation: number, lightness: number): string {
  const h = clamp(hue, 0, 360) / 360;
  const s = clamp(saturation, 0, 100) / 100;
  const l = clamp(lightness, 0, 100) / 100;

  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;

  const r = Math.round(hueToRgb(p, q, h + 1 / 3) * 255);
  const g = Math.round(hueToRgb(p, q, h) * 255);
  const b = Math.round(hueToRgb(p, q, h - 1 / 3) * 255);

  const toHex = (component: number) => component.toString(16).padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function normalizeHex(value: string): string {
  return value.trim().toUpperCase();
}

export function AnimatedColorPicker({
  label = "Cor",
  value,
  onChange,
  disabled,
  presets = DEFAULT_PRESETS,
}: AnimatedColorPickerProps) {
  const { tl } = useAppI18n();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [panelPosition, setPanelPosition] = useState<{
    top: number;
    left: number;
    width: number;
    maxHeight: number;
    placement: "top" | "bottom";
  } | null>(null);
  const normalizedValue = useMemo(
    () =>
      validateColor(value)
        ? normalizeHex(value)
        : hslToHex(DEFAULT_HUE, DEFAULT_SAT, DEFAULT_LIGHT),
    [value],
  );
  const [hexInput, setHexInput] = useState(normalizedValue);

  useEffect(() => {
    if (hexInput === normalizedValue) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      setHexInput(normalizedValue);
    });

    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [hexInput, normalizedValue]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !rootRef.current?.contains(target) &&
        !panelRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const updatePanelPosition = useCallback(() => {
    if (!triggerRef.current || !panelRef.current) {
      return;
    }

    const triggerRect = triggerRef.current.getBoundingClientRect();
    const panel = panelRef.current;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const viewportPadding = 12;
    const gap = 10;
    const width = Math.min(
      Math.max(triggerRect.width, 288),
      viewportWidth - viewportPadding * 2,
    );

    panel.style.width = `${width}px`;

    const panelRect = panel.getBoundingClientRect();
    const availableBelow =
      viewportHeight - triggerRect.bottom - viewportPadding - gap;
    const availableAbove = triggerRect.top - viewportPadding - gap;
    const placeAbove =
      availableBelow < panelRect.height && availableAbove > availableBelow;
    const maxHeight = Math.max(
      220,
      (placeAbove ? availableAbove : availableBelow),
    );
    const effectiveHeight = Math.min(panelRect.height, maxHeight);
    const top = placeAbove
      ? Math.max(viewportPadding, triggerRect.top - effectiveHeight - gap)
      : Math.max(
          viewportPadding,
          Math.min(
            triggerRect.bottom + gap,
            viewportHeight - viewportPadding - effectiveHeight,
          ),
        );
    const left = clamp(
      triggerRect.left,
      viewportPadding,
      viewportWidth - viewportPadding - width,
    );

    setPanelPosition({
      top,
      left,
      width,
      maxHeight,
      placement: placeAbove ? "top" : "bottom",
    });
  }, []);

  useLayoutEffect(() => {
    if (!open) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      updatePanelPosition();
    });

    const handleViewportChange = () => {
      updatePanelPosition();
    };

    window.addEventListener("resize", handleViewportChange);
    window.addEventListener("scroll", handleViewportChange, true);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", handleViewportChange);
      window.removeEventListener("scroll", handleViewportChange, true);
    };
  }, [open, updatePanelPosition]);

  const rgbString = useMemo(() => {
    const rgb = hexToRgb(hexInput);
    if (!rgb) {
      return "—";
    }
    return `${rgb.r}, ${rgb.g}, ${rgb.b}`;
  }, [hexInput]);

  const emitChange = useCallback(
    (nextHex: string) => {
      const nextValue = normalizeHex(nextHex);
      if (!validateColor(nextValue)) {
        return;
      }
      setHexInput(nextValue);
      onChange(nextValue);
    },
    [onChange],
  );

  const syncFromHex = useCallback(
    (nextHex: string) => {
      const candidate = normalizeHex(nextHex);
      if (!validateColor(candidate)) {
        return;
      }
      emitChange(candidate);
    },
    [emitChange],
  );

  const hueGradient = [
    "#ff0047",
    "#ff8f22",
    "#d7ff00",
    "#24e0a6",
    "#00bbff",
    "#5f6dff",
    "#c05cff",
    "#ff0047",
  ];

  const hasValidInput = validateColor(hexInput);
  const visibleHex = hasValidInput ? normalizeHex(hexInput) : normalizedValue;
  const previewHex = validateColor(visibleHex) ? visibleHex : normalizedValue;
  const [hue, saturation, lightness] = useMemo(() => {
    const rgb = hexToRgb(previewHex);
    if (!rgb) {
      return [DEFAULT_HUE, DEFAULT_SAT, DEFAULT_LIGHT] as const;
    }

    return rgbToHsl([rgb.r, rgb.g, rgb.b]);
  }, [previewHex]);
  const saturationGradient = `linear-gradient(90deg, hsl(${hue}, 0%, ${lightness}%), hsl(${hue}, 100%, ${lightness}%))`;
  const lightnessGradient = `linear-gradient(90deg, hsl(${hue}, ${saturation}%, 12%), hsl(${hue}, ${saturation}%, 56%), hsl(${hue}, ${saturation}%, 92%))`;
  const panelRoot = typeof document !== "undefined" ? document.body : null;

  return (
    <FormField label={label}>
      <div ref={rootRef} className="relative">
        <button
          ref={triggerRef}
          type="button"
          aria-label={tl("Abrir seletor de cor")}
          aria-expanded={open}
          aria-haspopup="dialog"
          disabled={disabled}
          onClick={() => setOpen((current) => !current)}
          className={cn(
            "field-shell flex w-full items-center gap-3 px-3 py-2.5 text-left transition-[border-color,background-color,box-shadow] duration-200",
            disabled && "cursor-not-allowed opacity-60",
            open && "border-[rgba(255,255,255,0.16)] bg-[rgba(255,255,255,0.03)]",
          )}
        >
          <motion.span
            aria-hidden="true"
            className="relative inline-flex h-8 w-8 shrink-0 overflow-hidden rounded-[0.65rem] border border-[rgba(255,255,255,0.08)]"
            style={{
              boxShadow: `0 0 0 4px ${previewHex}14`,
            }}
            animate={{ backgroundColor: previewHex }}
            transition={{ type: "spring", stiffness: 250, damping: 22 }}
          >
            <span
              className="h-full w-full"
              style={{
                background:
                  "conic-gradient(from 160deg at 50% 50%, rgba(255,255,255,0.08), rgba(255,255,255,0))",
              }}
            />
          </motion.span>

          <div className="min-w-0 flex-1">
            <p className="font-mono text-sm tracking-[0.08em] text-[var(--text-primary)]">
              {visibleHex}
            </p>
            <p className="text-[11px] text-[var(--text-quaternary)]">
              {rgbString}
            </p>
          </div>

          <span className="inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
            <Palette className="h-3.5 w-3.5" />
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 transition-transform duration-200",
                open && "rotate-180",
              )}
            />
          </span>
        </button>

        {panelRoot && open
          ? createPortal(
                  <div
                    ref={panelRef}
                    role="dialog"
                    aria-label={tl("Painel de cor")}
                    className="app-floating-panel app-overlay-fade-in z-[90] overflow-hidden rounded-[0.8rem] p-3"
                    style={{
                      position: "fixed",
                      top: panelPosition?.top ?? 0,
                      left: panelPosition?.left ?? 0,
                      width: panelPosition?.width,
                      maxHeight: panelPosition?.maxHeight,
                      visibility: panelPosition ? "visible" : "hidden",
                    }}
                  >
                    <div className="space-y-3 overflow-y-auto pr-1">
                      <div className="flex items-center gap-3">
                        <motion.div
                          aria-hidden="true"
                          className="relative h-11 w-11 shrink-0 overflow-hidden rounded-[0.8rem] border border-[rgba(255,255,255,0.08)]"
                          style={{
                            boxShadow: `0 0 0 4px ${previewHex}14`,
                          }}
                          animate={{ backgroundColor: previewHex }}
                          transition={{ type: "spring", stiffness: 250, damping: 22 }}
                        >
                          <div
                            className="h-full w-full"
                            style={{
                              background:
                                "conic-gradient(from 160deg at 50% 50%, rgba(255,255,255,0.08), rgba(255,255,255,0))",
                            }}
                          />
                        </motion.div>

                        <div className="min-w-0 flex-1 space-y-2">
                          <input
                            value={hexInput}
                            onChange={(event) =>
                              setHexInput(normalizeHex(event.target.value))
                            }
                            onBlur={() => syncFromHex(hexInput)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") {
                                event.preventDefault();
                                syncFromHex(hexInput);
                              }
                            }}
                            aria-label={tl("Hex color")}
                            maxLength={7}
                            inputMode="text"
                            className={cn(
                              "field-shell w-full px-3 py-2 text-sm font-mono tabular-nums tracking-[0.08em]",
                              !hasValidInput &&
                                "border-[rgba(240,82,82,0.32)] text-[var(--tone-danger-text)]",
                            )}
                            disabled={disabled}
                            spellCheck={false}
                          />
                          <div className="flex items-center justify-between text-[11px] text-[var(--text-quaternary)]">
                            <span>{rgbString}</span>
                            <span>{hue}°</span>
                          </div>
                        </div>
                      </div>

                      <div className="space-y-2.5">
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                              {tl("Tom")}
                            </span>
                            <span className="text-[11px] text-[var(--text-quaternary)]">
                              {hue}°
                            </span>
                          </div>
                          <input
                            type="range"
                            min={0}
                            max={360}
                            step={1}
                            value={hue}
                            onChange={(event) => {
                              emitChange(
                                hslToHex(
                                  Number(event.target.value),
                                  saturation,
                                  lightness,
                                ),
                              );
                            }}
                            aria-label={tl("Ajustar tom")}
                            className="agent-board-color-slider ui-slider"
                            style={{
                              background: `linear-gradient(90deg, ${hueGradient.join(",")})`,
                            }}
                            disabled={disabled}
                          />
                        </div>

                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                              {tl("Saturação")}
                            </span>
                            <span className="text-[11px] text-[var(--text-quaternary)]">
                              {saturation}%
                            </span>
                          </div>
                          <input
                            type="range"
                            min={6}
                            max={96}
                            step={1}
                            value={saturation}
                            onChange={(event) => {
                              emitChange(
                                hslToHex(
                                  hue,
                                  Number(event.target.value),
                                  lightness,
                                ),
                              );
                            }}
                            aria-label={tl("Ajustar saturacao")}
                            className="agent-board-color-slider ui-slider"
                            style={{ background: saturationGradient }}
                            disabled={disabled}
                          />
                        </div>

                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                              {tl("Luminosidade")}
                            </span>
                            <span className="text-[11px] text-[var(--text-quaternary)]">
                              {lightness}%
                            </span>
                          </div>
                          <input
                            type="range"
                            min={16}
                            max={86}
                            step={1}
                            value={lightness}
                            onChange={(event) => {
                              emitChange(
                                hslToHex(
                                  hue,
                                  saturation,
                                  Number(event.target.value),
                                ),
                              );
                            }}
                            aria-label={tl("Ajustar luminosidade")}
                            className="agent-board-color-slider ui-slider"
                            style={{ background: lightnessGradient }}
                            disabled={disabled}
                          />
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <p className="text-[11px] uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                          {tl("Paleta rápida")}
                        </p>
                        <div className="grid grid-cols-8 gap-2">
                          {presets.map((preset) => {
                            const isActive =
                              hasValidInput &&
                              normalizeHex(preset) === normalizeHex(hexInput);

                            return (
                              <button
                                key={preset}
                                type="button"
                                className="relative h-7 w-7 rounded-full border transition-all duration-200"
                                style={{
                                  borderColor: isActive
                                    ? "rgba(255,255,255,0.68)"
                                    : "rgba(255,255,255,0.18)",
                                  backgroundColor: preset,
                                  boxShadow: isActive
                                    ? `0 0 0 3px ${preset}1A`
                                    : "none",
                                }}
                                onClick={() => syncFromHex(preset)}
                                aria-label={`${tl("Cor")} ${preset}`}
                                disabled={disabled}
                              />
                            );
                          })}
                        </div>
                      </div>

                      {!hasValidInput ? (
                        <p className="text-xs text-[var(--tone-danger-text)]">
                          {tl("Use o formato hexadecimal #RRGGBB.")}
                        </p>
                      ) : null}
                    </div>
                  </div>,
              panelRoot,
            )
          : null}
      </div>
    </FormField>
  );
}
