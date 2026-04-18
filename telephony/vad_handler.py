"""
telephony/vad_handler.py — Smart Energy-based Voice Activity Detection.

Analyzes raw audio streams to intelligently detect when a user starts
and stops speaking based on volume (RMS energy) and silence timeouts.
"""

from __future__ import annotations

import time
import logging

try:
    import audioop
except ImportError:
    import audioop_lts as audioop

logger = logging.getLogger(__name__)

# Typical volume thresholds for 16-bit PCM
# The VAD debug showed line static peaking up to 20,800. Speech peaks are ~26,000.
ENERGY_THRESHOLD = 22000

# How much silence (in seconds) means the user finished their turn
SILENCE_TIMEOUT = 0.8

# Minimum duration (in seconds) to be considered real speech instead of random noise
MIN_SPEECH_DURATION = 0.3


class VADHandler:
    """Tracks continuous audio chunks to detect completed speech turns."""

    def __init__(
        self,
        energy_threshold: int = ENERGY_THRESHOLD,
        silence_timeout: float = SILENCE_TIMEOUT,
        min_speech_duration: float = MIN_SPEECH_DURATION,
        call_sid: str = "unknown",
    ):
        self.energy_threshold = energy_threshold
        self.silence_timeout = silence_timeout
        self.min_speech_duration = min_speech_duration
        self.call_sid = call_sid

        self.is_speaking = False
        self.speech_start_time = 0.0
        self.last_speech_time = 0.0
        self.last_debug_time = time.time()
        self.max_rms_interval = 0
        self.min_rms_interval = 999999

    def process_pcm_chunk(self, pcm_chunk: bytes) -> bool:
        """
        Process a chunk of 16-bit PCM audio.
        
        Returns:
            True if a complete, valid speech turn has finished.
            False otherwise.
        """
        if not pcm_chunk:
            return False

        now = time.time()
        
        # Calculate Root Mean Square energy (volume) of the 16-bit PCM chunk
        # Format "2" means 16-bit (2 byte) audio width
        rms = audioop.rms(pcm_chunk, 2)
        
        self.max_rms_interval = max(self.max_rms_interval, rms)
        self.min_rms_interval = min(self.min_rms_interval, rms)
        
        if now - self.last_debug_time >= 2.0:
            status = "🗣️ SPEAKING" if self.is_speaking else "🤫 SILENT"
            logger.info(f"[{self.call_sid}] |     [VAD DEBUG] {status} | Floor: {self.min_rms_interval} | Peak: {self.max_rms_interval} | Threshold: {self.energy_threshold}")
            self.last_debug_time = now
            self.max_rms_interval = 0
            self.min_rms_interval = 999999

        if rms > self.energy_threshold:
            # -- Active speech detected --
            if not self.is_speaking:
                self.is_speaking = True
                self.speech_start_time = now
                logger.info(f"[{self.call_sid}] |     [🎤] Speech started (energy: {rms})")
            
            self.last_speech_time = now
            return False
            
        else:
            # -- Silence detected --
            if self.is_speaking:
                silence_duration = now - self.last_speech_time
                
                # Check if they've been quiet long enough to trigger a turn
                if silence_duration >= self.silence_timeout:
                    self.is_speaking = False
                    
                    total_speech = self.last_speech_time - self.speech_start_time
                    
                    # Ensure it wasn't just a brief tap or cough
                    if total_speech >= self.min_speech_duration:
                        logger.info(f"[{self.call_sid}] |     [⏳] Speech ended (silence for {silence_duration:.2f}s). Processing turn...")
                        return True
                    else:
                        logger.info(f"[{self.call_sid}] |     [🚫] Ignored short noise burst ({total_speech:.2f}s)")
                        return False
            
            return False
