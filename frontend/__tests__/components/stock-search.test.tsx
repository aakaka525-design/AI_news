import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { StockSearch } from "@/components/layout/stock-search";

// Mock next/navigation
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

// Mock fetchSearch from api
const mockFetchSearch = vi.fn();
vi.mock("@/lib/api", () => ({
  fetchSearch: (...args: unknown[]) => mockFetchSearch(...args),
}));

// Mock useDebounce to return value immediately (no delay)
vi.mock("@/lib/use-debounce", () => ({
  useDebounce: <T,>(value: T, _delay: number): T => value,
}));

const mockStocks = [
  {
    ts_code: "000001.SZ",
    name: "平安银行",
    industry: "银行",
  },
  {
    ts_code: "600036.SH",
    name: "招商银行",
    industry: "银行",
  },
];

const mockNews = [
  {
    id: 1,
    title: "银行板块大涨",
    received_at: "2026-03-08T10:00:00",
  },
];

describe("StockSearch", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockFetchSearch.mockClear();
    mockFetchSearch.mockResolvedValue({ stocks: [], news: [] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders search input", () => {
    render(<StockSearch />);
    const input = screen.getByPlaceholderText("搜索股票/新闻...");
    expect(input).toBeDefined();
  });

  it("renders input with combobox role", () => {
    render(<StockSearch />);
    const input = screen.getByRole("combobox");
    expect(input).toBeDefined();
  });

  it("calls fetchSearch on input change", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: mockStocks, news: [] });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      expect(mockFetchSearch).toHaveBeenCalledWith("银行", "all", 10);
    });
  });

  it("displays stock results in dropdown", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: mockStocks, news: [] });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      expect(screen.getByText("平安银行")).toBeDefined();
      expect(screen.getByText("招商银行")).toBeDefined();
    });
  });

  it("displays ts_code in stock results", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: mockStocks, news: [] });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      expect(screen.getByText("000001.SZ")).toBeDefined();
      expect(screen.getByText("600036.SH")).toBeDefined();
    });
  });

  it("displays news results in dropdown", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: [], news: mockNews });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      expect(screen.getByText("银行板块大涨")).toBeDefined();
    });
  });

  it("displays grouped sections (stocks + news)", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: mockStocks, news: mockNews });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      // Stock section header
      expect(screen.getByText("股票")).toBeDefined();
      // News section header contains text "新闻"
      expect(screen.getByText("新闻")).toBeDefined();
      // Stock items
      expect(screen.getByText("平安银行")).toBeDefined();
      // News items
      expect(screen.getByText("银行板块大涨")).toBeDefined();
    });
  });

  it("navigates to stock page on stock result click", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: mockStocks, news: [] });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      expect(screen.getByText("平安银行")).toBeDefined();
    });

    fireEvent.click(screen.getByText("平安银行"));

    expect(mockPush).toHaveBeenCalledWith("/market/000001.SZ");
  });

  it("navigates to news page on news result click", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: [], news: mockNews });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      expect(screen.getByText("银行板块大涨")).toBeDefined();
    });

    fireEvent.click(screen.getByText("银行板块大涨"));

    expect(mockPush).toHaveBeenCalledWith("/news?highlight=1");
  });

  it("does not fetch when query is empty", async () => {
    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "" } });
    });

    expect(mockFetchSearch).not.toHaveBeenCalled();
  });

  it("does not show dropdown when no results", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: [], news: [] });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "xyz" } });
    });

    await waitFor(() => {
      expect(mockFetchSearch).toHaveBeenCalled();
    });

    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("shows listbox with options when results exist", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: mockStocks, news: [] });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      const listbox = screen.getByRole("listbox");
      expect(listbox).toBeDefined();
      const options = screen.getAllByRole("option");
      expect(options).toHaveLength(2);
    });
  });

  it("shows correct option count with stocks + news", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: mockStocks, news: mockNews });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      const options = screen.getAllByRole("option");
      // 2 stocks + 1 news = 3 options
      expect(options).toHaveLength(3);
    });
  });

  it("handles keyboard navigation with ArrowDown", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: mockStocks, news: [] });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeDefined();
    });

    // Press ArrowDown to select first item
    fireEvent.keyDown(input, { key: "ArrowDown" });

    const options = screen.getAllByRole("option");
    expect(options[0].getAttribute("aria-selected")).toBe("true");
  });

  it("handles Enter key to select stock item", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: mockStocks, news: [] });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeDefined();
    });

    // Navigate to first item and press Enter
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(mockPush).toHaveBeenCalledWith("/market/000001.SZ");
  });

  it("handles Enter key to select news item", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: [], news: mockNews });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeDefined();
    });

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(mockPush).toHaveBeenCalledWith("/news?highlight=1");
  });

  it("closes dropdown on Escape key", async () => {
    mockFetchSearch.mockResolvedValue({ stocks: mockStocks, news: [] });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeDefined();
    });

    fireEvent.keyDown(input, { key: "Escape" });

    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
