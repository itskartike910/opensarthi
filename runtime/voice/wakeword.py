import numpy as np
from typing import Optional

class WakeWordDetector:
    """
    Detects configurable wake word phrases using OpenWakeWord.
    Supports multiple simultaneous phrases.
    """

    # Built-in OpenWakeWord model names (pre-trained)
    BUILTIN_MODELS = {
        "hey sarthi": "hey_jarvis",      # Closest phoneme match
        "hey jarvis": "hey_jarvis",
        "alexa": "alexa",
    }

    DEFAULT_THRESHOLD = 0.5

    def __init__(
        self,
        phrases: list[str],
        threshold: float = DEFAULT_THRESHOLD
    ):
        self.phrases = [p.lower().strip() for p in phrases]
        self.threshold = threshold
        self._oww = None
        self._loaded = False
        self.load()

    def load(self):
        """Load OpenWakeWord models for configured phrases."""
        try:
            import openwakeword
            import os
            from openwakeword.model import Model

            # Map user phrases to available OWW models
            model_names = []
            for phrase in self.phrases:
                matched = False
                for k, v in self.BUILTIN_MODELS.items():
                    if k in phrase or phrase in k:
                        model_names.append(v)
                        matched = True
                        break
                if not matched:
                    # Default/fallback
                    model_names.append("hey_jarvis")

            # De-duplicate
            model_names = list(set(model_names))

            # Resolve actual file paths
            pretrained_paths = openwakeword.get_pretrained_model_paths()
            paths_to_load = []
            for path in pretrained_paths:
                for name in model_names:
                    if name in os.path.basename(path):
                        paths_to_load.append(path)
                        break

            self._oww = Model(
                wakeword_model_paths=paths_to_load
            )
            self._loaded = True
            print(f"[WakeWord] Loaded models for phrases: {self.phrases} (paths: {paths_to_load})")

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
        """
        if not self._loaded or self._oww is None:
            return False

        try:
            # OWW expects int16 PCM
            audio_int16 = (audio_chunk * 32767).astype(np.int16)
            prediction = self._oww.predict(audio_int16)

            for model_name, score in prediction.items():
                if score > 0.05:
                    print(f"[WakeWord] Candidate: '{model_name}' (score={score:.3f}, threshold={self.threshold})")
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
