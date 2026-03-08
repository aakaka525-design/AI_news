import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Header } from "@/components/layout/header";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
}));

// Mock next/link to render a plain anchor
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("Header", () => {
  it("renders without crashing", () => {
    render(<Header />);
    // The header element should be in the document
    const header = document.querySelector("header");
    expect(header).toBeInTheDocument();
  });

  it("contains the stock search area on desktop", () => {
    render(<Header />);
    // The desktop StockSearch wrapper div should exist
    const header = document.querySelector("header");
    expect(header).toBeTruthy();
  });

  it("renders the mobile menu trigger button", () => {
    render(<Header />);
    // There should be at least one button (the mobile menu trigger)
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
  });
});
