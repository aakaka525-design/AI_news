export default function NewsLoading() {
  return (
    <div className="container mx-auto p-6 space-y-4">
      <div className="h-8 w-32 bg-muted animate-pulse rounded" />
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-20 bg-muted animate-pulse rounded-lg" />
      ))}
    </div>
  );
}
