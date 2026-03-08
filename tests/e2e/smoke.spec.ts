import { test, expect } from "@playwright/test";

test.describe("Smoke Tests", () => {
  test("homepage loads", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/AI News/i);
  });

  test("market page loads", async ({ page }) => {
    await page.goto("/market");
    await expect(page.locator("body")).toBeVisible();
  });

  test("news page loads", async ({ page }) => {
    await page.goto("/news");
    await expect(page.locator("body")).toBeVisible();
  });

  test("navigation links work", async ({ page }) => {
    await page.goto("/");
    // Check that main nav links exist
    const nav = page.locator("nav, header");
    await expect(nav).toBeVisible();
  });

  test("search input is accessible", async ({ page }) => {
    await page.goto("/market");
    const searchInput = page.locator(
      'input[type="text"], input[placeholder*="搜索"], input[placeholder*="search"]'
    );
    if ((await searchInput.count()) > 0) {
      await expect(searchInput.first()).toBeVisible();
    }
  });
});
