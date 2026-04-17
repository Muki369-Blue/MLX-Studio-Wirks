"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchPersonaMemory,
  upsertPersonaMemory,
  deletePersonaMemory,
  PersonaMemoryEntry,
  Persona,
} from "../lib/api";

const PARTITIONS = ["canonical", "operational", "learned"] as const;
type Partition = (typeof PARTITIONS)[number];

const PARTITION_INFO: Record<Partition, { icon: string; desc: string }> = {
  canonical: { icon: "📋", desc: "Core identity facts — appearance, personality, backstory" },
  operational: { icon: "⚙️", desc: "Active settings — current scene preferences, schedule config" },
  learned: { icon: "🧠", desc: "AI-discovered insights — audience prefs, top-performing styles" },
};

export default function PersonaMemoryPanel({ personas }: { personas: Persona[] }) {
  const [personaId, setPersonaId] = useState<number>(personas[0]?.id ?? 0);
  const [partition, setPartition] = useState<Partition>("canonical");
  const [entries, setEntries] = useState<PersonaMemoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<PersonaMemoryEntry | null>(null);

  /* New/edit form */
  const [formKey, setFormKey] = useState("");
  const [formValue, setFormValue] = useState("");
  const [formSource, setFormSource] = useState("user");
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    if (!personaId) return;
    setLoading(true);
    try {
      const data = await fetchPersonaMemory(personaId, partition);
      setEntries(data);
    } finally {
      setLoading(false);
    }
  }, [personaId, partition]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  function startNew() {
    setEditing(null);
    setFormKey("");
    setFormValue("");
    setFormSource("user");
  }

  function startEdit(entry: PersonaMemoryEntry) {
    setEditing(entry);
    setFormKey(entry.key);
    setFormValue(JSON.stringify(entry.value, null, 2));
    setFormSource(entry.source ?? "user");
  }

  async function handleSave() {
    if (!formKey.trim()) return;
    setSaving(true);
    try {
      let parsed: any;
      try {
        parsed = JSON.parse(formValue);
      } catch {
        parsed = formValue;
      }
      await upsertPersonaMemory({
        persona_id: personaId,
        partition,
        key: formKey.trim(),
        value: typeof parsed === "object" ? parsed : { text: parsed },
        source: formSource,
      });
      setFormKey("");
      setFormValue("");
      setEditing(null);
      refresh();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    await deletePersonaMemory(id);
    refresh();
  }

  const personaName = personas.find((p) => p.id === personaId)?.name ?? "Unknown";

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={personaId}
          onChange={(e) => setPersonaId(Number(e.target.value))}
          className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5"
        >
          {personas.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        <div className="flex gap-1">
          {PARTITIONS.map((p) => (
            <button
              key={p}
              onClick={() => setPartition(p)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                partition === p
                  ? "bg-purple-600 text-white"
                  : "bg-zinc-800 text-zinc-400 hover:text-white"
              }`}
            >
              {PARTITION_INFO[p].icon} {p}
            </button>
          ))}
        </div>

        <div className="flex-1" />
        {loading && <span className="text-xs text-zinc-500">Loading...</span>}
      </div>

      <p className="text-[10px] text-zinc-500">{PARTITION_INFO[partition].desc}</p>

      {/* Memory entries */}
      <div className="space-y-2">
        {entries.length === 0 && !loading && (
          <p className="text-zinc-500 text-xs">
            No {partition} memory entries for {personaName}.
          </p>
        )}

        {entries.map((entry) => (
          <div
            key={entry.id}
            className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 group"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-purple-400">{entry.key}</span>
                  {entry.source && (
                    <span className="text-[10px] text-zinc-600">{entry.source}</span>
                  )}
                </div>
                <pre className="text-xs text-zinc-300 whitespace-pre-wrap mt-1 max-h-32 overflow-auto">
                  {typeof entry.value === "object"
                    ? JSON.stringify(entry.value, null, 2)
                    : String(entry.value)}
                </pre>
                <div className="text-[10px] text-zinc-600 mt-1">
                  Updated {new Date(entry.updated_at).toLocaleString()}
                </div>
              </div>
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-2 shrink-0">
                <button
                  onClick={() => startEdit(entry)}
                  className="px-2 py-1 bg-zinc-800 text-zinc-400 text-[10px] rounded hover:bg-zinc-700"
                >
                  Edit
                </button>
                <button
                  onClick={() => handleDelete(entry.id)}
                  className="px-2 py-1 bg-red-900/30 text-red-400 text-[10px] rounded hover:bg-red-900/50"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Add / Edit form */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-3">
        <h4 className="text-xs font-medium text-zinc-400">
          {editing ? `Edit: ${editing.key}` : "Add Memory Entry"}
        </h4>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] text-zinc-500 block mb-1">Key</label>
            <input
              value={formKey}
              onChange={(e) => setFormKey(e.target.value)}
              placeholder="e.g. top_scenes, personality_traits"
              disabled={!!editing}
              className="bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5 w-full disabled:opacity-50"
            />
          </div>
          <div>
            <label className="text-[10px] text-zinc-500 block mb-1">Source</label>
            <select
              value={formSource}
              onChange={(e) => setFormSource(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5 w-full"
            >
              <option value="user">user</option>
              <option value="agent:planner">agent:planner</option>
              <option value="agent:analyst">agent:analyst</option>
              <option value="agent:creative">agent:creative</option>
              <option value="system">system</option>
            </select>
          </div>
        </div>
        <div>
          <label className="text-[10px] text-zinc-500 block mb-1">Value (JSON or plain text)</label>
          <textarea
            value={formValue}
            onChange={(e) => setFormValue(e.target.value)}
            placeholder='e.g. ["beach sunset", "rooftop city"] or free text'
            rows={4}
            className="bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5 w-full resize-none font-mono"
          />
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleSave}
            disabled={saving || !formKey.trim()}
            className="px-4 py-1.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-white text-xs font-medium rounded transition-colors"
          >
            {saving ? "Saving..." : editing ? "Update" : "Add Entry"}
          </button>
          {editing && (
            <button
              onClick={startNew}
              className="px-3 py-1.5 bg-zinc-800 text-zinc-400 text-xs rounded hover:bg-zinc-700"
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
