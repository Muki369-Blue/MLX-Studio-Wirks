export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8800";
export const VIDEO_API = process.env.NEXT_PUBLIC_VIDEO_API_URL ?? API;

export function imageUrl(filename: string, subfolder: string = "Empire"): string {
  return `${API}/images/${encodeURIComponent(filename)}?subfolder=${encodeURIComponent(subfolder)}`;
}

export function referenceImageUrl(personaId: number): string {
  return `${API}/personas/${personaId}/reference-image`;
}

export async function uploadReferenceImage(personaId: number, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/personas/${personaId}/upload-reference`, { method: "POST", body: form });
  return res.json();
}

export async function deleteReferenceImage(personaId: number) {
  const res = await fetch(`${API}/personas/${personaId}/reference`, { method: "DELETE" });
  return res.json();
}

export interface Persona {
  id: number;
  name: string;
  prompt_base: string;
  lora_name: string | null;
  lora_status?: string;
  personality?: string | null;
  reference_image?: string | null;
  voice?: string | null;
  created_at: string | null;
}

export interface Generation {
  id: number;
  persona_id: number;
  file_path: string | null;
  prompt_used: string | null;
  comfy_job_id: string | null;
  status: string;
  upscaled_path?: string | null;
  watermarked_path?: string | null;
  caption?: string | null;
  hashtags?: string | null;
  is_posted?: boolean;
  posted_platforms?: string | null;
  set_id?: number | null;
  is_favorite?: boolean;
  tags?: string | null;
  created_at: string | null;
}

export interface Link {
  id: number;
  platform: string;
  url: string;
}

export interface ContentSet {
  id: number;
  persona_id: number;
  name: string;
  description: string | null;
  scene_prompt: string | null;
  set_size: number;
  status: string;
  items: Generation[];
  created_at: string | null;
}

export interface ScheduleItem {
  id: number;
  persona_id: number;
  prompt_template: string;
  cron_expression: string;
  batch_size: number;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
}

export interface PostQueueItem {
  id: number;
  content_id: number;
  platform: string;
  caption: string | null;
  scheduled_at: string | null;
  status: string;
  posted_at: string | null;
}

export interface ChatMessage {
  id: number;
  persona_id: number;
  conversation_id: string;
  role: string;
  message: string;
  created_at: string | null;
}

export interface VaultItem {
  id: number;
  persona_id: number;
  file_path: string | null;
  upscaled_path: string | null;
  watermarked_path: string | null;
  prompt_used: string | null;
  caption: string | null;
  hashtags: string | null;
  is_favorite: boolean;
  is_posted: boolean;
  posted_platforms: string | null;
  tags: string | null;
  set_id: number | null;
  created_at: string | null;
}

export interface AnalyticsSummary {
  total_revenue: number;
  total_tips: number;
  total_subscribers: number;
  total_content: number;
  top_persona: string | null;
  by_platform: Record<string, { revenue: number; tips: number; subscribers: number }>;
  by_persona: { persona_id: number; name: string; revenue: number; content_count: number }[];
}

// ─── Personas ─────────────────────

export async function fetchPersonas(): Promise<Persona[]> {
  const res = await fetch(`${API}/personas/`);
  if (!res.ok) throw new Error("Failed to fetch personas");
  return res.json();
}

export async function createPersona(data: {
  name: string;
  prompt_base: string;
  lora_name?: string;
  personality?: string;
}): Promise<Persona> {
  const res = await fetch(`${API}/personas/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to create persona");
  }
  return res.json();
}

export async function deletePersona(id: number): Promise<void> {
  await fetch(`${API}/personas/${id}`, { method: "DELETE" });
}

// ─── LoRA Training ────────────────

export async function uploadTrainingImages(personaId: number, files: FileList): Promise<any> {
  const form = new FormData();
  for (let i = 0; i < files.length; i++) form.append("files", files[i]);
  const res = await fetch(`${API}/personas/${personaId}/upload-training-images`, { method: "POST", body: form });
  if (!res.ok) throw new Error("Failed to upload images");
  return res.json();
}

