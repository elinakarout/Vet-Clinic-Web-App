import { useContext } from 'react';
import { ToastContext } from './toastContext';
import type { ToastApi } from './toastContext';

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (context === null) {
    throw new Error('useToast must be used inside <ToastProvider>');
  }
  return context;
}
