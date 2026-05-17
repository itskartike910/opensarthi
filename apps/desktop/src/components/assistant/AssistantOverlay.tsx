import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Settings, Minimize2, WifiOff, Activity } from "lucide-react";
import { VoiceButton } from "./VoiceButton";
import { Waveform } from "./Waveform";
import { TranscriptView } from "./TranscriptView";
import { MessageList } from "./ResponseBubble";
import { ActionLog } from "../execution/ActionLog";
import { useAssistantStore } from "../../stores/assistantStore";
import { wsClient } from "../../lib/ws";

interface AssistantOverlayProps {
  onOpenSettings: () => void;
}

export function AssistantOverlay({ onOpenSettings }: AssistantOverlayProps) {
  const [textInput, setTextInput] = useState("");
  const [minimized, setMinimized] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const {
    voiceState, isConnected, currentTranscript,
    messages, currentPlan,
    setVoiceState,
  } = useAssistantStore();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentTranscript]);

  const handleVoiceClick = useCallback(() => {
    if (voiceState === "idle" || voiceState === "error") {
      wsClient.send("session_state", { active: true });
      setVoiceState("listening");
    } else if (voiceState === "listening") {
      wsClient.send("session_state", { active: false });
      setVoiceState("idle");
    }
  }, [voiceState, setVoiceState]);

  const handleTextSend = useCallback(() => {
    const msg = textInput.trim();
    if (!msg || !isConnected) return;
    wsClient.send("user_message", { text: msg, source: "text" });
    setTextInput("");
    setVoiceState("processing");
  }, [textInput, isConnected, setVoiceState]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleTextSend(); }
  };

  const getFormattedTime = () => {
    return new Date().toLocaleTimeString('en-US', { hour12: false });
  };

  return (
    <div
      style={{
        width: "100vw", height: "100vh",
        display: "flex", flexDirection: "column",
        background: "var(--bg-primary)",
        padding: "12px",
        gap: "12px",
      }}
    >
      {/* ─── Top Drag Bar ─── */}
      <div
        data-tauri-drag-region
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexShrink: 0, cursor: "move",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px", color: "var(--accent)" }}>
          <Activity size={16} className={isConnected ? "animate-glow" : ""} />
          <span style={{ fontSize: "14px", fontWeight: "bold", letterSpacing: "0.1em" }}>
            // OPENSARTHI -- {isConnected ? "ONLINE" : "OFFLINE"}
          </span>
          <span style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
            {getFormattedTime()}
          </span>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <button onClick={() => setMinimized((m) => !m)} title="Minimize" style={{ padding: "4px 8px" }}>
            <Minimize2 size={14} />
          </button>
          <button onClick={onOpenSettings} title="Settings" style={{ padding: "4px 8px" }}>
            <Settings size={14} />
          </button>
        </div>
      </div>

      {/* ─── Main Content HUD ─── */}
      <AnimatePresence>
        {!minimized && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1, flex: 1 }}
            exit={{ height: 0, opacity: 0 }}
            style={{ display: "flex", gap: "16px", overflow: "hidden", flex: 1 }}
          >
            {/* LEFT PANEL */}
            <div style={{ width: "260px", display: "flex", flexDirection: "column", gap: "16px" }}>
              <div className="hud-panel" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
                <div className="hud-panel-title">// TASKS - ACTIVE</div>
                <div style={{ padding: "12px", overflowY: "auto", flex: 1 }}>
                  <ActionLog plan={currentPlan} />
                </div>
              </div>
              <div className="hud-panel" style={{ height: "160px" }}>
                <div className="hud-panel-title">// FIXES - 00</div>
                <div style={{ padding: "12px", fontSize: "12px", color: "var(--text-secondary)" }}>
                  01 System checks passing<br/>
                  02 Dependencies validated
                </div>
              </div>
            </div>

            {/* CENTER PANEL */}
            <div className="hud-panel" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
              <div style={{
                position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)",
                opacity: 0.05, pointerEvents: "none", display: "flex", flexDirection: "column", alignItems: "center"
              }}>
                <Activity size={180} color="var(--accent)" />
              </div>
              
              <div style={{ flex: 1, overflowY: "auto", padding: "16px", zIndex: 1 }}>
                {messages.length === 0 && (
                  <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", opacity: 0.6 }}>
                    <p style={{ color: "var(--text-secondary)", letterSpacing: "0.1em" }}>
                      INITIALIZING OPENSARTHI PROTOCOL...
                    </p>
                  </div>
                )}
                <MessageList messages={messages} />
                <div ref={bottomRef} />
              </div>

              {/* INPUT BAR */}
              <div style={{
                padding: "16px", borderTop: "1px solid var(--border)",
                display: "flex", alignItems: "center", gap: "16px", background: "rgba(0,0,0,0.4)", zIndex: 1
              }}>
                <VoiceButton voiceState={voiceState} onClick={handleVoiceClick} disabled={!isConnected} />
                <Waveform voiceState={voiceState} />
                <input
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={isConnected ? "ENTER COMMAND..." : "CONNECTING..."}
                  disabled={!isConnected || voiceState === "listening"}
                  style={{
                    flex: 1, background: "transparent", border: "none", borderBottom: "1px solid var(--border-accent)",
                    color: "var(--text-primary)", fontSize: "14px", fontFamily: "var(--font-mono)",
                    padding: "8px 4px", outline: "none", textTransform: "uppercase"
                  }}
                />
                <button
                  onClick={handleTextSend}
                  disabled={!textInput.trim() || !isConnected}
                  style={{
                    padding: "8px 16px", background: "var(--accent)", color: "#000", border: "none",
                    fontWeight: "bold", opacity: (!textInput.trim() || !isConnected) ? 0.4 : 1
                  }}
                >
                  <Send size={16} />
                </button>
              </div>
            </div>

            {/* RIGHT PANEL */}
            <div style={{ width: "240px", display: "flex", flexDirection: "column", gap: "16px" }}>
              <div className="hud-panel" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
                <div className="hud-panel-title">// LIVE ACTIVITY</div>
                <div style={{ padding: "12px", overflowY: "auto", flex: 1 }}>
                  <TranscriptView transcript={currentTranscript} />
                </div>
              </div>
              <div className="hud-panel" style={{ padding: "12px" }}>
                <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>
                  SYSTEM BUILD
                </div>
                <div style={{ color: "var(--accent)", fontWeight: "bold" }}>
                  OPENSARTHI 1.0<br/>
                  <span style={{ fontSize: "10px", color: "var(--text-primary)" }}>UID: DEV_01</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
