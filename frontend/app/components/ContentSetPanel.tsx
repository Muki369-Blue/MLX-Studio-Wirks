"use client";

import { useState, useEffect } from "react";
import {
  createContentSet,
  fetchContentSetPresets,
  fetchNegativePromptPresets,
  fetchLoras,
  refinePrompt,
  type Persona,
  type ContentSetPreset,
  type NegativePromptPreset,
  type InstalledLora,
  type RecommendedLora,
} from "../lib/api";

export default function ContentSetPanel({ personas }: { personas: Persona[] }) {
  const [personaId, setPersonaId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [scene, setScene] = useState("");
  const [setSize, setSetSize] = useState(4);
  const [creating, setCreating] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  // Refiner state for photo sets
  const [refiningScene, setRefiningScene] = useState(false);
  const [sceneIntensity, setSceneIntensity] = useState<"light" | "medium" | "heavy">("medium");

  // Presets
  const [setPresets, setSetPresets] = useState<ContentSetPreset[]>([]);

  // Negative prompt state (shared)
  const [negPresets, setNegPresets] = useState<NegativePromptPreset[]>([]);
  const [negativePrompt, setNegativePrompt] = useState("");
  const [negActivePreset, setNegActivePreset] = useState<string>("default");
  const [showNegative, setShowNegative] = useState(false);

  // LoRA state (shared)
  const [installedLoras, setInstalledLoras] = useState<InstalledLora[]>([]);
  const [recommendedLoras, setRecommendedLoras] = useState<RecommendedLora[]>([]);
  const [selectedLora, setSelectedLora] = useState<string>("");
  const [showLoras, setShowLoras] = useState(false);

  useEffect(() => {
    fetchContentSetPresets().then(setSetPresets);
    fetchNegativePromptPresets().then((np) => {
      setNegPresets(np);
      const def = np.find((p) => p.id === "default");
      if (def) setNegativePrompt(def.prompt);
    });
    fetchLoras().then((data) => {
      setInstalledLoras(data.installed);
      setRecommendedLoras(data.recommended);
    });
  }, []);

  const handleSelectSetPreset = (presetId: string) => {
    const preset = setPresets.find((p) => p.id === presetId);
    if (!preset) return;
    setName(preset.name);
    setScene(preset.prompt);
    setSetSize(preset.set_size);
  };

  const handleRefineScene = async () => {
    if (!scene.trim()) return;
    setRefiningScene(true);
    try {
      const data = await refinePrompt(scene, sceneIntensity);
      setScene(data.refined);
      setResult(`✨ Scene refined by Celeste`);
    } catch {
      setResult("Refine failed — is Ollama running?");
    }
    setRefiningScene(false);
  };

  const handleCreateSet = async () => {
    if (!personaId || !name.trim() || !scene.trim()) return;
    setCreating(true);
    setResult(null);
    try {
      const set = await createContentSet({
        persona_id: personaId,
        name,
        scene_prompt: scene,
        set_size: setSize,
        negative_prompt: negativePrompt.trim() || undefined,
        lora_override: selectedLora || undefined,
      });
      setResult(`Set "${set.name}" created with ${set.set_size} images! Status: ${set.status}`);
      setName("");
      setScene("");
    } catch {
      setResult("Failed to create set.");
    }
    setCreating(false);
  };

  return (
    <div className="space-y-6">
      {/* Photo Sets */}
      <div className="bg-zinc-900 p-6 rounded-xl border border-zinc-800">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <span>📸</span> Photo Set Generator
        </h2>
        <p className="text-xs text-zinc-500 mb-3">
          Generate coherent multi-image sets using seed-walking for consistent lighting & poses.
        </p>
        <p className="text-xs text-violet-300/80 mb-3">
          Video generation has moved to the ShadowVid tab.
        </p>

        <div className="space-y-3">
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

          {/* Content Set Preset Picker */}
          <div>
            <label className="text-xs text-zinc-500 mb-1 block">Quick Preset</label>
            <select
              className="w-full p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:border-orange-500 focus:outline-none"
              value=""
              onChange={(e) => handleSelectSetPreset(e.target.value)}
            >
              <option value="">Choose a preset or write your own...</option>
              {setPresets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label} — {p.description}
                </option>
              ))}
            </select>
          </div>

          <input
            className="w-full p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm placeholder-zinc-500 focus:border-purple-500 focus:outline-none"
            placeholder="Set name (e.g. 'Beach Sunset Series')"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />

          <textarea
            className="w-full p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm placeholder-zinc-500 focus:border-purple-500 focus:outline-none min-h-[60px]"
            placeholder="Scene prompt (e.g. 'bikini, tropical beach, sunset lighting, waves')"
            value={scene}
            onChange={(e) => setScene(e.target.value)}
          />

          {/* Scene Prompt Refiner */}
          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              {(["light", "medium", "heavy"] as const).map((lvl) => (
                <button
                  key={lvl}
                  onClick={() => setSceneIntensity(lvl)}
                  className={`text-xs px-2 py-1 rounded transition-colors ${
                    sceneIntensity === lvl
                      ? "bg-amber-600/30 text-amber-300 border border-amber-500"
                      : "bg-zinc-800 text-zinc-500 border border-zinc-700 hover:border-zinc-600"
                  }`}
                  title={lvl}
                >
                  {lvl === "light" ? "🔥" : lvl === "medium" ? "🔥🔥" : "🔥🔥🔥"}
                </button>
              ))}
            </div>
            <button
              onClick={handleRefineScene}
              disabled={refiningScene || !scene.trim()}
              className="flex-1 text-xs px-3 py-1.5 bg-amber-600/20 text-amber-300 border border-amber-600/40 hover:bg-amber-600/30 disabled:opacity-40 rounded-lg transition-colors"
            >
              {refiningScene ? "✨ Refining..." : "✨ Refine with Celeste"}
            </button>
          </div>

          {/* ── Negative Prompt (shared) ── */}
          <div className="border border-zinc-800 rounded-xl overflow-hidden">
            <button
              onClick={() => setShowNegative(!showNegative)}
              className="w-full flex items-center justify-between p-2.5 bg-zinc-800/40 hover:bg-zinc-800/60 transition-colors text-xs"
            >
              <span className="flex items-center gap-2">
                <span>⛔</span> Negative Prompt
                {negativePrompt && <span className="text-[10px] text-red-400 bg-red-900/30 px-1.5 py-0.5 rounded">active</span>}
              </span>
              <span className="text-zinc-500">{showNegative ? "▾" : "▸"}</span>
            </button>
            {showNegative && (
              <div className="p-2.5 space-y-2 border-t border-zinc-800">
                <div className="flex flex-wrap gap-1">
                  {negPresets.map((np) => (
                    <button
                      key={np.id}
                      onClick={() => { setNegativePrompt(np.prompt); setNegActivePreset(np.id); }}
                      title={np.description}
                      className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                        negActivePreset === np.id
                          ? "border-red-500 bg-red-600/20 text-red-300"
                          : "border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600"
                      }`}
                    >
                      {np.label}
                    </button>
                  ))}
                  <button
                    onClick={() => { setNegativePrompt(""); setNegActivePreset(""); }}
                    className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                      !negativePrompt ? "border-zinc-500 bg-zinc-700/50 text-zinc-300" : "border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600"
                    }`}
                  >
                    None
                  </button>
                </div>
                <textarea
                  className="w-full p-2 bg-zinc-800 border border-zinc-700 rounded-lg text-[11px] placeholder-zinc-500 focus:border-red-500 focus:outline-none min-h-[50px] text-red-300/80"
                  placeholder="Things to avoid..."
                  value={negativePrompt}
                  onChange={(e) => { setNegativePrompt(e.target.value); setNegActivePreset(""); }}
                />
              </div>
            )}
          </div>

          {/* ── LoRA Override ── */}
          <div className="border border-zinc-800 rounded-xl overflow-hidden">
            <button
              onClick={() => setShowLoras(!showLoras)}
              className="w-full flex items-center justify-between p-2.5 bg-zinc-800/40 hover:bg-zinc-800/60 transition-colors text-xs"
            >
              <span className="flex items-center gap-2">
                <span>🧬</span> LoRA
                {selectedLora && <span className="text-[10px] text-cyan-400 bg-cyan-900/30 px-1.5 py-0.5 rounded">{selectedLora.replace(/\.safetensors$/, "")}</span>}
              </span>
              <span className="text-zinc-500">{showLoras ? "▾" : "▸"}</span>
            </button>
            {showLoras && (
              <div className="p-2.5 space-y-2 border-t border-zinc-800">
                {installedLoras.length > 0 ? (
                  <div className="space-y-1">
                    {installedLoras.map((lora) => (
                      <label
                        key={lora.filename}
                        className={`flex items-center gap-2 p-1.5 rounded-lg cursor-pointer transition-colors text-xs ${
                          selectedLora === lora.filename ? "bg-cyan-900/20 border border-cyan-700" : "bg-zinc-800/50 border border-transparent hover:bg-zinc-800"
                        }`}
                      >
                        <input type="radio" name="setlora" checked={selectedLora === lora.filename} onChange={() => setSelectedLora(selectedLora === lora.filename ? "" : lora.filename)} className="accent-cyan-500" />
                        <span className="text-zinc-200 truncate">{lora.name}</span>
                        <span className="text-[10px] text-zinc-500 ml-auto">{lora.size_mb}MB</span>
                      </label>
                    ))}
                    {selectedLora && <button onClick={() => setSelectedLora("")} className="text-[10px] text-zinc-400 hover:text-zinc-300">✕ Clear</button>}
                  </div>
                ) : (
                  <p className="text-[10px] text-zinc-500">No LoRAs installed. Add .safetensors files to ~/Documents/ComfyUI/models/loras/</p>
                )}
                {recommendedLoras.filter((l) => !l.installed).length > 0 && (
                  <details className="text-[10px] text-zinc-500">
                    <summary className="cursor-pointer hover:text-zinc-400">Recommended LoRAs to install</summary>
                    <div className="mt-1 space-y-0.5">
                      {recommendedLoras.filter((l) => !l.installed).map((l) => (
                        <div key={l.id} className="flex justify-between px-1">
                          <span>{l.name}</span>
                          <span className="text-zinc-600">{l.category}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            <label className="text-sm text-zinc-400">Set Size:</label>
            <div className="flex gap-1.5">
              {[3, 4, 6, 8, 10].map((n) => (
                <button
                  key={n}
                  onClick={() => setSetSize(n)}
                  className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                    setSize === n
                      ? "border-orange-500 bg-orange-600/20 text-orange-300"
                      : "border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={handleCreateSet}
            disabled={creating || !personaId || !name.trim() || !scene.trim()}
            className="w-full bg-gradient-to-r from-orange-600 to-amber-600 hover:from-orange-700 hover:to-amber-700 disabled:opacity-40 px-4 py-2.5 rounded-lg font-semibold text-sm transition-all"
          >
            {creating ? "Generating Set..." : `Generate ${setSize}-Image Set`}
          </button>

          {result && (
            <p className={`text-xs p-2 rounded-lg ${
              result.includes("Failed") ? "bg-red-900/30 text-red-300" : "bg-emerald-900/30 text-emerald-300"
            }`}>
              {result}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
