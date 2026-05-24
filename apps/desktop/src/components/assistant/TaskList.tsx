import { useEffect } from "react";
import { motion } from "framer-motion";
import { Loader2, CheckCircle2, XCircle, Clock } from "lucide-react";
import type { Message, Plan } from "../../lib/schemas";

interface AgenticTask {
  id: string;           // user message id
  userMsgId: string;
  title: string;
  icon: string;
  prompt: string;
  status: "running" | "success" | "error" | "pending";
  timestamp: number;
  toolActions: Array<{
    tool: string;
    description: string;
    status: "pending" | "running" | "success" | "error" | "skipped";
    result?: any;
    timestamp?: number;
  }>;
}

interface TaskListProps {
  messages: Message[];
  voiceState: string;
  hasActivePlan: boolean;
  currentPlan: Plan | null;
  onScrollToMessage?: (msgId: string) => void;
  selectedTaskId: string | null;
  setSelectedTaskId: (id: string | null) => void;
  taskRefsMap?: React.MutableRefObject<Record<string, HTMLDivElement | null>>;
}

/** Returns true if the assistant response indicates it ran tool calls */
function responseHasToolCalls(content: string): boolean {
  // Check for plan markers in content (summary lines with checkmarks)
  return (
    content.includes("✓ ") ||
    content.includes("Task completed successfully") ||
    content.includes("❌ Failed at step")
  );
}

/** Infer task title from the prompt */
function parseTask(prompt: string): { title: string; icon: string } {
  const p = prompt.toLowerCase().trim();

  if (p.includes("update") || p.includes("upgrade")) return { title: "SYSTEM UPDATE", icon: "🔄" };
  if (p.includes("install") || p.includes("pacman -s") || p.includes("yay -s")) return { title: "INSTALL PACKAGE", icon: "📦" };
  if (p.includes("remove") || p.includes("uninstall")) return { title: "REMOVE PACKAGE", icon: "🗑️" };
  if (p.includes("reboot") || p.includes("restart")) return { title: "SYSTEM REBOOT", icon: "⚡" };
  if (p.includes("shutdown") || p.includes("poweroff")) return { title: "SYSTEM SHUTDOWN", icon: "🔌" };
  if (p.includes("search") || p.includes("find") || p.includes("grep")) return { title: "FILE SEARCH", icon: "🔍" };
  if (p.includes("open") || p.includes("launch") || p.includes("start")) return { title: "LAUNCH APP", icon: "🚀" };
  if (p.includes("create") || p.includes("write") || p.includes("mkdir") || p.includes("touch")) return { title: "CREATE FILE", icon: "📁" };
  if (p.includes("kill") || p.includes("pkill")) return { title: "KILL PROCESS", icon: "🚫" };
  if (p.includes("shell") || p.includes("command") || p.includes("run") || p.includes("sudo")) return { title: "SHELL COMMAND", icon: "🐚" };
  if (p.includes("chrome") || p.includes("firefox") || p.includes("browser")) return { title: "OPEN BROWSER", icon: "🌐" };
  if (p.includes("type") || p.includes("click") || p.includes("press")) return { title: "UI AUTOMATION", icon: "🖱️" };

  // Fallback: use first 3 meaningful words
  const words = prompt.trim().split(/\s+/).slice(0, 3).map(w => w.replace(/[^a-zA-Z]/g, "").toUpperCase()).filter(Boolean);
  return { title: words.join(" ") || "AGENT TASK", icon: "🤖" };
}

