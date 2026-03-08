"use client";

import { useState, useRef, useEffect, useCallback } from "react";
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
  const [activeIndex, setActiveIndex] = useState(-1);
  const debouncedQuery = useDebounce(query.trim(), 300);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const listboxId = "stock-search-listbox";

  useEffect(() => {
    if (!debouncedQuery) {
      setResults([]);
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    fetchStocks(1, 8, debouncedQuery)
      .then((res) => {
        if (!controller.signal.aborted) {
          setResults(res.data);
          setActiveIndex(-1);
          setOpen(true);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setResults([]);
      });

    return () => controller.abort();
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

  const handleSelect = useCallback(
    (tsCode: string) => {
      setOpen(false);
      setQuery("");
      setActiveIndex(-1);
      router.push(`/market/${tsCode}`);
    },
    [router],
  );

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!open || results.length === 0) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setActiveIndex((prev) => (prev < results.length - 1 ? prev + 1 : 0));
        break;
      case "ArrowUp":
        e.preventDefault();
        setActiveIndex((prev) => (prev > 0 ? prev - 1 : results.length - 1));
        break;
      case "Enter":
        e.preventDefault();
        if (activeIndex >= 0 && activeIndex < results.length) {
          handleSelect(results[activeIndex].ts_code);
        }
        break;
      case "Escape":
        setOpen(false);
        setActiveIndex(-1);
        break;
    }
  }

  const activeDescendant =
    activeIndex >= 0 && results[activeIndex]
      ? `stock-option-${results[activeIndex].ts_code}`
      : undefined;

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
          onKeyDown={handleKeyDown}
          className="pl-8 h-9"
          role="combobox"
          aria-expanded={open && results.length > 0}
          aria-controls={listboxId}
          aria-activedescendant={activeDescendant}
          aria-autocomplete="list"
        />
      </div>
      {open && results.length > 0 && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md"
        >
          {results.map((item, idx) => (
            <button
              key={item.ts_code}
              id={`stock-option-${item.ts_code}`}
              type="button"
              role="option"
              aria-selected={idx === activeIndex}
              className={`flex w-full items-center gap-3 px-3 py-2 text-sm transition-colors text-left ${
                idx === activeIndex ? "bg-muted" : "hover:bg-muted"
              }`}
              onClick={() => handleSelect(item.ts_code)}
              onMouseEnter={() => setActiveIndex(idx)}
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
