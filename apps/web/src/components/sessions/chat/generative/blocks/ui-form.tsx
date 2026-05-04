"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useBlockSubmit } from "@/hooks/use-block-submit";
import { cn } from "@/lib/utils";
import type { z } from "zod";
import type {
  uiFormBlockSchema,
  uiFormFieldSchema,
} from "@/lib/contracts/generative-ui";

export type UiFormBlock = z.infer<typeof uiFormBlockSchema>;
type FormField = z.infer<typeof uiFormFieldSchema>;

export interface UiFormProps {
  block: UiFormBlock;
  agentId?: string | null;
  sessionId?: string | null;
}

type Values = Record<string, string | number | boolean>;

function initialValuesFor(fields: FormField[]): Values {
  const out: Values = {};
  for (const field of fields) {
    if (field.kind === "toggle") {
      out[field.id] = field.default ?? false;
    } else if (field.kind === "select") {
      out[field.id] = field.options[0]?.value ?? "";
    } else if (field.kind === "number") {
      out[field.id] = "" as unknown as number;
    } else {
      out[field.id] = "";
    }
  }
  return out;
}

function validate(fields: FormField[], values: Values): string | null {
  for (const field of fields) {
    if (field.kind === "text" || field.kind === "textarea") {
      const v = String(values[field.id] ?? "");
      if (field.required && v.trim().length === 0) {
        return `${field.label} is required.`;
      }
      if (v.length > field.max) {
        return `${field.label} is too long.`;
      }
    }
    if (field.kind === "number") {
      const raw = values[field.id];
      if (field.required && (raw === "" || raw === undefined)) {
        return `${field.label} is required.`;
      }
      if (raw !== "" && raw !== undefined) {
        const n = Number(raw);
        if (!Number.isFinite(n)) return `${field.label} must be a number.`;
        if (typeof field.min === "number" && n < field.min) {
          return `${field.label} must be ≥ ${field.min}.`;
        }
        if (typeof field.max === "number" && n > field.max) {
          return `${field.label} must be ≤ ${field.max}.`;
        }
      }
    }
    if (field.kind === "select" && field.required) {
      if (!values[field.id]) return `${field.label} is required.`;
    }
  }
  return null;
}

export function UiForm({ block, agentId, sessionId }: UiFormProps) {
  const { title, description, fields, submit_label } = block.payload;
  const [values, setValues] = useState<Values>(() => initialValuesFor(fields));
  const [localError, setLocalError] = useState<string | null>(null);
  const blockSubmit = useBlockSubmit({ agentId, sessionId, blockId: block.id });

  const update = (id: string, value: Values[string]) => {
    setValues((prev) => ({ ...prev, [id]: value }));
    if (localError) setLocalError(null);
  };

  const handleSubmit = async () => {
    const validationError = validate(fields, values);
    if (validationError) {
      setLocalError(validationError);
      return;
    }
    const submitValues: Record<
      string,
      string | number | boolean | null | string[]
    > = {};
    for (const field of fields) {
      const raw = values[field.id];
      if (field.kind === "number") {
        submitValues[field.id] = raw === "" || raw === undefined ? null : Number(raw);
      } else {
        submitValues[field.id] = raw as string | number | boolean;
      }
    }
    await blockSubmit.submit({
      block_type: "ui_form",
      values: submitValues,
    });
  };

  const submitting = blockSubmit.isPending;
  const done = blockSubmit.isSubmitted;
  const submitError = localError ?? blockSubmit.error;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!submitting && !done) void handleSubmit();
      }}
      data-submitted={done || undefined}
      className={cn(
        "rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] p-3 flex flex-col gap-3",
        done && "opacity-60",
      )}
    >
      {title ? (
        <h4 className="m-0 text-[0.875rem] font-medium text-[var(--text-primary)]">
          {title}
        </h4>
      ) : null}
      {description ? (
        <p className="m-0 text-[0.8125rem] text-[var(--text-secondary)]">
          {description}
        </p>
      ) : null}
      <div className="flex flex-col gap-2.5">
        {fields.map((field) => {
          const id = `${block.id}-${field.id}`;
          if (field.kind === "text" || field.kind === "number") {
            return (
              <div key={field.id} className="flex flex-col gap-1">
                <label htmlFor={id} className="text-[0.75rem] text-[var(--text-secondary)]">
                  {field.label}
                  {field.required ? <span className="text-[var(--tone-danger-dot)]"> *</span> : null}
                </label>
                <Input
                  id={id}
                  sizeVariant="sm"
                  type={field.kind === "number" ? "number" : "text"}
                  value={String(values[field.id] ?? "")}
                  onChange={(e) => update(field.id, e.target.value)}
                  disabled={submitting || done}
                />
              </div>
            );
          }
          if (field.kind === "textarea") {
            return (
              <div key={field.id} className="flex flex-col gap-1">
                <label htmlFor={id} className="text-[0.75rem] text-[var(--text-secondary)]">
                  {field.label}
                  {field.required ? <span className="text-[var(--tone-danger-dot)]"> *</span> : null}
                </label>
                <Textarea
                  id={id}
                  rows={3}
                  value={String(values[field.id] ?? "")}
                  onChange={(e) => update(field.id, e.target.value)}
                  disabled={submitting || done}
                />
              </div>
            );
          }
          if (field.kind === "toggle") {
            const isOn = Boolean(values[field.id]);
            return (
              <label
                key={field.id}
                htmlFor={id}
                className="flex items-center justify-between gap-2 text-[0.8125rem] text-[var(--text-secondary)]"
              >
                <span>{field.label}</span>
                <input
                  id={id}
                  type="checkbox"
                  checked={isOn}
                  onChange={(e) => update(field.id, e.target.checked)}
                  disabled={submitting || done}
                  className="h-4 w-4 accent-[var(--accent)]"
                />
              </label>
            );
          }
          if (field.kind === "select") {
            const value = String(values[field.id] ?? "");
            return (
              <div key={field.id} className="flex flex-col gap-1">
                <label htmlFor={id} className="text-[0.75rem] text-[var(--text-secondary)]">
                  {field.label}
                  {field.required ? <span className="text-[var(--tone-danger-dot)]"> *</span> : null}
                </label>
                <Select
                  value={value}
                  onValueChange={(next) => update(field.id, next)}
                  disabled={submitting || done}
                >
                  <SelectTrigger id={id} sizeVariant="sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {field.options.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            );
          }
          return null;
        })}
      </div>
      {submitError ? (
        <p className="m-0 text-[0.75rem] text-[var(--tone-danger-dot)]">
          {submitError}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button
          type="submit"
          variant="accent"
          size="sm"
          disabled={submitting || done}
          aria-busy={submitting}
        >
          {done ? "✓" : submit_label}
        </Button>
      </div>
    </form>
  );
}
