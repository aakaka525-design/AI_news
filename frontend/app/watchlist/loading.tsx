export default function Loading() {
  return (
    <div className="space-y-6">
      {/* Title + badge */}
      <div className="flex items-center justify-between">
        <div className="h-8 w-28 bg-muted animate-pulse rounded" />
        <div className="h-6 w-12 bg-muted animate-pulse rounded-full" />
      </div>

      {/* Table skeleton: header + rows */}
      <div className="rounded-lg border">
        <div className="h-10 bg-muted/50 animate-pulse rounded-t-lg" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="h-14 bg-muted animate-pulse border-t"
          />
        ))}
      </div>
    </div>
  );
}
