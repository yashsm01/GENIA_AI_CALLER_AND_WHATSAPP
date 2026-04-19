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
# Normal speech hits 5,000-20,000. True line static is ~100-500.
ENERGY_THRESHOLD = 1500

# How much silence (in seconds) means the user finished their turn
# Shortened to 0.6s to greatly improve conversational turnaround time.
SILENCE_TIMEOUT = 0.6

# Minimum duration (in seconds) to be considered real speech instead of random noise
MIN_SPEECH_DURATION = 0.3

# Maximum duration (in seconds) the user can speak before the AI forces a response
MAX_SPEECH_DURATION = 10.0


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
        self.max_speech_duration = MAX_SPEECH_DURATION
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
        
        # Calculate Root Mean Square energy (volume) by first decoding mu-law to PCM
        try:
            pcm_data = audioop.ulaw2lin(pcm_chunk, 2)
            rms = audioop.rms(pcm_data, 2)
        except audioop.error:
            rms = 0
        
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
            
            # -- Max Duration Check --
            # If the user has been talking continuously for MAX_SPEECH_DURATION, force a cutoff.
            # if now - self.speech_start_time >= self.max_speech_duration:
            #     logger.info(f"[{self.call_sid}] |     [⏳] Speech reached max limit ({self.max_speech_duration}s). Forcing turn...")
            #     self.is_speaking = False
            #     return True
                
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
