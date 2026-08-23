import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { ApiError } from './api/client.ts'
import { AuthProvider } from './auth/AuthContext.tsx'
import { ToastProvider } from './components/ui/ToastContext.tsx'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Never retry a 4xx: a 403 is not going to become a 200, and retrying a
      // 404 four times just delays the message by two seconds.
      retry: (failureCount, error) =>
        error instanceof ApiError && error.isClientError
          ? false
          : failureCount < 2,
      refetchOnWindowFocus: false,
      staleTime: 30 * 1000,
    },
    mutations: {
      retry: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/* AuthProvider is inside QueryClientProvider: it clears the cache on
            sign-out so the next user never sees the previous one's pets. */}
        <AuthProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
