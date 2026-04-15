"use client";

import { useState, useEffect } from "react";
import {
  fetchAnalyticsSummary,
  addAnalytics,
  type Persona,
  type AnalyticsSummary,
} from "../lib/api";

export default function AnalyticsPanel({ personas }: { personas: Persona[] }) {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ persona_id: 0, date: new Date().toISOString().split("T")[0], platform: "onlyfans", subscribers: 0, revenue: 0, tips: 0 });
  const [adding, setAdding] = useState(false);

  const refresh = () => fetchAnalyticsSummary().then(setSummary).catch(() => {});
  useEffect(() => { refresh(); }, []);

  const handleAdd = async () => {
    if (!form.persona_id) return;
    setAdding(true);
    try {
      await addAnalytics(form);
      setShowAdd(false);
      refresh();
    } catch {}
    setAdding(false);
  };

  const fmt = (n: number) =>
    n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n.toFixed(2)}`;

  return (
    <div className="bg-zinc-900 p-6 rounded-xl border border-zinc-800">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <span>📊</span> Analytics Dashboard
        </h2>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="text-xs px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg hover:bg-zinc-700 transition-colors"
        >
          + Add Data
        </button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
            <div className="bg-gradient-to-br from-emerald-900/40 to-zinc-800 p-4 rounded-xl border border-emerald-800/30">
              <p className="text-xs text-zinc-400">Total Revenue</p>
              <p className="text-2xl font-bold text-emerald-300">{fmt(summary.total_revenue)}</p>
            </div>
            <div className="bg-gradient-to-br from-purple-900/40 to-zinc-800 p-4 rounded-xl border border-purple-800/30">
              <p className="text-xs text-zinc-400">Tips</p>
              <p className="text-2xl font-bold text-purple-300">{fmt(summary.total_tips)}</p>
            </div>
            <div className="bg-gradient-to-br from-blue-900/40 to-zinc-800 p-4 rounded-xl border border-blue-800/30">
              <p className="text-xs text-zinc-400">Subscribers</p>
              <p className="text-2xl font-bold text-blue-300">{summary.total_subscribers.toLocaleString()}</p>
            </div>
            <div className="bg-gradient-to-br from-pink-900/40 to-zinc-800 p-4 rounded-xl border border-pink-800/30">
              <p className="text-xs text-zinc-400">Content Produced</p>
              <p className="text-2xl font-bold text-pink-300">{summary.total_content}</p>
            </div>
          </div>

          {/* Top Persona */}
          {summary.top_persona && (
            <div className="bg-zinc-800/50 p-3 rounded-lg mb-4 flex items-center gap-2">
              <span className="text-lg">👑</span>
              <p className="text-sm"><span className="text-zinc-400">Top earner:</span> <span className="text-yellow-300 font-medium">{summary.top_persona}</span></p>
            </div>
          )}

          {/* Platform Breakdown */}
          {Object.keys(summary.by_platform).length > 0 && (
            <div className="mb-4">
              <h3 className="text-sm font-medium text-zinc-400 mb-2">By Platform</h3>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(summary.by_platform).map(([plat, data]) => (
                  <div key={plat} className="bg-zinc-800/50 p-3 rounded-lg border border-zinc-700/50">
                    <p className="text-xs text-zinc-400 capitalize mb-1">{plat}</p>
                    <div className="flex gap-3 text-xs">
                      <span className="text-emerald-400">{fmt(data.revenue)}</span>
                      <span className="text-purple-400">{fmt(data.tips)} tips</span>
                      <span className="text-blue-400">{data.subscribers} subs</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Per-Persona Revenue */}
          {summary.by_persona.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-zinc-400 mb-2">By Persona</h3>
              <div className="space-y-1.5">
                {summary.by_persona.map((p) => {
                  const maxRev = Math.max(...summary.by_persona.map((x) => x.revenue), 1);
                  return (
                    <div key={p.persona_id} className="flex items-center gap-3">
                      <span className="text-xs text-zinc-300 w-24 truncate">{p.name}</span>
                      <div className="flex-1 bg-zinc-800 rounded-full h-2 overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-emerald-500 to-blue-500 rounded-full transition-all"
                          style={{ width: `${(p.revenue / maxRev) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-emerald-400 w-16 text-right">{fmt(p.revenue)}</span>
                      <span className="text-[10px] text-zinc-500 w-12">{p.content_count} posts</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      {!summary && <p className="text-zinc-500 text-sm text-center py-8">Loading analytics...</p>}

      {/* Add Data Form */}
      {showAdd && (
        <div className="mt-4 p-4 bg-zinc-800/50 rounded-xl border border-zinc-700 space-y-3">
          <h3 className="text-sm font-medium">Add Analytics Entry</h3>
          <div className="grid grid-cols-2 gap-3">
            <select className="p-2 bg-zinc-800 border border-zinc-700 rounded-lg text-xs" value={form.persona_id}
              onChange={(e) => setForm({ ...form, persona_id: Number(e.target.value) })}
            >
              <option value={0}>Select persona...</option>
              {personas.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <select className="p-2 bg-zinc-800 border border-zinc-700 rounded-lg text-xs" value={form.platform}
              onChange={(e) => setForm({ ...form, platform: e.target.value })}
            >
              {["onlyfans", "fansly", "twitter", "reddit"].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <input type="date" className="p-2 bg-zinc-800 border border-zinc-700 rounded-lg text-xs" value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })} />
            <input type="number" placeholder="Revenue ($)" className="p-2 bg-zinc-800 border border-zinc-700 rounded-lg text-xs" value={form.revenue || ""}
              onChange={(e) => setForm({ ...form, revenue: Number(e.target.value) })} />
            <input type="number" placeholder="Tips ($)" className="p-2 bg-zinc-800 border border-zinc-700 rounded-lg text-xs" value={form.tips || ""}
              onChange={(e) => setForm({ ...form, tips: Number(e.target.value) })} />
            <input type="number" placeholder="Subscribers" className="p-2 bg-zinc-800 border border-zinc-700 rounded-lg text-xs" value={form.subscribers || ""}
              onChange={(e) => setForm({ ...form, subscribers: Number(e.target.value) })} />
          </div>
          <button onClick={handleAdd} disabled={adding || !form.persona_id}
            className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 px-4 py-2 rounded-lg text-sm font-semibold transition-all"
          >
            {adding ? "Saving..." : "Save Entry"}
          </button>
        </div>
      )}
    </div>
  );
}
