import { expect, test } from "@playwright/test";

test("real historical demo returns labeled estimates and downloads a workbook", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "A place for your next big idea." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Find matching spaces" }).click();
  await expect(page.locator(".listing-card")).toHaveCount(10);
  await expect(page.locator(".pin")).toHaveCount(10);
  await expect(
    page.getByText("Demo assumptions.", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".listing-card").first()).toContainText(
    "/ mo estimate",
  );
  await expect(page.locator(".listing-card").first()).toContainText(
    "Eligibility assumed",
  );
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Excel export" }).click();
  expect((await download).suggestedFilename()).toBe("lease-shortlist.xlsx");
  await page.getByRole("button", { name: "How scoring works" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Got it" }).click();
});

test("map and list hover both highlight the same fixture", async ({ page }) => {
  // Browser-only intercepted fixtures; never injected into production snapshot.
  const metadata = {
    version: "test-only",
    collection_period: "TEST ONLY",
    listing_count: 2,
    counties: ["Test County"],
    cuisines: ["Vietnamese"],
    report: { mapped_listings: 2, verified_listings: 2, quarantined_rows: 0 },
    mode: "test",
    demographics_available: false,
  };
  await page.route("**/api/metadata", (route) =>
    route.fulfill({ json: metadata }),
  );
  await page.route("**/api/search", async (route) => {
    const search = route.request().postDataJSON();
    const matches = [1, 2].map((i) => ({
      effective_monthly_cost: 2000,
      cost_basis: "verified_total",
      assumed_sqft: null,
      assumptions: [],
      rank: i,
      listing: {
        id: `test-${i}`,
        name: `TEST ONLY ${i}`,
        address: `TEST address ${i}`,
        county: "Test County",
        source_url: "https://example.com",
        lat: 34.05 + i * 0.01,
        lon: -118.24 + i * 0.01,
        sqft_min: 1000,
        sqft_max: 1000,
        verification: {
          monthly_occupancy_cost: 2000,
          valid_until: "2027-01-01",
          evidence: "TEST ONLY",
        },
      },
      fit_score: 70,
      evidence_coverage: 50,
      components: { site: 80, location: 50, competition: 60 },
      warnings: [],
      reasons: [],
    }));
    await route.fulfill({
      json: {
        dataset_version: "test-only",
        mode: "test",
        matches,
        total_eligible: 2,
        considered: 2,
        exclusions: {},
        search,
      },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Find matching spaces" }).click();
  const card = page.locator("#listing-test-1");
  await card.hover();
  await expect(page.locator(".is-active .pin")).toHaveText("1");
  await page.locator(".leaflet-marker-icon").nth(1).hover();
  await expect(page.locator("#listing-test-2")).toHaveClass(/selected/);
  await page.locator(".leaflet-marker-icon").first().focus();
  // Markers are keyboard-accessible links to selection as well.
  await page.locator(".leaflet-marker-icon").first().press("Enter");
  await expect(card).toHaveClass(/selected/);
});

test("mobile layout provides usable filter controls", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Filters", exact: true }).click();
  await expect(page.getByLabel("Cuisine", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Find matching spaces" }).click();
  await expect(page.locator(".listing-card")).toHaveCount(10);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