export async function startLoraTraining(personaId: number, steps: number = 1000): Promise<any> {
  const res = await fetch(`${API}/personas/${personaId}/train-lora`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona_id: personaId, training_steps: steps }),
  });
  if (!res.ok) throw new Error("Failed to start training");
  return res.json();
}

export async function getLoraStatus(personaId: number): Promise<{ lora_status: string; lora_name: string | null }> {
  const res = await fetch(`${API}/personas/${personaId}/lora-status`);
  if (!res.ok) throw new Error("Failed to get LoRA status");
  return res.json();
}

// ─── Generation ───────────────────

export async function triggerGeneration(
  personaId: number,
  promptExtra: string,
  batchSize: number = 1,
  negativePrompt?: string,
  loraOverride?: string,
): Promise<Generation[]> {
  const res = await fetch(`${API}/generate/${personaId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt_extra: promptExtra,
      batch_size: batchSize,
      negative_prompt: negativePrompt || null,
      lora_override: loraOverride || null,
    }),
  });
  if (!res.ok) throw new Error("Failed to trigger generation");
  return res.json();
}

export async function fetchGenerations(): Promise<Generation[]> {
  const res = await fetch(`${API}/generations/`);
  if (!res.ok) throw new Error("Failed to fetch generations");
  return res.json();
}

export async function checkGenerationStatus(
  contentId: number
): Promise<{ status: string; outputs: any[] }> {
  const res = await fetch(`${API}/generations/${contentId}/status`);
  if (!res.ok) throw new Error("Failed to check status");
  return res.json();
}

// ─── Content Sets ─────────────────

export async function createContentSet(data: {
  persona_id: number;
  name: string;
  description?: string;
  scene_prompt: string;
  set_size: number;
  negative_prompt?: string;
  lora_override?: string;
}): Promise<ContentSet> {
  const res = await fetch(`${API}/content-sets/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create content set");
  return res.json();
}

export async function fetchContentSets(): Promise<ContentSet[]> {
  const res = await fetch(`${API}/content-sets/`);
  if (!res.ok) throw new Error("Failed to fetch content sets");
  return res.json();
}

// ─── Schedules ────────────────────

export async function createSchedule(data: {
  persona_id: number;
  prompt_template: string;
  cron_expression: string;
  batch_size: number;
}): Promise<ScheduleItem> {
  const res = await fetch(`${API}/schedules/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create schedule");
  return res.json();
}

export async function fetchSchedules(): Promise<ScheduleItem[]> {
  const res = await fetch(`${API}/schedules/`);
  if (!res.ok) throw new Error("Failed to fetch schedules");
  return res.json();
}

export async function toggleSchedule(id: number): Promise<{ enabled: boolean }> {
  const res = await fetch(`${API}/schedules/${id}/toggle`, { method: "PATCH" });
  if (!res.ok) throw new Error("Failed to toggle schedule");
  return res.json();
}

export async function deleteSchedule(id: number): Promise<void> {
  await fetch(`${API}/schedules/${id}`, { method: "DELETE" });
}

// ─── Post Queue ───────────────────

export async function queuePost(data: {
  content_id: number;
  platform: string;
  caption?: string;
}): Promise<PostQueueItem> {
  const res = await fetch(`${API}/post-queue/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to queue post");
  return res.json();
}

export async function fetchPostQueue(): Promise<PostQueueItem[]> {
  const res = await fetch(`${API}/post-queue/`);
  if (!res.ok) throw new Error("Failed to fetch post queue");
  return res.json();
}

export async function postNow(id: number): Promise<any> {
  const res = await fetch(`${API}/post-queue/${id}/post-now`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to post");
  return res.json();
}

// ─── Captions ─────────────────────

export async function generateCaption(contentId: number, platform: string = "onlyfans"): Promise<{ caption: string; hashtags: string }> {
  const res = await fetch(`${API}/generate-caption`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content_id: contentId, platform }),
  });
  if (!res.ok) throw new Error("Failed to generate caption");
  return res.json();
}

// ─── Chat ─────────────────────────

