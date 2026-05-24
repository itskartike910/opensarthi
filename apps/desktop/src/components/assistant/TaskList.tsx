import { motion } from "framer-motion";
import { Loader2, CheckCircle2, XCircle, Clock } from "lucide-react";
import type { Message } from "../../lib/schemas";

interface Task {
  id: string;
  title: string;
  icon: string;
  details: string;
  status: "pending" | "running" | "success" | "error";
  timestamp: number;
}

interface TaskListProps {
  messages: Message[];
  voiceState: string;
  hasActivePlan: boolean;
}

function isAgenticTask(msg: Message, assistantMsg?: Message): boolean {
  const p = msg.content.toLowerCase();
  
  // Explicit task keywords
  const hasTaskKeyword = 
    p.includes("update") || p.includes("upgrade") ||
    p.includes("install") || p.includes("pacman") || p.includes("yay") ||
    p.includes("remove") || p.includes("uninstall") ||
    p.includes("reboot") || p.includes("restart") ||
    p.includes("shutdown") || p.includes("poweroff") ||
    p.includes("search") || p.includes("find") || p.includes("grep") ||
    p.includes("open") || p.includes("launch") || p.includes("start") ||
    p.includes("create") || p.includes("write") || p.includes("mkdir") || p.includes("touch") ||
    p.includes("kill") || p.includes("pkill") || p.includes("stop process") ||
    p.includes("shell") || p.includes("command") || p.includes("run") || p.includes("sudo");

  if (hasTaskKeyword) return true;

  // If assistant responded with a plan block
  if (assistantMsg) {
    const content = assistantMsg.content;
    if (content.includes("```json") || content.includes('"tool":') || content.includes('"steps":')) {
      return true;
    }
  }

  return false;
}

function parseTask(prompt: string): { title: string; icon: string } {
  const p = prompt.toLowerCase().trim();
  let title = "DESKTOP AGENT TASK";
  let icon = "🤖";
  
  if (p.includes("update") || p.includes("upgrade")) {
    title = "SYSTEM UPDATE";
    icon = "🔄";
  } else if (p.includes("install") || p.includes("pacman -s") || p.includes("yay -s")) {
    title = "INSTALL PACKAGE";
    icon = "📦";
  } else if (p.includes("remove") || p.includes("uninstall") || p.includes("pacman -r")) {
    title = "REMOVE PACKAGE";
    icon = "🗑️";
  } else if (p.includes("reboot") || p.includes("restart")) {
    title = "SYSTEM REBOOT";
    icon = "⚡";
  } else if (p.includes("shutdown") || p.includes("poweroff")) {
    title = "SYSTEM SHUTDOWN";
    icon = "🔌";
  } else if (p.includes("search") || p.includes("find") || p.includes("grep")) {
    title = "FILE SEARCH";
    icon = "🔍";
  } else if (p.includes("open") || p.includes("launch") || p.includes("start")) {
    title = "LAUNCH APPLICATION";
    icon = "🚀";
  } else if (p.includes("create") || p.includes("write") || p.includes("mkdir") || p.includes("touch")) {
    title = "CREATE RESOURCE";
    icon = "📁";
  } else if (p.includes("kill") || p.includes("pkill") || p.includes("stop process")) {
    title = "PROCESS TERMINATION";
    icon = "🚫";
  } else if (p.includes("shell") || p.includes("command") || p.includes("run") || p.includes("sudo") || p.includes("pkexec")) {
    title = "SHELL EXECUTION";
    icon = "🐚";
  } else if (prompt.trim().length > 0) {
    const words = prompt.trim().split(/\s+/).slice(0, 3).map(w => w.replace(/[^a-zA-Z]/g, "").toUpperCase()).filter(Boolean);
    if (words.length > 0) {
      title = words.join(" ");
    }
  }
  
  return { title, icon };
}

