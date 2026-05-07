Hier ist das gewünschte ausführliche Markdown-Dokument zur Distributionsmethodik, das du direkt in dein Projekt übernehmen kannst.

---

# Distributionsstrategie für birdnet-copter

Dieses Dokument beschreibt die geplanten Wege, um birdnet-copter an Nutzer auszuliefern.
Es behandelt die Erstellung von Docker-Images (CPU und GPU), die Einrichtung
einer CI/CD-Pipeline, die rechtlichen Rahmenbedingungen der enthaltenen
Komponenten sowie die alternative Installation via Poetry (Source-Distribution).

## Übersicht der Ansätze

birdnet-copter soll auf zwei Arten verteilt werden:

1. **Docker-Images (primär)** – für Nutzer aller Betriebssysteme, die eine
   sofort lauffähige Umgebung ohne manuelle Abhängigkeitsverwaltung wünschen.
2. **Poetry / Source (sekundär)** – für Entwickler, Tester und Power-User,
   die das Projekt aus dem Quellcode heraus betreiben oder modifizieren möchten.

Der Fokus liegt auf Docker, da es die grösste Nutzerfreundlichkeit bietet und
zugleich GPU-Unterstützung sauber kapselt.

---

## 1. Docker-basierte Distribution

### 1.1 Konzept: Mehrstufiges Dockerfile

Das Docker-Image wird in zwei Varianten angeboten:

| Tag | Basis-Image | GPU-Unterstützung |
|-----|-------------|-------------------|
| `birdnet-copter:gpu` | `nvidia/cuda:12.4-runtime-ubuntu22.04` | Ja (NVIDIA) |
| `birdnet-copter:cpu` | `python:3.11-slim` | Nein |

Beide Images durchlaufen einen zweistufigen Build:

- **Builder-Stage** – installiert Systempakete (Compiler, ffmpeg, …),
  Poetry und alle Python-Abhängigkeiten; lädt das BirdNET-Modell vor.
- **Runtime-Stage** – übernimmt nur die Laufzeitumgebung, das venv,
  das Modell und den Quellcode; enthält keine Build-Werkzeuge.

Durch die Trennung wird das finale Image klein und sicher.

### 1.2 Dockerfile für GPU (`Dockerfile.gpu`)

```dockerfile
# Stage 1: Builder
FROM nvidia/cuda:12.4-runtime-ubuntu22.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3.11-dev \
    ffmpeg libsndfile1 libportaudio2 \
    curl build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV POETRY_HOME=/opt/poetry
RUN curl -sSL https://install.python-poetry.org | python3.11 - && \
    ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

WORKDIR /app
COPY pyproject.toml poetry.lock ./

RUN python3.11 -m venv .venv && \
    . .venv/bin/activate && \
    poetry install --only main --no-interaction --no-ansi

# BirdNET-Modell vorab herunterladen
ENV BIRDNET_MODEL_PATH=/app/models
RUN . .venv/bin/activate && \
    python -c "import birdnet; birdnet.load('acoustic', '2.4', 'pb')"

# Stage 2: Runtime
FROM nvidia/cuda:12.4-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 ffmpeg libsndfile1 libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/models /app/models
COPY . /app

ENV BIRDNET_MODEL_PATH=/app/models

EXPOSE 8090

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "birdnet_copter"]
```

Das CPU-Image (`Dockerfile.cpu`) verwendet als Basis `python:3.11-slim`
und verzichtet auf CUDA. Die Build- und Runtime-Phasen sind analog,
nur ohne NVIDIA-spezifische Pakete.

### 1.3 Startup-Skript (`docker-entrypoint.sh`)

Das Skript stellt sicher, dass das BirdNET-Modell beim Containerstart
auf Aktualität geprüft wird. Ist eine neue Version verfügbar (z. B. nach
einem Update der BirdNET-Bibliothek), wird sie automatisch nachgeladen:

