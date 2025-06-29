# Transparent Sticky Notes with Speech Highlighting

A desktop sticky notes app with a transparent window, allowing you to type or paste notes, and highlight the content as you speak (using your laptop or Bluetooth mic). Powered by offline speech recognition (Vosk).

## Features

- Transparent, always-on-top sticky notes window
- Type or paste your notes
- Start/Stop listening to your microphone
- Highlights the words/phrases you speak in real-time
- Works offline (no paid API required)
- Package as a standalone Windows executable

## Setup

1. **Clone the repository**
2. **Create and activate a virtual environment**
   ```sh
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. **Install dependencies**
   ```sh
   pip install -r requirements.txt
   ```
4. **Download a Vosk model**

   - Download a model from [Vosk Models]()
   - Unzip it into the project directory (e.g., `model` folder)

5. **Run the app**

   ```sh
   python main.py
   ```

6. **Build executable (optional)**
   ```sh
   pyinstaller --onefile main.py
   ```

## Notes

- The app uses the Vosk speech recognition engine for offline transcription.
- You can select your preferred audio input device (laptop mic, Bluetooth mic, etc.).
- The app highlights the matching text in your sticky note as you speak.
