import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import {
  MapContainer,
  Marker,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";
import type { Match } from "./types";

function Bounds({ matches }: { matches: Match[] }) {
  const map = useMap();
  useEffect(() => {
    if (matches.length)
      map.fitBounds(
        L.latLngBounds(matches.map((m) => [m.listing.lat, m.listing.lon])),
        { padding: [50, 50], maxZoom: 13 },
      );
    else map.setView([36.6, -119.5], 6);
  }, [matches, map]);
  return null;
}

function MatchMarker({
  match,
  active,
  setActive,
}: {
  match: Match;
  active: boolean;
  setActive: (id: string | null) => void;
}) {
  const ref = useRef<L.Marker>(null);
  const icon = useMemo(
    () =>
      L.divIcon({
        className: "match-marker",
        html: `<span class="pin"><b>${match.rank}</b></span>`,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
      }),
    [match.rank],
  );
  useEffect(() => {
    ref.current?.getElement()?.classList.toggle("is-active", active);
  }, [active]);
  const select = () => {
    setActive(match.listing.id);
    const card = document.getElementById(`listing-${match.listing.id}`);
    card?.focus({ preventScroll: true });
    card?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  const clearHover = () => {
    if (document.activeElement?.id !== `listing-${match.listing.id}`)
      setActive(null);
  };
  useEffect(() => {
    const element = ref.current?.getElement();
    if (!element) return;
    const focus = () => setActive(match.listing.id);
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select();
      }
    };
    element.addEventListener("focus", focus);
    element.addEventListener("keydown", keyboard);
    return () => {
      element.removeEventListener("focus", focus);
      element.removeEventListener("keydown", keyboard);
    };
  }, [match.listing.id, setActive]);
  return (
    <Marker
      ref={ref}
      position={[match.listing.lat, match.listing.lon]}
      title={`Recommendation ${match.rank}: ${match.listing.address}${match.listing.coordinate_precision === "zip_centroid" ? " (approximate ZIP center)" : ""}`}
      riseOnHover
      zIndexOffset={active ? 1000 : 0}
      icon={icon}
      eventHandlers={{
        mouseover: () => setActive(match.listing.id),
        mouseout: clearHover,
        click: select,
      }}
    >
      <Tooltip direction="top">
        {match.listing.address}
        {match.listing.coordinate_precision === "zip_centroid" &&
          " · approximate ZIP center"}
      </Tooltip>
    </Marker>
  );
}

export default function RecommendationMap({
  matches,
  active,
  setActive,
}: {
  matches: Match[];
  active: string | null;
  setActive: (id: string | null) => void;
}) {
  const [tileError, setTileError] = useState(false);
  return (
    <MapContainer
      center={[36.6, -119.5]}
      zoom={6}
      scrollWheelZoom={false}
      className="map"
      aria-label="Recommended restaurant locations"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        eventHandlers={{ tileerror: () => setTileError(true) }}
      />
      {tileError && (
        <div className="tile-error" role="status">
          Some map tiles are unavailable. Your shortlist still works.
        </div>
      )}
      <Bounds matches={matches} />
      {matches.map((match) => (
        <MatchMarker
          key={match.listing.id}
          match={match}
          active={active === match.listing.id}
          setActive={setActive}
        />
      ))}
    </MapContainer>
  );
}
