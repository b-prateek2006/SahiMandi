import React, { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const API = "http://localhost:8000";

export default function SimulationDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchSimulation = async (path = "/sim/latest", options = {}) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      if (!res.ok) {
        throw new Error(`Simulation request failed: ${res.statusText}`);
      }
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSimulation("/sim/latest");
  }, []);

  const handleRunSimulation = () => {
    fetchSimulation("/sim/run", {
      method: "POST",
      body: JSON.stringify({ days: 30, seed: 42, policy: "BOTH" }),
    }).then(() => fetchSimulation("/sim/latest"));
  };

  const headline = data?.headline || {};
  const series = data?.series || [];

  return (
    <section className="sim-dashboard" style={{ padding: "20px", maxWidth: "1200px", margin: "0 auto" }}>
      <header style={{ marginBottom: "24px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ margin: "0 0 8px 0", color: "#1e293b" }}>Season Simulation Module</h1>
          <p style={{ margin: 0, color: "#64748b" }}>
            Replay a 30-day harvest season comparing Policy A (Unbounded walk-ins) vs Policy B (SahiMandi capacity engine).
          </p>
        </div>
        <button
          onClick={handleRunSimulation}
          disabled={loading}
          style={{
            padding: "10px 20px",
            backgroundColor: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            fontSize: "14px",
            fontWeight: "600",
            cursor: "pointer",
          }}
        >
          {loading ? "Running..." : "Run 30-Day Simulation"}
        </button>
      </header>

      {error && (
        <div style={{ padding: "12px", backgroundColor: "#fef2f2", color: "#991b1b", borderRadius: "6px", marginBottom: "20px" }}>
          {error}
        </div>
      )}

      {/* Headline Metric Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "20px", marginBottom: "32px" }}>
        <div style={{ padding: "20px", backgroundColor: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: "8px" }}>
          <span style={{ fontSize: "14px", color: "#166534", fontWeight: "600" }}>Peak Queue Reduction</span>
          <h2 style={{ fontSize: "32px", margin: "8px 0", color: "#15803d" }}>
            {headline.peak_queue_reduction_pct != null ? `${headline.peak_queue_reduction_pct}%` : "—"}
          </h2>
          <p style={{ margin: 0, fontSize: "13px", color: "#166534" }}>
            Baseline: {headline.peak_queue_a ?? "—"} qtl → SahiMandi: {headline.peak_queue_b ?? "—"} qtl
          </p>
        </div>

        <div style={{ padding: "20px", backgroundColor: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: "8px" }}>
          <span style={{ fontSize: "14px", color: "#1e40af", fontWeight: "600" }}>Average Wait Reduction</span>
          <h2 style={{ fontSize: "32px", margin: "8px 0", color: "#1d4ed8" }}>
            {headline.avg_wait_reduction_hours != null ? `${headline.avg_wait_reduction_hours} hrs` : "—"}
          </h2>
          <p style={{ margin: 0, fontSize: "13px", color: "#1e40af" }}>
            Baseline: {headline.avg_wait_a ?? "—"} hrs → SahiMandi: {headline.avg_wait_b ?? "—"} hrs
          </p>
        </div>

        <div style={{ padding: "20px", backgroundColor: "#faf5ff", border: "1px solid #e9d5ff", borderRadius: "8px" }}>
          <span style={{ fontSize: "14px", color: "#6b21a8", fontWeight: "600" }}>Farmers Redirected</span>
          <h2 style={{ fontSize: "32px", margin: "8px 0", color: "#7e22ce" }}>
            {headline.farmers_redirected_count ?? "—"}
          </h2>
          <p style={{ margin: 0, fontSize: "13px", color: "#6b21a8" }}>
            Prevented wasted trips before farmers travelled on choked days
          </p>
        </div>
      </div>

      {/* Chart 1: Queue Length by Day */}
      <div style={{ padding: "24px", backgroundColor: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "8px", marginBottom: "32px" }}>
        <h3 style={{ margin: "0 0 16px 0", color: "#334155" }}>1. Daily Queue Length (Quintals) — Policy A vs Policy B</h3>
        <div style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="day" label={{ value: "Day of Season", position: "insideBottom", offset: -5 }} />
              <YAxis label={{ value: "Queue (qtl)", angle: -90, position: "insideLeft" }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="queue_a" name="Policy A (Baseline)" stroke="#ef4444" strokeWidth={2.5} dot={false} />
              <Line type="monotone" dataKey="queue_b" name="Policy B (SahiMandi)" stroke="#10b981" strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Chart 2: Average Farmer Wait Hours */}
      <div style={{ padding: "24px", backgroundColor: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "8px" }}>
        <h3 style={{ margin: "0 0 16px 0", color: "#334155" }}>2. Average Farmer Wait Time (Hours) — Policy A vs Policy B</h3>
        <div style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="day" label={{ value: "Day of Season", position: "insideBottom", offset: -5 }} />
              <YAxis label={{ value: "Wait (Hours)", angle: -90, position: "insideLeft" }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="wait_hours_a" name="Policy A (Baseline)" stroke="#ef4444" strokeWidth={2.5} dot={false} />
              <Line type="monotone" dataKey="wait_hours_b" name="Policy B (SahiMandi)" stroke="#10b981" strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
