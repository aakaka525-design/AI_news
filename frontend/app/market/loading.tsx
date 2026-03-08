export default function Loading() {
  return (
    <div className="space-y-6">
      {/* Title */}
      <div className="h-8 w-36 bg-muted animate-pulse rounded" />

      {/* Index cards (3) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-28 bg-muted animate-pulse rounded-lg" />
        ))}
      </div>

      {/* Market breadth placeholder */}
      <div className="h-20 bg-muted animate-pulse rounded-lg" />

      {/* Filter bar */}
      <div className="flex flex-wrap gap-3">
        <div className="h-9 w-48 bg-muted animate-pulse rounded-md" />
        <div className="h-9 w-32 bg-muted animate-pulse rounded-md" />
        <div className="flex gap-1">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-9 w-16 bg-muted animate-pulse rounded-md" />
          ))}
        </div>
      </div>

      {/* Table skeleton */}
      <div className="space-y-2">
        <div className="h-10 bg-muted animate-pulse rounded" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-12 bg-muted animate-pulse rounded" />
        ))}
      </div>
    </div>
  );
}
