import asyncio
import structlog
import queue
from typing import AsyncGenerator
import speech_recognition as sr
import threading
import time

logger = structlog.get_logger()

class VoicePipeline:
    def __init__(self):
        self.is_listening = False
        self.recognizer = sr.Recognizer()
        self.audio_queue = queue.Queue()
        self.listen_thread = None
        self.current_playback_id = ""
        self.is_speaking = False

    async def initialize(self):
        """Lazy load models."""
        logger.info("Initializing voice models")
        # Pre-adjust for ambient noise if mic is available
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                logger.info("Microphone initialized and calibrated.")
        except Exception as e:
            logger.warning(f"Could not initialize microphone: {e}")

    def _listen_worker(self):
        with sr.Microphone() as source:
            while self.is_listening:
                try:
                    # Listen for phrases without fixed time constraints to support long inputs
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=None)
                    self.audio_queue.put(audio)
                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Mic error: {e}")
                    time.sleep(1)

    async def start_listening(self) -> AsyncGenerator[str, None]:
        self.is_listening = True
        logger.info("Started native Python listening")
        
        # Start background listening thread
        self.listen_thread = threading.Thread(target=self._listen_worker, daemon=True)
        self.listen_thread.start()
        
        try:
            while self.is_listening:
                # Flush the audio queue continuously if assistant is speaking
                if getattr(self, "is_speaking", False):
                    while not self.audio_queue.empty():
                        try:
                            self.audio_queue.get_nowait()
                        except queue.Empty:
                            break
                    await asyncio.sleep(0.1)
                    continue

                # Process audio queue asynchronously
                while not self.audio_queue.empty():
                    audio = self.audio_queue.get()
                    try:
                        # Double check speaking state
                        if getattr(self, "is_speaking", False):
                            continue

                        # Resolve correct Speech-to-Text (STT) language based on active voice accent
                        rec_lang = "en-IN"
                        try:
                            from config import settings
                            voice_config = getattr(settings, "voice_accent", "ie")
                            
                            if voice_config in ['fr', 'es', 'de', 'hi', 'ja', 'it', 'pt']:
                                if voice_config == 'hi':
                                    rec_lang = 'hi-IN'
                                elif voice_config == 'ja':
                                    rec_lang = 'ja-JP'
                                elif voice_config == 'pt':
                                    rec_lang = 'pt-BR'
                                else:
                                    rec_lang = f"{voice_config}-{voice_config.upper()}"
                            elif voice_config == 'co.uk':
                                rec_lang = 'en-GB'
                            elif voice_config == 'com':
                                rec_lang = 'en-US'
                            elif voice_config == 'com.au':
                                rec_lang = 'en-AU'
                            elif voice_config == 'ca':
                                rec_lang = 'en-CA'
                            elif voice_config == 'co.nz':
                                rec_lang = 'en-NZ'
                            else:
                                rec_lang = 'en-IE'
                        except Exception:
                            pass

                        # Use Google Web Speech API for fast, free recognition
                        text = self.recognizer.recognize_google(audio, language=rec_lang)
                        if text:
                            logger.info(f"Transcribed ({rec_lang}): {text}")
                            yield text
                    except sr.UnknownValueError:
                        # Could not understand audio
                        pass
                    except sr.RequestError as e:
                        logger.error(f"STT API Error: {e}")
                
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            self.stop_listening()

    async def stop_listening(self):
        self.is_listening = False
        if self.listen_thread:
            self.listen_thread = None
        logger.info("Stopped native Python listening")

    async def speak(self, text: str) -> str:
        """Synthesize and speak text using the best available Linux voice engine, awaiting completion."""
        import subprocess
        import shutil
        import os
        import threading
        
        self.is_speaking = True
        try:
            logger.info("Synthesizing speech", text=text)
            
            # Clean text from emojis or problematic characters
            cleaned_text = "".join(c for c in text if c.isalnum() or c.isspace() or c in ".,!?;:'\"-")
            if not cleaned_text.strip():
                return "none"

            # Check and self-install gtts if missing
            gtts_available = False
            try:
                import gtts
                gtts_available = True
            except ImportError:
                import sys
                logger.info("gtts is missing. Dynamically self-installing gtts...")
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", "gtts"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    import gtts
                    gtts_available = True
                    logger.info("gtts successfully self-installed!")
                except Exception as e:
                    logger.warning(f"Could not dynamically self-install gtts: {e}")

            # Layer 1: Premium Google Assistant Voice (gTTS)
            if gtts_available:
                try:
                    from gtts import gTTS
                    import uuid
                    import time
                    import re
                    
                    # Generate new unique playback ID to isolate this speech run and prevent overlaps
                    playback_id = str(uuid.uuid4())
                    self.current_playback_id = playback_id
                    
                    # Instantly terminate any active terminal audio players to interrupt speech immediately
                    os.system("killall -9 mpg123 mpv paplay aplay >/dev/null 2>&1")
                    
                    from config import settings
                    voice_config = getattr(settings, "voice_accent", "ie")
                    speed = getattr(settings, "voice_speed", 1.35)
                    
                    # Resolve language and TLD dynamically based on settings
                    if voice_config in ['fr', 'es', 'de', 'hi', 'ja', 'it', 'pt']:
                        lang = voice_config
                        if voice_config == 'hi':
                            tld = 'co.in'
                        elif voice_config == 'ja':
                            tld = 'co.jp'
                        elif voice_config == 'pt':
                            tld = 'com.br'
                        else:
                            tld = voice_config
                    else:
                        lang = 'en'
                        tld = voice_config
                    
                    # Split text into sentences for sub-second start latency
                    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', cleaned_text) if s.strip()]
                    if not sentences:
                        return "none"
                        
                    downloaded = [False] * len(sentences)
                    mp3_paths = [f"/tmp/opensarthi_voice_{i}.mp3" for i in range(len(sentences))]
                    wav_paths = [f"/tmp/opensarthi_voice_{i}.wav" for i in range(len(sentences))]
                    
                    # sequential downloader background thread (pre-fetches next sentences while playing current ones)
                    def download_worker(p_id):
                        for idx, sentence in enumerate(sentences):
                            if p_id != self.current_playback_id:
                                break
                            try:
                                tts = gTTS(text=sentence, lang=lang, tld=tld)
                                tts.save(mp3_paths[idx])
                                downloaded[idx] = True
                            except Exception as de:
                                logger.error(f"gTTS chunk {idx} download failed: {de}")
                                downloaded[idx] = True # Mark true so loop doesn't block forever
                    
                    # playback worker
                    def _play_gtts(p_id):
                        try:
                            for idx in range(len(sentences)):
                                # Check if we've been interrupted by a newer playback request
                                if p_id != self.current_playback_id:
                                    return
                                    
                                # Wait for this specific chunk to finish downloading
                                while not downloaded[idx]:
                                    if p_id != self.current_playback_id:
                                        return
                                    time.sleep(0.02)
                                    
                                mp3_path = mp3_paths[idx]
                                wav_path = wav_paths[idx]
                                
                                if not os.path.exists(mp3_path):
                                    continue
                                    
                                # Speed up using ffmpeg atempo if available to achieve perfect, pitch-corrected fast playback
                                speedup_mp3_path = f"/tmp/opensarthi_voice_fast_{idx}.mp3"
                                if shutil.which("ffmpeg"):
                                    try:
                                        if os.system(f"ffmpeg -y -i {mp3_path} -filter:a 'atempo={speed}' {speedup_mp3_path} >/dev/null 2>&1") == 0:
                                            mp3_path = speedup_mp3_path
                                    except Exception as fe:
                                        logger.warning(f"ffmpeg speedup failed on chunk {idx}: {fe}")
                                        
                                # Pre-convert to WAV in case we need to fall back to paplay/aplay (PulseAudio standard)
                                wav_converted = False
                                if shutil.which("mpg123"):
                                    try:
                                        os.system(f"mpg123 -w {wav_path} {mp3_path} >/dev/null 2>&1")
                                        wav_converted = True
                                    except Exception:
                                        pass
                                if not wav_converted and shutil.which("ffmpeg"):
                                    try:
                                        os.system(f"ffmpeg -y -i {mp3_path} {wav_path} >/dev/null 2>&1")
                                        wav_converted = True
                                    except Exception:
                                        pass

                                # Double-check interruption right before playing
                                if p_id != self.current_playback_id:
                                    return

                                # Find the best terminal audio player on host and play chunk
                                played = False
                                if shutil.which("mpv"):
                                    if mp3_path == speedup_mp3_path:
                                        os.system(f"mpv {mp3_path} >/dev/null 2>&1")
                                    else:
                                        os.system(f"mpv --speed={speed} {mp3_path} >/dev/null 2>&1")
                                    played = True
                                    
                                if not played and shutil.which("mpg123"):
                                    # Force pulse or alsa output driver to prevent silent blocks/locks under PipeWire
                                    for driver in ["pulse", "alsa"]:
                                        exit_code = os.system(f"mpg123 -o {driver} {mp3_path} >/dev/null 2>&1")
                                        if exit_code == 0:
                                            played = True
                                            break
                                    if not played:
                                        os.system(f"mpg123 {mp3_path} >/dev/null 2>&1")
                                        played = True
                                        
                                if not played and wav_converted:
                                    if shutil.which("paplay"):
                                        os.system(f"paplay {wav_path} >/dev/null 2>&1")
                                        played = True
                                    elif shutil.which("aplay"):
                                        os.system(f"aplay {wav_path} >/dev/null 2>&1")
                                        played = True
                                        
                                if not played:
                                    for player in ["mpg321", "play", "cvlc"]:
                                        if shutil.which(player):
                                            if player == "cvlc":
                                                os.system(f"cvlc --play-and-exit {mp3_path} >/dev/null 2>&1")
                                            elif player == "play":
                                                os.system(f"play {mp3_path} >/dev/null 2>&1")
                                            else:
                                                os.system(f"{player} {mp3_path} >/dev/null 2>&1")
                                            played = True
                                            break
                        except Exception as ex:
                            logger.error(f"gTTS playback failure: {ex}")
                    
                    # Start pre-fetch worker thread
                    threading.Thread(target=download_worker, args=(playback_id,), daemon=True).start()
                    
                    # Await playback worker thread pool execution in a responsive way
                    await asyncio.to_thread(_play_gtts, playback_id)
                    logger.info("Speech synthesis streaming completed successfully")
                    return "gtts"
                except Exception as e:
                    logger.warning(f"Failed to play premium gTTS voice: {e}")

            # Layer 2: Speech Dispatcher client (Offline Fallback)
            if shutil.which("spd-say"):
                try:
                    await asyncio.to_thread(
                        subprocess.run,
                        ["spd-say", "-t", "female1", "-r", "0", "-w", cleaned_text],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    logger.info("Speech synthesis completed via spd-say fallback")
                    return "spd-say"
                except Exception as e:
                    logger.warning(f"spd-say fallback execution failed: {e}")

            # Layer 3: eSpeak (Offline Fallback)
            if shutil.which("espeak"):
                try:
                    await asyncio.to_thread(
                        subprocess.run,
                        ["espeak", "-v", "en-us+f3", "-s", "160", cleaned_text],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    logger.info("Speech synthesis completed via espeak fallback")
                    return "espeak"
                except Exception as e:
                    logger.warning(f"espeak fallback execution failed: {e}")

            logger.warning("No speech synthesis engines could play the audio output!")
            return "none"
        finally:
            self.is_speaking = False