export function TaskList({
  messages,
  voiceState,
  hasActivePlan,
  currentPlan,
  onScrollToMessage,
  selectedTaskId,
  setSelectedTaskId,
  taskRefsMap,
}: TaskListProps) {

  // Derive agentic tasks from messages — a task is detected when the ASSISTANT replied with tool results
  const agenticTasks: AgenticTask[] = [];

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (msg.role !== "user") continue;

    // Find the next assistant response
    const nextAssistant = messages.slice(i + 1).find(m => m.role === "assistant");
    if (!nextAssistant) {
      // Find the last user message index
      let lastUserIdx = -1;
      for (let j = messages.length - 1; j >= 0; j--) {
        if (messages[j].role === "user") {
          lastUserIdx = j;
          break;
        }
      }
      // If we're processing and this is the last user message, it might be the active task
      const isLatest = i === lastUserIdx;
      if (isLatest && (voiceState === "processing" || hasActivePlan)) {
        const { title, icon } = parseTask(msg.content);
        // Only add it as running task if there's an active plan
        if (hasActivePlan && currentPlan) {
          agenticTasks.push({
            id: msg.id,
            userMsgId: msg.id,
            title,
            icon,
            prompt: msg.content,
            status: "running",
            timestamp: msg.timestamp,
            toolActions: currentPlan.steps.map(s => ({
              tool: s.tool,
              description: s.description || s.tool,
              status: s.status || "pending",
              result: s.result,
            })),
          });
        }
      }
      continue;
    }

    // Check if the assistant response indicates tool calls were made
    const isTask = responseHasToolCalls(nextAssistant.content);
    if (!isTask) continue;

    const { title, icon } = parseTask(msg.content);

    // Determine status from assistant response
    let status: AgenticTask["status"] = "success";
    if (nextAssistant.content.includes("❌")) status = "error";

    // Extract tool actions from assistant response (✓ lines)
    const toolActions: AgenticTask["toolActions"] = [];
    const lines = nextAssistant.content.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("✓ ")) {
        toolActions.push({ tool: "step", description: trimmed.slice(2), status: "success", timestamp: nextAssistant.timestamp });
      } else if (trimmed.startsWith("❌")) {
        toolActions.push({ tool: "step", description: trimmed, status: "error", timestamp: nextAssistant.timestamp });
      }
    }

    agenticTasks.push({
      id: msg.id,
      userMsgId: msg.id,
      title,
      icon,
      prompt: msg.content,
      status,
      timestamp: msg.timestamp,
      toolActions,
    });
  }



  // Auto-select latest running task
  useEffect(() => {
    const running = agenticTasks.find(t => t.status === "running");
    if (running) setSelectedTaskId(running.id);
  }, [hasActivePlan]);

  const reversedTasks = [...agenticTasks].reverse();

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {agenticTasks.length === 0 ? (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", opacity: 0.5 }}>
          <p style={{ color: "var(--text-secondary)", fontSize: "11px", letterSpacing: "0.05em", textAlign: "center" }}>
            // NO AGENT RUNS YET
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", overflowY: "auto", flex: 1 }}>
          {reversedTasks.map((task) => (
            <motion.div
              key={task.id}
              ref={(el) => {
                if (taskRefsMap) taskRefsMap.current[task.id] = el as HTMLDivElement;
              }}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={() => {
                setSelectedTaskId(task.id === selectedTaskId ? null : task.id);
                onScrollToMessage?.(task.userMsgId);
              }}
              style={{
                padding: "9px 11px",
                borderRadius: "var(--radius-md)",
                border: `1px solid ${task.id === selectedTaskId ? "var(--border-accent)" : task.status === "running" ? "var(--border-accent)" : "var(--border)"}`,
                background: task.id === selectedTaskId
                  ? "var(--accent-glow)"
                  : task.status === "running"
                  ? "var(--accent-glow)"
                  : "rgba(0,0,0,0.2)",
                display: "flex",
                flexDirection: "column",
                gap: "5px",
                cursor: "pointer",
                boxShadow: task.status === "running" ? "0 0 8px var(--accent-glow)" : "none",
                transition: "all 0.15s",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "7px", fontWeight: "bold", fontSize: "11px", color: "var(--text-primary)" }}>
                  <span>{task.icon}</span>
                  <span style={{ letterSpacing: "0.04em" }}>{task.title}</span>
                  <span style={{ fontSize: "9px", color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontWeight: "normal", opacity: 0.8 }}>
                    [{new Date(task.timestamp ?? Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}]
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                  {task.status === "running" && (
                    <span style={{ fontSize: "9px", color: "var(--accent)", display: "flex", alignItems: "center", gap: "3px", fontWeight: "bold" }}>
                      <Loader2 size={10} className="animate-spin" /> RUNNING
                    </span>
                  )}
                  {task.status === "success" && (
                    <span style={{ fontSize: "9px", color: "var(--success)", display: "flex", alignItems: "center", gap: "3px" }}>
                      <CheckCircle2 size={10} /> DONE
                    </span>
                  )}
                  {task.status === "error" && (
                    <span style={{ fontSize: "9px", color: "var(--danger)", display: "flex", alignItems: "center", gap: "3px" }}>
                      <XCircle size={10} /> FAILED
                    </span>
                  )}
                  {task.status === "pending" && (
                    <span style={{ fontSize: "9px", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "3px" }}>
                      <Clock size={10} /> QUEUED
                    </span>
                  )}
                </div>
              </div>
              <div style={{ fontSize: "10px", color: "var(--text-secondary)", fontFamily: "var(--font-mono)", opacity: 0.75, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {task.prompt}
              </div>
            </motion.div>
          ))}
        </div>
      )}


    </div>
  );
}
