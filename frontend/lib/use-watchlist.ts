"use client";

import { useSyncExternalStore } from "react";
import { watchlist } from "./watchlist";

export function useWatchlist() {
  const codes = useSyncExternalStore(
    (cb) => watchlist.onChange(cb),
    () => watchlist.getAll(),
    () => [] as string[], // server snapshot
  );

  return {
    codes,
    add: watchlist.add.bind(watchlist),
    remove: watchlist.remove.bind(watchlist),
    has: watchlist.has.bind(watchlist),
    toggle: watchlist.toggle.bind(watchlist),
  };
}
