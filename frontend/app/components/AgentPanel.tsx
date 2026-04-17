"use client";

import { useState, useEffect, useCallback } from "react";
import {
  invokePlanner,
  invokeCreative,
  invokeAnalyst,
  fetchAgentRuns,
  fetchContentMetricsSummary,
  AgentRun,
  Persona,
} from "../lib/api";

type View = "invoke" | "history";

const AGENT_TYPES = [
  { id: "planner", label: "🗓 Planner", desc: "Generate a multi-day campaign plan" },
  { id: "creative", label: "🎨 Creative", desc: "Generate prompts & content ideas" },
  { id: "analyst", label: "📈 Analyst", desc: "Analyze metrics & recommend strategy" },
] as const;

type AgentType = (typeof AGENT_TYPES)[number]["id"];

export default function AgentPanel({ personas }: { personas: Persona[] }) {
  const [view, setView] = useState<View>("invoke");
  const [loading, setLoading] = useState(false);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [filterType, setFilterType] = useState("");

  /* Invoke form */
  const [agentType, setAgentType] = useState<AgentType>("planner");
  const [personaId, setPersonaId] = useState<number>(personas[0]?.id ?? 0);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");

  /* Planner fields */
  const [totalDays, setTotalDays] = useState(4);
  const [slotsPerDay, setSlotsPerDay] = useState(3);
  const [plannerNotes, setPlannerNotes] = useState("");

  /* Creative fields */
  const [brief, setBrief] = useState("");
  const [contentType, setContentType] = useState("image");

  const refreshHistory = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchAgentRuns({
        agent_type: filterType || undefined,
        limit: 50,
      });
      setRuns(data);
    } finally {
      setLoading(false);
    }
  }, [filterType]);

  useEffect(() => {
    if (view === "history") refreshHistory();
  }, [view, refreshHistory]);

  async function handleInvoke() {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      let res: any;
      if (agentType === "planner") {
        res = await invokePlanner({
          persona_id: personaId,
          total_days: totalDays,
          slots_per_day: slotsPerDay,
          notes: plannerNotes || undefined,
        });
      } else if (agentType === "creative") {
        res = await invokeCreative({
          persona_id: personaId,
          brief,
          content_type: contentType,
        });
      } else {
        const metrics = await fetchContentMetricsSummary();
        res = await invokeAnalyst({
          persona_id: personaId,
          metrics_summary: metrics,
        });
      }
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Agent invocation failed");
    } finally {
      setLoading(false);
    }
  }

  const personaName = (pid: number | null) =>
    personas.find((p) => p.id === pid)?.name ?? "—";

  return (
    <div className="space-y-4">
      {/* Sub-nav */}
      <div className="flex gap-2">
        {(["invoke", "history"] as View[]).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              view === v
                ? "bg-purple-600 text-white"
                : "bg-zinc-800 text-zinc-400 hover:text-white"
            }`}
          >
            {v === "invoke" ? "🤖 Invoke Agent" : "📜 Run History"}
          </button>
        ))}
      </div>

      {/* ─── Invoke ────────────────────────────────────────── */}
      {view === "invoke" && (
        <div className="space-y-4">
          {/* Agent type selector */}
          <div className="grid grid-cols-3 gap-2">
            {AGENT_TYPES.map((a) => (
              <button
                key={a.id}
                onClick={() => setAgentType(a.id)}
                className={`p-3 rounded-lg border text-left transition-colors ${
                  agentType === a.id
                    ? "border-purple-500 bg-purple-500/10"
                    : "border-zinc-800 bg-zinc-900 hover:border-zinc-700"
                }`}
              >
                <div className="text-sm font-medium text-zinc-200">{a.label}</div>
                <div className="text-[10px] text-zinc-500 mt-0.5">{a.desc}</div>
              </button>
            ))}
          </div>

          {/* Persona */}
          <div>
            <label className="text-xs text-zinc-400 block mb-1">Persona</label>
            <select
              value={personaId}
              onChange={(e) => setPersonaId(Number(e.target.value))}
              className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5 w-full"
            >
              {personas.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>

          {/* Agent-specific fields */}
          {agentType === "planner" && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-zinc-400 block mb-1">Total Days</label>
                <input
                  type="number"
                  min={1}
                  max={30}
                  value={totalDays}
                  onChange={(e) => setTotalDays(Number(e.target.value))}
                  className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5 w-full"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-400 block mb-1">Slots/Day</label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={slotsPerDay}
                  onChange={(e) => setSlotsPerDay(Number(e.target.value))}
                  className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5 w-full"
                />
              </div>
              <div className="col-span-2">
                <label className="text-xs text-zinc-400 block mb-1">Notes (optional)</label>
                <input
                  value={plannerNotes}
                  onChange={(e) => setPlannerNotes(e.target.value)}
                  placeholder="e.g. focus on beach/pool content"
                  className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5 w-full"
                />
              </div>
            </div>
          )}

          {agentType === "creative" && (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-zinc-400 block mb-1">Brief</label>
                <textarea
                  value={brief}
                  onChange={(e) => setBrief(e.target.value)}
                  placeholder="Describe what kind of content you want..."
                  rows={3}
                  className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5 w-full resize-none"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-400 block mb-1">Content Type</label>
                <select
                  value={contentType}
                  onChange={(e) => setContentType(e.target.value)}
                  className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5"
                >
                  <option value="image">Image</option>
                  <option value="video">Video</option>
                  <option value="set">Content Set</option>
                </select>
              </div>
            </div>
          )}

          {agentType === "analyst" && (
            <p className="text-xs text-zinc-500">
              The analyst will automatically fetch the latest content metrics and provide strategic recommendations.
            </p>
          )}

          <button
            onClick={handleInvoke}
            disabled={loading || (agentType === "creative" && !brief.trim())}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-white text-xs font-medium rounded transition-colors"
          >
            {loading ? "Running..." : `Run ${agentType.charAt(0).toUpperCase() + agentType.slice(1)}`}
          </button>

          {error && (
            <div className="bg-red-900/20 border border-red-800 rounded-lg p-3 text-xs text-red-400">
              {error}
            </div>
          )}

          {result && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
              <h4 className="text-xs font-medium text-zinc-400 mb-2">Result</h4>
              <pre className="text-xs text-zinc-300 whitespace-pre-wrap overflow-auto max-h-96">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* ─── History ───────────────────────────────────────── */}
      {view === "history" && (
        <div className="space-y-3">
          <div className="flex gap-2 items-center">
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5"
            >
              <option value="">All Agents</option>
              <option value="planner">Planner</option>
              <option value="creative">Creative</option>
              <option value="analyst">Analyst</option>
              <option value="scorer">Scorer</option>
            </select>
            <button
              onClick={refreshHistory}
              className="px-3 py-1.5 bg-zinc-800 text-zinc-300 text-xs rounded hover:bg-zinc-700"
            >
              Refresh
            </button>
            {loading && <span className="text-xs text-zinc-500">Loading...</span>}
          </div>

          {runs.length === 0 && !loading && (
            <p className="text-zinc-500 text-xs">No agent runs recorded yet.</p>
          )}

          <div className="space-y-2">
            {runs.map((run) => (
              <RunCard key={run.id} run={run} personaName={personaName(run.persona_id)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RunCard({ run, personaName }: { run: AgentRun; personaName: string }) {
  const [expanded, setExpanded] = useState(false);

  const statusColor =
    run.status === "completed"
      ? "text-green-400"
      : run.status === "failed"
      ? "text-red-400"
      : "text-yellow-400";

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
      <div
        className="flex items-center gap-3 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="text-xs font-medium text-purple-400 w-16">{run.agent_type}</span>
        <span className="text-xs text-zinc-400">{personaName}</span>
        <span className={`text-xs ${statusColor}`}>{run.status}</span>
        {run.duration_seconds != null && (
          <span className="text-[10px] text-zinc-500">{run.duration_seconds.toFixed(1)}s</span>
        )}
        <span className="text-[10px] text-zinc-600 ml-auto">
          {new Date(run.created_at).toLocaleString()}
        </span>
        <span className="text-zinc-600 text-xs">{expanded ? "▼" : "▶"}</span>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2">
          {run.input_payload && (
            <div>
              <h5 className="text-[10px] text-zinc-500 uppercase">Input</h5>
              <pre className="text-[10px] text-zinc-400 whitespace-pre-wrap max-h-32 overflow-auto bg-zinc-800/50 rounded p-2 mt-1">
                {JSON.stringify(run.input_payload, null, 2)}
              </pre>
            </div>
          )}
          {run.output_payload && (
            <div>
              <h5 className="text-[10px] text-zinc-500 uppercase">Output</h5>
              <pre className="text-[10px] text-zinc-300 whitespace-pre-wrap max-h-48 overflow-auto bg-zinc-800/50 rounded p-2 mt-1">
                {JSON.stringify(run.output_payload, null, 2)}
              </pre>
            </div>
          )}
          {run.error && (
            <div>
              <h5 className="text-[10px] text-red-500 uppercase">Error</h5>
              <pre className="text-[10px] text-red-400 whitespace-pre-wrap bg-red-900/20 rounded p-2 mt-1">
                {run.error}
              </pre>
            </div>
          )}
          {run.model_used && (
            <div className="text-[10px] text-zinc-500">Model: {run.model_used}</div>
          )}
        </div>
      )}
    </div>
  );
}
