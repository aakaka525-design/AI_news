"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Search, Newspaper } from "lucide-react";
import { useDebounce } from "@/lib/use-debounce";
import { fetchSearch } from "@/lib/api";
import type { SearchStockResult, SearchNewsResult } from "@/lib/types";

interface FlatItem {
  type: "stock" | "news";
  stock?: SearchStockResult;
  news?: SearchNewsResult;
}

export function StockSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [stocks, setStocks] = useState<SearchStockResult[]>([]);
  const [news, setNews] = useState<SearchNewsResult[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const debouncedQuery = useDebounce(query.trim(), 300);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const listboxId = "stock-search-listbox";

  // Flatten results for keyboard navigation
  const flatItems: FlatItem[] = [
    ...stocks.map((s) => ({ type: "stock" as const, stock: s })),
    ...news.map((n) => ({ type: "news" as const, news: n })),
  ];

  useEffect(() => {
    if (!debouncedQuery) {
      setStocks([]);
      setNews([]);
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    fetchSearch(debouncedQuery, "all", 10)
      .then((res) => {
        if (!controller.signal.aborted) {
          setStocks(res.stocks ?? []);
          setNews(res.news ?? []);
          setActiveIndex(-1);
          setOpen(true);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setStocks([]);
          setNews([]);
        }
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

  const handleSelectStock = useCallback(
    (tsCode: string) => {
      setOpen(false);
      setQuery("");
      setActiveIndex(-1);
      router.push(`/market/${tsCode}`);
    },
    [router],
  );

  const handleSelectNews = useCallback(
    (newsId: number) => {
      setOpen(false);
      setQuery("");
      setActiveIndex(-1);
      router.push(`/news?highlight=${newsId}`);
    },
    [router],
  );

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!open || flatItems.length === 0) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setActiveIndex((prev) => (prev < flatItems.length - 1 ? prev + 1 : 0));
        break;
      case "ArrowUp":
        e.preventDefault();
        setActiveIndex((prev) => (prev > 0 ? prev - 1 : flatItems.length - 1));
        break;
      case "Enter":
        e.preventDefault();
        if (activeIndex >= 0 && activeIndex < flatItems.length) {
          const item = flatItems[activeIndex];
          if (item.type === "stock" && item.stock) {
            handleSelectStock(item.stock.ts_code);
          } else if (item.type === "news" && item.news) {
            handleSelectNews(item.news.id);
          }
        }
        break;
      case "Escape":
        setOpen(false);
        setActiveIndex(-1);
        break;
    }
  }

  const activeDescendant =
    activeIndex >= 0 && flatItems[activeIndex]
      ? `search-option-${activeIndex}`
      : undefined;

  const hasResults = stocks.length > 0 || news.length > 0;

  return (
    <div ref={wrapperRef} className="relative w-full max-w-sm">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="搜索股票/新闻..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => hasResults && setOpen(true)}
          onKeyDown={handleKeyDown}
          className="pl-8 h-9"
          role="combobox"
          aria-expanded={open && hasResults}
          aria-controls={listboxId}
          aria-activedescendant={activeDescendant}
          aria-autocomplete="list"
        />
      </div>
      {open && hasResults && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md max-h-80 overflow-y-auto"
        >
          {stocks.length > 0 && (
            <>
              <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-muted/50">
                股票
              </div>
              {stocks.map((item, idx) => (
                <button
                  key={item.ts_code}
                  id={`search-option-${idx}`}
                  type="button"
                  role="option"
                  aria-selected={idx === activeIndex}
                  className={`flex w-full items-center gap-3 px-3 py-2 text-sm transition-colors text-left ${
                    idx === activeIndex ? "bg-muted" : "hover:bg-muted"
                  }`}
                  onClick={() => handleSelectStock(item.ts_code)}
                  onMouseEnter={() => setActiveIndex(idx)}
                >
                  <span className="font-mono text-primary">{item.ts_code}</span>
                  <span>{item.name}</span>
                  <span className="text-muted-foreground text-xs ml-auto">{item.industry ?? ""}</span>
                </button>
              ))}
            </>
          )}
          {news.length > 0 && (
            <>
              <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-muted/50">
                <Newspaper className="inline h-3 w-3 mr-1" />
                新闻
              </div>
              {news.map((item, idx) => {
                const flatIdx = stocks.length + idx;
                return (
                  <button
                    key={item.id}
                    id={`search-option-${flatIdx}`}
                    type="button"
                    role="option"
                    aria-selected={flatIdx === activeIndex}
                    className={`flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors text-left ${
                      flatIdx === activeIndex ? "bg-muted" : "hover:bg-muted"
                    }`}
                    onClick={() => handleSelectNews(item.id)}
                    onMouseEnter={() => setActiveIndex(flatIdx)}
                  >
                    <span className="truncate flex-1">{item.title}</span>
                    <span className="text-muted-foreground text-xs whitespace-nowrap">
                      {item.received_at?.slice(0, 10)}
                    </span>
                  </button>
                );
              })}
            </>
          )}
        </div>
      )}
    </div>
  );
}