```bash
#!/bin/bash
set -e

echo "Checking BirdNET model..."
cd /app
. .venv/bin/activate
python -c "
import birdnet, logging
logging.basicConfig(level=logging.INFO)
model = birdnet.load('acoustic', '2.4', 'pb')
print('Model ready:', model)
"

echo "Starting birdnet-copter..."
exec "$@"
```

Solange das Modell aktuell ist, erfolgt kein Download; das Skript ist
daher auch in Offline-Umgebungen nutzbar (ein einmaliger Online-Start
genügt).

### 1.4 CI/CD-Pipeline (GitHub Actions)

Die folgende Pipeline baut bei jedem Push auf `main` automatisch beide
Images und pusht sie in die GitHub Container Registry. Dank des
`gha`-Caches werden unveränderte Abhängigkeiten nicht neu gebaut.

```yaml
name: Build and Publish Docker Images

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        flavor: [cpu, gpu]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          file: ./Dockerfile.${{ matrix.flavor }}
          push: true
          tags: ghcr.io/${{ github.repository }}/birdnet-copter:${{ matrix.flavor }}-latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### 1.5 Nutzung durch den Anwender

Nach dem Build kann der Anwender die Images direkt starten.

**CPU:**

```bash
docker run -d -p 8090:8090 \
  -v /pfad/zu/aufnahmen:/data \
  ghcr.io/mein-user/birdnet-copter:cpu-latest /data
```

**GPU:**

```bash
docker run -d -p 8090:8090 \
  --gpus all \
  -v /pfad/zu/aufnahmen:/data \
  ghcr.io/mein-user/birdnet-copter:gpu-latest /data
