/** Joins class names, dropping anything falsy. Saves adding `clsx` for six lines. */
export function cn(
  ...parts: (string | false | null | undefined)[]
): string {
  return parts.filter(Boolean).join(' ');
}
