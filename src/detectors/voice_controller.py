"""Voice Controller — Background Speech Recognition Engine (Turkish & English Support)."""

import threading
import time
from typing import Optional

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

class VoiceController:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._action: Optional[str] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        if HAS_SR:
            self.recognizer = sr.Recognizer()
            # Hoparlörden gelen müziği filtrelemek için ayarlar
            self.recognizer.dynamic_energy_threshold = True 
            self.recognizer.energy_threshold = 400 
            self.recognizer.pause_threshold = 0.8
            self.mic = sr.Microphone()
        else:
            self.recognizer = None
            self.mic = None

    def start(self) -> None:
        if not HAS_SR:
            print("[voice_controller] speech_recognition yüklü değil. Terminale yazın: pip install SpeechRecognition pyaudio", flush=True)
            return
            
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="voice-loop")
        self._thread.start()
        print("[voice_controller] started listening in background (Turkish & English)", flush=True)

    def consume_action(self) -> Optional[str]:
        with self._lock:
            a = self._action
            self._action = None
            return a

    def _set_action(self, action: str) -> None:
        with self._lock:
            self._action = action

    def _run(self) -> None:
        with self.mic as source:
            # Ortam gürültüsüne (müzik dahil) kalibrasyon
            self.recognizer.adjust_for_ambient_noise(source, duration=2.0)
            
        while not self._stop_event.is_set():
            try:
                with self.mic as source:
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=3)

                text = self.recognizer.recognize_google(audio, language="tr-TR").lower()
                print(f"[voice] Duyulan Komut: '{text}'", flush=True)
                
                if "uyut" in text or "kapat" in text or "sleep" in text or "dur" in text:
                    self._set_action("sleep_mode")
                elif "fare" in text or "mouse" in text:
                    self._set_action("mode_mouse")
                elif "kafa" in text or "baş" in text or "head" in text:
                    self._set_action("mode_head")
                elif "el" in text or "jest" in text or "hareket" in text or "gesture" in text:
                    self._set_action("mode_gesture")
                elif "oynat" in text or "başlat" in text or "play" in text or "pause" in text:
                    self._set_action("play_pause")
                elif "sonraki" in text or "geç" in text or "next" in text:
                    self._set_action("next_track")
                elif "önceki" in text or "geri" in text or "previous" in text or "prev" in text:
                    self._set_action("prev_track")
                elif "tam ekran" in text or "büyüt" in text or "fullscreen" in text:
                    self._set_action("fullscreen")
                    
            except sr.WaitTimeoutError:
                pass  
            except sr.UnknownValueError:
                pass  
            except Exception as e:
                time.sleep(1)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread: self._thread.join(timeout=3)
