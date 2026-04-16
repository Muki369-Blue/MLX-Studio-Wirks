"use client";

import { useEffect, useState, useRef } from "react";
import {
  buildVideoPersonaContext,
  composeVideoPrompt,
  fetchVideoPresets,
  fetchVideoLoras,
  generateVideo,
  generateVideoRemote,
  refineVideoPrompt,
  uploadVideoStartImage,
  uploadVideoStartImageRemote,
  checkVideoStatus,
  checkVideoStatusRemote,
  syncRemoteVideo,
  SHADOW_WIRKS_URL,
  type Persona,
  type VideoPreset,
  API,
} from "../lib/api";

export default function ShadowVidPanel({ personas, shadowOnline }: { personas: Persona[]; shadowOnline: boolean }) {
  const [videoPersona, setVideoPersona] = useState<number | null>(null);
  const [videoPrompt, setVideoPrompt] = useState("");
  const [videoPresets, setVideoPresets] = useState<VideoPreset[]>([]);
  const [generatingVideo, setGeneratingVideo] = useState(false);
  const [videoResult, setVideoResult] = useState<string | null>(null);
  const [useShadow, setUseShadow] = useState(shadowOnline);
  const [refiningVideo, setRefiningVideo] = useState(false);
  const [videoIntensity, setVideoIntensity] = useState<"light" | "medium" | "heavy">("medium");

  // I2V state
  const [mode, setMode] = useState<"t2v" | "i2v">("t2v");
  const [startImageFile, setStartImageFile] = useState<File | null>(null);
  const [startImagePreview, setStartImagePreview] = useState<string | null>(null);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [comfyImageName, setComfyImageName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // LoRA state
  const [videoLoras, setVideoLoras] = useState<string[]>([]);
  const [selectedLora, setSelectedLora] = useState<string>("");

  // Video settings
  const [width, setWidth] = useState(832);
  const [height, setHeight] = useState(480);
  const [length, setLength] = useState(241);
  const [steps, setSteps] = useState(30);
  const [cfg, setCfg] = useState(6.0);
  const [showSettings, setShowSettings] = useState(false);

  // Status polling
  const [contentId, setContentId] = useState<number | null>(null);
  const [videoStatus, setVideoStatus] = useState<string | null>(null);
  const [videoProgress, setVideoProgress] = useState(0);
  const [videoOutputs, setVideoOutputs] = useState<any[]>([]);

  useEffect(() => {
    fetchVideoPresets().then(setVideoPresets);
  }, []);

  // Auto-enable Shadow-Wirk on initial mount only (Mac has no Wan models)
  const shadowInitRef = useRef(false);
  useEffect(() => {
    if (shadowOnline && !shadowInitRef.current) {
      shadowInitRef.current = true;
      setUseShadow(true);
    }
  }, [shadowOnline]);

  // Fetch LoRAs from the active ComfyUI target
  useEffect(() => {
    const base = useShadow ? SHADOW_WIRKS_URL : API;
    fetchVideoLoras(base).then(setVideoLoras);
  }, [useShadow]);

  // Poll for video completion
  useEffect(() => {
    if (!contentId || videoStatus === "completed" || videoStatus === "error" || videoStatus === "failed") return;
    const interval = setInterval(async () => {
      try {
        const result = useShadow
          ? await checkVideoStatusRemote(SHADOW_WIRKS_URL, contentId)
          : await checkVideoStatus(contentId);
        setVideoStatus(result.status);
        if (result.progress !== undefined) setVideoProgress(result.progress);
        if (result.status === "completed" && result.outputs?.length) {
          setVideoOutputs(result.outputs);
          setGeneratingVideo(false);
          setVideoProgress(100);
          setVideoResult("Video generation complete!");
          clearInterval(interval);
          // Auto-sync Shadow-Wirk video to Mac vault
          if (useShadow) {
            try {
              const sync = await syncRemoteVideo(contentId);
              setVideoResult(`Video synced to Mac vault! (local #${sync.id})`);
            } catch (e: any) {
              console.warn("Auto-sync failed:", e.message);
              setVideoResult("Video complete on Shadow-Wirk (sync to Mac failed — retry from vault)");
            }
          }
        } else if (result.status === "failed") {
          setGeneratingVideo(false);
          setVideoProgress(0);
          setVideoResult("Video generation failed.");
          clearInterval(interval);
        }
      } catch {
        // keep polling
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [contentId, videoStatus, useShadow]);

  const handleSelectVideoPreset = (presetId: string) => {
    const preset = videoPresets.find((item) => item.id === presetId);
    if (preset) setVideoPrompt(preset.prompt);
  };

  const handleRefineVideo = async () => {
    if (!videoPrompt.trim()) return;
    setRefiningVideo(true);
    setVideoResult(null);
    try {
      const persona = personas.find((p) => p.id === videoPersona);
      const data = await refineVideoPrompt(
        videoPrompt,
        videoIntensity,
        buildVideoPersonaContext(persona?.prompt_base)
      );
      setVideoPrompt(data.refined);
      setVideoResult(`✨ Motion prompt refined${persona ? ` for ${persona.name}` : ""}`);
    } catch (error) {
      setVideoResult(error instanceof Error ? error.message : "Refine failed.");
    }
    setRefiningVideo(false);
  };

  const handleImageSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setStartImageFile(file);
    setStartImagePreview(URL.createObjectURL(file));
    setComfyImageName(null);

    // Upload to ComfyUI immediately
    setUploadingImage(true);
    try {
      const result = useShadow
        ? await uploadVideoStartImageRemote(SHADOW_WIRKS_URL, file)
        : await uploadVideoStartImage(file);
      setComfyImageName(result.comfy_image_name);
    } catch (error) {
      setVideoResult(error instanceof Error ? error.message : "Failed to upload image");
    }
    setUploadingImage(false);
  };

  const clearStartImage = () => {
    setStartImageFile(null);
    setStartImagePreview(null);
    setComfyImageName(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleGenerateVideo = async () => {
    // Persona required for T2V, optional for I2V
    if (mode === "t2v" && !videoPersona) return;
    if (!videoPrompt.trim()) return;
    if (mode === "i2v" && !comfyImageName) {
      setVideoResult("Upload a start image first for Image-to-Video mode.");
      return;
    }
    setGeneratingVideo(true);
    setVideoResult(null);
    setVideoOutputs([]);
    setVideoStatus(null);
    setVideoProgress(0);
    setContentId(null);
    try {
      const persona = videoPersona ? personas.find((p) => p.id === videoPersona) : null;
      const fullPrompt = composeVideoPrompt(videoPrompt, persona?.prompt_base);
      const videoOpts = {
        full_prompt: fullPrompt,
        width,
        height,
        length,
        steps,
        cfg,
        start_image: mode === "i2v" ? comfyImageName ?? undefined : undefined,
        lora_name: selectedLora || undefined,
      };
      const res = useShadow
        ? await generateVideoRemote(SHADOW_WIRKS_URL, videoPersona, videoPrompt, videoOpts)
        : await generateVideo(videoPersona, videoPrompt, videoOpts);
      setContentId(res.id);
      setVideoStatus("processing");
      const target = useShadow ? " on Shadow-Wirk" : "";
      setVideoResult(`Video queued${target} (${res.mode === "i2v" ? "Image→Video" : "Text→Video"}) — polling...`);
    } catch (error) {
      setVideoResult(error instanceof Error ? error.message : "Failed to generate video.");
      setGeneratingVideo(false);
    }
  };

  const frameCount = Math.floor((length - 1) / 4) + 1;
  const durationSecs = (length / 16).toFixed(1);

  return (
    <div className="space-y-6">
      <div className="bg-zinc-900 p-6 rounded-xl border border-zinc-800">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <span>🎥</span> ShadowVid
          <span className="text-xs bg-violet-600/20 text-violet-300 px-2 py-0.5 rounded-full ml-auto">
            Wan 2.1
          </span>
        </h2>
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-zinc-500">
            Video generation powered by Wan 2.1 via {useShadow ? "Shadow-Wirk GPU" : "local ComfyUI"}.
          </p>
          <button
            onClick={() => setUseShadow(!useShadow)}
            title={useShadow ? "Switch to local ComfyUI" : "Switch to Shadow-Wirk GPU"}
            className={`flex items-center gap-1.5 text-[10px] px-2.5 py-1 rounded-full border transition-colors ${
              useShadow
                ? "bg-emerald-600/20 text-emerald-300 border-emerald-500"
                : "bg-zinc-800 text-zinc-400 border-zinc-700 hover:border-zinc-500"
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${
              useShadow ? "bg-emerald-400" : shadowOnline ? "bg-zinc-500" : "bg-zinc-700"
            }`} />
            Shadow-Wirk
          </button>
        </div>

        <div className="space-y-3">
          {/* Mode selector */}
          <div className="flex gap-2">
            <button
              onClick={() => setMode("t2v")}
              className={`flex-1 text-xs px-3 py-2 rounded-lg border transition-colors ${
                mode === "t2v"
                  ? "bg-indigo-600/20 text-indigo-300 border-indigo-500"
                  : "bg-zinc-800 text-zinc-500 border-zinc-700 hover:border-zinc-600"
              }`}
            >
              📝 Text → Video
            </button>
            <button
              onClick={() => setMode("i2v")}
              className={`flex-1 text-xs px-3 py-2 rounded-lg border transition-colors ${
                mode === "i2v"
                  ? "bg-violet-600/20 text-violet-300 border-violet-500"
                  : "bg-zinc-800 text-zinc-500 border-zinc-700 hover:border-zinc-600"
              }`}
            >
              🖼️ Image → Video
            </button>
          </div>

          {/* I2V: Start image upload */}
          {mode === "i2v" && (
            <div className="border border-dashed border-zinc-700 rounded-lg p-3">
              <label className="text-xs text-zinc-500 mb-2 block">Start Image</label>
              {startImagePreview ? (
                <div className="relative">
                  <img
                    src={startImagePreview}
                    alt="Start"
                    className="max-h-32 rounded-lg object-cover mx-auto"
                  />
                  <button
                    onClick={clearStartImage}
                    className="absolute top-1 right-1 bg-zinc-900/80 text-zinc-400 hover:text-white rounded-full w-5 h-5 flex items-center justify-center text-xs"
                  >
                    ×
                  </button>
                  {uploadingImage && (
                    <div className="absolute inset-0 bg-black/50 flex items-center justify-center rounded-lg">
                      <span className="text-xs text-violet-300">Uploading...</span>
                    </div>
                  )}
                  {comfyImageName && (
                    <p className="text-xs text-emerald-400 mt-1 text-center">✓ Ready</p>
                  )}
                </div>
              ) : (
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full py-4 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  Click to upload a start image
                </button>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleImageSelect}
                className="hidden"
              />
            </div>
          )}

          {/* Persona selector */}
          <select
            className="w-full p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:border-violet-500 focus:outline-none"
            value={videoPersona ?? ""}
            onChange={(e) => setVideoPersona(Number(e.target.value) || null)}
          >
            <option value="">{mode === "i2v" ? "Persona (optional for I2V)..." : "Select persona..."}</option>
            {personas.map((persona) => (
              <option key={persona.id} value={persona.id}>{persona.name}</option>
            ))}
          </select>

          {/* LoRA selector */}
          {videoLoras.length > 0 && (
            <div>
              <label className="text-xs text-zinc-500 mb-1 block">LoRA (optional)</label>
              <select
                className="w-full p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:border-violet-500 focus:outline-none"
                value={selectedLora}
                onChange={(e) => setSelectedLora(e.target.value)}
              >
                <option value="">No LoRA</option>
                {videoLoras.map((lora) => (
                  <option key={lora} value={lora}>{lora.replace(/\.safetensors$/, "")}</option>
                ))}
              </select>
            </div>
          )}

          {/* Motion presets */}
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

          {/* Prompt textarea */}
          <textarea
            className="w-full p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm placeholder-zinc-500 focus:border-violet-500 focus:outline-none min-h-[72px]"
            placeholder="Motion prompt (e.g. 'hair blowing in wind, gentle smile, looking at camera')"
            value={videoPrompt}
            onChange={(e) => setVideoPrompt(e.target.value)}
          />

          {/* Refine controls */}
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

          {/* Video settings toggle */}
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            ⚙️ {showSettings ? "Hide" : "Show"} video settings
          </button>

          {showSettings && (
            <div className="grid grid-cols-2 gap-2 bg-zinc-800/50 p-3 rounded-lg border border-zinc-700">
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Width</label>
                <input type="number" step={16} min={256} max={1280} value={width}
                  onChange={e => setWidth(Number(e.target.value))}
                  className="w-full p-1.5 bg-zinc-800 border border-zinc-700 rounded text-xs" />
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Height</label>
                <input type="number" step={16} min={256} max={1280} value={height}
                  onChange={e => setHeight(Number(e.target.value))}
                  className="w-full p-1.5 bg-zinc-800 border border-zinc-700 rounded text-xs" />
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Frames ({durationSecs}s @ 16fps)</label>
                <input type="number" step={4} min={17} max={201} value={length}
                  onChange={e => setLength(Number(e.target.value))}
                  className="w-full p-1.5 bg-zinc-800 border border-zinc-700 rounded text-xs" />
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Steps</label>
                <input type="number" min={4} max={50} value={steps}
                  onChange={e => setSteps(Number(e.target.value))}
                  className="w-full p-1.5 bg-zinc-800 border border-zinc-700 rounded text-xs" />
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">CFG</label>
                <input type="number" step={0.5} min={1} max={15} value={cfg}
                  onChange={e => setCfg(Number(e.target.value))}
                  className="w-full p-1.5 bg-zinc-800 border border-zinc-700 rounded text-xs" />
              </div>
              <div className="flex items-end">
                <span className="text-xs text-zinc-600">{frameCount} latent frames</span>
              </div>
            </div>
          )}

          {/* Generate button */}
          <button
            onClick={handleGenerateVideo}
            disabled={generatingVideo || !videoPrompt.trim() || (mode === "t2v" && !videoPersona) || (mode === "i2v" && !comfyImageName)}
            className="w-full bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 disabled:opacity-40 px-4 py-2.5 rounded-lg font-semibold text-sm transition-all"
          >
            {generatingVideo
              ? `Generating ${mode === "i2v" ? "I2V" : "T2V"}...`
              : `Generate ${mode === "i2v" ? "Image→Video" : "Text→Video"}`}
          </button>

          {/* Progress bar */}
          {generatingVideo && (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-zinc-400">
                  {videoProgress === 0 ? "Queued — waiting for GPU..." : videoProgress >= 100 ? "Finalizing..." : "Generating..."}
                </span>
                <span className="text-violet-300 font-mono">{videoProgress}%</span>
              </div>
              <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden border border-zinc-700">
                <div
                  className="h-full rounded-full transition-all duration-700 ease-out"
                  style={{
                    width: `${Math.max(videoProgress, 2)}%`,
                    background: videoProgress >= 100
                      ? "linear-gradient(90deg, #10b981, #34d399)"
                      : "linear-gradient(90deg, #6366f1, #8b5cf6)",
                  }}
                />
              </div>
            </div>
          )}

          {/* Status / result */}
          {videoResult && (
            <p className={`text-xs p-2 rounded-lg ${
              videoResult.includes("Failed") || videoResult.includes("failed")
                ? "bg-red-900/30 text-red-300"
                : videoResult.includes("complete")
                  ? "bg-emerald-900/30 text-emerald-300"
                  : "bg-blue-900/30 text-blue-300"
            }`}>
              {videoResult}
            </p>
          )}

          {/* Video output display */}
          {videoOutputs.length > 0 && (() => {
            const videoBase = useShadow ? SHADOW_WIRKS_URL : API;
            return (
            <div className="border border-zinc-700 rounded-lg p-3">
              <label className="text-xs text-zinc-500 block mb-2">Output{useShadow ? " (from Shadow-Wirk)" : ""}</label>
              {videoOutputs.map((out, i) => {
                const src = `${videoBase}/images/${encodeURIComponent(out.filename)}?subfolder=${encodeURIComponent(out.subfolder || "")}`;
                const downloadUrl = `${videoBase}/download/${encodeURIComponent(out.filename)}?subfolder=${encodeURIComponent(out.subfolder || "")}`;
                return (
                <div key={i} className="text-center">
                  <img
                    src={src}
                    alt="Generated video"
                    className="max-w-full rounded-lg mx-auto"
                  />
                  <a
                    href={downloadUrl}
                    download={out.filename}
                    className="inline-block mt-2 text-xs text-violet-400 hover:text-violet-300"
                  >
                    ⬇ Download {out.filename}
                  </a>
                </div>
                );
              })}
            </div>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
