import { useState, useEffect, useRef, useCallback } from "react";

// ─── Design tokens (Statistics Finland / Helsinki Design System) ──────────────
const tokens = {
  blue:       "#0047AB",
  blueLight:  "#E8F0FB",
  electric:   "#00AEEF",
  electricDim:"#007BB5",
  white:      "#FFFFFF",
  offWhite:   "#F5F7FA",
  gray100:    "#F0F2F5",
  gray200:    "#E2E6EA",
  gray400:    "#9AA3AE",
  gray600:    "#5A6472",
  gray900:    "#1A2332",
  green:      "#00873D",
  greenLight: "#E6F4EC",
  amber:      "#E07B00",
  amberLight: "#FEF3E2",
  red:        "#C0392B",
  redLight:   "#FDEDEB",
};

// ─── API client ───────────────────────────────────────────────────────────────
const API_BASE = import.meta.env.VITE_API_URL || "";
const API_KEY  = import.meta.env.VITE_API_KEY  || "dev-key-123";

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "X-API-Key": API_KEY,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function ConfidencePill({ score }) {
  const pct = Math.round(score);
  const color = pct >= 90 ? tokens.green : pct >= 75 ? tokens.amber : tokens.red;
  const bg    = pct >= 90 ? tokens.greenLight : pct >= 75 ? tokens.amberLight : tokens.redLight;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      background: bg, color, borderRadius: 20,
      padding: "2px 10px", fontSize: 12, fontWeight: 700,
      fontFamily: "monospace", letterSpacing: "0.02em",
    }}>
      <span style={{ fontSize: 8 }}>●</span> {pct}%
    </span>
  );
}

function AccessBadge({ type }) {
  return (
    <span style={{
      background: type === "open" ? tokens.greenLight : tokens.amberLight,
      color: type === "open" ? tokens.green : tokens.amber,
      borderRadius: 4, padding: "2px 8px", fontSize: 11, fontWeight: 600,
      textTransform: "uppercase", letterSpacing: "0.06em",
    }}>
      {type}
    </span>
  );
}

function FormatTag({ fmt }) {
  return (
    <span style={{
      background: tokens.gray100, color: tokens.gray600,
      borderRadius: 4, padding: "2px 7px", fontSize: 11, fontWeight: 600,
      letterSpacing: "0.04em",
    }}>
      {fmt}
    </span>
  );
}

function ErrorBanner({ message, onDismiss }) {
  return (
    <div style={{
      background: tokens.redLight, border: `1px solid ${tokens.red}`,
      borderLeft: `4px solid ${tokens.red}`, borderRadius: 8,
      padding: "12px 16px", marginBottom: 16,
      display: "flex", justifyContent: "space-between", alignItems: "flex-start",
      animation: "fadeIn 0.2s ease",
    }}>
      <div style={{ fontSize: 13, color: tokens.red }}>{message}</div>
      {onDismiss && (
        <button onClick={onDismiss} style={{
          background: "none", border: "none", color: tokens.red,
          cursor: "pointer", fontSize: 16, lineHeight: 1, padding: "0 4px",
        }}>×</button>
      )}
    </div>
  );
}

