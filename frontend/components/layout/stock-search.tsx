"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";
import { useDebounce } from "@/lib/use-debounce";
import { fetchStocks } from "@/lib/api";
import type { StockBasicItem } from "@/lib/types";

export function StockSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<StockBasicItem[]>([]);
  const [open, setOpen] = useState(false);
  const debouncedQuery = useDebounce(query.trim(), 300);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!debouncedQuery) {
      setResults([]);
      return;
    }
    let cancelled = false;
    fetchStocks(1, 8, debouncedQuery).then((res) => {
      if (!cancelled) {
        setResults(res.data);
        setOpen(true);
      }
    }).catch(() => {
      if (!cancelled) setResults([]);
    });
    return () => { cancelled = true; };
  }, [debouncedQuery]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function handleSelect(tsCode: string) {
    setOpen(false);
    setQuery("");
    router.push(`/market/${tsCode}`);
  }

  return (
    <div ref={wrapperRef} className="relative w-full max-w-sm">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="搜索股票代码/名称..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => results.length > 0 && setOpen(true)}
          className="pl-8 h-9"
        />
      </div>
      {open && results.length > 0 && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md">
          {results.map((item) => (
            <button
              key={item.ts_code}
              type="button"
              className="flex w-full items-center gap-3 px-3 py-2 text-sm hover:bg-muted transition-colors text-left"
              onClick={() => handleSelect(item.ts_code)}
            >
              <span className="font-mono text-primary">{item.ts_code}</span>
              <span>{item.name}</span>
              <span className="text-muted-foreground text-xs ml-auto">{item.industry ?? ""}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
