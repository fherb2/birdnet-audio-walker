# Docker Audio Testing Guide

## Überblick

Audio im Docker-Container funktioniert über durchgereichte Audio-Devices vom Host-System. Es gibt zwei Hauptmethoden: **PulseAudio** (moderner Linux-Standard) oder **ALSA** (direkter Hardware-Zugriff).

---

## Methode 1: PulseAudio (empfohlen)

### Voraussetzungen prüfen

```bash
# PulseAudio läuft auf Host?
systemctl --user status pulseaudio

# Socket-Pfad finden
echo $XDG_RUNTIME_DIR
# Typisch: /run/user/1000
```

### Docker mit PulseAudio starten

```bash
docker run -it --rm \
  -e PULSE_SERVER=unix:/run/user/1000/pulse/native \
  -v /run/user/1000/pulse:/run/user/1000/pulse \
  -v $(pwd):/workspace \
  -w /workspace \
  your-birdnet-image \
  bash
```

**Wichtig:** Ersetze `1000` mit deiner User-ID (`id -u`).

### Im Container testen

```bash
# PulseAudio verfügbar?
pactl info

# TTS + Audio-Test
cd /workspace/source
python -m birdnet_play.tts

# Playback-Test
python ../test_audio_playback.py
```

---

## Methode 2: ALSA (direkter Hardware-Zugriff)

### Docker mit ALSA starten

```bash
docker run -it --rm \
  --device /dev/snd \
  -v $(pwd):/workspace \
  -w /workspace \
  your-birdnet-image \
  bash
```

### Im Container testen

```bash
# ALSA-Devices sichtbar?
aplay -l

# Audio-Test
cd /workspace/source
python ../test_audio_playback.py
```

---

## Methode 3: VSCode Remote Container

Wenn du mit VSCode Remote arbeitest:

**In `.devcontainer/devcontainer.json`:**

```json
{
  "mounts": [
    "source=/run/user/${localEnv:UID}/pulse,target=/run/user/1000/pulse,type=bind"
  ],
  "containerEnv": {
    "PULSE_SERVER": "unix:/run/user/1000/pulse/native"
  },
  "runArgs": [
    "--device=/dev/snd"
  ]
}
```

---

## Troubleshooting

### Problem: "Connection refused" (PulseAudio)

**Lösung 1:** PulseAudio für Netzwerk-Zugriff öffnen

```bash
# Auf Host
pactl load-module module-native-protocol-tcp auth-ip-acl=127.0.0.1

# Im Container
export PULSE_SERVER=tcp:host.docker.internal:4713
```

**Lösung 2:** PulseAudio Socket-Permissions

```bash
# Auf Host
chmod 777 /run/user/1000/pulse/native
```

### Problem: "No audio device found"

**Prüfen:**

```bash
# Im Container
ls -la /dev/snd/         # ALSA
echo $PULSE_SERVER       # PulseAudio
pactl list sinks short   # PulseAudio Outputs
```

### Problem: Audio funktioniert nicht, aber kein Fehler

**Test mit aplay (ALSA):**

```bash
# Erzeuge Test-Ton (440Hz Sinus, 1s)
ffmpeg -f lavfi -i "sine=frequency=440:duration=1" test.wav

# Abspielen
aplay test.wav
```

**Test mit paplay (PulseAudio):**

```bash
paplay test.wav
```

---

## Alternative: Streamlit-UI (kein Container-Audio nötig!)

**Wichtig:** Für Streamlit-Nutzung brauchst du **kein** Audio im Container!

```bash
# Container ohne Audio-Durchreichung
docker run -it --rm \
  -p 8501:8501 \
  -v $(pwd):/workspace \
  -w /workspace \
  your-birdnet-image \
  bash

# Streamlit starten
cd /workspace
streamlit run source/birdnet_play/streamlit_app.py -- /data/db.db

# Im Browser auf Host: http://localhost:8501
# Audio spielt im Browser auf dem Host!
```

**Vorteil:** Audio läuft komplett im Host-Browser, Container braucht keine Audio-Devices.

---

## Empfehlung

**Für lokale Entwicklung:**
- Ohne Docker arbeiten (wie jetzt)
- Audio funktioniert nativ problemlos

**Für Remote/Docker:**
- **Streamlit-UI nutzen** (kein Container-Audio nötig)
- CLI nur wenn PulseAudio durchgereicht werden kann

**Für Produktion:**
- Nur Export-Funktionalität nutzen (WAV-Files schreiben)
- Keine Live-Playback im Container

---

## Quick-Test Cheatsheet

```bash
# === Nativ (ohne Docker) ===
cd source/
python -m birdnet_play.tts
python ../test_audio_playback.py

# === Docker mit PulseAudio ===
docker run -it --rm \
  -e PULSE_SERVER=unix:/run/user/$(id -u)/pulse/native \
  -v /run/user/$(id -u)/pulse:/run/user/1000/pulse \
  -v $(pwd):/workspace -w /workspace \
  your-image bash

# Im Container:
cd /workspace/source
python ../test_audio_playback.py

# === Docker mit Streamlit (kein Audio nötig) ===
docker run -it --rm -p 8501:8501 \
  -v $(pwd):/workspace -w /workspace \
  your-image \
  streamlit run source/birdnet_play/streamlit_app.py -- /data/db.db

# Browser: http://localhost:8501
```

---

## Notizen

- **User-ID wichtig:** `/run/user/1000` anpassen an eigene UID
- **VSCode Port-Forwarding:** Funktioniert automatisch für Streamlit (8501)
- **Export funktioniert immer:** WAV-Files schreiben braucht kein Audio-Device
