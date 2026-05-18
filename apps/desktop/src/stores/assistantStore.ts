import { create } from "zustand";
import type { Message, Plan, PlanStep, VoiceState } from "../lib/schemas";

export interface Thread {
  id: string;
  created_at: string;
  first_message: string;
}

interface AssistantState {
  // Session
  voiceState: VoiceState;
  isConnected: boolean;
  currentTranscript: string | null;

  // Conversation
  messages: Message[];
  threads: Thread[];

  // Execution
  currentPlan: Plan | null;
  executingStepIndex: number | null;

  activeLocalModel: string;
  activeCloudModel: string;
  cloudApiKey: string;
  activeTheme: string;

  voiceAccent: string;
  voiceSpeed: number;
  continuousListening: boolean;

  // Actions
  setVoiceState: (state: VoiceState) => void;
  setConnected: (connected: boolean) => void;
  setTranscript: (text: string | null) => void;
  addMessage: (msg: Message) => void;
  setMessages: (msgs: Message[]) => void;
  setThreads: (threads: Thread[]) => void;
  clearMessages: () => void;
  setPlan: (plan: Plan | null) => void;
  updateStepStatus: (index: number, update: Partial<PlanStep>) => void;
  setExecutingStep: (index: number | null) => void;
  addOrUpdateToolAction: (tool: string, description: string, status: "pending" | "running" | "success" | "error" | "skipped", result?: any) => void;
  setActiveModels: (local: string, cloud: string) => void;
  setCloudApiKey: (key: string) => void;
  setActiveTheme: (theme: string) => void;
  setVoiceSettings: (accent: string, speed: number, continuous: boolean) => void;
}

export const useAssistantStore = create<AssistantState>((set) => ({
  voiceState: "idle",
  isConnected: false,
  currentTranscript: null,
  messages: [],
  threads: [],
  currentPlan: null,
  executingStepIndex: null,
  activeLocalModel: "qwen2.5-coder:3b",
  activeCloudModel: "gemini-2.5-flash",
  cloudApiKey: "",
  activeTheme: "theme-red-black",
  voiceAccent: "ie",
  voiceSpeed: 1.35,
  continuousListening: false,

  setVoiceState: (voiceState) => set({ voiceState }),
  setConnected: (isConnected) => set({ isConnected }),
  setTranscript: (currentTranscript) => set({ currentTranscript }),

  addMessage: (msg) =>
    set((s) => ({ messages: [...s.messages, msg] })),

  setMessages: (messages) => set({ messages }),
  setThreads: (threads) => set({ threads }),

  clearMessages: () => set({ messages: [], currentPlan: null }),

  setPlan: (currentPlan) => set({ currentPlan, executingStepIndex: null }),

  setActiveModels: (local, cloud) => set({ activeLocalModel: local, activeCloudModel: cloud }),
  setCloudApiKey: (cloudApiKey) => set({ cloudApiKey }),
  setActiveTheme: (activeTheme) => set({ activeTheme }),
  setVoiceSettings: (voiceAccent, voiceSpeed, continuousListening) => set({ voiceAccent, voiceSpeed, continuousListening }),

  updateStepStatus: (index, update) =>
    set((s) => {
      if (!s.currentPlan) return s;
      const steps = s.currentPlan.steps.map((step, i) =>
        i === index ? { ...step, ...update } : step
      );
      return { currentPlan: { ...s.currentPlan, steps } };
    }),

  setExecutingStep: (executingStepIndex) => set({ executingStepIndex }),

  addOrUpdateToolAction: (tool, description, status, result) => set((s) => {
    let plan = s.currentPlan;
    if (!plan) {
      plan = { 
        id: crypto.randomUUID(), 
        goal: "Executing User Command...", 
        steps: [], 
        recovery_hint: null 
      };
    }

    // See if the step exists. PydanticAI streams tools sequentially.
    // If status is 'running', we create a new step or update the last one if it matches.
    let steps = [...plan.steps];
    
    // Check if we are updating an existing step
    const existingIndex = steps.findIndex(st => st.tool === tool && st.description === description && st.status === "running");
    
    if (existingIndex >= 0) {
      // Update existing
      steps[existingIndex] = { ...steps[existingIndex], status, result };
    } else {
      // Add new step
      steps.push({
        index: steps.length,
        tool,
        args: {},
        description,
        status,
        result
      });
    }

    return { currentPlan: { ...plan, steps } };
  }),
}));