```

Der letzte Parameter (`/data`) wird als `root_path` an die Anwendung
übergeben und entspricht dem obersten Verzeichnis der Audio-Dateien.

---

## 2. Lizenzanalyse der enthaltenen Komponenten

Die Veröffentlichung eines Docker-Images erfordert die Beachtung der
Lizenzen aller eingebetteten Software.

### 2.1 NVIDIA CUDA (Basis-Image `nvidia/cuda`)

- **Lizenz:** NVIDIA EULA (End User License Agreement)
- **Bewertung:** Eine Weitergabe abgeleiteter Images ist erlaubt, solange
  das Gesamtimage unter der NVIDIA EULA bleibt. Dies muss in der
  Dokumentation klar kommuniziert werden (z. B. „This image is subject to
  the NVIDIA EULA …“).
- **Wichtig:** Das CUDA-Basisimage darf **nicht** für eine CPU-Variante
  verwendet werden, da die NVIDIA-Lizenz die Nutzung ohne NVIDIA-GPU
  untersagt. GPU- und CPU-Images müssen daher strikt getrennt auf
  unterschiedlichen Basisimages aufbauen.

### 2.2 FFmpeg

- **Lizenz:** LGPLv2.1+ (vorwiegend), optionale Teile GPL
- **Bewertung:** Die Installation über den Paketmanager (`apt install ffmpeg`)
  liefert eine LGPL-konforme Version, bei der die Bibliotheken dynamisch
  gelinkt sind. Dies ist für die Distribution im Docker-Image unproblematisch.
- **Zu vermeiden:** Eigenhändiges Kompilieren mit `--enable-gpl` oder
  `--enable-nonfree`, da dies strengere Lizenzpflichten (Offenlegung des
  eigenen Quellcodes) oder ein Verbot der Weitergabe nach sich ziehen kann.
- **Empfehlung:** Im Image und in den Notizen einen Hinweis auf FFmpeg
  und die LGPL aufnehmen.

### 2.3 BirdNET-Modell (Version 2.4)

- **Lizenz:** CC BY-NC-SA 4.0 (Creative Commons – Namensnennung,
  nicht kommerziell, Weitergabe unter gleichen Bedingungen)
- **Bewertung:** Das Hosting des Modells in einem öffentlichen Image ist
  grundsätzlich zulässig, solange die Nutzung überwiegend nicht-kommerziell
  ist (Forschung, Bildung, privates Monitoring). Eine klare Kennzeichnung
  und ein Hinweis auf die Lizenz im Projekt sind daher notwendig.
- **Achtung:** Eine kommerzielle Nutzung (z. B. als Teil eines kostenpflichtigen
  Dienstes) ist ohne separate Genehmigung des Cornell Lab of Ornithology
  nicht erlaubt. Das Image sollte diesen Hinweis enthalten oder die Nutzer
  entsprechend informieren.

### 2.4 edge-tts (Text-to-Speech)

- **Lizenz:** Unklar; das Paket (`edge-tts`) von rany2 hat keine gültige
  Open-Source-Lizenz; einige Forks verwenden absurde Eigenkonstrukte.
- **Bewertung:** Die Weitergabe in einem öffentlichen Image ist rechtlich
  riskant. Das Paket greift zudem auf die Microsoft-Cloud-TTS-API zu, was
  möglicherweise gegen Nutzungsbedingungen verstossen könnte.
- **Empfohlene Handhabung:** `edge-tts` **nicht** im Standard-Image
  ausliefern, sondern als optionale Komponente behandeln. Ein Installations-
  skript oder eine klare Anleitung ermöglichen es dem Nutzer, das Paket bei
  Bedarf selbst zu installieren. Das reduziert das rechtliche Risiko erheblich.

### 2.5 Weitere Python-Pakete

- **pydub** (MIT), **noisereduce** (MIT), **pedalboard** (GPLv3),
  **soundfile** (MIT), **numpy** (BSD), **tensorflow** (Apache 2.0) und
  die meisten anderen Abhängigkeiten sind unter klassischen Open-Source-
  Lizenzen verfügbar und unkritisch für die Distribution.
- **Hinweis:** Das Image sollte die entsprechenden Lizenztexte beinhalten
  (z. B. in einem `THIRD-PARTY-LICENSES`-Verzeichnis), wie es bei
  größeren Distributionen üblich ist.

### 2.6 Strategie für zwei Images

Aus der Lizenzanalyse ergeben sich zwei separate Images:

1. **`birdnet-copter:gpu`**

   - Basis: `nvidia/cuda` – unterliegt der NVIDIA EULA.
   - Enthält **kein** `edge-tts` (optionales Installationsskript).
   - Deutlicher Hinweis auf BirdNET CC-Lizenz.
2. **`birdnet-copter:cpu`**

   - Basis: `python:3.11-slim` – ohne NVIDIA-Bestandteile.
   - Muss die Lizenzanforderungen von FFmpeg und GPL-Komponenten
     erfüllen (Dokumentation, Beilegen der Lizenzen).
   - Ebenfalls ohne `edge-tts`.

Beide Images werden getrennt gebaut und versioniert.

---

## 3. Alternative: Poetry / Source-Installation

### 3.1 Funktionsweise

Anwender können birdnet-copter auch direkt aus dem Quellcode heraus
betreiben. Dafür wird [Poetry](https://python-poetry.org/) benötigt, das
die Abhängigkeiten aus `pyproject.toml` und dem `poetry.lock` installiert.

Voraussetzung:

- Python 3.11 (explizit in `pyproject.toml` gefordert)
- Systembibliotheken: `ffmpeg`, `libsndfile`, `portaudio` (unter Linux
  via `apt`, unter macOS via `brew`)
- Poetry (installierbar via `curl -sSL https://install.python-poetry.org | python3.11 -`)

Ablauf:

```bash
git clone https://github.com/…/birdnet-copter.git
cd birdnet-copter
poetry install
poetry run python -m birdnet_copter /pfad/zu/aufnahmen
```

Die erste Ausführung lädt das BirdNET-Modell automatisch herunter.

### 3.2 CPU vs. GPU bei Poetry

