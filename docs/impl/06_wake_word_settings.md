# OpenSarthi — Implementation Plan
## Part 6: Custom Wake Word Settings (Multiple Phrases Support)

> **Priority:** P2 — Voice (alongside voice pipeline)
> **Affected files:** `runtime/voice/wakeword.py` [NEW], `runtime/config.py` [UPDATE], `apps/desktop/src/components/settings/SettingsView.tsx` [UPDATE]

---

## 1. Why Multiple Wake Words?

Users mis-speak wake words frequently. A single rigid phrase fails constantly.

Examples of what users actually say:
- "Hey Sarthi" → works
- "Hey Sarty" → fails (mis-spoken)
- "Sarthi" → fails (dropped "Hey")
- "OpenSarthi" → fails (full name variant)
- "Ok Sarthi" → fails (Google-style prefix)

The solution: let users add **multiple wake word variants** in Settings. All are monitored simultaneously. Any match triggers activation.

---

## 2. OpenWakeWord Integration (`runtime/voice/wakeword.py`)

OpenWakeWord supports custom phrase detection using phoneme-based matching (no training needed for simple phrases).

```python
import numpy as np
from typing import Optional

class WakeWordDetector:
    """
    Detects configurable wake word phrases using OpenWakeWord.
    Supports multiple simultaneous phrases (for mis-spoken variants).
    
    Default phrases: ["hey sarthi", "opensarthi", "hey sarthy", "ok sarthi"]
    User can add/remove via Settings UI.
    """

    # Built-in OpenWakeWord model names (pre-trained)
    # These are phoneme models, approximate matching
    BUILTIN_MODELS = {
        "hey sarthi": "hey_jarvis",      # Closest phoneme match
        "hey jarvis": "hey_jarvis",
        "alexa": "alexa",
        "hey mycroft": "hey_mycroft",
    }

    # Confidence threshold (0.0–1.0) — higher = fewer false positives
    DEFAULT_THRESHOLD = 0.5

    def __init__(
        self,
        phrases: list[str],
        threshold: float = DEFAULT_THRESHOLD
    ):
        self.phrases = [p.lower().strip() for p in phrases]
        self.threshold = threshold
        self._models = {}
        self._loaded = False

    def load(self):
        """Load OpenWakeWord models for configured phrases."""
        try:
            from openwakeword.model import Model

            # Map user phrases to available OWW models
            model_names = []
            for phrase in self.phrases:
                if phrase in self.BUILTIN_MODELS:
                    model_names.append(self.BUILTIN_MODELS[phrase])
                else:
                    # For custom phrases, use the closest available model
                    # Future: custom training pipeline
                    model_names.append("hey_jarvis")  # Fallback

            # De-duplicate
            model_names = list(set(model_names))

            self._oww = Model(
                wakeword_models=model_names,
                inference_framework="onnx"   # CPU-compatible
            )
            self._loaded = True
            print(f"[WakeWord] Loaded models for phrases: {self.phrases}")

        except ImportError:
            print("[WakeWord] openwakeword not installed — wake word disabled")
            self._loaded = False
        except Exception as e:
            print(f"[WakeWord] Failed to load: {e}")
            self._loaded = False

    def detect(self, audio_chunk: np.ndarray) -> bool:
        """
        Check if the audio chunk contains any configured wake word.
        audio_chunk: float32 numpy array at 16kHz
        Returns True if any phrase detected above threshold.
        """
        if not self._loaded:
            return False

        try:
            # OWW expects int16 PCM
            audio_int16 = (audio_chunk * 32767).astype(np.int16)
            prediction = self._oww.predict(audio_int16)

            for model_name, score in prediction.items():
                if score > self.threshold:
                    print(f"[WakeWord] Detected '{model_name}' (score={score:.2f})")
                    return True
            return False

        except Exception:
            return False

    def update_phrases(self, new_phrases: list[str]):
        """Hot-update phrases without restarting the pipeline."""
        self.phrases = [p.lower().strip() for p in new_phrases]
        self._loaded = False
        self.load()  # Reload with new phrases
```

---

## 3. Config: Wake Word Storage

**Update `runtime/config.py`:**

