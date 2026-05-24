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
        self._load_attempted = False

    def load(self):
        """Load the Silero VAD model. Falls back to energy threshold if offline/unreachable."""
        try:
            import torch
            # Set hub directory inside .config/opensarthi
            import os
            os.environ["TORCH_HOME"] = os.path.expanduser("~/.config/opensarthi/torch")
            
            # Load locally or download
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True
            )
            self._model = model
            self._loaded = True
            print("[VAD] Silero VAD loaded successfully")
        except Exception as e:
            print(f"[VAD] Could not load Silero VAD, using RMS energy threshold fallback: {e}")
            self._model = None
            self._loaded = False

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """
        Returns True if audio chunk contains speech.
        audio_chunk: float32 numpy array, 16kHz mono
        """
        if not self._loaded and not self._load_attempted:
            self._load_attempted = True
            self.load()

        if self._loaded and self._model is not None:
            try:
                import torch
                tensor = torch.FloatTensor(audio_chunk)
                # Ensure correct dimension
                if len(tensor.shape) == 1:
                    tensor = tensor.unsqueeze(0)
                confidence = self._model(tensor, self.sample_rate).item()
                return confidence > self.threshold
            except Exception:
                pass

        # Fallback: Root Mean Square (RMS) energy thresholding
        rms = np.sqrt(np.mean(audio_chunk**2))
        return rms > 0.015  # Simple empirical threshold for active speech
