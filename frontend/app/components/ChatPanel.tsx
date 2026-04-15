"use client";

import { useState, useEffect, useRef } from "react";
import { sendChat, fetchChatHistory, fetchConversations, type Persona, type ChatMessage } from "../lib/api";

export default function ChatPanel({ personas }: { personas: Persona[] }) {
  const [personaId, setPersonaId] = useState<number | null>(null);
  const [conversationId, setConversationId] = useState("fan_" + Date.now());
  const [conversations, setConversations] = useState<{ conversation_id: string; message_count: number }[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (personaId) {
      fetchConversations(personaId).then(setConversations).catch(() => {});
    }
  }, [personaId]);

  useEffect(() => {
    if (personaId && conversationId) {
      fetchChatHistory(personaId, conversationId).then(setMessages).catch(() => {});
    }
  }, [personaId, conversationId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!personaId || !input.trim()) return;
    setSending(true);
    const fan: ChatMessage = { id: 0, persona_id: personaId, conversation_id: conversationId, role: "fan", message: input, created_at: null };
    setMessages((prev) => [...prev, fan]);
    setInput("");
    try {
      const reply = await sendChat(personaId, conversationId, input);
      setMessages((prev) => [...prev.filter((m) => m.id !== 0 || m.role !== "fan"), fan, reply]);
      // Refresh msg list removing temp
      fetchChatHistory(personaId, conversationId).then(setMessages);
    } catch {
      setMessages((prev) => [...prev, { id: -1, persona_id: personaId, conversation_id: conversationId, role: "persona", message: "Sorry, couldn't connect. Try again!", created_at: null }]);
    }
    setSending(false);
  };

  const persona = personas.find((p) => p.id === personaId);

  return (
    <div className="bg-zinc-900 p-6 rounded-xl border border-zinc-800 flex flex-col" style={{ minHeight: 400 }}>
      <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <span>💬</span> Fan Chat AI
      </h2>

      <div className="flex gap-2 mb-3">
        <select
          className="flex-1 p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:border-purple-500 focus:outline-none"
          value={personaId ?? ""}
          onChange={(e) => { setPersonaId(Number(e.target.value) || null); setMessages([]); setConversationId("fan_" + Date.now()); }}
        >
          <option value="">Select persona...</option>
          {personas.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <button
          onClick={() => { setConversationId("fan_" + Date.now()); setMessages([]); }}
          className="text-xs px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg hover:bg-zinc-700 transition-colors"
        >
          New Chat
        </button>
      </div>

      {/* Existing conversations */}
      {conversations.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {conversations.slice(0, 5).map((c) => (
            <button
              key={c.conversation_id}
              onClick={() => { setConversationId(c.conversation_id); }}
              className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                conversationId === c.conversation_id
                  ? "border-pink-500 bg-pink-600/20 text-pink-300"
                  : "border-zinc-700 text-zinc-500 hover:border-zinc-600"
              }`}
            >
              {c.conversation_id.substring(0, 12)}... ({c.message_count})
            </button>
          ))}
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-2 mb-3 min-h-[200px] max-h-[400px] pr-1">
        {messages.length === 0 && personaId && (
          <p className="text-zinc-500 text-sm text-center mt-8">
            Start chatting as a fan with {persona?.name ?? "the persona"}...
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "fan" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[80%] px-3 py-2 rounded-2xl text-sm ${
              msg.role === "fan"
                ? "bg-purple-600/30 text-purple-100 rounded-br-md"
                : "bg-zinc-800 text-zinc-200 rounded-bl-md"
            }`}>
              {msg.role === "persona" && (
                <span className="text-[10px] text-pink-400 font-medium block mb-0.5">{persona?.name}</span>
              )}
              {msg.message}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-zinc-800 px-3 py-2 rounded-2xl rounded-bl-md">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          className="flex-1 p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm placeholder-zinc-500 focus:border-pink-500 focus:outline-none"
          placeholder={personaId ? `Message ${persona?.name ?? "persona"}...` : "Select a persona first"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          disabled={!personaId}
        />
        <button
          onClick={handleSend}
          disabled={sending || !personaId || !input.trim()}
          className="px-4 py-2.5 bg-gradient-to-r from-pink-600 to-rose-600 hover:from-pink-700 hover:to-rose-700 disabled:opacity-40 rounded-lg font-semibold text-sm transition-all"
        >
          Send
        </button>
      </div>
    </div>
  );
}