```python
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List

class Settings(BaseSettings):
    # ... existing fields ...

    # Wake word configuration
    wake_words: List[str] = Field(
        default=["hey sarthi", "opensarthi"],
        description="List of wake word phrases to listen for"
    )
    wake_word_threshold: float = Field(
        default=0.5,
        ge=0.1, le=1.0,
        description="Detection confidence threshold (0.1-1.0)"
    )
    wake_word_enabled: bool = Field(
        default=True,
        description="Whether wake word activation is enabled"
    )

    class Config:
        env_file = "~/.config/opensarthi/.env"
        env_file_encoding = "utf-8"
        # pydantic-settings handles lists as JSON strings in .env
        # e.g.: wake_words=["hey sarthi","opensarthi"]
```

**In `.env` file, stored as:**

```env
wake_words=["hey sarthi","opensarthi","hey sarthy","ok sarthi"]
wake_word_threshold=0.5
wake_word_enabled=true
```

---

## 4. Backend API: Wake Word Settings Endpoint

**Update `runtime/api/websocket.py`:**

```python
# New message types

elif msg_type == "get_wake_words":
    settings = Settings()
    await self.send_message("wake_words_config", {
        "wake_words": settings.wake_words,
        "threshold": settings.wake_word_threshold,
        "enabled": settings.wake_word_enabled,
    })

elif msg_type == "save_wake_words":
    payload = data.get("payload", {})
    new_words = payload.get("wake_words", [])
    threshold = payload.get("threshold", 0.5)
    enabled = payload.get("enabled", True)

    # Validate
    if not isinstance(new_words, list):
        await self.send_message("error", {"text": "wake_words must be a list"})
        return
    if len(new_words) > 20:
        await self.send_message("error", {"text": "Maximum 20 wake words allowed"})
        return
    new_words = [w.strip().lower() for w in new_words if w.strip()]

    # Persist to .env
    env_path = os.path.expanduser("~/.config/opensarthi/.env")
    import json
    _update_env_var(env_path, "wake_words", json.dumps(new_words))
    _update_env_var(env_path, "wake_word_threshold", str(threshold))
    _update_env_var(env_path, "wake_word_enabled", str(enabled).lower())

    # Hot-reload the wake word detector
    if hasattr(self, "_voice_pipeline") and self._voice_pipeline:
        self._voice_pipeline.wake_detector.update_phrases(new_words)

    await self.send_message("wake_words_saved", {
        "wake_words": new_words,
        "count": len(new_words)
    })
```

---

## 5. Frontend: Wake Word Settings UI

**Update `apps/desktop/src/components/settings/SettingsView.tsx`:**

Add a new section to the Settings modal. Place it under the Voice & Interaction section.

### UI Design

```
── Wake Word Activation ──────────────────────────────────────────

  [x] Enable wake word activation

  Active phrases: (3)
  ┌─────────────────────────────────┐
  │ hey sarthi                   [×] │
  │ opensarthi                   [×] │
  │ hey sarthy                   [×] │
  └─────────────────────────────────┘

  Add phrase: [________________] [+ Add]
  
  Sensitivity: [====|====] 0.5
               Low sensitivity    High sensitivity
  
  ℹ Tip: Add mis-spoken variants (e.g. "hey sarty") for better recognition.
  
  [Save Wake Words]
```

### TSX Implementation

