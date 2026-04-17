"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchReviewInbox,
  scoreContent,
  reviewAction,
  imageUrl,
  ReviewItem,
  Persona,
} from "../lib/api";

const VERDICT_COLORS: Record<string, string> = {
  auto_approve: "text-green-400",
  needs_review: "text-orange-400",
  auto_reject: "text-red-400",
};

export default function ReviewInboxPanel({ personas }: { personas: Persona[] }) {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<ReviewItem | null>(null);
  const [notes, setNotes] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchReviewInbox({
        verdict: filter || undefined,
      });
      setItems(data);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const personaName = (pid: number | null) =>
    personas.find((p) => p.id === pid)?.name ?? "Unknown";

  async function handleScore(contentId: number) {
    setActionLoading(true);
    try {
      await scoreContent(contentId);
      refresh();
    } finally {
      setActionLoading(false);
    }
  }

  async function handleAction(contentId: number, action: "approve" | "reject" | "rerun") {
    setActionLoading(true);
    try {
      await reviewAction(contentId, action, notes || undefined);
      setNotes("");
      setSelected(null);
      refresh();
    } finally {
      setActionLoading(false);
    }
  }

  function ScoreBar({ label, value }: { label: string; value: number }) {
    const pct = Math.round(value * 100);
    const color = pct >= 75 ? "bg-green-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500";
    return (
      <div className="flex items-center gap-2 text-xs">
        <span className="w-28 text-gray-400 shrink-0">{label}</span>
        <div className="flex-1 bg-white/10 rounded-full h-2 overflow-hidden">
          <div className={`${color} h-full rounded-full`} style={{ width: `${pct}%` }} />
        </div>
        <span className="w-8 text-right text-gray-300">{pct}%</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <h2 className="text-white font-medium">Review Inbox</h2>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="bg-white/5 border border-white/10 rounded px-2 py-1 text-sm text-white"
        >
          <option value="">Needs Review + Unscored</option>
          <option value="needs_review">Needs Review</option>
          <option value="auto_approve">Auto-Approved</option>
          <option value="auto_reject">Auto-Rejected</option>
        </select>
        <div className="flex-1" />
        <span className="text-gray-400 text-sm">{items.length} items</span>
        <button onClick={refresh} className="text-sm text-blue-400 hover:underline">
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {/* Content grid */}
      <div className="grid grid-cols-3 gap-3">
        {/* Item list */}
        <div className="col-span-1 space-y-2 max-h-[65vh] overflow-y-auto">
          {items.length === 0 && (
            <p className="text-gray-500 text-sm text-center py-8">All clear — nothing to review!</p>
          )}
          {items.map((item) => (
            <div
              key={item.content.id}
              onClick={() => setSelected(item)}
              className={`rounded p-2 cursor-pointer text-sm ${
                selected?.content.id === item.content.id
                  ? "bg-white/10 border border-white/20"
                  : "bg-white/5 hover:bg-white/8"
              }`}
            >
              {/* Thumbnail */}
              {item.content.file_path && (
                <img
                  src={imageUrl(item.content.file_path.split("/").pop() ?? "")}
                  alt=""
                  className="w-full h-24 object-cover rounded mb-2"
                  loading="lazy"
                />
              )}
              <div className="flex items-center gap-2">
                <span className="text-gray-300 text-xs">#{item.content.id}</span>
                {item.score && (
                  <span className={`text-xs font-medium ${VERDICT_COLORS[item.score.verdict] ?? "text-gray-400"}`}>
                    {item.score.verdict.replace("_", " ")} ({Math.round(item.score.overall * 100)}%)
                  </span>
                )}
                {!item.score && <span className="text-gray-500 text-xs">unscored</span>}
              </div>
              <div className="text-gray-500 text-xs mt-0.5 truncate">
                {personaName(item.content.persona_id)}
              </div>
            </div>
          ))}
        </div>

        {/* Detail panel */}
        <div className="col-span-2">
          {!selected ? (
            <div className="text-gray-500 text-sm text-center py-12">
              Select a content item to review
            </div>
          ) : (
            <div className="bg-white/5 rounded p-4 space-y-4">
              {/* Image */}
              {selected.content.file_path && (
                <img
                  src={imageUrl(
                    (selected.content.upscaled_path ?? selected.content.file_path).split("/").pop() ?? ""
                  )}
                  alt=""
                  className="w-full max-h-72 object-contain rounded"
                />
              )}

              {/* Metadata */}
              <div className="text-sm">
                <div className="text-gray-400">
                  <strong className="text-white">Persona:</strong>{" "}
                  {personaName(selected.content.persona_id)}
                </div>
                {selected.content.prompt_used && (
                  <div className="text-gray-400 mt-1">
                    <strong className="text-white">Prompt:</strong>{" "}
                    {selected.content.prompt_used}
                  </div>
                )}
              </div>

              {/* Scores */}
              {selected.score ? (
                <div className="space-y-1.5">
                  <h4 className="text-xs text-gray-400 font-medium uppercase">Quality Scores</h4>
                  <ScoreBar label="Aesthetic" value={selected.score.aesthetic} />
                  <ScoreBar label="Consistency" value={selected.score.persona_consistency} />
                  <ScoreBar label="Prompt Match" value={selected.score.prompt_adherence} />
                  <ScoreBar label="Artifacts" value={1 - selected.score.artifact_penalty} />
                  <ScoreBar label="Novelty" value={selected.score.novelty} />
                  <div className="flex items-center gap-2 text-sm mt-2">
                    <span className="text-white font-medium">
                      Overall: {Math.round(selected.score.overall * 100)}%
                    </span>
                    <span
                      className={`font-medium ${VERDICT_COLORS[selected.score.verdict] ?? "text-gray-400"}`}
                    >
                      {selected.score.verdict.replace("_", " ")}
                    </span>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => handleScore(selected.content.id)}
                  disabled={actionLoading}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm px-4 py-2 rounded disabled:opacity-50"
                >
                  {actionLoading ? "Scoring…" : "Run Quality Score"}
                </button>
              )}

              {/* Notes + Actions */}
              <div className="space-y-2">
                <textarea
                  placeholder="Notes (optional — saved as persona feedback)…"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={2}
                  className="w-full bg-black/30 border border-white/10 rounded px-3 py-2 text-sm text-white"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => handleAction(selected.content.id, "approve")}
                    disabled={actionLoading}
                    className="bg-green-600 hover:bg-green-500 text-white text-sm px-4 py-1.5 rounded disabled:opacity-50"
                  >
                    ✓ Approve
                  </button>
                  <button
                    onClick={() => handleAction(selected.content.id, "reject")}
                    disabled={actionLoading}
                    className="bg-red-600 hover:bg-red-500 text-white text-sm px-4 py-1.5 rounded disabled:opacity-50"
                  >
                    ✗ Reject
                  </button>
                  <button
                    onClick={() => handleAction(selected.content.id, "rerun")}
                    disabled={actionLoading}
                    className="bg-yellow-600 hover:bg-yellow-500 text-white text-sm px-4 py-1.5 rounded disabled:opacity-50"
                  >
                    ↻ Rerun
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