- **CPU:** TensorFlow wird automatisch in der CPU-Variante installiert
  (über das `poetry.lock`). Das funktioniert sofort nach `poetry install`.
- **GPU:** Der Nutzer muss eine CUDA-kompatible TensorFlow-Version
  manuell installieren, z. B.:

  ```bash
  poetry run pip install tensorflow[and-cuda]
  ```

  Das erfordert zusätzlich korrekt installierte NVIDIA-Treiber und CUDA-
  Bibliotheken auf dem Host (CUDA 12.x, cuDNN). Da das Setup fehleranfällig
  ist, wird dieser Weg nur erfahrenen Nutzern empfohlen.

### 3.3 Windows-Kompatibilität

Unter Windows sind zusätzliche Schritte nötig:

- Python 3.11 installieren und zum `PATH` hinzufügen.
- `ffmpeg` manuell herunterladen und in den `PATH` aufnehmen.
- Für `sounddevice`/`pydub` wird ein funktionierendes `portaudio`-Binary
  benötigt (meist durch das wheel von `sounddevice` abgedeckt).
- Die Pfade für Labels (`Path.home() / ".local/share/…"`) zeigen nach
  `C:\Users\<Name>\.local\share\…`, was funktioniert, aber nicht dem
  Windows-Standard entspricht. Eine Anpassung könnte später erfolgen.
- GPU-Nutzung unter Windows ist mit Poetry noch aufwändiger, da
  CUDA-Toolkit und passende `tensorflow`-Wheels manuell abgestimmt
  werden müssen.

**Daher:** Die Poetry-Methode wird **nicht** als primärer Weg für
Endanwender beworben, sondern als Entwickler- und Testwerkzeug.

---

## 4. Vergleich Docker vs. Poetry


| Kriterium            | Docker                              | Poetry                                    |
| ---------------------- | ------------------------------------- | ------------------------------------------- |
| Einrichtungsaufwand  | `docker run …`                     | Python + Poetry + Systemlibs installieren |
| Reproduzierbarkeit   | 100 % (identisches Image)           | 100 % (durch`poetry.lock`)                |
| GPU-Support          | einfach (`--gpus all`)              | manuelle CUDA-Installation                |
| Windows-Tauglichkeit | gut (Docker Desktop, ggf. ohne GPU) | mässig (manuelle Konfiguration nötig)   |
| Aktualisierung       | `docker pull`                       | `git pull && poetry install`              |
| Zielgruppe           | Endanwender, produktiver Betrieb    | Entwickler, CI, Tester                    |

---

## 5. Fazit und Empfehlung

- **Docker** ist der bevorzugte Distributionsweg für birdnet-copter.
  Zwei separate Images (CPU/GPU) mit vorinstalliertem Modell und einer
  automatischen Modellprüfung bieten den höchsten Komfort und minimieren
  Supportanfragen.
- **Poetry** bleibt als ergänzende Installationsmethode für Entwickler
  und für den Betrieb in Umgebungen, in denen Docker nicht zur Verfügung
  steht, erhalten und wird in der Dokumentation klar beschrieben.
- Die Lizenzsituation erfordert bei der Veröffentlichung der Docker-Images
  besondere Sorgfalt, insbesondere in Bezug auf NVIDIA (EULA), FFmpeg
  (LGPL) und das BirdNET-Modell (CC BY-NC-SA). `edge-tts` wird als
  optionales Plugin ausgelagert, um rechtliche Risiken zu vermeiden.

Diese Strategie stellt sicher, dass das Projekt einem breiten Nutzerkreis
zugänglich gemacht werden kann, ohne Kompromisse bei der Lizenzkonformität
einzugehen.

```

Dieses Dokument kannst du als `docs/distributionsstrategie.md` in dein
Projekt einfügen und bei Bedarf erweitern. Falls du später konkrete
Umsetzungen (z. B. das Dockerfile oder die CI-Pipeline) weiter
ausarbeiten möchtest, kann ich darauf aufbauen.
```
