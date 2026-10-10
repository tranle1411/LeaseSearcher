import { lazy, Suspense, useEffect, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCheck,
  ChevronDown,
  Compass,
  Info,
  MapPin,
  SlidersHorizontal,
  Store,
  X,
} from "lucide-react";
import type { Metadata, Preferences, Results } from "./types";

const RecommendationMap = lazy(() => import("./Map"));
const money = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
const initial: Preferences = {
  cuisine: "Vietnamese",
  county: null,
  budget: 10000,
  sqft_min: 500,
  sqft_max: 4000,
  income_preference: "medium",
  population_preference: "high",
  use_ethnicity: false,
  require_parking: false,
  hide_unconfirmed: false,
  weights: { site: 40, location: 40, competition: 20 },
};

async function request<T>(path: string, body?: Preferences): Promise<T> {
  const response = await fetch(
    path,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : undefined,
  );
  if (!response.ok)
    throw new Error(
      response.status === 409
        ? "The dataset changed. Search again before downloading."
        : `The request could not be completed (${response.status}). Please try again.`,
    );
  return response.json();
}

export default function App() {
  const [metadata, setMetadata] = useState<Metadata>();
  const [form, setForm] = useState(initial);
  const [result, setResult] = useState<Results>();
  const [active, setActive] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [method, setMethod] = useState(false);
  const [mobileFilters, setMobileFilters] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!method) return;
    const opener = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    const controls = dialog?.querySelectorAll<HTMLElement>(
      "button, a[href], input, select",
    );
    controls?.[0]?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMethod(false);
      if (event.key === "Tab" && controls?.length) {
        const first = controls[0],
          last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", keyboard);
    return () => {
      document.removeEventListener("keydown", keyboard);
      opener?.focus();
    };
  }, [method]);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/metadata", { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then(setMetadata)
      .catch((e) => {
        if (e.name !== "AbortError")
          setError(
            "Unable to connect. A free demo may take about a minute to wake up. Try again shortly.",
          );
      });
    return () => controller.abort();
  }, [refresh]);
  const isDemo = metadata?.eligibility_policy === "demo_assumed";
  const update = <K extends keyof Preferences>(key: K, value: Preferences[K]) =>
    setForm((old) => ({ ...old, [key]: value }));
  const invalid =
    form.sqft_min > form.sqft_max ||
    form.budget <= 0 ||
    form.sqft_min <= 0 ||
    Object.values(form.weights).every((n) => n === 0);
  const dirty =
    result &&
    (Object.keys(form) as (keyof Preferences)[]).some(
      (key) => JSON.stringify(form[key]) !== JSON.stringify(result.search[key]),
    );

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (invalid) return;
    setBusy(true);
    setError("");
    try {
      setResult(await request<Results>("/api/search", form));
      setActive(null);
      setMobileFilters(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function download() {
    if (!result) return;
    setExporting(true);
    setError("");
    try {
      const response = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...result.search,
          dataset_version: result.dataset_version,
          evaluated_on: result.evaluated_on,
        }),
      });
      if (!response.ok)
        throw new Error(
          response.status === 409
            ? "The dataset changed. Search again before downloading."
            : "Download failed. Please try again.",
        );
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "lease-shortlist.xlsx";
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setExporting(false);
    }
  }
  return (
    <div className="shell">
      <header className="header">
        <a className="brand" href="/" aria-label="LeaseSearcher home">
          <span className="brand-icon">
            <Store size={21} />
          </span>
          Lease<span>Searcher</span>
          <small>LAB</small>
        </a>
        <div className="header-right">
          <span className="demo-badge">
            <i />
            Client demo
          </span>
          <button className="text-button" onClick={() => setMethod(true)}>
            How scoring works <ArrowUpRight size={15} />
          </button>
        </div>
      </header>
      <div className="workspace">
        <aside className={`sidebar ${mobileFilters ? "mobile-open" : ""}`}>
          <div className="sidebar-heading">
            <span className="eyebrow">THE BRIEF</span>
            <button
              className="mobile-only icon-button"
              aria-label="Close filters"
              onClick={() => setMobileFilters(false)}
            >
              <X />
            </button>
            <h2>
              Tell us about
              <br />
              your next restaurant.
            </h2>
            <p>A few essentials to narrow your search.</p>
          </div>
          <form onSubmit={search}>
            <section className="form-section">
              <h3>
                <span>01</span> Your concept
              </h3>
              <label htmlFor="cuisine">Cuisine</label>
              <select
                id="cuisine"
                value={form.cuisine}
                onChange={(e) => update("cuisine", e.target.value)}
              >
                {(metadata?.cuisines ?? ["Vietnamese"]).map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
              <p className="help">
                Compares observed restaurants of the same cuisine in each ZIP
                code.
              </p>
            </section>
            <section className="form-section">
              <h3>
                <span>02</span> The essentials
              </h3>
              <label htmlFor="county">Where in California?</label>
              <select
                id="county"
                value={form.county ?? ""}
                onChange={(e) => update("county", e.target.value || null)}
              >
                <option value="">All available counties</option>
                {metadata?.counties.map((v) => <option key={v}>{v}</option>)}
              </select>
              <label htmlFor="budget">
                {isDemo
                  ? "Monthly advertised rent budget"
                  : "Maximum monthly occupancy cost"}
              </label>
              <div className="input-affix">
                <span>$</span>
                <input
                  id="budget"
                  type="number"
                  min="1"
                  max="1000000"
                  required
                  value={form.budget}
                  onChange={(e) => update("budget", Number(e.target.value))}
                />
                <span>/ mo</span>
              </div>
              <p className="help">
                {isDemo
                  ? "Uses midpoint advertised rent and compatible space ranges, plus disclosed monthly fees. Unknown fees are excluded; actual costs may be higher."
                  : "Includes base rent and recurring occupancy fees. Unknown totals are excluded."}
              </p>
              <label htmlFor="minimum">
                Space required <small>sq ft</small>
              </label>
              <div className="range-input">
                <input
                  id="minimum"
                  aria-label="Minimum square feet"
                  type="number"
                  min="1"
                  max="200000"
                  required
                  value={form.sqft_min}
                  onChange={(e) => update("sqft_min", Number(e.target.value))}
                />
                <span>to</span>
                <input
                  aria-label="Maximum square feet"
                  type="number"
                  min="1"
                  max="200000"
                  required
                  value={form.sqft_max}
                  onChange={(e) => update("sqft_max", Number(e.target.value))}
                />
              </div>
              {form.sqft_min > form.sqft_max && (
                <p className="field-error">
                  Minimum space must be below the maximum.
                </p>
              )}
              <label className="check">
                <input
                  type="checkbox"
                  checked={form.require_parking}
                  onChange={(e) => update("require_parking", e.target.checked)}
                />
                {isDemo
                  ? "Require reported parking"
                  : "Require verified parking"}
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={form.hide_unconfirmed}
                  onChange={(e) => update("hide_unconfirmed", e.target.checked)}
                />
                Hide unconfirmed availability
              </label>
              <p className="help">
                Confirmed means checked within the past 30 days.
              </p>
            </section>
            <details className="preferences">
              <summary>
                <SlidersHorizontal size={15} />
                Fine-tune your priorities
                <ChevronDown size={14} />
              </summary>
              <div className="advanced">
                <label htmlFor="income">County household income</label>
                <select
                  id="income"
                  value={form.income_preference}
                  onChange={(e) =>
                    update(
                      "income_preference",
                      e.target.value as Preferences["income_preference"],
                    )
                  }
                >
                  <option value="low">Lower</option>
                  <option value="medium">Middle</option>
                  <option value="high">Higher</option>
                </select>
                <label htmlFor="population">County population</label>
                <select
                  id="population"
                  value={form.population_preference}
                  onChange={(e) =>
                    update(
                      "population_preference",
                      e.target.value as Preferences["population_preference"],
                    )
                  }
                >
                  <option value="low">Lower</option>
                  <option value="medium">Middle</option>
                  <option value="high">Higher</option>
                </select>
                <p className="help">
                  County totals describe broad context, not neighborhood demand.
                  Missing data scores a neutral 50.
                </p>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={form.use_ethnicity}
                    onChange={(e) => update("use_ethnicity", e.target.checked)}
                  />
                  Include broad Asian population share
                </label>
                <p className="help">
                  Optional context, not proof of cuisine preference. This metric
                  does not distinguish ethnic groups.
                </p>
                <h4>Score weights</h4>
                {(["site", "location", "competition"] as const).map((key) => (
                  <label className="weight" key={key}>
                    {key}
                    <input
                      aria-label={`${key} weight`}
                      type="range"
                      min="0"
                      max="100"
                      value={form.weights[key]}
                      onChange={(e) =>
                        update("weights", {
                          ...form.weights,
                          [key]: Number(e.target.value),
                        })
                      }
                    />
                    <output>{form.weights[key]}</output>
                  </label>
                ))}
                <p className="help">
                  Weights are normalized automatically. At least one must be
                  above zero.
                </p>
              </div>
            </details>
            <div className="form-footer">
              <button
                className="primary"
                type="submit"
                disabled={busy || invalid || !metadata}
              >
                {busy ? "Finding your matches…" : "Find matching spaces"}
                <ArrowRight size={18} />
              </button>
              <p>
                <CheckCheck size={13} />
                {isDemo
                  ? "Demo assumptions are labeled"
                  : "Strict verification is always on"}
              </p>
            </div>
          </form>
        </aside>
        <main>
          <div className="page-heading">
            <div>
              <span className="eyebrow">CALIFORNIA / LOCATION RESEARCH</span>
              <h1>
                A place for your
                <br />
                <em>next big idea.</em>
              </h1>
              <p>
                Explore restaurant spaces with a clear view of the evidence.
              </p>
            </div>
            <div className="snapshot-stamp">
              <span className="stamp-icon">
                <Compass size={25} />
              </span>
              <strong>California</strong>
              <span>Historical research snapshot</span>
              <small>{metadata?.collection_period ?? "Loading dataset…"}</small>
            </div>
          </div>
          <div className="notice">
            <Info size={18} />
            <p>
              {isDemo ? (
                <>
                  <strong>Demo assumptions.</strong> Listings are assumed to
                  exist and be restaurant-eligible. Rent and compatible space
                  ranges use midpoints. Undisclosed fees and exact unit
                  availability are unverified. This historical snapshot is not a
                  live availability feed.
                </>
              ) : (
                <>
                  <strong>Evidence before recommendations.</strong> Only spaces
                  with verified restaurant eligibility, complete monthly costs
                  and confirmed lease details can qualify. This historical
                  dataset is not a live availability feed.
                </>
              )}
            </p>
          </div>
          {(result?.mode ?? metadata?.mode) === "snapshot-fallback" && (
            <div className="notice" role="status">
              <Info size={18} />
              <p>
                Database unavailable. This search uses the identical pinned
                dataset; no records were substituted.
              </p>
            </div>
          )}
          {error && (
            <div className="error" role="alert">
              {error}{" "}
              {!metadata && (
                <button
                  onClick={() => {
                    setError("");
                    setRefresh((n) => n + 1);
                  }}
                >
                  Retry connection
                </button>
              )}
            </div>
          )}
          <div className="results-heading">
            <div>
              <h2>
                {result ? `Your shortlist` : "Explore the possibilities"}
                <span className="count">{result?.matches.length ?? "—"}</span>
              </h2>
              <p>
                {result
                  ? `${result.total_eligible} eligible of ${result.considered} historical listings reviewed`
                  : `${metadata?.listing_count ?? "…"} historical listings · explainable scores · up to 10 matches`}
              </p>
              {dirty && (
                <p className="dirty">
                  Preferences changed. Search again to update this shortlist.
                </p>
              )}
            </div>
            <div className="result-actions">
              <button
                className="secondary mobile-only"
                onClick={() => setMobileFilters(true)}
              >
                <SlidersHorizontal size={15} />
                Filters
              </button>
              <button
                className="secondary"
                disabled={!result || exporting}
                onClick={download}
              >
                <ArrowDownToLine size={15} />
                {exporting ? "Exporting…" : "Excel export"}
              </button>
            </div>
          </div>
          <div className="results-grid">
            <div className="list-panel" aria-live="polite">
              {!result || result.matches.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">
                    {result ? <CheckCheck size={28} /> : <MapPin size={28} />}
                  </div>
                  <span className="eyebrow">
                    {result
                      ? "A CLEAR ANSWER IS A USEFUL ANSWER"
                      : "YOUR SHORTLIST STARTS HERE"}
                  </span>
                  <h3>
                    {result
                      ? "No spaces meet every requirement."
                      : "Start with your restaurant brief."}
                  </h3>
                  <p>
                    {result
                      ? "The current records do not establish all the facts required to recommend a lease. We keep those spaces out of your shortlist."
                      : "Set your cuisine, budget and space needs. We’ll show only qualifying locations, with a transparent breakdown of each score."}
                  </p>
                  {result ? (
                    <div className="exclusions">
                      <h4>What kept listings out</h4>
                      {Object.entries(result.exclusions)
                        .sort((a, b) => b[1] - a[1])
                        .map(([reason, count]) => (
                          <div key={reason}>
                            <span>{reason}</span>
                            <strong>{count}</strong>
                          </div>
                        ))}
                      <p>
                        Counts overlap; a listing may fail more than one
                        requirement.
                      </p>
                    </div>
                  ) : (
                    <div className="empty-steps">
                      <span>
                        <Check size={15} />
                        {isDemo
                          ? "Advertised lease essentials"
                          : "Verified lease essentials"}
                      </span>
                      <span>
                        <Check size={15} />
                        Explainable fit, not a prediction
                      </span>
                      <span>
                        <Check size={15} />A shortlist you can export
                      </span>
                    </div>
                  )}
                  {result && (
                    <p className="next-step">
                      {isDemo ? (
                        <>
                          Try a wider space range, higher budget or another
                          county. Spaces without usable rent, size or map
                          coordinates remain excluded.
                        </>
                      ) : (
                        <>
                          <strong>To unlock real recommendations:</strong>{" "}
                          collect current unit details, written restaurant
                          eligibility evidence and a complete monthly cost
                          breakdown from the broker or owner.
                        </>
                      )}
                    </p>
                  )}
                </div>
              ) : (
                result.matches.map((match) => (
                  <article
                    id={`listing-${match.listing.id}`}
                    key={match.listing.id}
                    className={`listing-card ${active === match.listing.id ? "selected" : ""}`}
                    onMouseEnter={() => setActive(match.listing.id)}
                    onMouseLeave={() => setActive(null)}
                    onFocus={() => setActive(match.listing.id)}
                    onBlur={() => setActive(null)}
                    tabIndex={0}
                    aria-label={`Recommendation ${match.rank}: ${match.listing.address}`}
                  >
                    <div className="card-top">
                      <span className="rank">
                        {String(match.rank).padStart(2, "0")}
                      </span>
                      <span className="score">
                        {match.fit_score}
                        <small>/ 100 fit</small>
                      </span>
                    </div>
                    <h3>{match.listing.name}</h3>
                    <p className="address">
                      <MapPin size={13} />
                      {match.listing.address}
                    </p>
                    <div className="facts">
                      <strong>
                        {money(match.effective_monthly_cost)}
                        <small>
                          {match.cost_basis === "advertised_estimate"
                            ? "/ mo estimate"
                            : "/ mo total"}
                        </small>
                      </strong>
                      <span>
                        {match.listing.sqft_min.toLocaleString()}–
                        {match.listing.sqft_max.toLocaleString()} sq ft
                      </span>
                    </div>
                    {match.cost_basis === "advertised_estimate" && (
                      <p className="help">
                        Eligibility assumed · extra fees unknown
                        {match.assumed_sqft != null
                          ? ` · estimated ${match.assumed_sqft.toLocaleString()} sq ft`
                          : ""}
                      </p>
                    )}
                    {match.listing.coordinate_precision === "zip_centroid" && (
                      <p className="help">Approximate ZIP-center pin</p>
                    )}
                    {match.listing.advertised_price && (
                      <p className="help">
                        Advertised: {match.listing.advertised_price}
                      </p>
                    )}
                    <div className="score-bars">
                      {Object.entries(match.components).map(([key, value]) => (
                        <div key={key}>
                          <span>{key}</span>
                          <i>
                            <b style={{ width: `${value}%` }} />
                          </i>
                          <strong>{Math.round(value)}</strong>
                        </div>
                      ))}
                    </div>
                    <details>
                      <summary>Evidence & score details</summary>
                      <p>
                        Optional evidence coverage: {match.evidence_coverage}%
                      </p>
                      {match.listing.verification && (
                        <>
                          <p>
                            Verified through{" "}
                            {match.listing.verification.valid_until}
                          </p>
                          <p>{match.listing.verification.evidence}</p>
                        </>
                      )}
                      {match.listing.advertised_price && (
                        <p>Advertised: {match.listing.advertised_price}</p>
                      )}
                      {match.warnings.map((w) => (
                        <p key={w}>{w}</p>
                      ))}
                    </details>
                    <a
                      href={match.listing.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View original listing <ArrowUpRight size={14} />
                    </a>
                  </article>
                ))
              )}
            </div>
            <div className="map-panel">
              <div className="map-label">
                <span className="live-dot" />{" "}
                {result?.matches.length
                  ? "YOUR TOP LOCATIONS"
                  : "CALIFORNIA RESEARCH AREA"}
              </div>
              <Suspense
                fallback={<div className="map-placeholder">Loading map…</div>}
              >
                <RecommendationMap
                  matches={result?.matches ?? []}
                  active={active}
                  setActive={setActive}
                />
              </Suspense>
              <div className="map-caption">
                <MapPin size={14} />
                {result?.matches.length
                  ? "Hover or select a pin to explore its match."
                  : isDemo
                    ? "Pins appear for spaces with usable advertised details."
                    : "Pins appear only for verified recommendations."}
              </div>
            </div>
          </div>
          <details className="quality-panel">
            <summary>
              <span>
                <span className="eyebrow">UNDER THE HOOD</span>
                <strong>Know what’s in the data</strong>
              </span>
              <ChevronDown size={18} />
            </summary>
            <div className="quality-stats">
              <div>
                <strong>{metadata?.listing_count ?? "—"}</strong>
                <span>accepted listings</span>
              </div>
              <div>
                <strong>{metadata?.report.mapped_listings ?? "—"}</strong>
                <span>cached coordinates</span>
              </div>
              <div>
                <strong>{metadata?.report.verified_listings ?? "—"}</strong>
                <span>verification records</span>
              </div>
              <div>
                <strong>{metadata?.report.quarantined_rows ?? "—"}</strong>
                <span>quarantined rows</span>
              </div>
            </div>
            <p>
              {metadata?.demographics_available
                ? "County ACS aggregates available."
                : "County demographics are unavailable; those features receive neutral scores."}{" "}
              Restaurant observations do not measure foot traffic. Coverage is
              partial and historical.
            </p>
            <code>
              Dataset {metadata?.version ?? "loading"} ·{" "}
              {result?.mode ?? metadata?.mode}
            </code>
          </details>
          <footer>
            Built for informed first conversations.
            <span>Research demo · Always confirm details with the broker.</span>
          </footer>
        </main>
      </div>
      {method && (
        <div className="modal-backdrop" onClick={() => setMethod(false)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="method-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="icon-button close"
              aria-label="Close scoring explanation"
              onClick={() => setMethod(false)}
            >
              <X />
            </button>
            <span className="eyebrow">TRANSPARENT BY DESIGN</span>
            <h2 id="method-title">What a fit score means.</h2>
            <p>
              An explainable comparison of eligible spaces. It is not a
              prediction of revenue, demand or success.
            </p>
            <div className="method-row">
              <strong>40% Site</strong>
              <p>
                Budget headroom and overlap with your requested space range,
                weighted equally.
              </p>
            </div>
            <div className="method-row">
              <strong>40% Location</strong>
              <p>
                County household income (30%), population (40%) and optional
                broad Asian population share (30%). This does not describe the
                immediate neighborhood.
              </p>
            </div>
            <div className="method-row">
              <strong>20% Competition</strong>
              <p>
                Observed ZIP restaurant count (30%), same-cuisine count (50%)
                and prepared price-tier midpoint (20%). Fewer observed
                competitors and higher prepared price values score higher; that
                assumption may not suit every concept. Prepared price midpoints
                are not verified menu quotes.
              </p>
            </div>
            <p>
              Default weights come from the client’s final presentation. You can
              adjust them. Scaling uses the entire snapshot’s 10th and 90th
              percentiles, so changing county filters does not change the
              reference population. Constant or missing optional values receive
              50/100; evidence coverage is reported separately.
            </p>
            <p>
              {isDemo ? (
                <>
                  <strong>Demo eligibility.</strong> Existence and restaurant
                  suitability are assumed. Missing usable advertised rent,
                  offered size, coordinates or source links exclude a space.
                  Estimates use the midpoint rate and midpoint of the offered
                  size range overlapping your requested range. Unknown fees are
                  excluded, not treated as confirmed zero. No score predicts
                  permit approval or availability.
                </>
              ) : (
                <>
                  <strong>Eligibility comes first.</strong> Unverified
                  restaurant eligibility, total costs, lease details,
                  coordinates or source links exclude a space. No score can
                  override those rules.
                </>
              )}
            </p>
            <button className="primary" onClick={() => setMethod(false)}>
              Got it <Check size={16} />
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