export async function sendChat(personaId: number, conversationId: string, message: string): Promise<ChatMessage> {
  const res = await fetch(`${API}/chat/${personaId}/${conversationId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error("Failed to send message");
  return res.json();
}

export async function fetchChatHistory(personaId: number, conversationId: string): Promise<ChatMessage[]> {
  const res = await fetch(`${API}/chat/${personaId}/${conversationId}`);
  if (!res.ok) throw new Error("Failed to fetch chat");
  return res.json();
}

export async function fetchConversations(personaId: number): Promise<{ conversation_id: string; message_count: number; last_message: string }[]> {
  const res = await fetch(`${API}/chat/${personaId}/conversations`);
  if (!res.ok) throw new Error("Failed to fetch conversations");
  return res.json();
}

// ─── Video ────────────────────────

export async function uploadVideoStartImage(file: File): Promise<{ comfy_image_name: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${VIDEO_API}/upload-video-start-image`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to upload start image" }));
    throw new Error(err.detail || "Failed to upload start image");
  }
  return res.json();
}

export async function generateVideo(
  personaId: number,
  promptExtra: string,
  opts?: {
    negative_prompt?: string;
    width?: number;
    height?: number;
    length?: number;
    steps?: number;
    cfg?: number;
    start_image?: string;
  }
): Promise<any> {
  const res = await fetch(`${VIDEO_API}/generate-video/${personaId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt_extra: promptExtra,
      negative_prompt: opts?.negative_prompt || null,
      width: opts?.width ?? 832,
      height: opts?.height ?? 480,
      length: opts?.length ?? 81,
      steps: opts?.steps ?? 20,
      cfg: opts?.cfg ?? 6.0,
      start_image: opts?.start_image || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to generate video" }));
    throw new Error(err.detail || "Failed to generate video");
  }
  return res.json();
}

export async function checkVideoStatus(contentId: number): Promise<{ status: string; outputs: any[] }> {
  const res = await fetch(`${VIDEO_API}/video-status/${contentId}`);
  if (!res.ok) throw new Error("Failed to check video status");
  return res.json();
}

export async function refineVideoPrompt(
  prompt: string,
  intensity: "light" | "medium" | "heavy" = "medium"
): Promise<{ original?: string; refined: string; model?: string }> {
  const res = await fetch(`${VIDEO_API}/refine-video-prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, intensity }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Video refine failed" }));
    throw new Error(err.detail || `Video refine failed (${res.status})`);
  }
  return res.json();
}

// ─── Vault ────────────────────────

export async function fetchVault(opts?: { persona_id?: number; favorites_only?: boolean; tag?: string }): Promise<VaultItem[]> {
  const params = new URLSearchParams();
  if (opts?.persona_id) params.set("persona_id", String(opts.persona_id));
  if (opts?.favorites_only) params.set("favorites_only", "true");
  if (opts?.tag) params.set("tag", opts.tag);
  const res = await fetch(`${API}/vault/?${params}`);
  if (!res.ok) throw new Error("Failed to fetch vault");
  return res.json();
}

export async function toggleFavorite(contentId: number): Promise<{ is_favorite: boolean }> {
  const res = await fetch(`${API}/vault/${contentId}/favorite`, { method: "PATCH" });
  if (!res.ok) throw new Error("Failed to toggle favorite");
  return res.json();
}

export async function fetchVaultStats(): Promise<any> {
  const res = await fetch(`${API}/vault/stats`);
  if (!res.ok) throw new Error("Failed to fetch vault stats");
  return res.json();
}

// ─── Analytics ────────────────────

