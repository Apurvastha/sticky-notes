import sys
if getattr(sys, 'frozen', False):
    # Running as bundled exe, suppress prints
    import builtins
    builtins.print = lambda *a, **k: None
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import os
import sounddevice as sd
from vosk import Model, KaldiRecognizer
import json
import fugashi
import jaconv
from rapidfuzz import process, fuzz
import re
import unidic_lite

MODEL_PATH = "model-ja"  # Path to Japanese Vosk model

os.environ["MECABRC"] = ""

class StickyNotesApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sticky Notes JA")
        self.geometry("600x400")
        self.attributes('-topmost', True)
        self.attributes('-alpha', 0.75)
        self.configure(bg='#f7f7de')
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Dragging support
        self._offsetx = 0
        self._offsety = 0
        self.bind('<Button-1>', self.click_win)
        self.bind('<B1-Motion>', self.drag_win)

        # UI Layout
        top_frame = tk.Frame(self, bg='#f7f7de')
        top_frame.pack(fill=tk.X, pady=(10, 0), padx=10)
        mic_label = tk.Label(top_frame, text="Select Microphone:", bg='#f7f7de', font=("Segoe UI", 10))
        mic_label.pack(side=tk.LEFT)
        self.device_var = tk.StringVar()
        self.device_menu = ttk.Combobox(top_frame, textvariable=self.device_var, state="readonly", width=25)
        self.device_menu.pack(side=tk.LEFT, padx=5)
        self.refresh_devices()
        refresh_btn = ttk.Button(top_frame, text="⟳", width=2, command=self.refresh_devices)
        refresh_btn.pack(side=tk.LEFT, padx=2)
        controls = tk.Frame(self, bg='#f7f7de')
        controls.pack(fill=tk.X, pady=5, padx=10)
        self.start_btn = ttk.Button(controls, text="Start Listening", command=self.start_listening)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(controls, text="Stop Listening", command=self.stop_listening, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        self.text = tk.Text(self, wrap=tk.WORD, font=("Segoe UI", 13), bg='#f7f7de', fg='#333', undo=True, relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        self.text.pack(expand=True, fill=tk.BOTH, padx=10, pady=(0,10))
        self.text.tag_configure("highlight", background="#e6e6b8")

        # Speech recognition
        self.listening = False
        self.audio_thread = None
        self.q = queue.Queue()
        self.model = None
        self.rec = None
        # Set up fugashi tagger with correct dictionary path for both script and exe
        if hasattr(sys, "_MEIPASS"):
            dicdir = os.path.join(sys._MEIPASS, "_internal", "unidic_lite", "dicdir")
        else:
            dicdir = os.path.join(os.path.dirname(unidic_lite.__file__), "dicdir")
        os.environ["MECABRC"] = ""
        # print("Using MeCab dictionary directory:", dicdir)
        # print("Contents:", os.listdir(dicdir))
        self.tagger = fugashi.Tagger(f'-d "{dicdir}"')

        # Check for Vosk model
        if not os.path.exists(MODEL_PATH):
            messagebox.showinfo(
                "Vosk Model Missing",
                f"Please download a Japanese Vosk model and unzip it as '{MODEL_PATH}' in the project directory."
            )

    # --- Window Dragging ---
    def click_win(self, event):
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget == self.text:
            return
        self._offsetx = event.x_root - self.winfo_x()
        self._offsety = event.y_root - self.winfo_y()
    def drag_win(self, event):
        x = event.x_root - self._offsetx
        y = event.y_root - self._offsety
        self.geometry(f'+{x}+{y}')

    # --- Audio Device Selection ---
    def refresh_devices(self):
        try:
            devices = sd.query_devices()
            input_devices = [f"{i}: {d['name']}" for i, d in enumerate(devices) if d['max_input_channels'] > 0]
            self.device_menu['values'] = input_devices
            if input_devices:
                self.device_menu.current(0)
            else:
                self.device_menu.set('No input devices found')
        except Exception as e:
            self.device_menu['values'] = []
            self.device_menu.set('Error listing devices')

    def get_selected_device_index(self):
        val = self.device_var.get()
        if val and ':' in val:
            return int(val.split(':')[0])
        return None

    # --- Speech Recognition ---
    def start_listening(self):
        if not os.path.exists(MODEL_PATH):
            messagebox.showerror("Model Missing", f"Vosk model not found at '{MODEL_PATH}'.")
            return
        if not self.device_menu.get() or 'No input' in self.device_menu.get() or 'Error' in self.device_menu.get():
            messagebox.showerror("No Microphone", "No valid microphone selected.")
            return
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.listening = True
        self.audio_thread = threading.Thread(target=self.listen_audio, daemon=True)
        self.audio_thread.start()
        self.after(100, self.process_queue)

    def stop_listening(self):
        self.listening = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def listen_audio(self):
        try:
            if self.model is None:
                self.model = Model(MODEL_PATH)
            device = self.get_selected_device_index()
            if device is None:
                self.q.put(('error', 'No valid microphone selected.'))
                return
            samplerate = int(sd.query_devices(device, 'input')['default_samplerate'])
            self.rec = KaldiRecognizer(self.model, samplerate)
            with sd.RawInputStream(samplerate=samplerate, blocksize=8000, device=device, dtype='int16', channels=1, callback=self.audio_callback):
                while self.listening:
                    sd.sleep(100)
        except Exception as e:
            self.q.put(('error', str(e)))

    def audio_callback(self, indata, frames, time, status):
        data_bytes = bytes(indata)
        if self.rec.AcceptWaveform(data_bytes):
            result = self.rec.Result()
            self.q.put(('result', result))
        else:
            partial = self.rec.PartialResult()
            self.q.put(('partial', partial))

    def process_queue(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == 'result':
                    text = json.loads(data).get('text', '')
                    if text:
                        self.highlight_text(text)
                elif kind == 'partial':
                    text = json.loads(data).get('partial', '')
                    if text:
                        self.highlight_text(text, partial=True)
                elif kind == 'error':
                    messagebox.showerror("Error", data)
                    self.stop_listening()
        except queue.Empty:
            pass
        if self.listening:
            self.after(100, self.process_queue)

    # --- Highlighting ---
    def kanji_to_romaji(self, text):
        kana = ''.join([word.feature.kana or word.surface for word in self.tagger(text)])
        # print(f"Kana: {kana}")  # Debug print
        kana = kana.replace(' ', '')  # Remove spaces for better conversion
        hira = jaconv.kata2hira(kana)
        # print(f"Hiragana: {hira}")  # Debug print
        try:
            romaji = jaconv.kana2alphabet(hira)
        except Exception as e:
            # print(f"jaconv error: {e}")
            romaji = hira  # Fallback
        # print(f"Romaji (from kana): {romaji}")  # Debug print
        return romaji

    def highlight_text(self, spoken, partial=False):
        # print(f"Recognized: {spoken}")
        self.text.tag_remove("highlight", "1.0", tk.END)
        note = self.text.get("1.0", tk.END)
        if not spoken.strip():
            return
        spoken_romaji = self.kanji_to_romaji(spoken.strip())
        note_blocks = [block.strip() for block in re.split(r'\n\s*\n', note)]
        # Use partial_ratio for block matching
        match, score, idx = process.extractOne(
            spoken_romaji, note_blocks, scorer=fuzz.partial_ratio
        ) if note_blocks else (None, 0, None)
        # print(f"Fuzzy match score: {score}, matched block: {match}")
        if score > 30 and match and idx is not None:
            block_start_idx = note.find(match)
            if block_start_idx == -1:
                return
            block_text = match
            # Try matching against each line in the block for better accuracy
            block_lines = block_text.splitlines()
            best_line = block_text
            best_line_score = 0
            for line in block_lines:
                line_score = fuzz.partial_ratio(spoken_romaji.lower(), line.lower())
                if line_score > best_line_score:
                    best_line_score = line_score
                    best_line = line
            # Now do sliding window fuzzy match on best_line
            block_words = re.findall(r'\b\w+\b', best_line)
            best_window_score = 0
            best_window_span = (0, 0)
            best_window_text = ''
            best_line_lower = best_line.lower()
            spoken_romaji_lower = spoken_romaji.lower()
            for window_size in [4, 3]:
                if len(block_words) < window_size:
                    continue
                for i in range(len(block_words) - window_size + 1):
                    window_words = block_words[i:i+window_size]
                    window_text = ' '.join(window_words)
                    window_score = fuzz.partial_ratio(spoken_romaji_lower, window_text.lower())
                    if window_score > best_window_score:
                        best_window_score = window_score
                        idx_in_line = best_line_lower.find(window_text.lower())
                        if idx_in_line != -1:
                            span_start = idx_in_line
                            span_end = idx_in_line + len(window_text)
                            best_window_span = (span_start, span_end)
                            best_window_text = window_text
            # print(f"Best window score: {best_window_score}, window: '{best_window_text}'")
            # Fallback to first 3-4 words if no good window found
            if best_window_span == (0, 0) and block_words:
                joined = ' '.join(block_words[:4])
                idx_in_line = best_line_lower.find(joined.lower())
                if idx_in_line != -1:
                    best_window_span = (idx_in_line, idx_in_line + len(joined))
                else:
                    best_window_span = (0, min(20, len(best_line)))
            # Calculate highlight start/end in the whole note
            line_offset_in_block = block_text.find(best_line)
            highlight_start = block_start_idx + line_offset_in_block + best_window_span[0]
            highlight_end = block_start_idx + line_offset_in_block + best_window_span[1]
            start = f"1.0+{highlight_start}c"
            end = f"1.0+{highlight_end}c"
            self.text.tag_add("highlight", start, end)

    def on_close(self):
        self.listening = False
        self.destroy()

if __name__ == "__main__":
    app = StickyNotesApp()
    app.mainloop() 