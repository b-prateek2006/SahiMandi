import React, { useEffect, useState } from "react";

const API = "http://localhost:8000";

export default function DistrictDashboard() {
  const [centres, setCentres] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sortOrder, setSortOrder] = useState("desc"); // "desc" | "asc"
  const [selectedCentre, setSelectedCentre] = useState(null);
  const [drilldownLoading, setDrilldownLoading] = useState(false);

  const fetchOverview = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/district/overview`);
      if (!res.ok) throw new Error("Failed to load district overview.");
      const data = await res.json();
      setCentres(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
  }, []);

  const handleDrilldown = async (centreId) => {
    setDrilldownLoading(true);
    try {
      const res = await fetch(`${API}/district/centre/${centreId}`);
      if (!res.ok) throw new Error("Failed to load centre drilldown.");
      const data = await res.json();
      setSelectedCentre(data);
    } catch (err) {
      alert(err.message);
    } finally {
      setDrilldownLoading(false);
    }
  };

  const sortedCentres = [...centres].sort((a, b) => {
    const valA = Number(a.backlog_qtl || 0);
    const valB = Number(b.backlog_qtl || 0);
    return sortOrder === "desc" ? valB - valA : valA - valB;
  });

  const toggleSort = () => {
    setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
  };

  return (
    <section className="district-dashboard" style={{ padding: "20px", maxWidth: "1200px", margin: "0 auto" }}>
      <header style={{ marginBottom: "20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ margin: "0 0 6px 0", color: "#0f172a" }}>District Officer Dashboard</h1>
          <p style={{ margin: 0, color: "#64748b" }}>
            Multi-centre capacity supervision, choked centre detection, and backlog tracking.
          </p>
        </div>
        <button
          onClick={fetchOverview}
          disabled={loading}
          style={{
            padding: "8px 16px",
            backgroundColor: "#0f172a",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            fontWeight: "600",
            cursor: "pointer",
          }}
        >
          {loading ? "Refreshing..." : "Refresh Overview"}
        </button>
      </header>

      {error && (
        <div style={{ padding: "12px", backgroundColor: "#fef2f2", color: "#991b1b", borderRadius: "6px", marginBottom: "16px" }}>
          {error}
        </div>
      )}

      {/* Overview Table */}
      <div style={{ backgroundColor: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "8px", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
          <thead>
            <tr style={{ backgroundColor: "#f8fafc", borderBottom: "2px solid #e2e8f0" }}>
              <th style={{ padding: "12px 16px" }}>ID</th>
              <th style={{ padding: "12px 16px" }}>Centre Name</th>
              <th style={{ padding: "12px 16px" }}>District</th>
              <th style={{ padding: "12px 16px" }}>Capacity (qtl)</th>
              <th style={{ padding: "12px 16px" }}>Binding Constraint</th>
              <th
                style={{ padding: "12px 16px", cursor: "pointer", userSelect: "none" }}
                onClick={toggleSort}
                title="Click to sort by backlog"
              >
                Backlog (qtl) {sortOrder === "desc" ? "▼" : "▲"}
              </th>
              <th style={{ padding: "12px 16px" }}>Status</th>
              <th style={{ padding: "12px 16px" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedCentres.length === 0 ? (
              <tr>
                <td colSpan="8" style={{ padding: "24px", textAlign: "center", color: "#64748b" }}>
                  {loading ? "Loading overview..." : "No centres found."}
                </td>
              </tr>
            ) : (
              sortedCentres.map((c) => {
                const isChoked = c.choked;
                return (
                  <tr
                    key={c.centre_id}
                    style={{
                      borderBottom: "1px solid #f1f5f9",
                      backgroundColor: isChoked ? "#fef2f2" : "transparent",
                    }}
                  >
                    <td style={{ padding: "12px 16px", fontWeight: "600" }}>{c.centre_id}</td>
                    <td style={{ padding: "12px 16px", fontWeight: "600", color: isChoked ? "#991b1b" : "#1e293b" }}>
                      {c.name}
                    </td>
                    <td style={{ padding: "12px 16px" }}>{c.district}</td>
                    <td style={{ padding: "12px 16px" }}>{c.daily_capacity ?? "—"}</td>
                    <td style={{ padding: "12px 16px" }}>
                      <span
                        style={{
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "12px",
                          fontWeight: "600",
                          backgroundColor: "#f1f5f9",
                          color: "#475569",
                        }}
                      >
                        {c.binding_constraint ?? "STAFF"}
                      </span>
                    </td>
                    <td style={{ padding: "12px 16px", fontWeight: "600", color: isChoked ? "#dc2626" : "#0f172a" }}>
                      {c.backlog_qtl} qtl
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      {isChoked ? (
                        <span
                          style={{
                            padding: "4px 10px",
                            borderRadius: "4px",
                            backgroundColor: "#dc2626",
                            color: "#ffffff",
                            fontWeight: "700",
                            fontSize: "12px",
                            textTransform: "uppercase",
                            letterSpacing: "0.5px",
                          }}
                        >
                          CHOKED
                        </span>
                      ) : (
                        <span
                          style={{
                            padding: "4px 10px",
                            borderRadius: "4px",
                            backgroundColor: "#dcfce7",
                            color: "#166534",
                            fontWeight: "600",
                            fontSize: "12px",
                          }}
                        >
                          NORMAL
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <button
                        onClick={() => handleDrilldown(c.centre_id)}
                        style={{
                          padding: "4px 12px",
                          backgroundColor: "#3b82f6",
                          color: "#fff",
                          border: "none",
                          borderRadius: "4px",
                          cursor: "pointer",
                          fontSize: "12px",
                          fontWeight: "600",
                        }}
                      >
                        Drilldown
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Drilldown Detail Modal / View */}
      {selectedCentre && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(15, 23, 42, 0.6)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: "#ffffff",
              padding: "24px",
              borderRadius: "8px",
              maxWidth: "600px",
              width: "90%",
              maxHeight: "90vh",
              overflowY: "auto",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <h2 style={{ margin: 0, color: selectedCentre.choked ? "#dc2626" : "#0f172a" }}>
                {selectedCentre.name} ({selectedCentre.district})
              </h2>
              <button
                onClick={() => setSelectedCentre(null)}
                style={{ background: "none", border: "none", fontSize: "20px", cursor: "pointer", fontWeight: "bold" }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "16px" }}>
              <div>
                <strong>Daily Capacity:</strong> {selectedCentre.daily_capacity ?? "—"} qtl
              </div>
              <div>
                <strong>Binding Constraint:</strong> {selectedCentre.binding_constraint ?? "—"}
              </div>
              <div>
                <strong>Choked Status:</strong>{" "}
                <span style={{ color: selectedCentre.choked ? "#dc2626" : "#166534", fontWeight: "bold" }}>
                  {selectedCentre.choked ? "CHOKED" : "NORMAL"}
                </span>
              </div>
              <div>
                <strong>Backlog:</strong> {selectedCentre.backlog_qtl} qtl
              </div>
              <div>
                <strong>Open Counters:</strong> {selectedCentre.counters ?? "—"}
              </div>
              <div>
                <strong>Operating Hours:</strong> {selectedCentre.hours ?? "—"} hrs
              </div>
              <div>
                <strong>Gunny Bags:</strong> {selectedCentre.bags_available ?? "—"}
              </div>
              <div>
                <strong>Hamalis on Duty:</strong> {selectedCentre.hamalis ?? "—"}
              </div>
              <div>
                <strong>Trucks Assigned:</strong> {selectedCentre.trucks ?? "—"}
              </div>
              <div>
                <strong>Active Lots Count:</strong> {selectedCentre.active_lots_count}
              </div>
            </div>

            <button
              onClick={() => setSelectedCentre(null)}
              style={{
                width: "100%",
                padding: "10px",
                backgroundColor: "#0f172a",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                fontWeight: "600",
                cursor: "pointer",
              }}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