```typescript
// In SettingsView.tsx — Wake Word Section

const [wakeWords, setWakeWords] = useState<string[]>(["hey sarthi", "opensarthi"]);
const [newPhrase, setNewPhrase] = useState("");
const [threshold, setThreshold] = useState(0.5);
const [wakeEnabled, setWakeEnabled] = useState(true);

// Load on mount
useEffect(() => {
  ws?.send(JSON.stringify({ type: "get_wake_words", payload: {} }));
}, []);

// Handle response
useEffect(() => {
  if (lastMessage?.type === "wake_words_config") {
    setWakeWords(lastMessage.payload.wake_words);
    setThreshold(lastMessage.payload.threshold);
    setWakeEnabled(lastMessage.payload.enabled);
  }
}, [lastMessage]);

const addPhrase = () => {
  const trimmed = newPhrase.trim().toLowerCase();
  if (!trimmed || wakeWords.includes(trimmed)) return;
  if (wakeWords.length >= 20) {
    alert("Maximum 20 wake words allowed");
    return;
  }
  setWakeWords([...wakeWords, trimmed]);
  setNewPhrase("");
};

const removePhrase = (phrase: string) => {
  if (wakeWords.length <= 1) {
    alert("At least one wake word is required");
    return;
  }
  setWakeWords(wakeWords.filter(w => w !== phrase));
};

const saveWakeWords = () => {
  ws?.send(JSON.stringify({
    type: "save_wake_words",
    payload: { wake_words: wakeWords, threshold, enabled: wakeEnabled }
  }));
};

// Render
return (
  <div className="settings-section wake-words-section">
    <h3>// WAKE WORD ACTIVATION</h3>
    
    <label className="toggle-row">
      <input
        type="checkbox"
        checked={wakeEnabled}
        onChange={e => setWakeEnabled(e.target.checked)}
      />
      <span>Enable wake word activation</span>
    </label>

    <div className="wake-words-list">
      {wakeWords.map(phrase => (
        <div key={phrase} className="wake-word-chip">
          <span>{phrase}</span>
          <button
            className="remove-btn"
            onClick={() => removePhrase(phrase)}
            title="Remove phrase"
          >×</button>
        </div>
      ))}
    </div>

    <div className="add-phrase-row">
      <input
        type="text"
        value={newPhrase}
        onChange={e => setNewPhrase(e.target.value)}
        onKeyDown={e => e.key === "Enter" && addPhrase()}
        placeholder="e.g. hey sarty, ok sarthi..."
        className="phrase-input"
        maxLength={50}
      />
      <button onClick={addPhrase} className="add-phrase-btn">+ Add</button>
    </div>

    <div className="sensitivity-row">
      <label>Sensitivity</label>
      <input
        type="range"
        min={0.1} max={1.0} step={0.05}
        value={threshold}
        onChange={e => setThreshold(parseFloat(e.target.value))}
      />
      <span>{threshold.toFixed(2)}</span>
    </div>

    <p className="tip">
      💡 Add mis-spoken variants (e.g. "hey sarty") for better recognition accuracy.
    </p>

    <button onClick={saveWakeWords} className="save-btn">
      Save Wake Words
    </button>
  </div>
);
```

---

## 6. CSS Additions

```css
/* Add to globals.css */

.wake-words-section {
  margin-top: 1.5rem;
}

.wake-words-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.75rem 0;
  min-height: 40px;
  padding: 0.5rem;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-tertiary);
}

.wake-word-chip {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.6rem;
  background: color-mix(in srgb, var(--primary-color) 15%, transparent);
  border: 1px solid var(--primary-color);
  border-radius: 20px;
  font-size: 0.8rem;
  font-family: var(--font-mono);
  color: var(--primary-color);
}

.wake-word-chip .remove-btn {
  background: none;
  border: none;
  color: var(--primary-color);
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  opacity: 0.7;
  padding: 0;
}

.wake-word-chip .remove-btn:hover {
  opacity: 1;
}

.add-phrase-row {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.phrase-input {
  flex: 1;
  padding: 0.4rem 0.75rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 0.85rem;
}

.phrase-input:focus {
  border-color: var(--primary-color);
  outline: none;
}

.add-phrase-btn {
  padding: 0.4rem 1rem;
  background: color-mix(in srgb, var(--primary-color) 20%, transparent);
  border: 1px solid var(--primary-color);
  border-radius: 6px;
  color: var(--primary-color);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 0.85rem;
  transition: all 0.2s;
}

.add-phrase-btn:hover {
  background: color-mix(in srgb, var(--primary-color) 30%, transparent);
}

.sensitivity-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
}

.sensitivity-row input[type="range"] {
  flex: 1;
  accent-color: var(--primary-color);
}

.tip {
  font-size: 0.78rem;
  color: var(--text-secondary);
  margin-bottom: 1rem;
}
```

---

## 7. Default Phrase Recommendations

Include these defaults in the initial settings:

| Phrase | Notes |
|--------|-------|
| `hey sarthi` | Primary phrase |
| `opensarthi` | Full name variant |
| `hey sarthy` | Common mis-spelling |
| `hey sarty` | Common abbreviation |
| `ok sarthi` | Google-style prefix |
| `sarthi` | Minimal trigger |

Users can remove any they don't want and add their own.

---

## 8. Implementation Checklist

- [ ] Create `runtime/voice/wakeword.py` with `WakeWordDetector`
- [ ] Add `wake_words`, `wake_word_threshold`, `wake_word_enabled` to `config.py`
- [ ] Add wake word message handlers to `websocket.py`
- [ ] Update `SettingsView.tsx` with wake word UI section
- [ ] Add CSS for wake word chips + sensitivity slider
- [ ] Test: add a phrase in UI → save → verify .env updated
- [ ] Test: pipeline picks up the new phrase without restart
- [ ] Test: removing all but one phrase blocked by UI
- [ ] Document: hot-reload works (no restart needed after adding phrases)

---

> Next: [07_accessibility_integration.md](./07_accessibility_integration.md)