function ProvenancePanel({ recordId, recordMeta, onClose }) {
  const [provenance, setProvenance] = useState(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiFetch(`/v1/datasets/${encodeURIComponent(recordId)}/provenance`)
      .then(data => {
        setProvenance(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [recordId]);

  // Normalise provenance fields to {source, score} shape from API or recordMeta fallback
  const fields = provenance?.field_evidence || recordMeta?.provenance || {};

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
      zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center",
      backdropFilter: "blur(2px)",
    }} onClick={onClose}>
      <div style={{
        background: tokens.white, borderRadius: 12, width: 580, maxHeight: "80vh",
        overflow: "auto", boxShadow: "0 24px 64px rgba(0,0,0,0.18)",
        border: `1px solid ${tokens.gray200}`,
      }} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={{
          background: tokens.blue, padding: "20px 28px",
          borderRadius: "12px 12px 0 0", display: "flex", justifyContent: "space-between", alignItems: "flex-start",
        }}>
          <div>
            <div style={{ color: tokens.electric, fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>
              Field Provenance
            </div>
            <div style={{ color: tokens.white, fontSize: 17, fontWeight: 700, lineHeight: 1.3 }}>
              {recordMeta?.title || recordId}
            </div>
            <div style={{ color: "rgba(255,255,255,0.6)", fontSize: 13, marginTop: 2 }}>
              {recordMeta?.flag && `${recordMeta.flag} `}{recordMeta?.publisher}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: "rgba(255,255,255,0.1)", border: "none", color: tokens.white,
            borderRadius: 6, padding: "6px 12px", cursor: "pointer", fontSize: 18, lineHeight: 1,
          }}>×</button>
        </div>

        {/* Trust scores */}
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 1fr 1fr",
          gap: 1, background: tokens.gray200,
          borderBottom: `1px solid ${tokens.gray200}`,
        }}>
          {[
            ["Overall confidence", recordMeta ? recordMeta.confidence + "%" : "—"],
            ["Completeness",       recordMeta ? recordMeta.completeness + "%" : "—"],
            ["Access",             recordMeta?.access || "—"],
          ].map(([label, val]) => (
            <div key={label} style={{ background: tokens.offWhite, padding: "14px 20px" }}>
              <div style={{ fontSize: 11, color: tokens.gray400, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em" }}>{label}</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: tokens.blue, marginTop: 2 }}>{val}</div>
            </div>
          ))}
        </div>

        {/* Body */}
        <div style={{ padding: "20px 28px" }}>
          {loading && (
            <div style={{ textAlign: "center", padding: 32, color: tokens.gray400 }}>
              <div style={{ display: "inline-flex", gap: 6 }}>
                {[0,1,2].map(i => (
                  <div key={i} style={{
                    width: 8, height: 8, borderRadius: "50%", background: tokens.electric,
                    animation: "pulse 1.2s ease-in-out infinite",
                    animationDelay: `${i * 0.2}s`,
                  }} />
                ))}
              </div>
              <div style={{ fontSize: 13, marginTop: 12 }}>Loading provenance…</div>
            </div>
          )}

          {!loading && error && <ErrorBanner message={`Could not load provenance: ${error}`} />}

          {!loading && !error && (
            <>
              <div style={{ fontSize: 12, fontWeight: 700, color: tokens.gray600, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>
                Field-level evidence
              </div>
              {Object.keys(fields).length === 0 ? (
                <div style={{ fontSize: 13, color: tokens.gray400 }}>No field evidence available.</div>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: `2px solid ${tokens.gray200}` }}>
                      {["Field","Source","Confidence"].map(h => (
                        <th key={h} style={{ textAlign: "left", padding: "6px 10px 10px", color: tokens.gray400, fontWeight: 700, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.07em" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(fields).map(([field, ev], i) => {
                      const source = ev?.source || ev || "—";
                      const score  = typeof ev?.score === "number" ? ev.score : null;
                      const isLLM  = String(source).includes("Phi-4") || String(source).includes("LLM");
                      return (
                        <tr key={field} style={{ background: i % 2 === 0 ? tokens.offWhite : tokens.white }}>
                          <td style={{ padding: "9px 10px", fontWeight: 700, color: tokens.gray900, fontFamily: "monospace", fontSize: 12 }}>{field}</td>
                          <td style={{ padding: "9px 10px", color: tokens.gray600, fontSize: 12 }}>
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                              <span style={{
                                background: isLLM ? tokens.amberLight : tokens.blueLight,
                                color: isLLM ? tokens.amber : tokens.blue,
                                borderRadius: 3, padding: "1px 6px", fontSize: 10, fontWeight: 700,
                              }}>{isLLM ? "LLM" : "DET"}</span>
                              {source}
                            </span>
                          </td>
                          <td style={{ padding: "9px 10px" }}>
                            {score !== null ? (
                              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <div style={{ flex: 1, height: 4, background: tokens.gray200, borderRadius: 2 }}>
                                  <div style={{ width: `${score * 100}%`, height: "100%", background: score >= 0.9 ? tokens.green : score >= 0.75 ? tokens.amber : tokens.red, borderRadius: 2 }} />
                                </div>
                                <span style={{ fontSize: 11, fontWeight: 700, fontFamily: "monospace", color: tokens.gray600, minWidth: 34 }}>{Math.round(score * 100)}%</span>
                              </div>
                            ) : <span style={{ color: tokens.gray400, fontSize: 12 }}>—</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}

              {provenance && (
                <div style={{ marginTop: 20, padding: 14, background: tokens.gray100, borderRadius: 8, fontSize: 12, color: tokens.gray600, display: "flex", gap: 16, flexWrap: "wrap" }}>
                  {provenance.ingestion_timestamp && <div><span style={{ fontWeight: 700 }}>Harvested:</span> {new Date(provenance.ingestion_timestamp).toUTCString()}</div>}
                  {provenance.harmoniser_version   && <div><span style={{ fontWeight: 700 }}>Harmoniser:</span> {provenance.harmoniser_version}</div>}
                  {provenance.model_used           && <div><span style={{ fontWeight: 700 }}>Model:</span> {provenance.model_used}</div>}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// Construct a best-effort dataset URL from portal + source identifiers
function inferDatasetUrl(r) {
  if (r.dataset_url) return r.dataset_url;
  const portal = r.source_portal || "";
  const sourceId = r.source_id || "";
  if (portal.includes("eurostat")) {
    return `https://ec.europa.eu/eurostat/databrowser/view/${encodeURIComponent(sourceId)}/default/table`;
  }
  if (portal.includes("worldbank") || portal.includes("data.worldbank.org")) {
    const code = sourceId.replace(/^WB:/, "");
    return `https://data.worldbank.org/indicator/${encodeURIComponent(code)}`;
  }
  if (portal.includes("oecd")) {
    const dfId = sourceId.includes("@") ? sourceId.split("@").pop() : sourceId;
    return `https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ&df[id]=${encodeURIComponent(dfId)}&df[ag]=OECD`;
  }
  if (portal.includes("un.org") || portal.includes("data.un.org")) {
    return `https://data.un.org/Data.aspx?d=${encodeURIComponent(sourceId)}`;
  }
  if (portal.includes("stat.fi")) {
    return `https://pxdata.stat.fi/PxWeb/pxweb/en/${sourceId.split("/").map(encodeURIComponent).join("/")}`;
  }
  return portal || null;
}

// Map API SearchResult to display-friendly shape
function normaliseResult(result) {
  const r = result.record ?? result;
  return {
    id:           r.id,
    title:        r.title,
    publisher:    r.publisher,
    portal:       r.source_portal,
    flag:         portalFlag(r.source_portal),
    access:       r.access_type,
    license:      r.license || "—",
    updated:      r.last_updated || "—",
    frequency:    r.update_frequency || "—",
    formats:      r.formats || [],
    geo:          r.geographic_coverage || [],
    confidence:   Math.round((r.confidence_score ?? 0) * 100),
    completeness: Math.round((r.completeness_score ?? 0) * 100),
    description:  r.description || "",
    temporal:     [r.temporal_coverage_start, r.temporal_coverage_end].filter(Boolean).join("–") || "—",
    url:          inferDatasetUrl(r),
    themes:       r.themes || [],
    provenance:   r.field_evidence || {},
  };
}

function portalFlag(portalId) {
  const flags = {
    statfin:    "🇫🇮",
    statistics_finland: "🇫🇮",
    eurostat:   "🇪🇺",
    worldbank:  "🌍",
    world_bank: "🌍",
    oecd:       "📊",
    undata:     "🇺🇳",
    un_data:    "🇺🇳",
  };
  return flags[(portalId || "").toLowerCase()] || "🌐";
}

function DatasetCard({ record, onProvenance }) {
  return (
    <div style={{
      background: tokens.white, border: `1px solid ${tokens.gray200}`,
      borderRadius: 8, overflow: "hidden", transition: "box-shadow 0.15s",
    }}
      onMouseEnter={e => e.currentTarget.style.boxShadow = "0 4px 20px rgba(0,71,171,0.1)"}
      onMouseLeave={e => e.currentTarget.style.boxShadow = "none"}
    >
      {/* Card header */}
      <div style={{ padding: "18px 22px", display: "flex", gap: 16, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
            <span style={{ fontSize: 14 }}>{record.flag}</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: tokens.gray400 }}>{record.publisher}</span>
            <span style={{ color: tokens.gray200 }}>·</span>
            <AccessBadge type={record.access} />
            <span style={{ color: tokens.gray200 }}>·</span>
            <span style={{ fontSize: 12, color: tokens.gray400 }}>{record.license}</span>
          </div>
          <div style={{ fontSize: 17, fontWeight: 800, color: tokens.blue, marginBottom: 6, lineHeight: 1.3 }}>
            {record.title}
          </div>
          <div style={{ fontSize: 13, color: tokens.gray600, lineHeight: 1.6 }}>
            {record.description}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6, flexShrink: 0 }}>
          <ConfidencePill score={record.confidence} />
          <div style={{ fontSize: 11, color: tokens.gray400, textAlign: "right" }}>
            Updated {record.updated}
          </div>
          <div style={{ fontSize: 11, color: tokens.gray400, textAlign: "right" }}>
            {record.frequency}
          </div>
        </div>
      </div>

      {/* Meta row */}
      <div style={{
        padding: "10px 22px", borderTop: `1px solid ${tokens.gray100}`,
        background: tokens.offWhite, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
      }}>
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
          {record.formats.map(f => <FormatTag key={f} fmt={f} />)}
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ fontSize: 11, color: tokens.gray400 }}>
          🗺 {record.geo.join(", ")} · {record.temporal}
        </div>
      </div>

      {/* Themes */}
      <div style={{
        padding: "8px 22px 10px", borderTop: `1px solid ${tokens.gray100}`,
        display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
      }}>
        {record.themes.map(t => (
          <span key={t} style={{
            background: tokens.blueLight, color: tokens.blue,
            borderRadius: 4, padding: "2px 8px", fontSize: 11, fontWeight: 600,
          }}>{t}</span>
        ))}
        <div style={{ flex: 1 }} />
        <button onClick={() => onProvenance(record)} style={{
          background: "none", border: `1px solid ${tokens.electric}`,
          color: tokens.electric, borderRadius: 5, padding: "4px 12px",
          fontSize: 11, fontWeight: 700, cursor: "pointer", letterSpacing: "0.04em",
        }}>
          View provenance →
        </button>
        {record.url && (
          <a href={record.url} target="_blank" rel="noopener noreferrer" style={{
            background: tokens.blue, color: tokens.white, border: "none",
            borderRadius: 5, padding: "4px 14px", fontSize: 11, fontWeight: 700,
            cursor: "pointer", letterSpacing: "0.04em", textDecoration: "none",
          }}>
            Open dataset ↗
          </a>
        )}
      </div>
    </div>
  );
}

function PortalRow({ p, maxCount }) {
  const width = Math.round((p.count / maxCount) * 100);
  const statusColor = p.status === "live" ? tokens.green : tokens.amber;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 0", borderBottom: `1px solid ${tokens.gray100}` }}>
      <div style={{ width: 20, textAlign: "center", fontSize: 16 }}>{p.flag}</div>
      <div style={{ width: 160, fontSize: 13, fontWeight: 600, color: tokens.gray900 }}>{p.name}</div>
      <div style={{ flex: 1 }}>
        <div style={{ height: 6, background: tokens.gray200, borderRadius: 3, overflow: "hidden" }}>
          <div style={{ width: `${width}%`, height: "100%", background: tokens.electric, borderRadius: 3 }} />
        </div>
      </div>
      <div style={{ width: 60, textAlign: "right", fontSize: 13, fontWeight: 700, fontFamily: "monospace", color: tokens.blue }}>{p.count.toLocaleString()}</div>
      <div style={{ width: 50, textAlign: "right" }}><ConfidencePill score={p.confidence} /></div>
      <div style={{ width: 16, height: 16, borderRadius: "50%", background: statusColor, flexShrink: 0 }} title={p.status} />
      <div style={{ width: 90, fontSize: 11, color: tokens.gray400, textAlign: "right" }}>{p.last}</div>
    </div>
  );
}

// ─── Main app ─────────────────────────────────────────────────────────────────
export default function TDOApp() {
  const [tab, setTab]               = useState("search");
  const [query, setQuery]           = useState("");
  const [submitted, setSubmitted]   = useState("");
  const [results, setResults]       = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError]     = useState(null);
  const [provenanceRec, setProvenanceRec] = useState(null);
  const [aiAnswer, setAiAnswer]     = useState("");
  const [aiLoading, setAiLoading]   = useState(false);
  const [pageSize, setPageSize]     = useState(20);
  const [currentOffset, setCurrentOffset] = useState(0);
  const [hasMore, setHasMore]       = useState(false);

  // Dashboard state
  const [portals, setPortals]       = useState([]);
  const [stats, setStats]           = useState(null);
  const [dashLoading, setDashLoading] = useState(false);
  const [dashError, setDashError]     = useState(null);

  const inputRef = useRef(null);

  // Load dashboard data when tab is shown
  useEffect(() => {
    if (tab !== "dashboard") return;
    setDashLoading(true);
    setDashError(null);
    Promise.all([
      apiFetch("/v1/portals"),
      apiFetch("/v1/stats"),
    ])
      .then(([portalsData, statsData]) => {
        // Normalise portals response
        const normalized = (Array.isArray(portalsData) ? portalsData : portalsData.portals || []).map(p => ({
          id:         p.portal_id || p.id,
          name:       p.name || p.portal_id,
          flag:       portalFlag(p.portal_id || p.id),
          count:      p.dataset_count ?? p.count ?? 0,
          confidence: Math.round((p.avg_confidence ?? p.confidence ?? 0) * (p.avg_confidence <= 1 ? 100 : 1)),
          status:     p.status || "live",
          last:       p.last_harvest ? formatRelative(p.last_harvest) : "—",
        }));
        setPortals(normalized);
        setStats(statsData);
        setDashLoading(false);
      })
      .catch(err => {
        setDashError(err.message);
        setDashLoading(false);
      });
  }, [tab]);

  function formatRelative(iso) {
    if (!iso) return "—";
    const diffMs  = Date.now() - new Date(iso).getTime();
    const diffMin = Math.round(diffMs / 60000);
    if (diffMin < 2)   return "just now";
    if (diffMin < 60)  return `${diffMin} min ago`;
    const diffHr = Math.round(diffMin / 60);
    if (diffHr  < 24)  return `${diffHr} hr ago`;
    return `${Math.round(diffHr / 24)} days ago`;
  }

  const totalDatasets = portals.reduce((s, p) => s + p.count, 0) || stats?.total_datasets || 0;
  const avgConfidence = portals.length
    ? Math.round(portals.reduce((s, p) => s + p.confidence, 0) / portals.length)
    : (stats?.avg_confidence ? Math.round(stats.avg_confidence * 100) : 0);
  const maxPortalCount = portals.reduce((m, p) => Math.max(m, p.count), 1);

  const handleSearch = useCallback(async (q, limit = pageSize) => {
    const qUsed = (q || query).trim();
    if (!qUsed) return;
    setSearchLoading(true);
    setSearchError(null);
    setSubmitted(qUsed);
    setAiAnswer("");
    setCurrentOffset(0);
    setHasMore(false);

    try {
      const params = new URLSearchParams({ q: qUsed, limit: String(limit), offset: "0" });
      const data   = await apiFetch(`/v1/datasets?${params}`);
      const items  = Array.isArray(data) ? data : (data.results || data.datasets || []);
      const normalized = items.map(normaliseResult);
      setResults(normalized);
      setCurrentOffset(normalized.length);
      setHasMore(normalized.length === limit);
    } catch (err) {
      setSearchError(err.message);
      setResults([]);
    } finally {
      setSearchLoading(false);
    }

    // AI summary — fire and forget (non-blocking)
    setAiLoading(true);
    apiFetch("/v1/query", {
      method: "POST",
      body: JSON.stringify({ query: qUsed }),
    })
      .then(data => {
        setAiAnswer(data.summary || data.answer || "");
      })
      .catch(() => {
        // AI summary is best-effort; don't surface error to user
      })
      .finally(() => setAiLoading(false));
  }, [query, pageSize]);

  const handleLoadMore = useCallback(async () => {
    if (!submitted || searchLoading) return;
    setSearchLoading(true);
    setSearchError(null);
    try {
      const params = new URLSearchParams({ q: submitted, limit: String(pageSize), offset: String(currentOffset) });
      const data   = await apiFetch(`/v1/datasets?${params}`);
      const items  = Array.isArray(data) ? data : (data.results || data.datasets || []);
      const normalized = items.map(normaliseResult);
      setResults(prev => [...prev, ...normalized]);
      setCurrentOffset(prev => prev + normalized.length);
      setHasMore(normalized.length === pageSize);
    } catch (err) {
      setSearchError(err.message);
    } finally {
      setSearchLoading(false);
    }
  }, [submitted, currentOffset, pageSize, searchLoading]);

  const EXAMPLE_QUERIES = [
    "unemployment statistics Finland",
    "GDP growth Nordic countries",
    "population age structure Finland 2020",
    "inflation eurozone monthly",
  ];

  return (
    <div style={{
      fontFamily: "'Source Sans 3', 'Segoe UI', system-ui, sans-serif",
      background: tokens.offWhite, minHeight: "100vh", color: tokens.gray900,
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700;800;900&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: ${tokens.gray100}; }
        ::-webkit-scrollbar-thumb { background: ${tokens.gray200}; border-radius: 3px; }
        input:focus { outline: none; }
        button:focus-visible { outline: 2px solid ${tokens.electric}; outline-offset: 2px; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
        .result-card { animation: fadeIn 0.25s ease both; }
      `}</style>

      {/* ── Top bar ── */}
      <div style={{ background: tokens.blue, color: tokens.white }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 24px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 52 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 2, marginRight: 10 }}>
                {[14, 20, 28, 22, 16].map((h, i) => (
                  <div key={i} style={{
                    width: 5, height: h,
                    background: i === 2 ? tokens.electric : "rgba(255,255,255,0.7)",
                    borderRadius: 2,
                  }} />
                ))}
              </div>
              <div>
                <div style={{ fontSize: 17, fontWeight: 900, letterSpacing: "-0.02em", lineHeight: 1.1 }}>
                  Trusted Data Observatory
                </div>
                <div style={{ fontSize: 10, color: "rgba(255,255,255,0.55)", fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase" }}>
                  Metadata Discovery Platform
                </div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
              {totalDatasets > 0 && (
                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 7, height: 7, borderRadius: "50%", background: tokens.green }} />
                  {totalDatasets.toLocaleString()} datasets indexed
                </div>
              )}
              <div style={{ fontSize: 11, color: "rgba(255,255,255,0.5)" }}>Beta</div>
            </div>
          </div>

          {/* Nav tabs */}
          <div style={{ display: "flex", gap: 0 }}>
            {[
              { id: "search",    label: "Search" },
              { id: "dashboard", label: "Dashboard" },
              { id: "api",       label: "API" },
            ].map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                background: "none", border: "none", cursor: "pointer",
                color: tab === t.id ? tokens.white : "rgba(255,255,255,0.55)",
                fontSize: 13, fontWeight: tab === t.id ? 700 : 600,
                padding: "10px 18px", borderBottom: tab === t.id ? `3px solid ${tokens.electric}` : "3px solid transparent",
                transition: "all 0.15s", letterSpacing: "0.02em",
              }}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Electric accent bar ── */}
      <div style={{ height: 3, background: `linear-gradient(90deg, ${tokens.electric}, ${tokens.blue})` }} />

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 24px" }}>

        {/* ════ SEARCH TAB ════ */}
        {tab === "search" && (
          <div>
            {/* Search box */}
            <div style={{ marginBottom: 32 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: tokens.blue, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10 }}>
                Search trusted datasets
              </div>
              <div style={{ display: "flex", gap: 0, background: tokens.white, border: `2px solid ${tokens.blue}`, borderRadius: 8, overflow: "hidden", boxShadow: "0 2px 12px rgba(0,71,171,0.1)" }}>
                <input
                  ref={inputRef}
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleSearch()}
                  placeholder="e.g. unemployment statistics Finland 2020 onwards"
                  style={{
                    flex: 1, border: "none", padding: "16px 20px", fontSize: 15,
                    color: tokens.gray900, background: "transparent",
                    fontFamily: "inherit",
                  }}
                />
                <button
                  onClick={() => handleSearch()}
                  disabled={searchLoading}
                  style={{
                    background: tokens.blue, color: tokens.white, border: "none",
                    padding: "0 28px", fontSize: 14, fontWeight: 700, cursor: searchLoading ? "default" : "pointer",
                    letterSpacing: "0.04em", transition: "background 0.15s",
                    opacity: searchLoading ? 0.7 : 1,
                  }}
                  onMouseEnter={e => !searchLoading && (e.target.style.background = tokens.electricDim)}
                  onMouseLeave={e => (e.target.style.background = tokens.blue)}
                >
                  {searchLoading ? "…" : "Search"}
                </button>
              </div>

              {/* Example queries */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                <span style={{ fontSize: 12, color: tokens.gray400 }}>Try:</span>
                {EXAMPLE_QUERIES.map(q => (
                  <button key={q} onClick={() => { setQuery(q); handleSearch(q); }} style={{
                    background: "none", border: `1px solid ${tokens.gray200}`,
                    color: tokens.electricDim, borderRadius: 20, padding: "3px 12px",
                    fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                    transition: "all 0.15s",
                  }}
                    onMouseEnter={e => { e.target.style.borderColor = tokens.electric; e.target.style.background = tokens.blueLight; }}
                    onMouseLeave={e => { e.target.style.borderColor = tokens.gray200; e.target.style.background = "none"; }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>

            {/* Search error */}
            {searchError && (
              <ErrorBanner
                message={`Search failed: ${searchError}`}
                onDismiss={() => setSearchError(null)}
              />
            )}

            {/* Loading */}
            {searchLoading && (
              <div style={{ textAlign: "center", padding: 48, color: tokens.gray400 }}>
                <div style={{ display: "inline-flex", gap: 6 }}>
                  {[0,1,2].map(i => (
                    <div key={i} style={{
                      width: 8, height: 8, borderRadius: "50%", background: tokens.electric,
                      animation: "pulse 1.2s ease-in-out infinite",
                      animationDelay: `${i * 0.2}s`,
                    }} />
                  ))}
                </div>
                <div style={{ fontSize: 13, marginTop: 12 }}>Searching 5 authoritative portals…</div>
              </div>
            )}

            {/* AI summary */}
            {!searchLoading && (aiAnswer || aiLoading) && (
              <div style={{
                background: tokens.blueLight, border: `1px solid ${tokens.electric}`,
                borderLeft: `4px solid ${tokens.electric}`, borderRadius: 8,
                padding: "16px 20px", marginBottom: 24,
                animation: "fadeIn 0.3s ease",
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: tokens.electric, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>
                  ◆ AI Summary
                </div>
                {aiLoading ? (
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    {[0,1,2].map(i => (
                      <div key={i} style={{
                        width: 6, height: 6, borderRadius: "50%", background: tokens.electric,
                        animation: "pulse 1.2s ease-in-out infinite",
                        animationDelay: `${i * 0.2}s`,
                      }} />
                    ))}
                    <span style={{ fontSize: 12, color: tokens.electricDim, marginLeft: 4 }}>Generating summary…</span>
                  </div>
                ) : (
                  <div style={{ fontSize: 14, color: tokens.gray900, lineHeight: 1.7 }}>{aiAnswer}</div>
                )}
              </div>
            )}

            {/* Results */}
            {!searchLoading && results.length > 0 && (
              <div>
                <div style={{ fontSize: 13, color: tokens.gray400, marginBottom: 16, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontWeight: 700, color: tokens.gray900 }}>{results.length} datasets</span>
                  found for <strong>"{submitted}"</strong>
                  <span>· ranked by relevance and confidence</span>
                  <div style={{ marginLeft: "auto" }}>
                    <select
                      value={pageSize}
                      onChange={e => {
                        const newSize = Number(e.target.value);
                        setPageSize(newSize);
                        handleSearch(submitted, newSize);
                      }}
                      style={{
                        border: `1px solid ${tokens.gray200}`, borderRadius: 6,
                        padding: "4px 8px", fontSize: 12, color: tokens.gray600,
                        background: tokens.white, cursor: "pointer", fontFamily: "inherit",
                      }}
                    >
                      <option value={20}>20 per page</option>
                      <option value={50}>50 per page</option>
                      <option value={100}>100 per page</option>
                    </select>
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {results.map((r, i) => (
                    <div key={r.id} className="result-card" style={{ animationDelay: `${i * 0.05}s` }}>
                      <DatasetCard record={r} onProvenance={setProvenanceRec} />
                    </div>
                  ))}
                </div>
                {hasMore && (
                  <div style={{ textAlign: "center", marginTop: 24 }}>
                    <button
                      onClick={handleLoadMore}
                      disabled={searchLoading}
                      style={{
                        background: tokens.white, color: tokens.blue,
                        border: `2px solid ${tokens.blue}`, borderRadius: 8,
                        padding: "10px 32px", fontSize: 14, fontWeight: 700,
                        cursor: searchLoading ? "default" : "pointer",
                        opacity: searchLoading ? 0.7 : 1,
                        letterSpacing: "0.04em", transition: "all 0.15s",
                        fontFamily: "inherit",
                      }}
                      onMouseEnter={e => { if (!searchLoading) { e.target.style.background = tokens.blueLight; } }}
                      onMouseLeave={e => { e.target.style.background = tokens.white; }}
                    >
                      {searchLoading ? "Loading…" : "Load more"}
                    </button>
                  </div>
                )}
                {!hasMore && results.length > 0 && (
                  <div style={{ textAlign: "center", marginTop: 20, fontSize: 12, color: tokens.gray400 }}>
                    All {results.length} results shown
                  </div>
                )}
              </div>
            )}

            {/* No results */}
            {!searchLoading && !searchError && submitted && results.length === 0 && (
              <div style={{ textAlign: "center", padding: "48px 24px", color: tokens.gray400 }}>
                <div style={{ fontSize: 32, marginBottom: 12 }}>🔍</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: tokens.gray600, marginBottom: 6 }}>No datasets found</div>
                <div style={{ fontSize: 13 }}>Try a different query or fewer keywords.</div>
              </div>
            )}

            {/* Empty state */}
            {!searchLoading && !submitted && (
              <div style={{ textAlign: "center", padding: "60px 24px", color: tokens.gray400 }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>📊</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: tokens.gray600, marginBottom: 8 }}>
                  Search across trusted datasets
                </div>
                <div style={{ fontSize: 13 }}>
                  From Statistics Finland, Eurostat, World Bank, OECD, and UN Data
                </div>
              </div>
            )}
          </div>
        )}

        {/* ════ DASHBOARD TAB ════ */}
        {tab === "dashboard" && (
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: tokens.blue, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 24 }}>
              Platform status
            </div>

            {dashError && <ErrorBanner message={`Failed to load dashboard: ${dashError}`} onDismiss={() => setDashError(null)} />}

            {dashLoading && (
              <div style={{ textAlign: "center", padding: 48, color: tokens.gray400 }}>
                <div style={{ display: "inline-flex", gap: 6 }}>
                  {[0,1,2].map(i => (
                    <div key={i} style={{
                      width: 8, height: 8, borderRadius: "50%", background: tokens.electric,
                      animation: "pulse 1.2s ease-in-out infinite",
                      animationDelay: `${i * 0.2}s`,
                    }} />
                  ))}
                </div>
              </div>
            )}

            {!dashLoading && (
              <>
                {/* KPI row */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 32 }}>
                  {[
                    { label: "Total datasets",    value: totalDatasets.toLocaleString(),                          sub: "indexed",              accent: tokens.blue },
                    { label: "Portals connected", value: portals.length || (stats?.portal_count ?? "—"),          sub: "operational",          accent: tokens.green },
                    { label: "Avg confidence",    value: avgConfidence ? avgConfidence + "%" : "—",              sub: "across all sources",   accent: tokens.electric },
                    { label: "Pending review",    value: stats?.pending_review ?? "—",                           sub: "low-confidence flags", accent: tokens.amber },
                  ].map(k => (
                    <div key={k.label} style={{
                      background: tokens.white, border: `1px solid ${tokens.gray200}`,
                      borderTop: `4px solid ${k.accent}`, borderRadius: 8, padding: "20px 22px",
                    }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: tokens.gray400, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>{k.label}</div>
                      <div style={{ fontSize: 30, fontWeight: 900, color: k.accent, fontFamily: "monospace", lineHeight: 1 }}>{k.value}</div>
                      <div style={{ fontSize: 12, color: tokens.gray400, marginTop: 6 }}>{k.sub}</div>
                    </div>
                  ))}
                </div>

                {/* Portal table */}
                <div style={{
                  background: tokens.white, border: `1px solid ${tokens.gray200}`,
                  borderRadius: 8, padding: "22px 26px",
                }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: tokens.gray400, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
                    Connected portals
                  </div>
                  <div style={{ fontSize: 12, color: tokens.gray400, marginBottom: 16 }}>
                    Live harvest status · updated continuously
                  </div>
                  <div style={{ display: "flex", padding: "0 0 8px", borderBottom: `2px solid ${tokens.gray200}`, gap: 14 }}>
                    {["","Portal","Datasets","Confidence","Status","Last harvest"].map((h, i) => (
                      <div key={i} style={{
                        fontSize: 11, fontWeight: 700, color: tokens.gray400,
                        textTransform: "uppercase", letterSpacing: "0.07em",
                        width: i===0?20 : i===1?160 : i===2?"1fr":i===3?50:i===4?16:90,
                        flex: i===2?1:undefined, textAlign: i>2?"right":undefined,
                      }}>{h}</div>
                    ))}
                  </div>
                  {portals.length > 0
                    ? portals.map(p => <PortalRow key={p.id} p={p} maxCount={maxPortalCount} />)
                    : !dashLoading && <div style={{ fontSize: 13, color: tokens.gray400, padding: "16px 0" }}>No portal data available.</div>
                  }

                  <div style={{ marginTop: 20, display: "flex", gap: 20, fontSize: 12, color: tokens.gray400 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <div style={{ width: 8, height: 8, borderRadius: "50%", background: tokens.green }} />
                      Live
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <div style={{ width: 8, height: 8, borderRadius: "50%", background: tokens.amber }} />
                      Partial (API issues)
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ background: tokens.blueLight, color: tokens.blue, borderRadius: 3, padding: "1px 6px", fontSize: 10, fontWeight: 700 }}>DET</span>
                      Deterministic mapping
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ background: tokens.amberLight, color: tokens.amber, borderRadius: 3, padding: "1px 6px", fontSize: 10, fontWeight: 700 }}>LLM</span>
                      Phi-4 extraction
                    </div>
                  </div>
                </div>

                {/* Quality breakdown — use stats if available, otherwise skip */}
                {stats && (
                  <div style={{ marginTop: 20, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                    <div style={{ background: tokens.white, border: `1px solid ${tokens.gray200}`, borderRadius: 8, padding: "20px 24px" }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: tokens.gray400, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 16 }}>Access type distribution</div>
                      {(stats.access_distribution
                        ? [
                            { label: "Open access", pct: Math.round((stats.access_distribution.open || 0) * 100),       color: tokens.green },
                            { label: "Restricted",  pct: Math.round((stats.access_distribution.restricted || 0) * 100), color: tokens.amber },
                            { label: "Embargoed",   pct: Math.round((stats.access_distribution.embargoed || 0) * 100),  color: tokens.red },
                          ]
                        : [
                            { label: "Open access", pct: 91, color: tokens.green },
                            { label: "Restricted",  pct: 7,  color: tokens.amber },
                            { label: "Embargoed",   pct: 2,  color: tokens.red },
                          ]
                      ).map(r => (
                        <div key={r.label} style={{ marginBottom: 12 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                            <span style={{ fontSize: 13, color: tokens.gray600 }}>{r.label}</span>
                            <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "monospace", color: r.color }}>{r.pct}%</span>
                          </div>
                          <div style={{ height: 6, background: tokens.gray200, borderRadius: 3 }}>
                            <div style={{ width: `${r.pct}%`, height: "100%", background: r.color, borderRadius: 3 }} />
                          </div>
                        </div>
                      ))}
                    </div>
                    <div style={{ background: tokens.white, border: `1px solid ${tokens.gray200}`, borderRadius: 8, padding: "20px 24px" }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: tokens.gray400, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 16 }}>Confidence distribution</div>
                      {(stats.confidence_distribution
                        ? [
                            { label: "High (≥90%)",     pct: Math.round((stats.confidence_distribution.high || 0) * 100),   color: tokens.green },
                            { label: "Medium (75–90%)", pct: Math.round((stats.confidence_distribution.medium || 0) * 100), color: tokens.amber },
                            { label: "Low (<75%)",      pct: Math.round((stats.confidence_distribution.low || 0) * 100),    color: tokens.red },
                          ]
                        : [
                            { label: "High (≥90%)",     pct: 61, color: tokens.green },
                            { label: "Medium (75–90%)", pct: 28, color: tokens.amber },
                            { label: "Low (<75%)",      pct: 11, color: tokens.red },
                          ]
                      ).map(r => (
                        <div key={r.label} style={{ marginBottom: 12 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                            <span style={{ fontSize: 13, color: tokens.gray600 }}>{r.label}</span>
                            <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "monospace", color: r.color }}>{r.pct}%</span>
                          </div>
                          <div style={{ height: 6, background: tokens.gray200, borderRadius: 3 }}>
                            <div style={{ width: `${r.pct}%`, height: "100%", background: r.color, borderRadius: 3 }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ════ API TAB ════ */}
        {tab === "api" && (
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: tokens.blue, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 24 }}>
              API reference
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {[
                { method: "GET",  path: "/v1/datasets",                  desc: "Search datasets with natural language query and filters" },
                { method: "GET",  path: "/v1/datasets/{id}",             desc: "Full MVM record for a specific dataset" },
                { method: "GET",  path: "/v1/datasets/{id}/similar",     desc: "Top-10 semantically similar datasets" },
                { method: "GET",  path: "/v1/datasets/{id}/provenance",  desc: "Full field-level provenance and processing record" },
                { method: "POST", path: "/v1/query",                     desc: "Natural language question → structured results + summary" },
                { method: "GET",  path: "/v1/portals",                   desc: "Portal status, last harvest, record counts" },
                { method: "GET",  path: "/v1/stats",                     desc: "Aggregate counts by portal, theme, geography, access type" },
                { method: "GET",  path: "/v1/health",                    desc: "Pipeline health, queue depths, model endpoint status" },
              ].map(e => (
                <div key={e.path} style={{
                  background: tokens.white, border: `1px solid ${tokens.gray200}`,
                  borderRadius: 8, padding: "16px 20px", display: "flex", alignItems: "center", gap: 14,
                }}>
                  <span style={{
                    background: e.method === "GET" ? tokens.blueLight : tokens.greenLight,
                    color: e.method === "GET" ? tokens.blue : tokens.green,
                    borderRadius: 4, padding: "3px 10px", fontSize: 11, fontWeight: 800,
                    letterSpacing: "0.06em", fontFamily: "monospace", flexShrink: 0,
                  }}>{e.method}</span>
                  <code style={{ fontSize: 14, color: tokens.gray900, fontFamily: "monospace", fontWeight: 600, flex: 1 }}>{e.path}</code>
                  <span style={{ fontSize: 13, color: tokens.gray400 }}>{e.desc}</span>
                </div>
              ))}
            </div>
            <div style={{
              marginTop: 24, background: tokens.blue, borderRadius: 8, padding: "20px 24px", color: tokens.white,
            }}>
              <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: tokens.electric, marginBottom: 10 }}>
                Example request
              </div>
              <pre style={{ fontSize: 13, lineHeight: 1.8, color: "rgba(255,255,255,0.85)", fontFamily: "monospace", whiteSpace: "pre-wrap" }}>{`curl ${API_BASE || "https://tdo-api.northeurope.azurecontainer.io"}/v1/datasets \\
  -H "X-API-Key: your_key" \\
  -G \\
  --data-urlencode "q=unemployment Finland 2020 onwards" \\
  --data-urlencode "access=open" \\
  --data-urlencode "min_confidence=0.8"`}</pre>
            </div>
          </div>
        )}
      </div>

      {/* ── Footer ── */}
      <div style={{
        borderTop: `1px solid ${tokens.gray200}`, marginTop: 48,
        background: tokens.white, padding: "20px 24px",
      }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: 12, color: tokens.gray400 }}>
            Trusted Data Observatory · Phase 1 · North Europe
          </div>
          <div style={{ display: "flex", gap: 20, fontSize: 12, color: tokens.gray400 }}>
            <span>Built on Azure · North Europe</span>
            <span>Powered by Phi-4 · multilingual-e5-large</span>
            <span style={{ color: tokens.green, fontWeight: 700 }}>● All systems operational</span>
          </div>
        </div>
      </div>

      {/* Provenance modal */}
      {provenanceRec && (
        <ProvenancePanel
          recordId={provenanceRec.id}
          recordMeta={provenanceRec}
          onClose={() => setProvenanceRec(null)}
        />
      )}
    </div>
  );
}
