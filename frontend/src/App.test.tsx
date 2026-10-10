import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";

vi.mock("./Map", () => ({ default: () => <div>Map test boundary</div> }));
const metadata = {
  version: "test",
  collection_period: "2025",
  listing_count: 4,
  counties: ["Test County"],
  cuisines: ["Vietnamese"],
  report: { mapped_listings: 2, verified_listings: 0, quarantined_rows: 1 },
  mode: "snapshot",
  demographics_available: false,
};
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => metadata }),
  );
});

test("explains the strict gates and prevents an invalid range", async () => {
  render(<App />);
  const button = screen.getByRole("button", { name: "Find matching spaces" });
  await waitFor(() => expect(button).toBeEnabled());
  expect(screen.getByText(/Unknown totals are excluded/)).toBeInTheDocument();
  fireEvent.change(
    screen.getByRole("spinbutton", { name: "Minimum square feet" }),
    { target: { value: "5000" } },
  );
  expect(button).toBeDisabled();
  expect(screen.getByText(/Minimum space must be below/)).toBeInTheDocument();
});

test("shows zero matches with exclusion reasons, never fabricated pins", async () => {
  render(<App />);
  const button = screen.getByRole("button", { name: "Find matching spaces" });
  await waitFor(() => expect(button).toBeEnabled());
  vi.mocked(fetch).mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      dataset_version: "test",
      mode: "snapshot",
      matches: [],
      total_eligible: 0,
      considered: 4,
      exclusions: { "Complete monthly cost unknown": 4 },
      search: {},
    }),
  } as Response);
  await userEvent.click(button);
  expect(
    await screen.findByText("No spaces meet every requirement."),
  ).toBeInTheDocument();
  expect(screen.getByText("Complete monthly cost unknown")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Excel export" })).toBeEnabled();
});

test("failed API exposes retry and recovers", async () => {
  vi.mocked(fetch).mockRejectedValueOnce(new Error("offline"));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to connect",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Retry connection" }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Find matching spaces" }),
    ).toBeEnabled(),
  );
});

test("demo estimates render without a verification record", async () => {
  vi.mocked(fetch).mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      ...metadata,
      eligibility_policy: "demo_assumed",
      pricing_policy: "midpoint",
    }),
  } as Response);
  render(<App />);
  const button = screen.getByRole("button", { name: "Find matching spaces" });
  await waitFor(() => expect(button).toBeEnabled());
  expect(
    screen.getByLabelText("Monthly advertised rent budget"),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("Strict verification is always on"),
  ).not.toBeInTheDocument();
  vi.mocked(fetch).mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      dataset_version: "test",
      mode: "snapshot",
      considered: 4,
      total_eligible: 1,
      search: {},
      exclusions: {},
      matches: [
        {
          rank: 1,
          fit_score: 70,
          listing: {
            id: "demo",
            name: "Demo space",
            address: "Test address",
            source_url: "https://example.com",
            sqft_min: 1000,
            sqft_max: 1500,
            verification: null,
          },
          effective_monthly_cost: 3750,
          cost_basis: "advertised_estimate",
          assumed_sqft: 1250,
          evidence_coverage: 0,
          components: { site: 70 },
          warnings: ["Undisclosed fees remain unknown."],
          reasons: [],
          assumptions: [],
        },
      ],
    }),
  } as Response);
  await userEvent.click(button);
  expect(await screen.findByText("$3,750")).toBeInTheDocument();
  expect(screen.getByText("/ mo estimate")).toBeInTheDocument();
  expect(screen.getByText(/Eligibility assumed/)).toBeInTheDocument();
  expect(screen.queryByText(/Verified through/)).not.toBeInTheDocument();
});
