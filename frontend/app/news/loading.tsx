export default function Loading() {
  return (
    <div className="space-y-4">
      {/* Title */}
      <div className="h-8 w-32 bg-muted animate-pulse rounded" />

      {/* Tabs placeholder */}
      <div className="flex gap-2">
        <div className="h-9 w-24 bg-muted animate-pulse rounded-md" />
        <div className="h-9 w-24 bg-muted animate-pulse rounded-md" />
      </div>

      {/* News card list */}
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-24 bg-muted animate-pulse rounded-lg" />
        ))}
      </div>
    </div>
  );
}
