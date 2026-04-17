"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchContentMetricsSummary,
  fetchPersonaMetricsSummary,
  fetchCostSummary,
  fetchCostMetrics,
  fetchPersonaMetrics,
  ContentMetricsSummary,
  PersonaMetricsSummary,
  CostSummary,
  GenerationCost,
  PersonaMetricsDaily,
  Persona,
} from "../lib/api";

type View = "overview" | "persona" | "costs";

export default function MetricsPanel({ personas }: { personas: Persona[] }) {
  const [view, setView] = useState<View>("overview");
  const [loading, setLoading] = useState(false);

  /* Overview */
  const [contentSummary, setContentSummary] = useState<ContentMetricsSummary | null>(null);
  const [costSummary, setCostSummary] = useState<CostSummary | null>(null);

  /* Persona drill-down */
  const [selectedPersonaId, setSelectedPersonaId] = useState<number>(personas[0]?.id ?? 0);
  const [personaSummary, setPersonaSummary] = useState<PersonaMetricsSummary | null>(null);
  const [personaDaily, setPersonaDaily] = useState<PersonaMetricsDaily[]>([]);

  /* Costs */
  const [costs, setCosts] = useState<GenerationCost[]>([]);

  const refreshOverview = useCallback(async () => {
    setLoading(true);
    try {
      const [cs, co] = await Promise.all([
        fetchContentMetricsSummary(),
        fetchCostSummary(),
      ]);
      setContentSummary(cs);
      setCostSummary(co);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshPersona = useCallback(async () => {
    if (!selectedPersonaId) return;
    setLoading(true);
    try {
      const [summary, daily] = await Promise.all([
        fetchPersonaMetricsSummary(selectedPersonaId),
        fetchPersonaMetrics(selectedPersonaId, { limit: 30 }),
      ]);
      setPersonaSummary(summary);
      setPersonaDaily(daily);
    } finally {
      setLoading(false);
    }
  }, [selectedPersonaId]);

  const refreshCosts = useCallback(async () => {
    setLoading(true);
    try {
      const [summary, list] = await Promise.all([
        fetchCostSummary(),
        fetchCostMetrics({ limit: 50 }),
      ]);
      setCostSummary(summary);
      setCosts(list);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (view === "overview") refreshOverview();
    else if (view === "persona") refreshPersona();
    else if (view === "costs") refreshCosts();
  }, [view, refreshOverview, refreshPersona, refreshCosts]);

  return (
    <div className="space-y-4">
      {/* Sub-nav */}
      <div className="flex gap-2">
        {(["overview", "persona", "costs"] as View[]).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              view === v
                ? "bg-purple-600 text-white"
                : "bg-zinc-800 text-zinc-400 hover:text-white"
            }`}
          >
            {v === "overview" ? "📊 Overview" : v === "persona" ? "👤 Persona" : "💰 Costs"}
          </button>
        ))}
        <div className="flex-1" />
        {loading && (
          <span className="text-xs text-zinc-500 self-center">Loading...</span>
        )}
      </div>

      {/* ─── Overview ───────────────────────────────────────── */}
      {view === "overview" && contentSummary && costSummary && (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-zinc-300">Content Performance</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard label="Views" value={contentSummary.total_views.toLocaleString()} />
            <StatCard label="Likes" value={contentSummary.total_likes.toLocaleString()} />
            <StatCard label="Comments" value={contentSummary.total_comments.toLocaleString()} />
            <StatCard label="Tips" value={`$${contentSummary.total_tips.toFixed(2)}`} />
            <StatCard label="Unlocks" value={contentSummary.total_unlocks.toLocaleString()} />
            <StatCard label="Tracked" value={`${contentSummary.count} entries`} />
          </div>

          <h3 className="text-sm font-semibold text-zinc-300 mt-6">Generation Costs</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <StatCard label="Total Cost" value={`$${costSummary.total_cost_usd.toFixed(4)}`} />
            <StatCard label="Total Jobs" value={costSummary.total_jobs.toLocaleString()} />
            <StatCard label="Avg Duration" value={`${costSummary.avg_duration_seconds.toFixed(1)}s`} />
          </div>

          {Object.keys(costSummary.by_machine).length > 0 && (
            <div className="mt-4">
              <h4 className="text-xs font-medium text-zinc-400 mb-2">By Machine</h4>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(costSummary.by_machine).map(([machine, data]) => (
                  <div key={machine} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
                    <div className="text-xs font-medium text-zinc-300">{machine}</div>
                    <div className="text-[10px] text-zinc-500">{data.count} jobs · ${data.cost.toFixed(4)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {Object.keys(costSummary.by_type).length > 0 && (
            <div className="mt-4">
              <h4 className="text-xs font-medium text-zinc-400 mb-2">By Type</h4>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {Object.entries(costSummary.by_type).map(([type, data]) => (
                  <div key={type} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
                    <div className="text-xs font-medium text-zinc-300">{type}</div>
                    <div className="text-[10px] text-zinc-500">{data.count} jobs · ${data.cost.toFixed(4)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── Persona Drill-Down ─────────────────────────────── */}
      {view === "persona" && (
        <div className="space-y-4">
          <select
            value={selectedPersonaId}
            onChange={(e) => setSelectedPersonaId(Number(e.target.value))}
            className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5"
          >
            {personas.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>

          {personaSummary && (
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <StatCard label="Revenue" value={`$${personaSummary.total_revenue.toFixed(2)}`} />
              <StatCard label="Tips" value={`$${personaSummary.total_tips.toFixed(2)}`} />
              <StatCard label="Net Subs" value={personaSummary.net_subscribers.toLocaleString()} />
              <StatCard label="Content Posted" value={personaSummary.total_content_posted.toLocaleString()} />
              <StatCard label="Days Tracked" value={String(personaSummary.days_tracked)} />
            </div>
          )}

          {personaDaily.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-400">
                    <th className="px-3 py-2 text-left">Date</th>
                    <th className="px-3 py-2 text-left">Platform</th>
                    <th className="px-3 py-2 text-right">Revenue</th>
                    <th className="px-3 py-2 text-right">Tips</th>
                    <th className="px-3 py-2 text-right">New Subs</th>
                    <th className="px-3 py-2 text-right">Churned</th>
                    <th className="px-3 py-2 text-right">Content</th>
                    <th className="px-3 py-2 text-right">Engagement</th>
                  </tr>
                </thead>
                <tbody>
                  {personaDaily.map((row) => (
                    <tr key={row.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                      <td className="px-3 py-2 text-zinc-300">{row.date}</td>
                      <td className="px-3 py-2 text-zinc-400">{row.platform}</td>
                      <td className="px-3 py-2 text-right text-green-400">${(row.revenue ?? 0).toFixed(2)}</td>
                      <td className="px-3 py-2 text-right text-yellow-400">${(row.tips ?? 0).toFixed(2)}</td>
                      <td className="px-3 py-2 text-right text-zinc-300">{row.new_subscribers ?? 0}</td>
                      <td className="px-3 py-2 text-right text-red-400">{row.churned_subscribers ?? 0}</td>
                      <td className="px-3 py-2 text-right text-zinc-300">{row.content_posted ?? 0}</td>
                      <td className="px-3 py-2 text-right text-zinc-400">{((row.avg_engagement_rate ?? 0) * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {personaDaily.length === 0 && !loading && (
            <p className="text-zinc-500 text-xs">No daily metrics recorded for this persona yet.</p>
          )}
        </div>
      )}

      {/* ─── Generation Costs ───────────────────────────────── */}
      {view === "costs" && (
        <div className="space-y-4">
          {costSummary && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <StatCard label="Total Cost" value={`$${costSummary.total_cost_usd.toFixed(4)}`} />
              <StatCard label="Total Jobs" value={costSummary.total_jobs.toLocaleString()} />
              <StatCard label="Avg Duration" value={`${costSummary.avg_duration_seconds.toFixed(1)}s`} />
            </div>
          )}

          {costs.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-400">
                    <th className="px-3 py-2 text-left">Job</th>
                    <th className="px-3 py-2 text-left">Machine</th>
                    <th className="px-3 py-2 text-left">Type</th>
                    <th className="px-3 py-2 text-left">Model</th>
                    <th className="px-3 py-2 text-right">Duration</th>
                    <th className="px-3 py-2 text-right">Cost</th>
                    <th className="px-3 py-2 text-left">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {costs.map((c) => (
                    <tr key={c.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                      <td className="px-3 py-2 text-zinc-300">#{c.job_id ?? "—"}</td>
                      <td className="px-3 py-2 text-zinc-400">{c.machine}</td>
                      <td className="px-3 py-2 text-zinc-400">{c.job_type}</td>
                      <td className="px-3 py-2 text-zinc-500 truncate max-w-[120px]">{c.model_used ?? "—"}</td>
                      <td className="px-3 py-2 text-right text-zinc-300">{c.duration_seconds.toFixed(1)}s</td>
                      <td className="px-3 py-2 text-right text-green-400">${c.estimated_cost_usd.toFixed(4)}</td>
                      <td className="px-3 py-2 text-zinc-500">{new Date(c.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {costs.length === 0 && !loading && (
            <p className="text-zinc-500 text-xs">No generation costs recorded yet.</p>
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
      <div className="text-[10px] text-zinc-500 uppercase tracking-wide">{label}</div>
      <div className="text-sm font-semibold text-zinc-200 mt-0.5">{value}</div>
    </div>
  );
}
