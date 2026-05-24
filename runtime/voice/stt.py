import asyncio
import numpy as np
import io
import wave
import httpx
from typing import Optional
from faster_whisper import WhisperModel
import structlog

logger = structlog.get_logger()

class FasterWhisperSTT:
    """
    STT using a hybrid approach: Groq Cloud API for ultra-fast, high-accuracy transcription
    if the Groq API key is available, falling back to local offline faster-whisper.
    """

    MODEL_SIZE = "base.en"  # Options: tiny.en, tiny, base, base.en, small, medium, large-v3-turbo

    def __init__(self, language: str = "en"):
        self.language = language
        self._model: Optional[WhisperModel] = None

    def load(self):
        """Load the Whisper model (downloads on first use)."""
        if self._model is not None:
            return
        try:
            self._model = WhisperModel(
                self.MODEL_SIZE,
                device="cpu",        # Use "cuda" if GPU available
                compute_type="int8", # Memory efficient
                cpu_threads=4
            )
            print(f"[STT] faster-whisper '{self.MODEL_SIZE}' loaded successfully")
        except Exception as e:
            logger.error("Failed to load local faster-whisper model", error=str(e))

    def transcribe(self, audio_array: np.ndarray) -> tuple[str, float]:
        """
        Transcribe audio to text.
        Returns: (transcript, confidence)
        audio_array: float32 numpy array at 16kHz
        """
        if self._model is None:
            self.load()

        if self._model is None:
            return "", 0.0

        try:
            segments, info = self._model.transcribe(
                audio_array,
                language=self.language,
                vad_filter=True,         # Skip silent segments
                beam_size=3,             # Lower = faster, less accurate
                word_timestamps=False,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return text, info.language_probability
        except Exception as e:
            logger.error("Local STT transcription failed", error=str(e))
            return "", 0.0

    async def transcribe_async(self, audio_array: np.ndarray) -> str:
        """Non-blocking transcription via Groq Cloud API or thread pool fallback."""
        from config import settings
        
        # Try Groq API if key is set
        groq_key = getattr(settings, "groq_api_key", None)
        if groq_key and groq_key.strip():
            logger.info("Using Groq Cloud Whisper API for real-time transcription")
            try:
                # Convert float32 numpy array to 16-bit PCM WAV in memory
                wav_io = io.BytesIO()
                with wave.open(wav_io, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2) # 16-bit PCM
                    wav_file.setframerate(16000)
                    # Convert float32 [-1.0, 1.0] to int16
                    audio_int16 = np.clip(audio_array, -1.0, 1.0)
                    audio_int16 = (audio_int16 * 32767).astype(np.int16)
                    wav_file.writeframes(audio_int16.tobytes())
                wav_bytes = wav_io.getvalue()

                headers = {
                    "Authorization": f"Bearer {groq_key}",
                }
                files = {
                    "file": ("audio.wav", wav_bytes, "audio/wav"),
                }
                data = {
                    "model": "whisper-large-v3-turbo",
                    "language": self.language,
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=8.0
                    )
                    if response.status_code == 200:
                        transcript = response.json().get("text", "").strip()
                        logger.info("Groq STT transcription success", text=transcript)
                        return transcript
                    else:
                        logger.error("Groq STT API returned error code", status_code=response.status_code, body=response.text)
            except Exception as e:
                logger.error("Failed transcribing via Groq API, falling back to local Whisper", error=str(e))

        # Fallback to local faster-whisper
        loop = asyncio.get_event_loop()
        text, _ = await loop.run_in_executor(None, self.transcribe, audio_array)
        return text
