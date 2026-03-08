/**
 * WatchlistService -- localStorage-backed watchlist for tracking stocks.
 */

export interface WatchlistService {
  getAll(): string[];
  add(tsCode: string): void;
  remove(tsCode: string): void;
  has(tsCode: string): boolean;
  toggle(tsCode: string): void;
  onChange(cb: () => void): () => void;
}

class LocalStorageWatchlist implements WatchlistService {
  private key = "ai_news_watchlist";
  private listeners: Set<() => void> = new Set();

  getAll(): string[] {
    if (typeof window === "undefined") return [];
    try {
      const raw = localStorage.getItem(this.key);
      if (!raw) return [];
      const parsed: unknown = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((v): v is string => typeof v === "string");
    } catch {
      return [];
    }
  }

  add(tsCode: string): void {
    const list = this.getAll();
    if (list.includes(tsCode)) return;
    list.push(tsCode);
    this.save(list);
  }

  remove(tsCode: string): void {
    const list = this.getAll().filter((c) => c !== tsCode);
    this.save(list);
  }

  has(tsCode: string): boolean {
    return this.getAll().includes(tsCode);
  }

  toggle(tsCode: string): void {
    if (this.has(tsCode)) {
      this.remove(tsCode);
    } else {
      this.add(tsCode);
    }
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => {
      this.listeners.delete(cb);
    };
  }

  private save(list: string[]): void {
    if (typeof window === "undefined") return;
    localStorage.setItem(this.key, JSON.stringify(list));
    this.notify();
  }

  private notify(): void {
    this.listeners.forEach((cb) => cb());
  }
}

export const watchlist: WatchlistService = new LocalStorageWatchlist();
