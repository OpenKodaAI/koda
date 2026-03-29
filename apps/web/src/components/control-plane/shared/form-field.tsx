"use client";

import type {
  ChangeEvent,
  ChangeEventHandler,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { useState } from "react";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
} from "@/components/ui/select";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { formatCost } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/*  FormField                                                                  */
/* -------------------------------------------------------------------------- */

interface FormFieldProps {
  label: string;
  description?: string;
  required?: boolean;
  error?: string;
  children: ReactNode;
}

export function FormField({
  label,
  description,
  required,
  error,
  children,
}: FormFieldProps) {
  const { tl } = useAppI18n();

  return (
    <label className="flex flex-col gap-1.5">
      {label && (
        <span className="eyebrow">
          {tl(label)}
          {required && (
            <span className="text-[var(--tone-danger-dot)] ml-0.5">*</span>
          )}
        </span>
      )}

      {description && (
        <span className="text-xs text-[var(--text-quaternary)] leading-relaxed">
          {tl(description)}
        </span>
      )}

      {children}

      {error && (
        <span className="text-xs text-[var(--tone-danger-text)]">{tl(error)}</span>
      )}
    </label>
  );
}

/* -------------------------------------------------------------------------- */
/*  FormInput                                                                  */
/* -------------------------------------------------------------------------- */

interface FormInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  description?: string;
  required?: boolean;
  error?: string;
}

export function FormInput({
  label,
  description,
  required,
  error,
  className,
  ...rest
}: FormInputProps) {
  const { tl } = useAppI18n();

  return (
    <FormField
      label={label}
      description={description}
      required={required}
      error={error}
    >
      <input
        className={`field-shell px-4 py-3 text-sm text-[var(--text-primary)] ${className ?? ""}`}
        {...rest}
        placeholder={typeof rest.placeholder === "string" ? tl(rest.placeholder) : rest.placeholder}
      />
    </FormField>
  );
}

/* -------------------------------------------------------------------------- */
/*  FormCurrencyInput                                                          */
/* -------------------------------------------------------------------------- */

interface FormCurrencyInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> {
  label: string;
  description?: string;
  required?: boolean;
  error?: string;
  value: number | null | undefined;
  onValueChange: (value: number | null) => void;
}

function normalizeCurrencyInput(raw: string) {
  const cleaned = raw.replace(/[^\d.,]/g, "");
  const lastSeparator = Math.max(cleaned.lastIndexOf("."), cleaned.lastIndexOf(","));

  if (lastSeparator === -1) {
    return cleaned.replace(/[^\d]/g, "");
  }

  const integerPart = cleaned.slice(0, lastSeparator).replace(/[^\d]/g, "");
  const fractionPart = cleaned
    .slice(lastSeparator + 1)
    .replace(/[^\d]/g, "")
    .slice(0, 2);

  return fractionPart.length > 0 ? `${integerPart}.${fractionPart}` : `${integerPart}.`;
}

function parseCurrencyInput(raw: string) {
  if (!raw.trim() || raw === ".") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function FormCurrencyInput({
  label,
  description,
  required,
  error,
  value,
  onValueChange,
  className,
  onFocus,
  onBlur,
  ...rest
}: FormCurrencyInputProps) {
  const [displayValue, setDisplayValue] = useState(value == null ? "" : formatCost(value));
  const [isFocused, setIsFocused] = useState(false);
  const renderedValue = isFocused
    ? displayValue
    : value == null
      ? ""
      : formatCost(value);

  return (
    <FormField
      label={label}
      description={description}
      required={required}
      error={error}
    >
      <input
        {...rest}
        inputMode="decimal"
        autoComplete="off"
        className={`field-shell px-4 py-3 text-sm text-[var(--text-primary)] ${className ?? ""}`}
        value={renderedValue}
        onFocus={(event) => {
          setIsFocused(true);
          setDisplayValue(value == null ? "" : value.toFixed(2));
          onFocus?.(event);
        }}
        onChange={(event) => {
          const normalized = normalizeCurrencyInput(event.target.value);
          setDisplayValue(normalized);
          onValueChange(parseCurrencyInput(normalized));
        }}
        onBlur={(event) => {
          setIsFocused(false);
          const parsed = parseCurrencyInput(displayValue);
          onValueChange(parsed);
          setDisplayValue(parsed == null ? "" : formatCost(parsed));
          onBlur?.(event);
        }}
        placeholder={typeof rest.placeholder === "string" ? rest.placeholder : rest.placeholder}
      />
    </FormField>
  );
}

/* -------------------------------------------------------------------------- */
/*  FormSelect                                                                 */
/* -------------------------------------------------------------------------- */

interface FormSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  description?: string;
  required?: boolean;
  error?: string;
  placeholder?: string;
  options: {
    value: string;
    label: string;
    description?: string;
    group?: string;
    icon?: ReactNode;
    disabled?: boolean;
  }[];
}

