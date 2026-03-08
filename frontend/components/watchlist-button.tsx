"use client";

import { Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWatchlist } from "@/lib/use-watchlist";
import { cn } from "@/lib/utils";

interface WatchlistButtonProps {
  tsCode: string;
  className?: string;
}

export function WatchlistButton({ tsCode, className }: WatchlistButtonProps) {
  const { has, toggle } = useWatchlist();
  const active = has(tsCode);

  return (
    <Button
      variant={active ? "default" : "outline"}
      size="sm"
      onClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
        toggle(tsCode);
      }}
      className={cn("gap-1.5", className)}
    >
      <Star
        className={cn("h-4 w-4", active && "fill-current")}
      />
      {active ? "已自选" : "加自选"}
    </Button>
  );
}
