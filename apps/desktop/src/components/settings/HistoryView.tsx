import { useEffect, useState } from "react";
import { X, MessageSquare, Trash2 } from "lucide-react";
import { motion } from "framer-motion";
import { useAssistantStore } from "../../stores/assistantStore";
import { wsClient } from "../../lib/ws";

interface HistoryViewProps {
  onClose: () => void;
}

export function HistoryView({ onClose }: HistoryViewProps) {
  const { threads } = useAssistantStore();
  const [hoveredThreadId, setHoveredThreadId] = useState<string | null>(null);

  useEffect(() => {
    wsClient.send("get_history", {});
  }, []);

  const handleLoadThread = (id: string) => {
    wsClient.send("load_thread", { thread_id: id });
    onClose();
  };

  const handleDeleteThread = (e: React.MouseEvent, id: string) => {
    e.stopPropagation(); // Avoid triggering load thread
    if (window.confirm("Are you sure you want to delete this conversation?")) {
      wsClient.send("delete_thread", { thread_id: id });
    }
  };

  const handleDeleteAll = () => {
    if (window.confirm("Are you sure you want to delete ALL conversations? This cannot be undone.")) {
      wsClient.send("delete_all_threads", {});
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      style={{
        position: "fixed",
        top: 0, left: 0, right: 0, bottom: 0,
        background: "var(--bg-glass)",
        backdropFilter: "blur(10px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
    >
      <div
        className="hud-panel"
        style={{ width: "450px", height: "500px", padding: "24px", display: "flex", flexDirection: "column", gap: "20px" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ fontSize: "16px", color: "var(--accent)", letterSpacing: "0.1em", fontWeight: "bold" }}>
            // CONVERSATION HISTORY
          </h2>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            {threads.length > 0 && (
              <button
                id="delete-all-threads"
                onClick={handleDeleteAll}
                title="Delete all conversations"
                style={{
                  color: "var(--text-secondary)",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  transition: "color 0.2s"
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = "var(--red)"}
                onMouseLeave={(e) => e.currentTarget.style.color = "var(--text-secondary)"}
              >
                <Trash2 size={18} />
              </button>
            )}
            <button onClick={onClose} style={{ color: "var(--text-secondary)", background: "transparent", border: "none", cursor: "pointer" }}>
              <X size={18} />
            </button>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "10px" }}>
          {threads.length === 0 ? (
            <div style={{ color: "var(--text-secondary)", fontSize: "13px", textAlign: "center", marginTop: "40px" }}>
              NO PAST CONVERSATIONS FOUND
            </div>
          ) : (
            threads.map((thread) => (
              <div
                key={thread.id}
                onClick={() => handleLoadThread(thread.id)}
                onMouseEnter={() => setHoveredThreadId(thread.id)}
                onMouseLeave={() => setHoveredThreadId(null)}
                style={{
                  padding: "12px",
                  background: "rgba(0,0,0,0.3)",
                  border: "1px solid var(--border)",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "12px",
                  position: "relative",
                  transition: "border-color 0.2s"
                }}
                onFocus={() => setHoveredThreadId(thread.id)}
                onBlur={() => setHoveredThreadId(null)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  handleDeleteThread(e as any, thread.id);
                }}
              >
                <MessageSquare size={16} style={{ color: "var(--accent)", marginTop: "2px" }} />
                <div style={{ flex: 1, minWidth: 0, paddingRight: "24px" }}>
                  <div style={{ fontSize: "13px", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {thread.first_message || "Empty Conversation"}
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "4px" }}>
                    {new Date(thread.created_at).toLocaleString()}
                  </div>
                </div>

                {hoveredThreadId === thread.id && (
                  <button
                    className="delete-thread-btn"
                    onClick={(e) => handleDeleteThread(e, thread.id)}
                    title="Delete conversation"
                    style={{
                      position: "absolute",
                      right: "12px",
                      top: "50%",
                      transform: "translateY(-50%)",
                      color: "var(--text-secondary)",
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      padding: "4px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      transition: "color 0.2s"
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.color = "var(--red)"}
                    onMouseLeave={(e) => e.currentTarget.style.color = "var(--text-secondary)"}
                  >
                    <Trash2 size={15} />
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </motion.div>
  );
}
