"use client";

import { QueryClient, QueryClientProvider, QueryCache, MutationCache } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState, useCallback, useRef, type ReactNode } from "react";

interface ToastItem {
  id: number;
  message: string;
}

let toastId = 0;

function ErrorToastStack({
  toasts,
  onDismiss,
}: {
  toasts: ToastItem[];
  onDismiss: (id: number) => void;
}) {
  if (toasts.length === 0) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="bg-destructive text-destructive-foreground px-4 py-3 rounded-lg shadow-lg flex items-start gap-2 animate-in slide-in-from-right-5"
        >
          <p className="text-sm flex-1">{toast.message}</p>
          <button
            onClick={() => onDismiss(toast.id)}
            className="text-destructive-foreground/70 hover:text-destructive-foreground shrink-0"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const recentMessagesRef = useRef<Set<string>>(new Set());

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const handleError = useCallback(
    (err: unknown) => {
      const message = err instanceof Error ? err.message : "请求失败，请稍后重试";

      // 打印到控制台便于调试
      console.error("[QueryProvider] 请求错误:", err);

      // 去重：5秒内相同消息不重复弹出
      if (recentMessagesRef.current.has(message)) {
        return;
      }
      recentMessagesRef.current.add(message);
      setTimeout(() => {
        recentMessagesRef.current.delete(message);
      }, 5000);

      const id = ++toastId;
      setToasts((prev) => [...prev.slice(-4), { id, message }]);

      // 5秒后自动消失
      setTimeout(() => {
        dismissToast(id);
      }, 5000);
    },
    [dismissToast],
  );

  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
          mutations: {
            retry: 0,
          },
        },
        queryCache: new QueryCache({
          onError: (error, query) => {
            // 如果 query meta 中标记了 skipGlobalError，则跳过全局处理
            if (query.meta?.skipGlobalError) {
              return;
            }
            // 如果 query meta 中提供了自定义错误消息，优先使用
            const customMessage = query.meta?.errorMessage;
            if (typeof customMessage === "string") {
              console.error("[QueryProvider] 请求错误:", error);
              handleError(new Error(customMessage));
            } else {
              handleError(error);
            }
          },
        }),
        mutationCache: new MutationCache({
          onError: (error, _variables, _context, mutation) => {
            if (mutation.meta?.skipGlobalError) {
              return;
            }
            const customMessage = mutation.meta?.errorMessage;
            if (typeof customMessage === "string") {
              console.error("[QueryProvider] Mutation 错误:", error);
              handleError(new Error(customMessage));
            } else {
              handleError(error);
            }
          },
        }),
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ErrorToastStack toasts={toasts} onDismiss={dismissToast} />
      {process.env.NODE_ENV === "development" ? (
        <ReactQueryDevtools initialIsOpen={false} />
      ) : null}
    </QueryClientProvider>
  );
}