export async function addAnalytics(data: {
  persona_id: number;
  date: string;
  platform: string;
  subscribers?: number;
  revenue?: number;
  tips?: number;
}): Promise<any> {
  const res = await fetch(`${API}/analytics/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to add analytics");
  return res.json();
}

export async function fetchAnalyticsSummary(): Promise<AnalyticsSummary> {
  const res = await fetch(`${API}/analytics/summary`);
  if (!res.ok) throw new Error("Failed to fetch analytics");
  return res.json();
}

// ─── Links ────────────────────────

export async function fetchLinks(): Promise<Link[]> {
  const res = await fetch(`${API}/links/`);
  if (!res.ok) throw new Error("Failed to fetch links");
  return res.json();
}

export async function createLink(data: { platform: string; url: string }): Promise<Link> {
  const res = await fetch(`${API}/links/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create link");
  return res.json();
}

export async function deleteLink(id: number): Promise<void> {
  await fetch(`${API}/links/${id}`, { method: "DELETE" });
}

// ─── Presets ──────────────────────

export interface ScenePreset {
  id: string;
  label: string;
  prompt: string;
}

export interface ContentSetPreset {
  id: string;
  label: string;
  name: string;
  prompt: string;
  set_size: number;
  description: string;
}

export interface VideoPreset {
  id: string;
  label: string;
  prompt: string;
}

export interface PersonaPreset {
  id: string;
  label: string;
  name: string;
  prompt_base: string;
}

export async function fetchScenePresets(): Promise<ScenePreset[]> {
  const res = await fetch(`${API}/presets/scenes`);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchContentSetPresets(): Promise<ContentSetPreset[]> {
  const res = await fetch(`${API}/presets/content-sets`);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchVideoPresets(): Promise<VideoPreset[]> {
  const res = await fetch(`${VIDEO_API}/presets/videos`);
  if (!res.ok) return [];
  return res.json();
}

// ─── Negative Prompt Presets ──────

export interface NegativePromptPreset {
  id: string;
  label: string;
  prompt: string;
  description: string;
}

export async function fetchNegativePromptPresets(): Promise<NegativePromptPreset[]> {
  const res = await fetch(`${API}/presets/negative-prompts`);
  if (!res.ok) return [];
  return res.json();
}

// ─── LoRA Discovery ───────────────

export interface InstalledLora {
  filename: string;
  name: string;
  size_mb: number;
}

export interface RecommendedLora {
  id: string;
  name: string;
  filename: string;
  description: string;
  category: string;
  installed: boolean;
}

export async function fetchLoras(): Promise<{ installed: InstalledLora[]; recommended: RecommendedLora[] }> {
  const res = await fetch(`${API}/loras`);
  if (!res.ok) return { installed: [], recommended: [] };
  return res.json();
}

export async function fetchPersonaPresets(): Promise<PersonaPreset[]> {
  const res = await fetch(`${API}/presets/personas`);
  if (!res.ok) return [];
  return res.json();
}

// ─── Voice ────────────────────────

export interface VoicePreset {
  id: string;
  label: string;
  accent: string;
  style: string;
  styles: string[];
}

export interface VoiceMood {
  persona_id: number;
  mood: string;
  prosody: { rate: string; pitch: string; volume: string };
  style: string;
}

export async function fetchVoicePresets(): Promise<VoicePreset[]> {
  const res = await fetch(`${API}/presets/voices`);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchVoiceMood(personaId: number): Promise<VoiceMood | null> {
  const res = await fetch(`${API}/personas/${personaId}/voice-mood`);
  if (!res.ok) return null;
  return res.json();
}

export async function setPersonaVoice(personaId: number, voiceId: string): Promise<void> {
  await fetch(`${API}/personas/${personaId}/set-voice`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ voice_id: voiceId }),
  });
}

export async function removePersonaVoice(personaId: number): Promise<void> {
  await fetch(`${API}/personas/${personaId}/voice`, { method: "DELETE" });
}

export async function speakAsPersona(personaId: number, text: string): Promise<Blob> {
  const res = await fetch(`${API}/personas/${personaId}/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error("TTS failed");
  return res.blob();
}

export function previewVoiceUrl(personaId: number): string {
  return `${API}/personas/${personaId}/preview-voice`;
}

// ─── Health ───────────────────────

export async function fetchHealth(): Promise<{ api: string; comfyui: boolean }> {
  const res = await fetch(`${API}/health`);
  if (!res.ok) throw new Error("API unreachable");
  return res.json();
}

// ─── Prompt Refiner ───────────────

export async function refinePrompt(
  prompt: string,
  intensity: "light" | "medium" | "heavy" = "medium"
): Promise<{ original: string; refined: string; model?: string }> {
  const res = await fetch(`${API}/refine-prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, intensity }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || `Refine failed (${res.status})`);
  }
  return res.json();
}
