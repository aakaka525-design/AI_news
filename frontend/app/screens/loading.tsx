export default function Loading() {
  return (
    <div className="space-y-6">
      {/* Title */}
      <div className="h-8 w-32 bg-muted animate-pulse rounded" />

      {/* Tabs toggle */}
      <div className="flex gap-2">
        <div className="h-9 w-28 bg-muted animate-pulse rounded-md" />
        <div className="h-9 w-28 bg-muted animate-pulse rounded-md" />
      </div>

      {/* Freshness banner */}
      <div className="h-14 bg-muted animate-pulse rounded-lg" />

      {/* Table skeleton: header + rows */}
      <div className="space-y-2">
        <div className="h-12 bg-muted animate-pulse rounded" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-12 bg-muted animate-pulse rounded" />
        ))}
      </div>
    </div>
  );
}
