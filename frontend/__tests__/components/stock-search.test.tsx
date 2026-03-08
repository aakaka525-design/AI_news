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

// Mock fetchStocks from api
const mockFetchStocks = vi.fn();
vi.mock("@/lib/api", () => ({
  fetchStocks: (...args: unknown[]) => mockFetchStocks(...args),
}));

// Mock useDebounce to return value immediately (no delay)
vi.mock("@/lib/use-debounce", () => ({
  useDebounce: <T,>(value: T, _delay: number): T => value,
}));

const mockResults = [
  {
    ts_code: "000001.SZ",
    symbol: "000001",
    name: "平安银行",
    industry: "银行",
  },
  {
    ts_code: "600036.SH",
    symbol: "600036",
    name: "招商银行",
    industry: "银行",
  },
];

describe("StockSearch", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockFetchStocks.mockClear();
    mockFetchStocks.mockResolvedValue({ data: [], total: 0 });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders search input", () => {
    render(<StockSearch />);
    const input = screen.getByPlaceholderText("搜索股票代码/名称...");
    expect(input).toBeDefined();
  });

  it("renders input with combobox role", () => {
    render(<StockSearch />);
    const input = screen.getByRole("combobox");
    expect(input).toBeDefined();
  });

  it("calls fetchStocks on input change", async () => {
    mockFetchStocks.mockResolvedValue({ data: mockResults, total: 2 });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "银行" } });
    });

    await waitFor(() => {
      expect(mockFetchStocks).toHaveBeenCalledWith(1, 8, "银行");
    });
  });

  it("displays search results in dropdown", async () => {
    mockFetchStocks.mockResolvedValue({ data: mockResults, total: 2 });

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

  it("displays ts_code in results", async () => {
    mockFetchStocks.mockResolvedValue({ data: mockResults, total: 2 });

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

  it("navigates to stock page on result click", async () => {
    mockFetchStocks.mockResolvedValue({ data: mockResults, total: 2 });

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

  it("does not fetch when query is empty", async () => {
    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "" } });
    });

    expect(mockFetchStocks).not.toHaveBeenCalled();
  });

  it("does not show dropdown when no results", async () => {
    mockFetchStocks.mockResolvedValue({ data: [], total: 0 });

    render(<StockSearch />);
    const input = screen.getByRole("combobox");

    await act(async () => {
      fireEvent.change(input, { target: { value: "xyz" } });
    });

    await waitFor(() => {
      expect(mockFetchStocks).toHaveBeenCalled();
    });

    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("shows listbox with options when results exist", async () => {
    mockFetchStocks.mockResolvedValue({ data: mockResults, total: 2 });

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

  it("handles keyboard navigation with ArrowDown", async () => {
    mockFetchStocks.mockResolvedValue({ data: mockResults, total: 2 });

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

  it("handles Enter key to select item", async () => {
    mockFetchStocks.mockResolvedValue({ data: mockResults, total: 2 });

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

  it("closes dropdown on Escape key", async () => {
    mockFetchStocks.mockResolvedValue({ data: mockResults, total: 2 });

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
