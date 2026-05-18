import { useState, useCallback, useEffect } from "react";
import { AssistantOverlay } from "./components/assistant/AssistantOverlay";
import { PermissionDialog } from "./components/permissions/PermissionDialog";
import { SettingsView } from "./components/settings/SettingsView";
import { HistoryView } from "./components/settings/HistoryView";
import { useTauriEvent } from "./hooks/useTauriEvent";
import { useWebSocket } from "./hooks/useWebSocket";
import { useAssistantStore } from "./stores/assistantStore";
import { TAURI_EVENTS } from "./lib/constants";
import { wsClient } from "./lib/ws";
import { AnimatePresence } from "framer-motion";

export default function App() {
  const [runtimePort, setRuntimePort] = useState<number | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const { 
    activeLocalModel, 
    activeCloudModel, 
    cloudApiKey, 
    voiceAccent, 
    voiceSpeed, 
    activeTheme,
    setVoiceSettings,
    setActiveTheme,
    setActiveModels,
    setCloudApiKey
  } = useAssistantStore();

  // Dynamic Theme application to document.body
  useEffect(() => {
    // Remove all previous theme classes
    document.body.className = document.body.className
      .split(" ")
      .filter((c) => !c.startsWith("theme-"))
      .join(" ");
    
    // Add the active theme class
    document.body.classList.add(activeTheme);
  }, [activeTheme]);

  // Listen for the runtime sidecar to announce its port
  useTauriEvent<number>(TAURI_EVENTS.RUNTIME_PORT_READY, useCallback((port) => {
    setRuntimePort(port);
  }, []));

  // Connect WebSocket once port is known
  useWebSocket(runtimePort);

  const handleSaveSettings = (
    newLocal: string, 
    newCloud: string, 
    newKey: string,
    newAccent: string,
    newSpeed: number,
    newContinuous: boolean,
    newTheme: string
  ) => {
    setActiveModels(newLocal, newCloud);
    setCloudApiKey(newKey);
    setVoiceSettings(newAccent, newSpeed, newContinuous);
    setActiveTheme(newTheme);
    
    wsClient.send("update_settings", {
      local_model: newLocal,
      cloud_model: newCloud,
      gemini_api_key: newKey,
      voice_accent: newAccent,
      voice_speed: newSpeed,
      continuous_listening: newContinuous,
      active_theme: newTheme
    });
  };

  return (
    <>
      <AssistantOverlay 
        onOpenSettings={() => setShowSettings(true)} 
        onOpenHistory={() => setShowHistory(true)} 
      />
      <PermissionDialog />
      <AnimatePresence>
        {showSettings && (
          <SettingsView
            onClose={() => setShowSettings(false)}
            currentLocalModel={activeLocalModel}
            currentCloudModel={activeCloudModel}
            currentGeminiKey={cloudApiKey}
            currentVoiceAccent={voiceAccent}
            currentVoiceSpeed={voiceSpeed}
            currentTheme={activeTheme}
            onSave={handleSaveSettings}
          />
        )}
        {showHistory && (
          <HistoryView
            onClose={() => setShowHistory(false)}
          />
        )}
      </AnimatePresence>
    </>
  );
}
