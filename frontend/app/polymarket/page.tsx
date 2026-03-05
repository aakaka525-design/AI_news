import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import PolymarketPageClient from "./page-client";

function PolymarketPageFallback() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">预测市场</h1>
        <p className="text-sm text-muted-foreground mt-1">Polymarket 活跃预测市场 — 实时概率追踪</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      <Skeleton className="h-[420px]" />
    </div>
  );
}

export default function PolymarketPage() {
  return (
    <Suspense fallback={<PolymarketPageFallback />}>
      <PolymarketPageClient />
    </Suspense>
  );
}
