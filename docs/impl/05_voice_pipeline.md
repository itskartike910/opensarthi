# OpenSarthi — Implementation Plan
## Part 5: Voice Pipeline — Streaming STT, Wake Word, VAD, Barge-In

> **Priority:** P2 — Voice. After P0 execution engine is stable.
> **Affected files:** `runtime/voice/pipeline.py` [REFACTOR], `runtime/voice/wakeword.py` [NEW], `runtime/voice/vad.py` [NEW], `runtime/voice/stt.py` [NEW]

---

## 1. Current State & Problems

### What Exists

```
SpeechRecognition (Google Cloud STT)
  → basic microphone capture
  → echo protection (is_speaking flag)
  → 8-second silence timeout
```

### Problems

| Problem | Impact |
|---------|--------|
| Google Cloud STT — requires internet | No offline use |
| SpeechRecognition is blocking (not streaming) | High latency (1-3s delay) |
| No wake word — must press button | Not hands-free |
| No VAD — always recording | Wastes resources |
| No barge-in — can't interrupt TTS | Bad UX |
| No partial transcript streaming | No live feedback |

### Target Architecture

```
Microphone (sounddevice)
    │
    ▼
VAD (silero-vad or webrtcvad)
    │ speech detected
    ▼
Wake Word (OpenWakeWord) ←── configurable phrases from settings
    │ triggered
    ▼
faster-whisper (local STT, streaming)
    │ partial transcripts
    ▼
WebSocket → Frontend (live transcript display)
    │ final transcript
    ▼
Agent Runtime
    │ response
    ▼
TTS (Kokoro) → Speaker
    │
    └── is_speaking=True → suspends VAD capture
```

---

## 2. Dependencies

Add to `runtime/requirements.txt`:

```
sounddevice>=0.5           # Better mic capture than PyAudio
faster-whisper>=1.1        # Already in requirements, ensure it's there
openwakeword>=0.6          # Already in requirements
silero-vad>=5.1            # VAD model (alternative: webrtcvad)
numpy>=1.26                # Audio processing
```

---

## 3. Voice Activity Detection (`runtime/voice/vad.py`)

VAD prevents the system from constantly sending silent audio to Whisper:

```python
import numpy as np
import asyncio
from typing import Callable

class SileroVAD:
    """
    Voice Activity Detection using Silero VAD model.
    Lightweight, runs on CPU, works offline.
    """

    def __init__(self, sample_rate: int = 16000, threshold: float = 0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._model = None
        self._loaded = False

    def load(self):
        """Load the Silero VAD model (downloads on first use, ~1MB)."""
        import torch
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True
        )
        self._model = model
        self._get_speech_ts = utils[0]
        self._loaded = True

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """
        Returns True if audio chunk contains speech.
        audio_chunk: float32 numpy array, 16kHz mono
        """
        if not self._loaded:
            self.load()

        import torch
        tensor = torch.FloatTensor(audio_chunk)
        confidence = self._model(tensor, self.sample_rate).item()
        return confidence > self.threshold


class WebRTCVAD:
    """
    Lightweight alternative using webrtcvad (no ML model needed).
    Less accurate than Silero but zero dependencies beyond webrtcvad.
    """

    def __init__(self, aggressiveness: int = 2, sample_rate: int = 16000):
        import webrtcvad
        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate
        self.frame_duration_ms = 30  # 10, 20, or 30ms frames only

    def is_speech(self, audio_chunk: bytes) -> bool:
        try:
            return self.vad.is_speech(audio_chunk, self.sample_rate)
        except Exception:
            return True  # Fail open (assume speech on error)
```

---

## 4. Streaming STT with faster-whisper (`runtime/voice/stt.py`)

```python
import asyncio
import numpy as np
from typing import AsyncGenerator, Optional, Callable
from faster_whisper import WhisperModel

class FasterWhisperSTT:
    """
    Local STT using faster-whisper. Runs fully offline.
    Supports partial transcript streaming.
    """

    MODEL_SIZE = "base"  # Options: tiny, base, small, medium, large-v3-turbo
    # "base" is the best balance for realtime use on CPU
    # "large-v3-turbo" for GPU with best accuracy

    def __init__(self, language: str = "en"):
        self.language = language
        self._model: Optional[WhisperModel] = None

    def load(self):
        """Load the Whisper model (downloads on first use)."""
        self._model = WhisperModel(
            self.MODEL_SIZE,
            device="cpu",        # Use "cuda" if GPU available
            compute_type="int8", # Memory efficient
            cpu_threads=4
        )
        print(f"[STT] faster-whisper '{self.MODEL_SIZE}' loaded")

    def transcribe(self, audio_array: np.ndarray) -> tuple[str, float]:
        """
        Transcribe audio to text.
        Returns: (transcript, confidence)
        audio_array: float32 numpy array at 16kHz
        """
        if self._model is None:
            self.load()

        segments, info = self._model.transcribe(
            audio_array,
            language=self.language,
            vad_filter=True,         # Skip silent segments
            beam_size=3,             # Lower = faster, less accurate
            word_timestamps=False,
        )

        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text, info.language_probability

    async def transcribe_async(self, audio_array: np.ndarray) -> str:
        """Non-blocking transcription via thread pool."""
        loop = asyncio.get_event_loop()
        text, _ = await loop.run_in_executor(None, self.transcribe, audio_array)
        return text
```

---

## 5. Complete Voice Pipeline (`runtime/voice/pipeline.py`)

Replaces the current SpeechRecognition-based pipeline:

