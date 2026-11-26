'use client';

import { useState } from 'react';

interface PasswordInputProps {
  id: string;
  name: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  autoComplete: 'current-password' | 'new-password';
  error?: string | null;
  hintAbove?: React.ReactNode;
  hintId?: string;
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  enterKeyHint?: 'next' | 'done';
  inputRef?: React.RefObject<HTMLInputElement>;
}

export function PasswordInput({
  id,
  name,
  label,
  value,
  onChange,
  onBlur,
  autoComplete,
  error,
  hintAbove,
  hintId,
  required = true,
  minLength,
  maxLength = 128,
  enterKeyHint = 'done',
  inputRef,
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  const errorId = `${id}-error`;
  const describedByParts = [hintId, error ? errorId : undefined].filter(Boolean);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <label
          htmlFor={id}
          className="block text-sm font-medium text-surface-800 dark:text-surface-200"
        >
          {label}
          {required ? (
            <span className="ml-1 text-red-600" aria-hidden="true">
              *
            </span>
          ) : null}
        </label>
        <button
          type="button"
          onClick={() => setVisible((prev) => !prev)}
          aria-pressed={visible}
          aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
          className="min-h-[32px] rounded px-2 py-1 text-xs font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 dark:text-primary-300 dark:hover:bg-primary-950"
        >
          {visible ? 'Hide password' : 'Show password'}
        </button>
      </div>

      {hintAbove}

      <input
        ref={inputRef}
        id={id}
        name={name}
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        autoComplete={autoComplete}
        required={required}
        minLength={minLength}
        maxLength={maxLength}
        enterKeyHint={enterKeyHint}
        aria-invalid={error ? 'true' : 'false'}
        aria-describedby={describedByParts.length > 0 ? describedByParts.join(' ') : undefined}
        className={`finsight-input min-h-[48px] w-full rounded-lg border px-3.5 py-2.5 text-base text-surface-900 shadow-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary-600 dark:bg-surface-950 dark:text-surface-50 ${
          error
            ? 'border-red-600 bg-red-50/50 dark:border-red-500 dark:bg-red-950/20'
            : 'border-surface-300 bg-white dark:border-surface-700'
        }`}
      />

      {error ? (
        <p id={errorId} className="flex items-start gap-1.5 text-sm text-red-700 dark:text-red-300">
          <span role="img" aria-label="Error" className="select-none">
            !
          </span>
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}
