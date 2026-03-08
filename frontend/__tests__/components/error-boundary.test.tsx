import React from "react";
import { describe, it, expect, vi, beforeAll, afterAll } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ErrorBoundary } from "@/components/error-boundary";

function ThrowingComponent({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error("Test error");
  return <div>Normal content</div>;
}

describe("ErrorBoundary", () => {
  // Suppress React error boundary console.error in tests
  const originalError = console.error;
  beforeAll(() => {
    console.error = vi.fn();
  });
  afterAll(() => {
    console.error = originalError;
  });

  it("renders children when no error", () => {
    render(
      <ErrorBoundary>
        <div>Child content</div>
      </ErrorBoundary>
    );
    expect(screen.getByText("Child content")).toBeDefined();
  });

  it("renders fallback UI when child throws", () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );
    // Should show error UI, not crash
    expect(screen.queryByText("Normal content")).toBeNull();
    // Should display the default error heading
    expect(screen.getByText("页面加载出错")).toBeDefined();
    // Should display the error message
    expect(screen.getByText("Test error")).toBeDefined();
  });

  it("renders custom fallback when provided", () => {
    render(
      <ErrorBoundary fallback={<div>Custom fallback</div>}>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(screen.getByText("Custom fallback")).toBeDefined();
    expect(screen.queryByText("页面加载出错")).toBeNull();
  });

  it("renders retry button in default error UI", () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );
    const retryButton = screen.getByText("重试");
    expect(retryButton).toBeDefined();
    expect(retryButton.tagName).toBe("BUTTON");
  });

  it("resets error state when retry button is clicked", () => {
    // We need a component that can toggle throwing behavior
    let shouldThrow = true;

    function ConditionalThrower() {
      if (shouldThrow) throw new Error("Conditional error");
      return <div>Recovered content</div>;
    }

    const { rerender } = render(
      <ErrorBoundary>
        <ConditionalThrower />
      </ErrorBoundary>
    );

    // Verify error UI is shown
    expect(screen.getByText("页面加载出错")).toBeDefined();

    // Stop throwing, then click retry
    shouldThrow = false;
    fireEvent.click(screen.getByText("重试"));

    // After retry, the component should re-render children
    // Need to rerender to apply the new shouldThrow value
    rerender(
      <ErrorBoundary>
        <ConditionalThrower />
      </ErrorBoundary>
    );

    expect(screen.getByText("Recovered content")).toBeDefined();
    expect(screen.queryByText("页面加载出错")).toBeNull();
  });

  it("displays unknown error message when error has no message", () => {
    function EmptyErrorComponent(): React.ReactElement {
      throw new Error("");
    }

    render(
      <ErrorBoundary>
        <EmptyErrorComponent />
      </ErrorBoundary>
    );

    // The default fallback shows "发生未知错误" when error.message is empty
    expect(screen.getByText("发生未知错误")).toBeDefined();
  });
});
