"use client";

import { useState } from "react";
import { createLink, deleteLink, type Link } from "../lib/api";

interface Props {
  links: Link[];
  onChanged: () => void;
}

const QUICK_LINKS = [
  { platform: "OnlyFans", url: "https://onlyfans.com", icon: "💎", color: "bg-sky-600/20 text-sky-300" },
  { platform: "Fansly", url: "https://fansly.com", icon: "💜", color: "bg-purple-600/20 text-purple-300" },
  { platform: "Instagram", url: "https://instagram.com", icon: "📸", color: "bg-pink-600/20 text-pink-300" },
  { platform: "X / Twitter", url: "https://x.com", icon: "𝕏", color: "bg-zinc-600/20 text-zinc-300" },
  { platform: "TikTok", url: "https://tiktok.com", icon: "🎵", color: "bg-rose-600/20 text-rose-300" },
  { platform: "Reddit", url: "https://reddit.com", icon: "🔴", color: "bg-orange-600/20 text-orange-300" },
  { platform: "Linktree", url: "https://linktr.ee", icon: "🌳", color: "bg-green-600/20 text-green-300" },
  { platform: "Patreon", url: "https://patreon.com", icon: "🅿️", color: "bg-orange-600/20 text-orange-300" },
  { platform: "Throne", url: "https://throne.com", icon: "🎁", color: "bg-amber-600/20 text-amber-300" },
  { platform: "Snapchat", url: "https://snapchat.com", icon: "👻", color: "bg-yellow-600/20 text-yellow-300" },
  { platform: "YouTube", url: "https://youtube.com", icon: "▶️", color: "bg-red-600/20 text-red-300" },
  { platform: "Twitch", url: "https://twitch.tv", icon: "🟣", color: "bg-violet-600/20 text-violet-300" },
  { platform: "Chaturbate", url: "https://chaturbate.com", icon: "🔥", color: "bg-amber-600/20 text-amber-300" },
  { platform: "ManyVids", url: "https://manyvids.com", icon: "💰", color: "bg-teal-600/20 text-teal-300" },
  { platform: "Telegram", url: "https://telegram.org", icon: "✈️", color: "bg-blue-600/20 text-blue-300" },
  { platform: "Discord", url: "https://discord.com", icon: "🎮", color: "bg-indigo-600/20 text-indigo-300" },
];

const platformColor = (name: string) => {
  const q = QUICK_LINKS.find((q) => q.platform.toLowerCase() === name.toLowerCase());
  return q?.color ?? "bg-purple-600/20 text-purple-300";
};

const platformIcon = (name: string) => {
  const q = QUICK_LINKS.find((q) => q.platform.toLowerCase() === name.toLowerCase());
  return q?.icon ?? "🔗";
};

export default function LinkManager({ links, onChanged }: Props) {
  const [platform, setPlatform] = useState("");
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [showQuick, setShowQuick] = useState(false);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!platform.trim() || !url.trim()) return;

    setAdding(true);
    try {
      await createLink({ platform: platform.trim(), url: url.trim() });
      setPlatform("");
      setUrl("");
      onChanged();
    } catch {
      // silent fail
    } finally {
      setAdding(false);
    }
  };

  const handleQuickAdd = (q: (typeof QUICK_LINKS)[0]) => {
    setPlatform(q.platform);
    setUrl(q.url);
    setShowQuick(false);
  };

  const handleDelete = async (id: number) => {
    await deleteLink(id);
    onChanged();
  };

  // Platforms already added
  const addedPlatforms = new Set(links.map((l) => l.platform.toLowerCase()));

  return (
    <div className="bg-zinc-900 p-6 rounded-xl border border-zinc-800">
      <h2 className="text-xl font-semibold mb-4">Money Links</h2>

      {/* Existing links */}
      <div className="space-y-2 mb-4">
        {links.length === 0 && (
          <p className="text-zinc-500 text-sm">No links yet. Use quick-add below to get started.</p>
        )}
        {links.map((link) => (
          <div
            key={link.id}
            className="flex items-center justify-between p-2.5 bg-zinc-800/50 rounded-lg"
          >
            <div className="flex items-center gap-2">
              <span className="text-sm">{platformIcon(link.platform)}</span>
              <span className={`text-xs font-medium px-2 py-0.5 rounded ${platformColor(link.platform)}`}>
                {link.platform}
              </span>
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-purple-400 hover:text-purple-300 underline truncate max-w-[200px]"
              >
                {link.url}
              </a>
            </div>
            <button
              onClick={() => handleDelete(link.id)}
              className="text-zinc-500 hover:text-red-400 text-xs px-2 py-1 transition-colors"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {/* Quick-add platform buttons */}
      <div className="mb-3">
        <button
          onClick={() => setShowQuick(!showQuick)}
          className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1"
        >
          <span>{showQuick ? "▾" : "▸"}</span> Quick Add Platforms
        </button>
        {showQuick && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {QUICK_LINKS.filter((q) => !addedPlatforms.has(q.platform.toLowerCase())).map((q) => (
              <button
                key={q.platform}
                onClick={() => handleQuickAdd(q)}
                className={`text-xs px-2.5 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors ${q.color}`}
              >
                {q.icon} {q.platform}
              </button>
            ))}
            {QUICK_LINKS.filter((q) => !addedPlatforms.has(q.platform.toLowerCase())).length === 0 && (
              <p className="text-xs text-zinc-500">All platforms added!</p>
            )}
          </div>
        )}
      </div>

      {/* Add link form */}
      <form onSubmit={handleAdd} className="flex gap-2">
        <input
          className="flex-1 p-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm placeholder-zinc-500 focus:border-purple-500 focus:outline-none"
          placeholder="Platform"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          required
        />
        <input
          className="flex-[2] p-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm placeholder-zinc-500 focus:border-purple-500 focus:outline-none"
          placeholder="https://..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
        />
        <button
          type="submit"
          disabled={adding}
          className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 rounded-lg text-sm font-medium transition-colors"
        >
          Add
        </button>
      </form>
    </div>
  );
}