export function TaskList({ messages, voiceState, hasActivePlan }: TaskListProps) {
  // Extract only agentic user messages
  const agenticUserMessages = messages.filter((m) => {
    if (m.role !== "user") return false;
    
    // Find corresponding assistant message
    const userIdx = messages.findIndex((x) => x.id === m.id);
    const nextAssistantMsg = messages.slice(userIdx + 1).find((x) => x.role === "assistant");
    
    return isAgenticTask(m, nextAssistantMsg);
  });

  const tasks: Task[] = agenticUserMessages.map((msg, index) => {
    const { title, icon } = parseTask(msg.content);
    const isLatest = index === agenticUserMessages.length - 1;
    
    let status: Task["status"] = "success";
    if (isLatest) {
      const latestUserMsgIndex = messages.findIndex((m) => m.id === msg.id);
      const hasResponse = messages.slice(latestUserMsgIndex + 1).some((m) => m.role === "assistant");
      
      if (!hasResponse) {
        if (voiceState === "processing" || voiceState === "speaking" || hasActivePlan) {
          status = "running";
        } else {
          status = "pending";
        }
      }
    } else {
      const currentIdx = messages.findIndex((m) => m.id === msg.id);
      const nextMsgs = messages.slice(currentIdx + 1);
      const nextAssistantMsg = nextMsgs.find((m) => m.role === "assistant");
      if (nextAssistantMsg && (
        nextAssistantMsg.content.toLowerCase().includes("error") || 
        nextAssistantMsg.content.toLowerCase().includes("failed") ||
        nextAssistantMsg.content.toLowerCase().includes("couldn't run")
      )) {
        status = "error";
      }
    }

    return {
      id: msg.id,
      title,
      icon,
      details: msg.content,
      status,
      timestamp: msg.timestamp,
    };
  });

  if (tasks.length === 0) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", opacity: 0.5 }}>
        <p style={{ color: "var(--text-secondary)", fontSize: "12px", letterSpacing: "0.05em", textAlign: "center" }}>
          // NO ACTIVE TASKS
        </p>
      </div>
    );
  }

  // Reverse list so latest active task is at the top!
  const reversedTasks = [...tasks].reverse();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {reversedTasks.map((task) => (
        <motion.div
          key={task.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          style={{
            padding: "10px 12px",
            borderRadius: "var(--radius-md)",
            border: `1px solid ${task.status === "running" ? "var(--border-accent)" : "var(--border)"}`,
            background: task.status === "running" ? "var(--accent-glow)" : "rgba(0, 0, 0, 0.2)",
            display: "flex",
            flexDirection: "column",
            gap: "6px",
            position: "relative",
            overflow: "hidden",
            boxShadow: task.status === "running" ? "0 0 10px rgba(255, 0, 0, 0.15)" : "none",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: "bold", fontSize: "12px", color: "var(--text-primary)" }}>
              <span>{task.icon}</span>
              <span style={{ letterSpacing: "0.05em" }}>{task.title}</span>
            </div>
            
            {/* Status indicator */}
            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              {task.status === "running" && (
                <span style={{ fontSize: "10px", color: "var(--accent)", display: "flex", alignItems: "center", gap: "4px", fontWeight: "bold" }}>
                  <Loader2 size={12} className="animate-spin" />
                  RUNNING
                </span>
              )}
              {task.status === "success" && (
                <span style={{ fontSize: "10px", color: "var(--success)", display: "flex", alignItems: "center", gap: "4px", fontWeight: "bold" }}>
                  <CheckCircle2 size={12} />
                  COMPLETED
                </span>
              )}
              {task.status === "error" && (
                <span style={{ fontSize: "10px", color: "var(--danger)", display: "flex", alignItems: "center", gap: "4px", fontWeight: "bold" }}>
                  <XCircle size={12} />
                  FAILED
                </span>
              )}
              {task.status === "pending" && (
                <span style={{ fontSize: "10px", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "4px" }}>
                  <Clock size={12} />
                  QUEUED
                </span>
              )}
            </div>
          </div>

          <div style={{ fontSize: "11px", color: "var(--text-secondary)", wordBreak: "break-word", fontFamily: "var(--font-mono)", textTransform: "uppercase", opacity: 0.8 }}>
            {task.details}
          </div>
        </motion.div>
      ))}
    </div>
  );
}
