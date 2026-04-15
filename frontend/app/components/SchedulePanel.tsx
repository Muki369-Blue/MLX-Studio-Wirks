"use client";

import { useState, useEffect } from "react";
import {
  fetchSchedules,
  createSchedule,
  toggleSchedule,
  deleteSchedule,
  type Persona,
  type ScheduleItem,
} from "../lib/api";

const CRON_PRESETS = [
  { label: "3x Daily (9am, 1pm, 6pm)", cron: "0 9,13,18 * * *" },
  { label: "2x Daily (10am, 8pm)", cron: "0 10,20 * * *" },
  { label: "Every 6 hours", cron: "0 */6 * * *" },
  { label: "Once daily (noon)", cron: "0 12 * * *" },
  { label: "Every 4 hours", cron: "0 */4 * * *" },
];

export default function SchedulePanel({ personas }: { personas: Persona[] }) {
  const [schedules, setSchedules] = useState<ScheduleItem[]>([]);
  const [personaId, setPersonaId] = useState<number | null>(null);
  const [prompt, setPrompt] = useState("");
  const [cron, setCron] = useState("0 9,13,18 * * *");
  const [batch, setBatch] = useState(1);
  const [adding, setAdding] = useState(false);

  const refresh = () => fetchSchedules().then(setSchedules).catch(() => {});
  useEffect(() => { refresh(); }, []);

  const handleAdd = async () => {
    if (!personaId || !prompt.trim() || !cron.trim()) return;
    setAdding(true);
    try {
      await createSchedule({ persona_id: personaId, prompt_template: prompt, cron_expression: cron, batch_size: batch });
      setPrompt("");
      refresh();
    } catch {}
    setAdding(false);
  };

  return (
    <div className="bg-zinc-900 p-6 rounded-xl border border-zinc-800">
      <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <span>📅</span> Content Calendar
      </h2>

      <div className="space-y-3 mb-4">
        <select
          className="w-full p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:border-purple-500 focus:outline-none"
          value={personaId ?? ""}
          onChange={(e) => setPersonaId(Number(e.target.value) || null)}
        >
          <option value="">Select persona...</option>
          {personas.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        <textarea
          className="w-full p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm placeholder-zinc-500 focus:border-purple-500 focus:outline-none min-h-[60px]"
          placeholder="Prompt template (e.g. 'bikini, poolside, golden hour')"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />

        <div>
          <label className="text-xs text-zinc-500 mb-1 block">Schedule</label>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {CRON_PRESETS.map((p) => (
              <button
                key={p.cron}
                onClick={() => setCron(p.cron)}
                className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors ${
                  cron === p.cron
                    ? "border-blue-500 bg-blue-600/20 text-blue-300"
                    : "border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <input
            className="w-full p-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm font-mono focus:border-purple-500 focus:outline-none"
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            placeholder="Cron expression"
          />
        </div>

        <div className="flex items-center gap-3">
          <label className="text-sm text-zinc-400">Batch:</label>
          <input type="number" min={1} max={10} value={batch} onChange={(e) => setBatch(Math.max(1, Math.min(10, Number(e.target.value))))}
            className="w-20 p-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-center focus:border-purple-500 focus:outline-none"
          />
        </div>

        <button onClick={handleAdd} disabled={adding || !personaId || !prompt.trim()}
          className="w-full bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700 disabled:opacity-40 px-4 py-2.5 rounded-lg font-semibold text-sm transition-all"
        >
          {adding ? "Creating..." : "Add Schedule"}
        </button>
      </div>

      {/* Active schedules */}
      {schedules.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-zinc-400">Active Schedules</h3>
          {schedules.map((s) => (
            <div key={s.id} className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg border border-zinc-700/50">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${s.enabled ? "bg-emerald-400" : "bg-zinc-600"}`} />
                  <span className="text-sm font-medium truncate">
                    {personas.find((p) => p.id === s.persona_id)?.name ?? `#${s.persona_id}`}
                  </span>
                  <span className="text-[10px] text-zinc-500 font-mono">{s.cron_expression}</span>
                </div>
                <p className="text-xs text-zinc-500 truncate mt-0.5">{s.prompt_template}</p>
                {s.next_run && (
                  <p className="text-[10px] text-zinc-600 mt-0.5">Next: {new Date(s.next_run).toLocaleString()}</p>
                )}
              </div>
              <div className="flex items-center gap-1 ml-2">
                <button onClick={() => { toggleSchedule(s.id).then(refresh); }}
                  className="text-xs px-2 py-1 rounded bg-zinc-700 hover:bg-zinc-600 transition-colors"
                >
                  {s.enabled ? "Pause" : "Resume"}
                </button>
                <button onClick={() => { deleteSchedule(s.id).then(refresh); }}
                  className="text-xs px-2 py-1 rounded text-red-400 hover:bg-red-900/30 transition-colors"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
