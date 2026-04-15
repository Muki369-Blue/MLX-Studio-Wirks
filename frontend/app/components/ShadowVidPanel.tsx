"use client";

import { useEffect, useState } from "react";
import {
  fetchVideoPresets,
  generateVideo,
  refinePrompt,
  type Persona,
  type VideoPreset,
} from "../lib/api";

export default function ShadowVidPanel({ personas }: { personas: Persona[] }) {
  const [videoPersona, setVideoPersona] = useState<number | null>(null);
  const [videoPrompt, setVideoPrompt] = useState("");
  const [videoPresets, setVideoPresets] = useState<VideoPreset[]>([]);
  const [generatingVideo, setGeneratingVideo] = useState(false);
  const [videoResult, setVideoResult] = useState<string | null>(null);
  const [refiningVideo, setRefiningVideo] = useState(false);
  const [videoIntensity, setVideoIntensity] = useState<"light" | "medium" | "heavy">("medium");

  useEffect(() => {
    fetchVideoPresets().then(setVideoPresets);
  }, []);

  const handleSelectVideoPreset = (presetId: string) => {
    const preset = videoPresets.find((item) => item.id === presetId);
    if (preset) setVideoPrompt(preset.prompt);
  };

  const handleRefineVideo = async () => {
    if (!videoPrompt.trim()) return;
    setRefiningVideo(true);
    try {
      const data = await refinePrompt(videoPrompt, videoIntensity);
      setVideoPrompt(data.refined);
      setVideoResult("✨ Motion prompt refined by Celeste");
    } catch {
      setVideoResult("Refine failed — is Ollama running?");
    }
    setRefiningVideo(false);
  };

  const handleGenerateVideo = async () => {
    if (!videoPersona || !videoPrompt.trim()) return;
    setGeneratingVideo(true);
    setVideoResult(null);
    try {
      const res = await generateVideo(videoPersona, videoPrompt);
      setVideoResult(res.message || "Video generation queued!");
    } catch {
      setVideoResult("Failed to generate video.");
    }
    setGeneratingVideo(false);
  };

  return (
    <div className="space-y-6">
      <div className="bg-zinc-900 p-6 rounded-xl border border-zinc-800">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <span>🎥</span> ShadowVid
        </h2>
        <p className="text-xs text-zinc-500 mb-3">
          Dedicated video workspace for motion prompts and animated WEBP generation.
        </p>

        <div className="space-y-3">
          <select
            className="w-full p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:border-violet-500 focus:outline-none"
            value={videoPersona ?? ""}
            onChange={(e) => setVideoPersona(Number(e.target.value) || null)}
          >
            <option value="">Select persona...</option>
            {personas.map((persona) => (
              <option key={persona.id} value={persona.id}>{persona.name}</option>
            ))}
          </select>

          <div>
            <label className="text-xs text-zinc-500 mb-1 block">Motion Preset</label>
            <select
              className="w-full p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:border-violet-500 focus:outline-none"
              value=""
              onChange={(e) => handleSelectVideoPreset(e.target.value)}
            >
              <option value="">Choose a motion preset or write your own...</option>
              {videoPresets.map((preset) => (
                <option key={preset.id} value={preset.id}>{preset.label}</option>
              ))}
            </select>
          </div>

          <textarea
            className="w-full p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm placeholder-zinc-500 focus:border-violet-500 focus:outline-none min-h-[72px]"
            placeholder="Motion prompt (e.g. 'hair blowing in wind, gentle smile, looking at camera')"
            value={videoPrompt}
            onChange={(e) => setVideoPrompt(e.target.value)}
          />

          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              {(["light", "medium", "heavy"] as const).map((level) => (
                <button
                  key={level}
                  onClick={() => setVideoIntensity(level)}
                  className={`text-xs px-2 py-1 rounded transition-colors ${
                    videoIntensity === level
                      ? "bg-violet-600/30 text-violet-300 border border-violet-500"
                      : "bg-zinc-800 text-zinc-500 border border-zinc-700 hover:border-zinc-600"
                  }`}
                  title={level}
                >
                  {level === "light" ? "🔥" : level === "medium" ? "🔥🔥" : "🔥🔥🔥"}
                </button>
              ))}
            </div>
            <button
              onClick={handleRefineVideo}
              disabled={refiningVideo || !videoPrompt.trim()}
              className="flex-1 text-xs px-3 py-1.5 bg-violet-600/20 text-violet-300 border border-violet-600/40 hover:bg-violet-600/30 disabled:opacity-40 rounded-lg transition-colors"
            >
              {refiningVideo ? "✨ Refining..." : "✨ Refine with Celeste"}
            </button>
          </div>

          <button
            onClick={handleGenerateVideo}
            disabled={generatingVideo || !videoPersona || !videoPrompt.trim()}
            className="w-full bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 disabled:opacity-40 px-4 py-2.5 rounded-lg font-semibold text-sm transition-all"
          >
            {generatingVideo ? "Generating..." : "Generate Video/GIF"}
          </button>

          {videoResult && (
            <p className={`text-xs p-2 rounded-lg ${
              videoResult.includes("Failed") ? "bg-red-900/30 text-red-300" : "bg-emerald-900/30 text-emerald-300"
            }`}>
              {videoResult}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}