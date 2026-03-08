"use client";

import { QueryClient, QueryClientProvider, QueryCache, MutationCache } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState, useCallback, type ReactNode } from "react";

function ErrorToast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-sm bg-destructive text-destructive-foreground px-4 py-3 rounded-lg shadow-lg flex items-start gap-2">
      <p className="text-sm flex-1">{message}</p>
      <button onClick={onDismiss} className="text-destructive-foreground/70 hover:text-destructive-foreground">
        ✕
      </button>
    </div>
  );
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [error, setError] = useState<string | null>(null);

  const handleError = useCallback((err: unknown) => {
    const message = err instanceof Error ? err.message : "请求失败";
    setError(message);
    setTimeout(() => setError(null), 5000);
  }, []);

  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 2,
            refetchOnWindowFocus: false,
          },
        },
        queryCache: new QueryCache({
          onError: (err) => handleError(err),
        }),
        mutationCache: new MutationCache({
          onError: (err) => handleError(err),
        }),
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {error && <ErrorToast message={error} onDismiss={() => setError(null)} />}
      {process.env.NODE_ENV === "development" ? (
        <ReactQueryDevtools initialIsOpen={false} />
      ) : null}
    </QueryClientProvider>
  );
}
