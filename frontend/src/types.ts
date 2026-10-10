export type Preferences = {
  cuisine: string;
  county: string | null;
  budget: number;
  sqft_min: number;
  sqft_max: number;
  income_preference: "low" | "medium" | "high";
  population_preference: "low" | "medium" | "high";
  use_ethnicity: boolean;
  require_parking: boolean;
  hide_unconfirmed: boolean;
  weights: { site: number; location: number; competition: number };
  dataset_version?: string;
  evaluated_on?: string;
};
export type Listing = {
  id: string;
  name: string;
  address: string;
  county: string;
  source_url: string;
  lat: number;
  lon: number;
  sqft_min: number;
  sqft_max: number;
  availability: string;
  coordinate_precision?: "address" | "zip_centroid";
  advertised_price?: string | null;
  verification: {
    monthly_occupancy_cost: number;
    valid_until: string;
    evidence: string;
  } | null;
};
export type Match = {
  effective_monthly_cost: number;
  cost_basis: "advertised_estimate" | "verified_total";
  assumed_sqft: number | null;
  assumptions: string[];
  rank: number;
  listing: Listing;
  fit_score: number;
  evidence_coverage: number;
  components: Record<string, number>;
  contributions: Record<string, number>;
  warnings: string[];
  reasons: string[];
};
export type Results = {
  dataset_version: string;
  evaluated_on: string;
  eligibility_policy?: "strict" | "demo_assumed";
  pricing_policy?: "conservative" | "midpoint";
  allow_zip_centroids?: boolean;
  mode: string;
  matches: Match[];
  total_eligible: number;
  considered: number;
  exclusions: Record<string, number>;
  search: Preferences;
};
export type Metadata = {
  version: string;
  collection_period: string;
  counties: string[];
  cuisines: string[];
  listing_count: number;
  eligibility_policy?: "strict" | "demo_assumed";
  pricing_policy?: "conservative" | "midpoint";
  allow_zip_centroids?: boolean;
  mode: string;
  demographics_available: boolean;
  report: {
    mapped_listings: number;
    verified_listings: number;
    quarantined_rows: number;
    limitations: string[];
  };
};
