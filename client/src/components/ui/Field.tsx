import { useId } from 'react';
import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';
import { cn } from '../../lib/cn';

const controlClasses =
  'block w-full rounded-lg bg-white px-3 py-2 text-sm text-ink-900 ' +
  'ring-1 ring-ink-300 placeholder:text-ink-400 ' +
  'hover:ring-ink-400 disabled:cursor-not-allowed disabled:bg-ink-50 disabled:text-ink-500 ' +
  'dark:bg-ink-900 dark:text-ink-50 dark:ring-ink-700 dark:placeholder:text-ink-500 ' +
  'dark:hover:ring-ink-600 dark:disabled:bg-ink-800';

const errorClasses = 'ring-rose-500 hover:ring-rose-500 dark:ring-rose-500';

interface FieldShellProps {
  label: string;
  /** Validation message. Its presence is what marks the control invalid. */
  error?: string | null;
  hint?: ReactNode;
  required?: boolean;
  children: (props: {
    id: string;
    describedBy: string | undefined;
    invalid: boolean;
  }) => ReactNode;
}

/**
 * Label + control + hint + error, wired together.
 *
 * The point of the render-prop shape is that `aria-describedby` and `id` cannot
 * be forgotten: the control cannot be rendered without receiving them. Hand-
 * wiring these per form is where accessible forms quietly stop being accessible.
 */
export function Field({
  label,
  error,
  hint,
  required,
  children,
}: FieldShellProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy =
    [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') ||
    undefined;

  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1.5 block text-sm font-medium text-ink-700 dark:text-ink-200"
      >
        {label}
        {required && (
          <span className="ml-0.5 text-rose-600 dark:text-rose-400" aria-hidden="true">
            *
          </span>
        )}
        {!required && (
          <span className="ml-1.5 text-xs font-normal text-ink-400">optional</span>
        )}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {hint && !error && (
        <p id={hintId} className="mt-1.5 text-xs text-ink-500 dark:text-ink-400">
          {hint}
        </p>
      )}
      {error && (
        <p
          id={errorId}
          className="mt-1.5 text-xs font-medium text-rose-600 dark:text-rose-400"
        >
          {error}
        </p>
      )}
    </div>
  );
}

type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> & {
  label: string;
  error?: string | null;
  hint?: ReactNode;
};

export function Input({ label, error, hint, required, ...rest }: InputProps) {
  return (
    <Field label={label} error={error} hint={hint} required={required}>
      {({ id, describedBy, invalid }) => (
        <input
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required={required}
          className={cn(controlClasses, invalid && errorClasses)}
          {...rest}
        />
      )}
    </Field>
  );
}

type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id'> & {
  label: string;
  error?: string | null;
  hint?: ReactNode;
};

export function Select({ label, error, hint, required, children, ...rest }: SelectProps) {
  return (
    <Field label={label} error={error} hint={hint} required={required}>
      {({ id, describedBy, invalid }) => (
        <select
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required={required}
          className={cn(controlClasses, 'pr-8', invalid && errorClasses)}
          {...rest}
        >
          {children}
        </select>
      )}
    </Field>
  );
}

type TextareaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id'> & {
  label: string;
  error?: string | null;
  hint?: ReactNode;
};

export function Textarea({ label, error, hint, required, ...rest }: TextareaProps) {
  return (
    <Field label={label} error={error} hint={hint} required={required}>
      {({ id, describedBy, invalid }) => (
        <textarea
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required={required}
          className={cn(controlClasses, 'min-h-20 resize-y', invalid && errorClasses)}
          {...rest}
        />
      )}
    </Field>
  );
}