const EMPTY_SELECT_SENTINEL = "__cp_empty_option__";

export function FormSelect({
  label,
  description,
  required,
  error,
  options,
  className,
  value,
  defaultValue,
  onChange,
  disabled,
  name,
  id,
  placeholder,
}: FormSelectProps) {
  const { tl } = useAppI18n();
  const selectedValue = typeof value === "string" ? value : typeof defaultValue === "string" ? defaultValue : "";
  const hasExplicitEmptyOption = options.some((option) => option.value === "");
  const internalSelectedValue =
    selectedValue === "" && hasExplicitEmptyOption ? EMPTY_SELECT_SENTINEL : selectedValue;
  const selectedOption = options.find((option) => option.value === selectedValue);
  const placeholderLabel =
    typeof placeholder === "string" ? tl(placeholder) : tl("Selecione");
  const groupedOptions = options.reduce<
    Array<{
      group: string | null;
      items: FormSelectProps["options"];
    }>
  >((accumulator, option) => {
    const group = option.group ?? null;
    const existing = accumulator.find((entry) => entry.group === group);
    if (existing) {
      existing.items.push(option);
      return accumulator;
    }
    accumulator.push({ group, items: [option] });
    return accumulator;
  }, []);

  const emitChange: ChangeEventHandler<HTMLSelectElement> | undefined = onChange;

  return (
    <FormField
      label={label}
      description={description}
      required={required}
      error={error}
    >
      <>
        {name ? <input type="hidden" name={name} value={selectedValue} /> : null}
        <Select
          value={internalSelectedValue}
          onValueChange={(nextValue) => {
            const emittedValue =
              nextValue === EMPTY_SELECT_SENTINEL ? "" : nextValue;
            emitChange?.({
              target: { value: emittedValue, name },
              currentTarget: { value: emittedValue, name },
            } as unknown as ChangeEvent<HTMLSelectElement>);
          }}
          disabled={disabled}
        >
          <SelectTrigger id={id} className={className}>
            {selectedOption ? (
              <span className="flex min-w-0 items-center gap-3">
                {selectedOption.icon ? (
                  <span className="flex shrink-0 items-center justify-center">
                    {selectedOption.icon}
                  </span>
                ) : null}
                <span className="min-w-0 truncate text-left text-[var(--text-primary)]">
                  {tl(selectedOption.label)}
                </span>
              </span>
            ) : (
              <span className="truncate text-left text-[var(--text-quaternary)]">
                {placeholderLabel}
              </span>
            )}
          </SelectTrigger>
          <SelectContent>
            {groupedOptions.map((group, groupIndex) => (
              <SelectGroup key={`${group.group ?? "default"}-${groupIndex}`}>
                {group.group ? <SelectLabel>{tl(group.group)}</SelectLabel> : null}
                {group.items.map((option) => (
                  <SelectItem
                    key={`${group.group ?? "default"}:${option.value || EMPTY_SELECT_SENTINEL}`}
                    value={option.value === "" ? EMPTY_SELECT_SENTINEL : option.value}
                    disabled={option.disabled}
                    textValue={tl(option.label)}
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      {option.icon ? (
                        <span className="flex shrink-0 items-center justify-center">
                          {option.icon}
                        </span>
                      ) : null}
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm text-[var(--text-primary)]">
                          {tl(option.label)}
                        </span>
                        {option.description ? (
                          <span className="mt-0.5 block truncate text-xs text-[var(--text-tertiary)]">
                            {tl(option.description)}
                          </span>
                        ) : null}
                      </span>
                    </div>
                  </SelectItem>
                ))}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
      </>
    </FormField>
  );
}

/* -------------------------------------------------------------------------- */
/*  FormTextarea                                                               */
/* -------------------------------------------------------------------------- */

interface FormTextareaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  description?: string;
  required?: boolean;
  error?: string;
}

export function FormTextarea({
  label,
  description,
  required,
  error,
  className,
  ...rest
}: FormTextareaProps) {
  const { tl } = useAppI18n();

  return (
    <FormField
      label={label}
      description={description}
      required={required}
      error={error}
    >
      <textarea
        className={`field-shell w-full rounded-[22px] px-5 py-4 text-sm leading-7 text-[var(--text-primary)] ${className ?? ""}`}
        spellCheck
        {...rest}
        placeholder={typeof rest.placeholder === "string" ? tl(rest.placeholder) : rest.placeholder}
      />
    </FormField>
  );
}