```python
import asyncio
import numpy as np
import sounddevice as sd
from typing import Callable, Optional

from voice.vad import SileroVAD
from voice.stt import FasterWhisperSTT
from voice.wakeword import WakeWordDetector  # see Part 6

class VoicePipeline:
    """
    Full voice pipeline:
    Mic → VAD → Wake Word → STT → callback(transcript)
    
    Echo protection: pauses while is_speaking=True
    Barge-in: can interrupt speaking if wake word detected mid-TTS
    """

    SAMPLE_RATE = 16000
    CHUNK_DURATION_MS = 30      # VAD frame size
    SILENCE_TIMEOUT = 8.0       # seconds of silence before sleeping
    MIN_SPEECH_DURATION = 0.3   # seconds — ignore very short utterances

    def __init__(
        self,
        on_transcript: Callable[[str], None],
        on_partial_transcript: Optional[Callable[[str], None]] = None,
        on_wake_word: Optional[Callable[[], None]] = None,
        wake_words: list[str] = None,
    ):
        self.on_transcript = on_transcript
        self.on_partial_transcript = on_partial_transcript
        self.on_wake_word = on_wake_word

        # State
        self.is_speaking = False     # TTS is active — suspend capture
        self.is_listening = False    # Pipeline is actively listening
        self._running = False
        self._speech_buffer: list[np.ndarray] = []
        self._last_speech_time = 0.0

        # Components
        self.vad = SileroVAD()
        self.stt = FasterWhisperSTT()
        self.wake_detector = WakeWordDetector(wake_words or ["hey sarthi", "opensarthi"])

    def start(self):
        """Start the voice pipeline in a background thread."""
        self._running = True
        import threading
        self._thread = threading.Thread(target=self._run_sync, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the pipeline."""
        self._running = False

    def _run_sync(self):
        """Synchronous mic loop — runs in a thread."""
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self._run())

    async def _run(self):
        chunk_samples = int(self.SAMPLE_RATE * self.CHUNK_DURATION_MS / 1000)

        with sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=chunk_samples
        ) as stream:
            print("[Voice] Pipeline started. Listening for wake word...")
            import time
            last_speech = time.time()

            while self._running:
                # Don't capture while TTS is speaking (echo protection)
                if self.is_speaking:
                    await asyncio.sleep(0.1)
                    continue

                chunk, _ = stream.read(chunk_samples)
                audio = chunk.flatten()

                # VAD check
                if not self.vad.is_speech(audio):
                    if self.is_listening and (time.time() - last_speech > self.SILENCE_TIMEOUT):
                        # Silence timeout — commit current buffer if any
                        await self._commit_speech_buffer()
                        self.is_listening = False
                        print("[Voice] Silence timeout — sleeping.")
                    continue

                last_speech = time.time()

                # Wake word check (if not already listening)
                if not self.is_listening:
                    if self.wake_detector.detect(audio):
                        print("[Voice] Wake word detected!")
                        self.is_listening = True
                        self._speech_buffer = []
                        if self.on_wake_word:
                            asyncio.create_task(asyncio.to_thread(self.on_wake_word))
                    continue  # Don't add wake word audio to buffer

                # Accumulate speech
                self._speech_buffer.append(audio)

                # Partial transcript every ~2 seconds of speech
                if len(self._speech_buffer) > int(2.0 / (self.CHUNK_DURATION_MS / 1000)):
                    partial_audio = np.concatenate(self._speech_buffer)
                    partial = await self.stt.transcribe_async(partial_audio)
                    if partial and self.on_partial_transcript:
                        self.on_partial_transcript(partial)

    async def _commit_speech_buffer(self):
        """Transcribe accumulated speech and call on_transcript."""
        if not self._speech_buffer:
            return

        audio = np.concatenate(self._speech_buffer)
        self._speech_buffer = []

        # Ignore very short utterances
        duration = len(audio) / self.SAMPLE_RATE
        if duration < self.MIN_SPEECH_DURATION:
            return

        transcript = await self.stt.transcribe_async(audio)
        if transcript:
            print(f"[Voice] Transcript: {transcript}")
            self.on_transcript(transcript)
```

---

## 6. Implementation Checklist

- [ ] Add `sounddevice`, `silero-vad`, `webrtcvad` to `requirements.txt`
- [ ] Create `runtime/voice/vad.py` with SileroVAD and WebRTCVAD
- [ ] Create `runtime/voice/stt.py` with FasterWhisperSTT
- [ ] Refactor `runtime/voice/pipeline.py` to use new components
- [ ] Test: run `python -c "from voice.pipeline import VoicePipeline"` (no crash)
- [ ] Test: `python tests/test_voice.py` — all imports pass
- [ ] Manual test: speak to the mic, verify transcript in console
- [ ] Integrate with WebSocket — emit `transcript_update` messages for partial transcripts
- [ ] Emit `voice_state` (idle/listening/processing) events to UI

---

## 7. WebSocket Voice Events

```python
# New events to emit from voice pipeline

# When pipeline is active (wake word heard)
{"type": "voice_state", "payload": {"state": "listening"}}

# Partial transcript (live feedback)
{"type": "transcript_update", "payload": {"text": "open fire...", "final": false}}

# Final transcript submitted to agent
{"type": "transcript_update", "payload": {"text": "open firefox", "final": true}}

# TTS started (suspend mic)
{"type": "voice_state", "payload": {"state": "speaking"}}

# TTS ended (resume mic)
{"type": "voice_state", "payload": {"state": "idle"}}
```

---

> Next: [06_wake_word_settings.md](./06_wake_word_settings.md)
