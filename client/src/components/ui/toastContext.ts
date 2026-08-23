import { createContext } from 'react';

export type ToastTone = 'success' | 'error' | 'info';

export interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

/** Separate from the provider so that file exports only a component. */
export const ToastContext = createContext<ToastApi | null>(null);
