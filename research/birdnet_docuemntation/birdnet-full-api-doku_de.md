# BirdNET API-Dokumentation

**Version:** 2.4  
**Stand:** Januar 2025

---

## Einführung

Diese Dokumentation richtet sich an Anwender, die bereits erste Erfahrungen mit BirdNET gemacht haben und nun die vollständige Funktionalität der Bibliothek verstehen und professionell nutzen möchten. Sie werden hier nicht nur die technischen Schnittstellen finden, sondern vor allem umfassende Erklärungen darüber, was die einzelnen Komponenten leisten, wie sie zusammenspielen und wie Sie sie für Ihre spezifischen Anforderungen optimal einsetzen können.

BirdNET ist eine Python-Bibliothek zur automatisierten Vogelerkennung aus Audioaufnahmen mittels Deep Learning. Die Bibliothek bietet zwei Hauptfunktionalitäten: die akustische Analyse von Audiodateien zur Identifikation von Vogelarten sowie geografische Modelle zur Vorhersage von Vogelvorkommen basierend auf Standort und Jahreszeit. Darüber hinaus ermöglicht BirdNET die Extraktion von Embeddings – hochdimensionalen Feature-Vektoren – die für weiterführende Analysen, Transfer Learning oder eigene Machine-Learning-Pipelines genutzt werden können.

### Was Sie in dieser Dokumentation finden

Die Dokumentation ist modular aufgebaut und führt Sie von den grundlegenden Konzepten über die einzelnen Modulbereiche bis hin zu vollständigen Anwendungsbeispielen. Sie erfahren dabei nicht nur, welche Parameter eine Methode akzeptiert, sondern vor allem, was diese Parameter inhaltlich bedeuten, wie sie die Verarbeitung beeinflussen und welche Auswirkungen unterschiedliche Einstellungen auf Ihre Ergebnisse haben.

**Übersicht der Hauptfunktionalitäten:**

- **Akustische Vogelarten-Erkennung**: Analysieren Sie Audioaufnahmen und erhalten Sie präzise Vorhersagen darüber, welche Vogelarten zu welchen Zeitpunkten in der Aufnahme zu hören sind. Das System arbeitet mit überlappenden Zeitfenstern und kann große Datenmengen effizient verarbeiten.

- **Embedding-Extraktion**: Extrahieren Sie numerische Feature-Repräsentationen aus Audioaufnahmen, die den "akustischen Fingerabdruck" eines Audiosegments darstellen. Diese Embeddings können für Clustering, Ähnlichkeitssuchen oder als Input für eigene Machine-Learning-Modelle verwendet werden.

- **Geografische Filterung**: Nutzen Sie Metadaten wie GPS-Koordinaten und Zeitinformationen, um die Wahrscheinlichkeit des Vorkommens bestimmter Vogelarten an einem Ort zu einem bestimmten Zeitpunkt zu ermitteln. Dies hilft, falsch-positive Erkennungen zu reduzieren und Ergebnisse zu kontextualisieren.

**Nebenfunktionalitäten, die Sie nicht selbst implementieren müssen:**

- **Parallele Verarbeitung**: BirdNET verarbeitet Audiodateien automatisch parallel über mehrere CPU-Kerne oder GPU-Geräte, um maximale Performance zu erreichen.

- **Batch-Processing**: Das System organisiert die Verarbeitung intern in optimierten Batches, sodass Sie sich nicht um die Details der Batch-Bildung kümmern müssen.

- **Speicherverwaltung**: Die Bibliothek nutzt Shared Memory für effiziente Datenübertragung zwischen Prozessen und verwaltet Ressourcen automatisch.

- **Fortschrittsanzeigen und Benchmarking**: Integrierte Mechanismen zur Überwachung des Verarbeitungsfortschritts und zur Leistungsmessung.

- **Flexible Audio-Verarbeitung**: Automatisches Resampling, Bandpass-Filterung und weitere Vorverarbeitungsschritte werden transparent im Hintergrund durchgeführt.

---

## Architektur-Überblick

BirdNET ist in mehrere Modulbereiche unterteilt, die jeweils spezifische Aufgaben erfüllen. Das Verständnis dieser Struktur hilft Ihnen, die richtigen Komponenten für Ihre Anwendungsfälle zu identifizieren.

**Core-Module** bilden die Grundlage der Bibliothek. Hier finden Sie abstrakte Basisklassen, das Backend-System zur Ausführung der neuronalen Netze auf verschiedenen Hardware-Plattformen sowie grundlegende Datenstrukturen für Ergebnisse und Sessions. Das Backend-System ist besonders wichtig, da es die Abstraktion zwischen Ihrer Anwendung und der darunter liegenden Ausführungsumgebung (CPU, GPU, verschiedene ML-Frameworks) bereitstellt.

**Acoustic-Module** enthalten alles, was mit der Verarbeitung von Audiodaten zusammenhängt. Dies umfasst die Modellklassen für verschiedene Versionen der akustischen Modelle, die komplette Inference-Pipeline für Prediction und Encoding sowie die Result-Objekte, die Ihre Analyseergebnisse kapseln. Die Inference-Pipeline ist eine hoch optimierte Verarbeitungskette, die Producer-Consumer-Muster verwendet, um Audio-Segmente effizient zu laden, zu verarbeiten und Ergebnisse zu aggregieren.

**Geo-Module** stellen die geografischen Modelle bereit. Diese Modelle sind deutlich schlanker als die akustischen, da sie keine Audio-Verarbeitung durchführen, sondern lediglich aus geografischen und zeitlichen Eingaben Artenwahrs cheinlichkeiten berechnen. Die Struktur ist analog zu den Acoustic-Modulen aufgebaut, mit eigenen Model-, Session- und Result-Klassen.

**Utils-Module** bieten Hilfsfunktionen für wiederkehrende Aufgaben wie Datei-Handling, Logging-Konfiguration und lokale Datenverwaltung. Hier werden beispielsweise auch die Pfade für heruntergeladene Modelle verwaltet und Funktionen zum Validieren von Eingabedaten bereitgestellt.

---

## Core-Module: Fundament und Backend-System

Die Core-Module bilden das technische Fundament von BirdNET und definieren die grundlegenden Abstraktionen, auf denen alle anderen Komponenten aufbauen. Für Sie als Anwender ist vor allem das Backend-System von Bedeutung, da es bestimmt, wie und wo die Modellberechnungen ausgeführt werden.

### Das Backend-System

Das Backend-System in BirdNET trennt die Modelllogik von der konkreten Ausführungsumgebung. Dies bedeutet, dass Sie dasselbe Modell auf verschiedenen Hardware-Konfigurationen ausführen können, ohne Ihren Anwendungscode ändern zu müssen. Die Bibliothek unterstützt mehrere Backend-Typen, die jeweils unterschiedliche Trade-offs zwischen Performance, Kompatibilität und Flexibilität bieten.

**TensorFlow Lite (TFLite) Backend:**

Das TFLite-Backend führt Modelle als TensorFlow Lite-Dateien aus und ist primär für CPU-Ausführung konzipiert. TFLite-Modelle sind kompakt und für Edge-Geräte optimiert. Wenn Sie BirdNET auf einem Laptop, Desktop-PC oder Server ohne dedizierte GPU verwenden möchten, ist dies oft die einfachste Option. Das TFLite-Backend unterstützt verschiedene Modell-Präzisionen (INT8, FP16, FP32), wobei INT8-Modelle besonders klein und schnell sind, aber möglicherweise minimale Genauigkeitseinbußen aufweisen. FP32-Modelle bieten die höchste Genauigkeit, benötigen aber mehr Speicher und Rechenzeit.

Ein wichtiger Hinweis: Die Zukunft des TFLite-Backends ist unsicher, da Google die Entwicklung teilweise auf LiteRT verlagert hat. Für neue Projekte sollten Sie dies berücksichtigen.

**Protobuf (PB) Backend:**

Das Protobuf-Backend ist für professionelle Anwendungen mit GPU-Unterstützung konzipiert. Es verwendet TensorFlow-SavedModel-Formate, die volle GPU-Beschleunigung ermöglichen. Wenn Sie große Datenmengen verarbeiten oder Echtzeit-Performance benötigen, ist dies die empfohlene Wahl. Das PB-Backend erlaubt es, Berechnungen auf spezifischen GPUs auszuführen und unterstützt verschiedene Präzisionsstufen. Die Modelle sind größer als TFLite-Varianten, bieten aber maximale Flexibilität und Performance.

**Backend-Auswahl in der Praxis:**

Die Wahl des Backends erfolgt beim Laden eines Modells über den `backend_type`-Parameter. Für die meisten Anwendungsfälle werden Sie vordefinierte Backend-Klassen verwenden:

```python
from birdnet.acoustic.models.v2_4.backends.pb import AcousticPBBackendV2_4
from birdnet.acoustic.models.v2_4.backends.tf import AcousticTFBackendV2_4

# Für GPU mit Protobuf:
backend_type = AcousticPBBackendV2_4
backend_kwargs = {}

# Für CPU mit TFLite FP32:
backend_type = AcousticTFBackendV2_4
backend_kwargs = {"inference_library": "tflite"}  # oder "litert"
```

Die `backend_kwargs` ermöglichen zusätzliche Backend-spezifische Konfigurationen. Beim TFLite-Backend können Sie beispielsweise zwischen der originalen TensorFlow-Implementierung (`"tflite"`) und der neueren LiteRT-Variante (`"litert"`) wählen.

### Model-Präzision und Performance

Die Modell-Präzision bestimmt, mit welcher numerischen Genauigkeit die Berechnungen durchgeführt werden. BirdNET unterstützt drei Präzisionsstufen:

**FP32 (Float32)**: Dies ist die Standard-Gleitkomma-Präzision mit 32 Bit. Sie bietet höchste Genauigkeit und ist die Basis, auf der die Modelle ursprünglich trainiert wurden. Verwenden Sie FP32, wenn Genauigkeit wichtiger ist als Speicher- oder Geschwindigkeitsoptimierung.

**FP16 (Float16)**: Halbpräzisions-Gleitkommazahlen nutzen nur 16 Bit. Dies halbiert den Speicherbedarf und kann auf modernen GPUs zu deutlichen Geschwindigkeitsgewinnen führen. Die Genauigkeitseinbußen sind in der Regel minimal und für die meisten Anwendungsfälle vernachlässigbar.

**INT8**: Integer-Quantisierung mit 8 Bit pro Zahl reduziert den Speicherbedarf auf ein Viertel von FP32. Dies ist die kompakteste Variante und ermöglicht sehr schnelle Inferenz auf CPUs. Die Genauigkeitsverluste sind etwas größer als bei FP16, aber für Vogelartenerkennung oft noch akzeptabel.

Die Präzision wird beim Model-Download festgelegt. Das Protobuf-Backend unterstützt derzeit nur FP32, während TFLite-Modelle in allen drei Varianten verfügbar sind.

### Basis-Klassen für Modelle und Results

Im Core-Modul finden sich abstrakte Basisklassen, die das Interface für alle Modelle und Ergebnisse definieren. Diese Abstraktion ermöglicht es, verschiedene Modellversionen und -typen einheitlich zu verwenden.

**ModelBase:**

Jedes Modell in BirdNET erbt von `ModelBase` und implementiert grundlegende Eigenschaften wie den Modellpfad, die Liste der erkennbaren Arten (`species_list`) und einen Flag, ob es sich um ein benutzerdefiniertes Modell handelt. Wichtige Methoden sind `load()` für das Laden vortrainierter Modelle und `load_custom()` für das Laden eigener, trainierter Modelle.

**ResultBase:**

Alle Ergebnisobjekte erben von `ResultBase` und können gespeichert und geladen werden. Dies ermöglicht es Ihnen, Analyseergebnisse persistent zu machen und später weiterzuverarbeiten, ohne die Analyse erneut durchführen zu müssen. Ergebnisse werden als komprimierte NumPy-Archive (`.npz`) gespeichert, die alle relevanten Daten und Metadaten enthalten.

**SessionBase:**

Sessions sind Context-Manager, die eine wiederverwendbare Inference-Umgebung bereitstellen. Wenn Sie mehrere Analysen mit denselben Parametern durchführen möchten, ist eine Session effizienter, da das Modell nur einmal geladen wird und Ressourcen wiederverwendet werden können.

---

## Acoustic-Modul: Audio-Analyse und Feature-Extraktion

Das Acoustic-Modul ist das Herzstück von BirdNET für die Arbeit mit Audiodaten. Es umfasst die Modellklassen, die Inference-Pipeline zur effizienten Verarbeitung sowie die Result-Objekte, die Ihre Analyseergebnisse strukturiert zurückgeben.

### Das AcousticModelV2_4

Die Klasse `AcousticModelV2_4` ist Ihr Haupteinstiegspunkt für alle akustischen Analysen. Ein Objekt dieser Klasse repräsentiert ein geladenes BirdNET-Modell der Version 2.4, das entweder Vogelarten vorhersagen oder Embeddings extrahieren kann.

**Laden eines vortrainierten Modells:**

BirdNET wird mit vortrainierten Modellen ausgeliefert, die automatisch heruntergeladen werden, wenn sie noch nicht lokal verfügbar sind. Der Download-Prozess ist in der Regel transparent und erfolgt beim ersten Aufruf von `load()`. Sie müssen lediglich die gewünschte Sprache für die Artennamen angeben:

```python
from birdnet.acoustic.models.v2_4.model import AcousticModelV2_4
from birdnet.acoustic.models.v2_4.backends.pb import AcousticPBBackendV2_4

model = AcousticModelV2_4.load(
    lang="de",  # Deutsche Artennamen
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={}
)
```

Das `lang`-Argument bestimmt nicht nur die Sprache der Artennamen in den Ergebnissen, sondern kann auch die Liste der erkennbaren Arten beeinflussen, da verschiedene Sprach-Versionen auf unterschiedliche geografische Regionen trainiert sein können. Verfügbare Sprachen sind unter anderem: Deutsch (`"de"`), Englisch UK (`"en_uk"`), Englisch US (`"en_us"`), Spanisch (`"es"`), Französisch (`"fr"`), Japanisch (`"ja"`), und viele weitere.

Der `backend_type` und `backend_kwargs` wurden bereits im Abschnitt über Backends erläutert. Für CPU-Nutzung würden Sie beispielsweise schreiben:

```python
from birdnet.acoustic.models.v2_4.backends.tf import AcousticTFBackendV2_4

model = AcousticModelV2_4.load(
    lang="de",
    backend_type=AcousticTFBackendV2_4,
    backend_kwargs={"inference_library": "tflite"}
)
```

**Laden eines benutzerdefinierten Modells:**

Falls Sie ein eigenes Modell trainiert haben oder ein spezialisiertes Modell verwenden möchten, nutzen Sie `load_custom()`. Hierbei müssen Sie explizit den Pfad zum Modell und zur Artenliste angeben:

```python
from pathlib import Path

model = AcousticModelV2_4.load_custom(
    model_path=Path("/pfad/zum/modell"),
    species_list=Path("/pfad/zur/artenliste.txt"),
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={},
    check_validity=True  # Prüft Konsistenz zwischen Modell und Artenliste
)
```

Der Parameter `check_validity` ist wichtig: Wenn er auf `True` gesetzt ist, überprüft BirdNET, ob die Anzahl der Ausgaben des Modells mit der Anzahl der Arten in der Liste übereinstimmt. Dies verhindert Laufzeitfehler durch inkonsistente Daten.

**Modell-Eigenschaften:**

Ein geladenes Modell bietet mehrere nützliche Klassenmethoden, um technische Details abzufragen:

- `get_segment_size_s()`: Gibt die Segment-Länge in Sekunden zurück (für v2.4: 3.0 Sekunden). Diese Information ist wichtig, um zu verstehen, mit welcher zeitlichen Auflösung das Modell arbeitet.
  
- `get_sample_rate()`: Die Abtastrate, für die das Modell trainiert wurde (48 kHz für v2.4). Audiodateien werden intern auf diese Rate resampled.

- `get_sig_fmin()` und `get_sig_fmax()`: Der Frequenzbereich, den das Modell verarbeitet (0 Hz bis 15 kHz). Frequenzen außerhalb dieses Bereichs werden während der Vorverarbeitung herausgefiltert.

- `get_embeddings_dim()`: Die Dimensionalität der Embeddings (1024 für v2.4). Dies ist relevant, wenn Sie mit den extrahierten Feature-Vektoren weiterarbeiten möchten.

Diese Eigenschaften sind als Klassenmethoden implementiert, sodass Sie sie auch ohne geladenes Modell-Objekt abfragen können, falls Sie nur Metadaten benötigen.

### Prediction: Vogelarten erkennen

Die `predict()`-Methode ist die zentrale Funktion zur Vogelartenerkennung. Sie analysiert eine oder mehrere Audiodateien und gibt strukturierte Ergebnisse zurück, die angeben, welche Vogelarten zu welchen Zeitpunkten mit welcher Konfidenz erkannt wurden.

**Grundlegende Verwendung:**

```python
from pathlib import Path

result = model.predict(
    Path("/pfad/zur/audiodatei.wav"),
    top_k=5,
    overlap_duration_s=1.5,
    device="CPU"
)
```

Dieser einfache Aufruf analysiert eine einzelne Audiodatei und gibt die Top-5-Vorhersagen für jedes Zeitfenster zurück. Die Überlappung von 1.5 Sekunden sorgt dafür, dass aufeinanderfolgende 3-Sekunden-Segmente jeweils um 1.5 Sekunden versetzt sind, was zu einer höheren zeitlichen Auflösung führt und Edge-Effekte an Segmentgrenzen reduziert.

**Mehrere Dateien gleichzeitig verarbeiten:**

Ein großer Vorteil von BirdNET ist die Fähigkeit, große Datenmengen effizient zu verarbeiten. Sie können einfach eine Liste von Pfaden oder ein Verzeichnis übergeben:

```python
from pathlib import Path

input_dir = Path("/pfad/zu/audio/ordner")
audio_files = list(input_dir.glob("*.wav"))

result = model.predict(
    audio_files,
    top_k=5,
    overlap_duration_s=1.5,
    n_producers=2,
    n_workers=4,
    batch_size=16,
    device="CPU"
)
```

Hier werden die Dateien intern parallel verarbeitet. Die Parameter `n_producers`, `n_workers` und `batch_size` steuern die Parallelisierung, worauf wir gleich genauer eingehen.

**Wichtige Parameter im Detail:**

**`top_k`:** Bestimmt, wie viele der wahrscheinlichsten Vogelarten pro Zeitfenster zurückgegeben werden. Wenn Sie `top_k=5` setzen, erhalten Sie für jedes 3-Sekunden-Segment die fünf Arten mit den höchsten Konfidenzwerten. `top_k=None` gibt alle Arten zurück, was zu sehr großen Ergebnismengen führen kann. Für die meisten Anwendungsfälle sind Werte zwischen 3 und 10 sinnvoll.

**`overlap_duration_s`:** Die Überlappung zwischen aufeinanderfolgenden Segmenten in Sekunden. Bei einer Segment-Länge von 3.0 Sekunden führt `overlap_duration_s=0` zu aneinandergereihten Segmenten ohne Überlappung (0-3s, 3-6s, 6-9s, ...). Mit `overlap_duration_s=1.5` überlappen sich die Segmente zur Hälfte (0-3s, 1.5-4.5s, 3-6s, ...), was die zeitliche Auflösung verdoppelt. Höhere Überlappungen erhöhen die Rechenzeit proportional, verbessern aber die Erfassung von Lauten, die an Segmentgrenzen liegen.

**`speed`:** Ein Beschleunigungsfaktor für die Audio-Verarbeitung. `speed=1.0` bedeutet Echtzeit-Geschwindigkeit. `speed=2.0` verarbeitet die Audio-Daten mit doppelter Geschwindigkeit, was die Anzahl der analysierten Segmente halbiert und die Rechenzeit reduziert, aber möglicherweise Details verliert. Werte unter 1.0 sind ebenfalls möglich und führen zu detaillierteren Analysen mit mehr Überlappung.

**`apply_sigmoid` und `sigmoid_sensitivity`:** Das Modell gibt intern Logits (unnormalisierte Scores) aus. Wenn `apply_sigmoid=True` ist, werden diese Scores durch eine Sigmoid-Funktion in Wahrscheinlichkeiten zwischen 0 und 1 transformiert. Der Parameter `sigmoid_sensitivity` (Standard: 1.0) verschiebt die Sigmoid-Kurve und beeinflusst damit die Empfindlichkeit der Erkennung. Höhere Werte führen zu konservativeren Vorhersagen (weniger falsch-positive, aber auch mehr verpasste Erkennungen), niedrigere Werte zu liberaleren Vorhersagen.

**`default_confidence_threshold`:** Vorhersagen mit einer Konfidenz unterhalb dieses Schwellwerts werden ausgefiltert. Der Standardwert von 0.1 ist relativ niedrig und schließt nur sehr unsichere Vorhersagen aus. Wenn Sie präzisere Ergebnisse möchten, können Sie diesen Wert erhöhen (z.B. auf 0.3 oder 0.5), allerdings auf Kosten der Sensitivität.

**`custom_confidence_thresholds`:** Falls Sie artspezifische Schwellwerte benötigen, können Sie ein Dictionary übergeben, das Artennamen auf Schwellwerte mappt. Dies ist nützlich, wenn bestimmte Arten schwerer zu erkennen sind oder wenn Sie für häufige Arten strengere Kriterien anlegen möchten.

**`custom_species_list`:** Beschränkt die Ausgabe auf eine Teilmenge der vom Modell erkennbaren Arten. Sie können entweder eine Liste von Artennamen, einen Dateipfad zu einer Artenliste oder ein `Collection`-Objekt übergeben. Dies ist nützlich, um Ergebnisse auf lokal vorkommende Arten zu filtern.

**`bandpass_fmin` und `bandpass_fmax`:** Diese Parameter definieren einen Bandpass-Filter, der vor der Analyse angewendet wird. Frequenzen außerhalb des Bereichs [fmin, fmax] werden herausgefiltert. Der Standardbereich (0 Hz bis 15 kHz) entspricht dem Trainingsbereich des Modells. Wenn Sie wissen, dass Ihre Zielarten hauptsächlich in einem bestimmten Frequenzbereich singen, können Sie den Filter enger setzen, um Rauschen zu reduzieren.

**`half_precision`:** Wenn `True`, werden Berechnungen intern mit halber Präzision (FP16) durchgeführt. Dies spart Speicher und kann auf GPUs die Geschwindigkeit erhöhen, führt aber zu minimal geringerer numerischer Genauigkeit. Für CPU-Ausführung hat dieser Parameter meist keinen Effekt.

**`max_audio_duration_min`:** Begrenzt die maximale Länge einer einzelnen Audiodatei in Minuten. Dies ist ein Schutzmechanismus gegen versehentliches Laden extrem langer Dateien, die den Speicher überlasten könnten. Der Standardwert erlaubt Dateien bis zu mehreren Stunden Länge.

**Parallelisierung und Performance-Tuning:**

Die Parameter `n_producers`, `n_workers` und `batch_size` steuern die interne Parallelverarbeitung und sind entscheidend für optimale Performance.

**`n_producers`:** Anzahl der Producer-Prozesse, die Audio-Dateien laden und in Segmente zerlegen. Producer lesen Dateien von der Festplatte, führen Resampling und Filterung durch und legen die Segmente in einen Puffer für die Worker. Wenn Sie viele kleine Dateien haben, können mehrere Producer den I/O-Durchsatz erhöhen. Für wenige große Dateien ist meist ein Producer ausreichend.

**`n_workers`:** Anzahl der Worker-Prozesse, die die eigentliche Modell-Inferenz durchführen. Jeder Worker lädt eine eigene Kopie des Modells und verarbeitet Batches von Audio-Segmenten. Die optimale Anzahl hängt von Ihrer Hardware ab: Für CPU-Ausführung ist die Anzahl der physischen CPU-Kerne ein guter Startwert. Für GPU-Ausführung ist oft ein Worker pro GPU optimal, es sei denn, Sie haben eine sehr leistungsstarke GPU, die mehrere Worker effizient bedienen kann.

**`batch_size`:** Anzahl der Audio-Segmente, die ein Worker gleichzeitig verarbeitet. Größere Batches erhöhen den Durchsatz, da moderne Hardware (besonders GPUs) parallele Berechnungen effizienter durchführen kann. Allerdings steigt auch der Speicherbedarf. Für CPU sind Werte zwischen 4 und 32 üblich, für GPU zwischen 32 und 256, abhängig vom verfügbaren Speicher.

**`prefetch_ratio`:** Bestimmt, wie viele Batches im Voraus geladen werden. Ein Wert von 2 bedeutet, dass immer zwei Batches pro Worker im Puffer bereitstehen, während der Worker den aktuellen Batch verarbeitet. Dies verhindert, dass Worker auf Daten warten müssen (I/O-Blocking), erhöht aber den Speicherbedarf.

**`device`:** Spezifiziert das Ausführungsgerät. Für CPU-Ausführung verwenden Sie `"CPU"`. Für GPU-Ausführung können Sie `"GPU:0"` für die erste GPU, `"GPU:1"` für die zweite usw. angeben. Sie können auch eine Liste von Geräten übergeben, z.B. `["GPU:0", "GPU:1"]`, um Worker auf mehrere GPUs zu verteilen.

**Fortschrittsanzeige und Monitoring:**

Der Parameter `show_stats` steuert, welche Informationen während der Verarbeitung ausgegeben werden:

- `None` (Standard): Keine Ausgabe, stille Verarbeitung.
- `"minimal"`: Minimale Informationen wie Start- und Endzeitpunkt.
- `"progress"`: Detaillierte Fortschrittsanzeige mit geschätzter Restzeit und Verarbeitungsgeschwindigkeit.
- `"benchmark"`: Zusätzlich zu Progress-Informationen werden detaillierte Performance-Metriken erfasst und am Ende ausgegeben.

Sie können auch einen eigenen `progress_callback` übergeben, eine Funktion, die periodisch mit einem `AcousticProgressStats`-Objekt aufgerufen wird. Dieses Objekt enthält Informationen wie die Anzahl verarbeiteter Segmente, verstrichene Zeit und geschätzte Restzeit. Dies ist nützlich, um den Fortschritt in eine GUI oder ein Logging-System zu integrieren.

### Sessions für wiederholte Analyse

Wenn Sie mehrere Analysen mit denselben Parametern durchführen möchten (z.B. eine Liste von Dateien nacheinander verarbeiten, aber für jede detaillierte Zwischenergebnisse benötigen), ist die Verwendung einer Session effizienter:

```python
with model.predict_session(
    top_k=5,
    overlap_duration_s=1.5,
    n_producers=2,
    n_workers=4,
    batch_size=16,
    device="CPU"
) as session:
    result1 = session.run(Path("/pfad/zu/datei1.wav"))
    result2 = session.run(Path("/pfad/zu/datei2.wav"))
    # ... weitere Dateien
```

Die Session lädt das Modell und die Ressourcen einmal beim Betreten des Context-Managers (`with`-Block) und gibt sie beim Verlassen wieder frei. Während der Session können Sie `session.run()` beliebig oft aufrufen. Dies ist schneller als wiederholte `model.predict()`-Aufrufe, da Initialisierungskosten vermieden werden.

### Encoding: Feature-Vektoren extrahieren

Die `encode()`-Methode extrahiert Embeddings anstelle von Artenvorhersagen. Embeddings sind hochdimensionale numerische Vektoren (1024 Dimensionen für v2.4), die die akustischen Eigenschaften eines Audio-Segments in komprimierter Form repräsentieren.

**Warum Embeddings verwenden?**

Embeddings sind nützlich, wenn Sie:

- **Ähnlichkeitssuchen** durchführen möchten: Finden Sie Audio-Segmente, die akustisch ähnlich sind, ohne auf Artenklassifikation angewiesen zu sein.
- **Clustering** betreiben: Gruppieren Sie Aufnahmen automatisch nach akustischen Merkmalen.
- **Transfer Learning** anwenden: Nutzen Sie die vortrainierten Features als Input für eigene Machine-Learning-Modelle, z.B. zur Erkennung von Nicht-Vogel-Geräuschen oder seltenen Arten.
- **Dimensionsreduktion** durchführen: Projizieren Sie die Embeddings auf 2D/3D für Visualisierung und explorative Datenanalyse.

**Grundlegende Verwendung:**

```python
embedding_result = model.encode(
    Path("/pfad/zur/audiodatei.wav"),
    overlap_duration_s=1.5,
    device="CPU"
)

# Zugriff auf die Embeddings
embeddings = embedding_result.embeddings  # NumPy-Array mit Shape (n_files, n_segments, 1024)
```

Die Parameter sind weitgehend identisch mit `predict()`, mit einigen Ausnahmen: Es gibt keine Prediction-spezifischen Parameter wie `top_k`, `apply_sigmoid` oder `confidence_threshold`, da keine Klassifikation stattfindet.

**Arbeiten mit extrahierten Embeddings:**

Das zurückgegebene `AcousticEncodingResultBase`-Objekt kapselt die Embeddings und Metadaten. Die Embeddings selbst sind als 3D-NumPy-Array zugänglich:

- **Dimension 0**: Index der Eingabedatei (wenn mehrere Dateien verarbeitet wurden)
- **Dimension 1**: Segment-Index innerhalb der Datei
- **Dimension 2**: Embedding-Dimension (1024)

Wenn Sie nur die ersten 10 Sekunden einer 60-Sekunden-Aufnahme mit 1.5s Überlappung analysiert haben, erhalten Sie etwa 13 Segmente (bei 3s Segment-Länge und 1.5s Schritt). Das Embeddings-Array hätte dann die Form `(1, 13, 1024)` für eine einzelne Datei.

Das Result-Objekt bietet auch Masken, um gültige von ungültigen Segmenten zu unterscheiden (falls Dateien kürzer als ein Segment waren oder Verarbeitungsfehler auftraten):

```python
valid_embeddings = embedding_result.embeddings[~embedding_result.embeddings_masked]
```

**Encoding-Sessions:**

Analog zu Prediction-Sessions gibt es `encode_session()`:

```python
with model.encode_session(
    overlap_duration_s=1.5,
    n_workers=4,
    batch_size=16,
    device="CPU"
) as session:
    emb1 = session.run(Path("/pfad/zu/datei1.wav"))
    emb2 = session.run(Path("/pfad/zu/datei2.wav"))
```

**Hinweis zur Backend-Unterstützung:**

Nicht alle Backends unterstützen Encoding. Das Protobuf-Backend für v2.4 bietet diese Funktionalität, aber einige TFLite-Modelle könnten nur Prediction-Outputs haben. Sie können die Unterstützung über `backend_type.supports_encoding()` abfragen. *(Hinweis: Bitte prüfen Sie die Backend-Dokumentation für genaue Details zur Encoding-Unterstützung.)*

### Arbeiten mit Ergebnissen

Die Result-Objekte sind nicht nur Datencontainer, sondern bieten umfangreiche Methoden zur Weiterverarbeitung und Persistierung.

**AcousticFilePredictionResult:**

Dieses Objekt wird zurückgegeben, wenn Sie Audiodateien mit `predict()` analysieren. Es enthält alle Vorhersagen strukturiert nach Datei, Zeitfenster und Art.

```python
result = model.predict(audio_files, top_k=5)

# Grundlegende Eigenschaften
print(f"Analysierte Dateien: {result.n_inputs}")
print(f"Erkannte Arten: {result.n_species}")
print(f"Gesamtzahl Vorhersagen: {len(result.species_ids)}")

# Zugriff auf rohe Daten
predictions = result.to_structured_array()
# Gibt ein strukturiertes NumPy-Array mit Feldern:
# - input (Dateipfad)
# - start_time (Sekunden)
# - end_time (Sekunden)
# - species_name
# - confidence
```

**Export und Persistierung:**

Sie können Ergebnisse in verschiedenen Formaten exportieren:

```python
# Als CSV für Excel/Pandas
result.to_csv("ergebnisse.csv")

# Als Parquet für effiziente Speicherung und Analyse
result.to_parquet("ergebnisse.parquet")

# Als NPZ für kompakte Speicherung aller NumPy-Arrays
result.save("ergebnisse.npz", compress=True)

# Später wieder laden
from birdnet.acoustic.inference.core.prediction.prediction_result import AcousticFilePredictionResult
loaded_result = AcousticFilePredictionResult.load("ergebnisse.npz")
```

Das NPZ-Format ist besonders nützlich, wenn Sie Ergebnisse für spätere Python-Verarbeitung speichern möchten, da es alle Metadaten und Arrays verlustfrei erhält. CSV und Parquet sind hingegen besser für den Austausch mit anderen Tools oder für Datenanalyse in Pandas geeignet.

**Filterung und Aggregation:**

Die Result-Objekte bieten Methoden zur Filterung und Aggregation, die allerdings über die privaten Implementierungsdetails hinausgehen. Sie können die strukturierten Arrays oder Parquet-Exporte mit Pandas oder anderen Tools weiterverarbeiten:

```python
import pandas as pd

# Export als Parquet und Laden in Pandas
result.to_parquet("temp.parquet")
df = pd.read_parquet("temp.parquet")

# Filterung auf spezifische Art
amsel_detections = df[df["species_name"] == "Amsel_Turdus merula"]

# Aggregation: Wie oft wurde jede Art erkannt?
species_counts = df.groupby("species_name").size().sort_values(ascending=False)
```

**Umgang mit unverarbeiteten Dateien:**

Falls einige Audiodateien nicht verarbeitet werden konnten (z.B. wegen defekter Dateien oder nicht unterstützter Formate), können Sie diese identifizieren:

```python
if hasattr(result, 'get_unprocessed_files'):
    unprocessed = result.get_unprocessed_files()
    if unprocessed:
        print(f"Folgende Dateien konnten nicht verarbeitet werden: {unprocessed}")
```

Dies ist wichtig für robuste Produktiv-Pipelines, um sicherzustellen, dass keine Daten verloren gehen.

### Audio-Arrays direkt verarbeiten

Neben Audiodateien können Sie auch NumPy-Arrays direkt verarbeiten. Dies ist nützlich, wenn Sie Audio-Daten bereits im Speicher haben oder eigene Vorverarbeitung durchführen:

```python
import numpy as np

# Audio-Array mit 48 kHz Abtastrate
audio_data = np.random.randn(48000 * 30)  # 30 Sekunden
sample_rate = 48000

result = model.predict(
    [(audio_data, sample_rate)],  # Liste von Tupeln (array, sr)
    top_k=5
)
```

Beachten Sie, dass die Abtastrate angegeben werden muss, auch wenn sie der Modell-Abtastrate entspricht, da BirdNET sonst nicht weiß, wie die Zeitachse zu interpretieren ist. Das Array sollte 1-dimensional sein (mono) und die Werte im Bereich [-1, 1] liegen (Standard-Float-Normalisierung für Audio).

Für Sessions verwenden Sie die entsprechende Methode:

```python
with model.predict_session(...) as session:
    result = session.run_arrays([(audio_data, sample_rate)])
```

Die Rückgabewerte sind dann `AcousticDataPredictionResult` bzw. `AcousticDataEncodingResult`, die ähnlich strukturiert sind, aber keine Dateipfade, sondern Array-Indizes verwenden.

---

## Geo-Modul: Geografische Filterung

Das Geo-Modul ergänzt die akustische Analyse durch geografische und zeitliche Kontextualisierung. Geografische Modelle sagen vorher, welche Vogelarten an einem bestimmten Ort zu einer bestimmten Jahreszeit wahrscheinlich vorkommen.

### GeoModelV2_4

Die `GeoModelV2_4`-Klasse funktioniert konzeptionell ähnlich wie `AcousticModelV2_4`, ist aber deutlich schlanker, da keine Audio-Verarbeitung erforderlich ist.

**Laden eines geografischen Modells:**

```python
from birdnet.geo.models.v2_4.model import GeoModelV2_4
from birdnet.geo.models.v2_4.backends.pb import GeoPBBackendV2_4

geo_model = GeoModelV2_4.load(
    lang="de",
    backend_type=GeoPBBackendV2_4,
    backend_kwargs={}
)
```

Der Ladevorgang ist analog zum akustischen Modell. Die Sprache bestimmt die Artennamen, und das Backend definiert die Ausführungsumgebung.

**Vorhersage für einen Standort:**

```python
prediction = geo_model.predict(
    latitude=51.5074,   # Breitengrad (London)
    longitude=-0.1278,  # Längengrad
    week=20,            # Kalenderwoche (Mai)
    min_confidence=0.03,
    device="CPU"
)
```

**Interpretation der Parameter:**

**`latitude` und `longitude`:** Die GPS-Koordinaten des Standorts in Dezimalgrad. Breitengrade reichen von -90 (Südpol) bis +90 (Nordpol), Längengrade von -180 bis +180 (mit 0 als Greenwich-Meridian). Das Modell ist global trainiert, funktioniert aber in Regionen mit umfangreichen Trainingsdaten (Nordamerika, Europa) am besten.

**`week`:** Die Kalenderwoche (1 bis 48), die die Jahreszeit repräsentiert. Woche 1 ist Anfang Januar, Woche 48 Ende November. Dieser Parameter ermöglicht es dem Modell, saisonale Vogelmigration zu berücksichtigen. Sie können auch `week=None` übergeben, was zu einer jahreszeitunabhängigen Vorhersage führt (oder das Modell verwendet einen Standardwert – bitte prüfen).

**`min_confidence`:** Arten mit einer Wahrscheinlichkeit unterhalb dieses Schwellwerts werden aus den Ergebnissen ausgefiltert. Der Standardwert von 0.03 (3%) ist relativ niedrig und schließt nur sehr unwahrscheinliche Arten aus.

**`device`:** Wie bei akustischen Modellen können Sie `"CPU"` oder `"GPU:0"` usw. angeben.

**Ergebnis-Objekt:**

Das zurückgegebene `GeoPredictionResult`-Objekt enthält für jede Art die Wahrscheinlichkeit ihres Vorkommens:

```python
# Zugriff auf Wahrscheinlichkeiten
species_names = prediction.species_list  # NumPy-Array mit Artennamen
probabilities = prediction.species_probs  # NumPy-Array mit Wahrscheinlichkeiten (0-1)

# Gefilterte Arten (über min_confidence)
valid_mask = ~prediction.species_masked
likely_species = species_names[valid_mask]
likely_probs = probabilities[valid_mask]

# Sortierung nach Wahrscheinlichkeit
sorted_indices = np.argsort(likely_probs)[::-1]  # Absteigend
top_species = likely_species[sorted_indices][:10]
top_probs = likely_probs[sorted_indices][:10]

for species, prob in zip(top_species, top_probs):
    print(f"{species}: {prob:.3f}")
```

**Verwendung in Kombination mit akustischer Analyse:**

Ein typischer Workflow kombiniert beide Modelle, um falsch-positive akustische Erkennungen zu filtern:

```python
# 1. Geografische Vorhersage
geo_pred = geo_model.predict(
    latitude=51.5074,
    longitude=-0.1278,
    week=20,
    min_confidence=0.1  # Nur Arten mit >10% Wahrscheinlichkeit
)

likely_species_set = set(geo_pred.species_list[~geo_pred.species_masked])

# 2. Akustische Analyse mit geografischer Filterung
acoustic_result = acoustic_model.predict(
    audio_files,
    custom_species_list=likely_species_set,
    top_k=5
)
```

Dieser Ansatz reduziert falsch-positive Erkennungen erheblich, da nur Arten berücksichtigt werden, die an diesem Ort und zu dieser Zeit plausibel vorkommen.

**Sessions für wiederholte Vorhersagen:**

Wenn Sie Vorhersagen für mehrere Standorte mit denselben Parametern machen möchten:

```python
with geo_model.predict_session(
    min_confidence=0.03,
    device="CPU"
) as session:
    pred1 = session.run(latitude=51.5074, longitude=-0.1278, week=20)
    pred2 = session.run(latitude=48.8566, longitude=2.3522, week=20)  # Paris
    # ... weitere Standorte
```

**Eigene geografische Modelle:**

Falls Sie ein spezialisiertes geografisches Modell für eine spezifische Region trainiert haben:

```python
geo_model = GeoModelV2_4.load_custom(
    model_path=Path("/pfad/zum/geo/modell"),
    species_list=Path("/pfad/zur/artenliste.txt"),
    backend_type=GeoPBBackendV2_4,
    backend_kwargs={},
    check_validity=True
)
```

Die Validierung stellt sicher, dass die Anzahl der Modell-Ausgaben mit der Länge der Artenliste übereinstimmt.

---

## Utils-Modul: Hilfsfunktionen

Das Utils-Modul enthält verschiedene Hilfsfunktionen und -klassen, die Infrastrukturaufgaben übernehmen. Als Anwender werden Sie nur selten direkt mit diesen Komponenten interagieren, aber es ist hilfreich zu verstehen, was im Hintergrund passiert.

### Lokale Datenverwaltung

BirdNET speichert heruntergeladene Modelle und Konfigurationsdaten lokal auf Ihrem System. Die genauen Pfade hängen vom Betriebssystem ab:

- **Windows**: `%APPDATA%\birdnet\`
- **macOS**: `~/Library/Application Support/birdnet/`
- **Linux**: `~/.local/share/birdnet/`

Innerhalb dieses Verzeichnisses werden Modelle nach Typ, Version, Backend und Präzision organisiert:

```
birdnet/
├── acoustic-models/
│   └── v2.4/
│       ├── pb/
│       │   ├── model-fp32/
│       │   └── labels/
│       └── tf/
│           ├── model-fp32.tflite
│           ├── model-fp16.tflite
│           └── labels/
└── geo-models/
    └── v2.4/
        └── pb/
            ├── model-fp32/
            └── labels/
```

Wenn ein Modell bereits heruntergeladen wurde, überprüft BirdNET beim Laden, ob es lokal verfügbar ist, und verwendet die gecachte Version. Falls nicht, wird es automatisch von Zenodo oder einem anderen konfigurierten Server heruntergeladen.

Sie können das App-Datenverzeichnis programmatisch abrufen:

```python
from birdnet.utils.local_data import get_birdnet_app_data_folder

app_dir = get_birdnet_app_data_folder()
print(f"BirdNET-Daten befinden sich in: {app_dir}")
```

Falls Sie aus Platz- oder Sicherheitsgründen Modelle manuell herunterladen und an einem anderen Ort speichern möchten, können Sie `load_custom()` verwenden und den expliziten Pfad angeben.

### Logging

BirdNET verwendet das Standard-Python-Logging-Framework. Standardmäßig ist Logging auf INFO-Ebene aktiviert, wobei Meldungen an die Konsole ausgegeben werden. Sie können das Log-Level anpassen:

```python
import logging
from birdnet.utils.logging_utils import init_package_logger

# Debug-Meldungen aktivieren
init_package_logger(logging.DEBUG)

# Nur Warnungen und Fehler anzeigen
init_package_logger(logging.WARNING)

# Logging vollständig deaktivieren
init_package_logger(logging.CRITICAL + 1)
```

Während Inference-Sessions werden detaillierte Logs in temporären Dateien gespeichert, die bei Problemen hilfreich zur Fehlerdiagnose sind. Wenn `show_stats="benchmark"` gesetzt ist, werden diese Logs auch in das Benchmark-Verzeichnis kopiert.

Logger folgen einer hierarchischen Namensstruktur:

```
birdnet (Hauptlogger)
├── birdnet.session_<ID> (Sessionlogger)
│   ├── birdnet.session_<ID>.producer
│   ├── birdnet.session_<ID>.worker
│   └── birdnet.session_<ID>.analyzer
```

Sie können eigene Handler hinzufügen, um Logs in Ihre Anwendung zu integrieren:

```python
import logging

birdnet_logger = logging.getLogger("birdnet")
handler = logging.FileHandler("my_birdnet.log")
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
birdnet_logger.addHandler(handler)
```

### Supported Audio-Formate

BirdNET nutzt intern die SoundFile-Bibliothek (libsndfile), um Audiodateien zu laden. Unterstützte Formate umfassen:

WAV, FLAC, OGG, MP3 (über MPEG-Decoder), AIFF, AU, CAF und viele weitere. Die vollständige Liste finden Sie in `birdnet.utils.helper.SF_FORMATS`. Nicht unterstützt sind proprietäre Formate wie AAC, WMA oder M4A ohne entsprechende System-Codecs.

Wenn Sie unsicher sind, ob eine Datei unterstützt wird, können Sie die Prüffunktion verwenden:

```python
from pathlib import Path
from birdnet.utils.helper import is_supported_audio_file

file_path = Path("/pfad/zu/audio.mp3")
if is_supported_audio_file(file_path):
    print("Datei wird unterstützt")
else:
    print("Datei wird NICHT unterstützt")
```

Für die rekursive Suche nach allen unterstützten Audiodateien in einem Verzeichnis:

```python
from pathlib import Path
from birdnet.utils.helper import get_supported_audio_files_recursive

audio_dir = Path("/pfad/zu/audio/ordner")
all_audio_files = list(get_supported_audio_files_recursive(audio_dir))
print(f"Gefunden: {len(all_audio_files)} Audiodateien")
```

Dies ist nützlich, wenn Sie einen Ordner mit gemischten Dateitypen haben und nur die Audio-Dateien verarbeiten möchten.

---

## Performance-Optimierung und Best Practices

Die effiziente Verarbeitung großer Audio-Datenmengen erfordert ein Verständnis der internen Abläufe und einige Best Practices. In diesem Abschnitt beleuchten wir, wie die Inference-Pipeline funktioniert und wie Sie Parameter optimal einstellen.

### Die Inference-Pipeline im Detail

Wenn Sie `predict()` oder `encode()` aufrufen, startet intern eine komplexe Pipeline mit mehreren parallelen Prozessen. Das Verständnis dieser Pipeline hilft Ihnen, Engpässe zu identifizieren und die Parameter richtig zu wählen.

**Producer-Prozesse:** Producer lesen Audiodateien von der Festplatte, führen Resampling auf die Modell-Abtastrate (48 kHz) durch, wenden Bandpass-Filter an und zerlegen das Audio in überlappende 3-Sekunden-Segmente. Diese Segmente werden in einen Shared-Memory-Ring-Buffer geschrieben, aus dem Worker sie abrufen können. Producer arbeiten asynchron, um I/O-Wartezeiten zu verbergen.

**Ring-Buffer:** Der Ring-Buffer ist ein zirkulärer Puffer im Shared Memory, der Producer und Worker entkoppelt. Er hat eine feste Anzahl von Slots (berechnet aus `n_workers * batch_size * prefetch_ratio`). Producer füllen Slots, Worker leeren sie. Semaphore synchronisieren den Zugriff und verhindern Race Conditions. Der Ring-Buffer ermöglicht effizientes Zero-Copy-Sharing zwischen Prozessen.

**Worker-Prozesse:** Worker laden jeweils eine eigene Kopie des Modells und verarbeiten Batches von Segmenten aus dem Ring-Buffer. Jeder Worker arbeitet unabhängig und schreibt seine Ergebnisse in eine gemeinsame Ergebnis-Queue. Worker sind CPU- oder GPU-bound, abhängig vom Backend.

**Analyzer-Prozess:** Der Analyzer läuft im Hauptprozess und koordiniert die Pipeline. Er verwaltet die Eingabe-Queue für Producer, sammelt Ergebnisse von Workern und aggregiert sie zu einem finalen Result-Objekt. Der Analyzer überwacht auch den Fortschritt und kann die Pipeline bei Bedarf abbrechen.

**Datenfluss:**

```
Audiodateien
    ↓
[Producer 1] [Producer 2] ... [Producer N]
    ↓         ↓                 ↓
    +---------+-----------------+
              ↓
      [Ring-Buffer (Shared Memory)]
              ↓
    +---------+-----------------+
    ↓         ↓                 ↓
[Worker 1] [Worker 2] ... [Worker M]
    ↓         ↓                 ↓
    +---------+-----------------+
              ↓
        [Results Queue]
              ↓
          [Analyzer]
              ↓
        Result-Objekt
```

### Parameter-Tuning für verschiedene Szenarien

**Szenario 1: Wenige große Dateien (z.B. 10 Dateien à 1 Stunde):**

Hier ist I/O kein Engpass, sondern die Modell-Inferenz. Verwenden Sie:

```python
result = model.predict(
    files,
    n_producers=1,        # Ein Producer reicht
    n_workers=8,          # Viele Worker für Parallelität
    batch_size=64,        # Große Batches für GPU-Auslastung
    prefetch_ratio=2,     # Moderates Prefetching
    device="GPU:0"
)
```

**Szenario 2: Viele kleine Dateien (z.B. 10.000 Dateien à 10 Sekunden):**

I/O kann zum Engpass werden. Verwenden Sie:

```python
result = model.predict(
    files,
    n_producers=4,        # Mehrere Producer für paralleles Lesen
    n_workers=4,          # Weniger Worker, da Dateien kurz sind
    batch_size=16,        # Kleinere Batches für schnelleres Durchreichen
    prefetch_ratio=3,     # Höheres Prefetching um I/O-Lücken zu füllen
    device="CPU"
)
```

**Szenario 3: Echtzeit-Verarbeitung (Audio-Stream):**

Minimale Latenz ist wichtig:

```python
# Verarbeiten Sie kurze Chunks als Arrays
with model.predict_session(
    n_producers=1,
    n_workers=1,
    batch_size=1,         # Keine Batching-Verzögerung
    overlap_duration_s=0, # Keine Überlappung für schnellste Verarbeitung
    device="GPU:0"        # GPU für niedrige Latenz
) as session:
    while audio_stream_active:
        chunk = get_next_audio_chunk()  # Z.B. 3 Sekunden
        result = session.run_arrays([(chunk, 48000)])
        process_result(result)
```

**Szenario 4: GPU mit mehreren Geräten:**

Verteilen Sie Worker auf GPUs:

```python
result = model.predict(
    files,
    n_producers=2,
    n_workers=4,
    batch_size=128,
    device=["GPU:0", "GPU:1", "GPU:0", "GPU:1"],  # Abwechselnd auf 2 GPUs
)
```

Jeder Worker wird dem entsprechenden Gerät aus der Liste zugewiesen. Achten Sie darauf, dass die Liste die Länge `n_workers` hat.

### Speichermanagement

Der Speicherbedarf hängt hauptsächlich von folgenden Faktoren ab:

**Ring-Buffer-Größe:** `n_workers * batch_size * prefetch_ratio * segment_size * 4 Bytes (Float32)`

Für `n_workers=4`, `batch_size=32`, `prefetch_ratio=2` und `segment_size=144.000` Samples (3s bei 48 kHz) ergibt das:

`4 * 32 * 2 * 144.000 * 4 ≈ 147 MB`

**Modell-Speicher:** Jeder Worker lädt eine Modell-Kopie. Das akustische FP32-Modell benötigt etwa 50-120 MB pro Kopie (abhängig vom Backend). Bei 4 Workern sind das 200-480 MB.

**Result-Speicher:** Ergebnisse werden im Hauptprozess aggregiert. Die Größe hängt von der Anzahl der Vorhersagen ab. Für eine einstündige Aufnahme mit 1.5s Überlappung (`speed=1.0`) erhalten Sie etwa 2400 Segmente. Bei `top_k=5` sind das 12.000 Vorhersagen. Jede Vorhersage speichert:

- Input-Index (2-4 Bytes)
- Segment-Index (2-4 Bytes)
- Start/End-Zeit (8 Bytes Float64)
- Arten-ID (2-4 Bytes)
- Konfidenz (4 Bytes Float32)

≈ 20-30 Bytes pro Vorhersage, also ~360 KB für 12.000 Vorhersagen. Bei 100 Stunden sind das ~36 MB.

**Gesamt-Speicherbedarf:** Für typische Konfigurationen sollten Sie mit 1-3 GB RAM rechnen, je nach Anzahl der Worker und Batch-Größe.

Falls Sie an Speichergrenzen stoßen, reduzieren Sie `prefetch_ratio`, `batch_size` oder `n_workers`. Oder setzen Sie `max_audio_duration_min`, um sehr lange Dateien in Chunks zu verarbeiten (allerdings führt dies zu mehreren Durchläufen).

### Benchmarking

Für detaillierte Performance-Analysen verwenden Sie `show_stats="benchmark"`:

```python
result = model.predict(
    files,
    n_workers=4,
    batch_size=32,
    show_stats="benchmark"
)
```

Nach der Verarbeitung werden detaillierte Metriken ausgegeben:

- **Wall-Clock-Zeit:** Gesamtdauer der Verarbeitung
- **Audio-Dauer:** Summe der verarbeiteten Audio-Längen
- **Echtzeit-Faktor:** Audio-Dauer / Wall-Clock-Zeit (z.B. 10.0 bedeutet 10 Stunden Audio in 1 Stunde verarbeitet)
- **Segment-Durchsatz:** Segmente pro Sekunde
- **Speicher-Nutzung:** Größe des Ring-Buffers und der Ergebnisse

Diese Informationen werden auch in einer Benchmark-Datei im App-Datenverzeichnis gespeichert, sodass Sie verschiedene Konfigurationen vergleichen können.

---

## Fortgeschrittene Anwendungsfälle

### Benutzerdefinierte Konfidenz-Schwellwerte

In manchen Szenarien möchten Sie unterschiedliche Schwellwerte für verschiedene Arten verwenden. Beispielsweise könnten häufige Arten wie Amsel oder Kohlmeise höhere Schwellwerte erhalten, um falsch-positive zu reduzieren, während seltene Arten niedrigere Schwellwerte bekommen, um keine Nachweise zu verpassen:

```python
custom_thresholds = {
    "Amsel_Turdus merula": 0.5,
    "Kohlmeise_Parus major": 0.5,
    "Seltene Art_Species rara": 0.1,
}

result = model.predict(
    files,
    default_confidence_threshold=0.3,
    custom_confidence_thresholds=custom_thresholds,
    top_k=None  # Alle Arten zurückgeben, Filterung erfolgt über Schwellwerte
)
```

Arten ohne Eintrag in `custom_thresholds` verwenden `default_confidence_threshold`.

### Eigene Artenlisten

Falls Sie nur an einer Teilmenge von Arten interessiert sind, können Sie eine benutzerdefinierte Artenliste übergeben. Dies reduziert nicht die Rechenzeit (das Modell berechnet immer alle Ausgaben), aber die Ergebnisgröße und vereinfacht die Nachverarbeitung:

```python
zielarten = [
    "Amsel_Turdus merula",
    "Nachtigall_Luscinia megarhynchos",
    "Rotkehlchen_Erithacus rubecula",
]

result = model.predict(
    files,
    custom_species_list=zielarten,
    top_k=3
)
```

Alternativ können Sie auch einen Pfad zu einer Textdatei angeben, die Artennamen enthält (ein Name pro Zeile):

```python
result = model.predict(
    files,
    custom_species_list=Path("/pfad/zur/zielarten.txt"),
    top_k=3
)
```

### Batch-Verarbeitung großer Datensets

Wenn Sie tausende von Dateien verarbeiten möchten, kann es sinnvoll sein, diese in Chunks aufzuteilen und zwischen den Chunks Zwischenergebnisse zu speichern:

```python
from pathlib import Path
import numpy as np

all_files = list(Path("/audio/dataset").rglob("*.wav"))
chunk_size = 1000

with model.predict_session(
    n_workers=8,
    batch_size=64,
    device="GPU:0",
    show_stats="progress"
) as session:
    for i in range(0, len(all_files), chunk_size):
        chunk = all_files[i:i+chunk_size]
        print(f"Verarbeite Chunk {i//chunk_size + 1}/{(len(all_files)-1)//chunk_size + 1}")
        
        result = session.run(chunk)
        result.save(f"results_chunk_{i//chunk_size}.npz")
        
        # Optional: Speicher freigeben
        del result
```

Später können Sie die Chunk-Ergebnisse kombinieren oder separat analysieren.

### Eigene Progress-Callbacks

Falls Sie eine GUI oder ein Dashboard entwickeln, können Sie eigene Progress-Callbacks registrieren:

```python
from birdnet.acoustic.inference.core.perf_tracker import AcousticProgressStats

def my_progress_callback(stats: AcousticProgressStats):
    progress_percent = (stats.segments_processed / stats.segments_total) * 100
    eta_seconds = stats.estimated_time_remaining
    
    # Aktualisiere GUI-Elemente
    update_progress_bar(progress_percent)
    update_eta_label(f"Verbleibend: {eta_seconds:.0f}s")
    
    # Optional: Logging
    print(f"Fortschritt: {progress_percent:.1f}% | "
          f"Geschwindigkeit: {stats.segments_per_second:.1f} seg/s")

result = model.predict(
    files,
    show_stats="progress",  # Aktiviert Progress-Tracking
    progress_callback=my_progress_callback
)
```

Das `AcousticProgressStats`-Objekt enthält folgende Attribute:

- `segments_total`: Gesamtzahl zu verarbeitender Segmente
- `segments_processed`: Anzahl bereits verarbeiteter Segmente
- `elapsed_time`: Verstrichene Zeit in Sekunden
- `estimated_time_remaining`: Geschätzte Restzeit in Sekunden
- `segments_per_second`: Aktuelle Verarbeitungsgeschwindigkeit

Der Callback wird etwa alle 1-2 Sekunden aufgerufen, sodass Sie Ihre UI flüssig aktualisieren können, ohne zu viel Overhead zu erzeugen.

---

## Vollständige Workflow-Beispiele

In diesem Abschnitt führen wir drei realistische Anwendungsszenarien von Anfang bis Ende durch, um zu zeigen, wie die verschiedenen Komponenten von BirdNET zusammenspielen.

### Beispiel 1: Akustische Vogelarten-Erkennung mit geografischer Filterung

**Szenario:** Sie haben Audioaufnahmen aus einem Waldgebiet in Deutschland (Koordinaten: 51.1657°N, 10.4515°E) gemacht und möchten wissen, welche Vogelarten im Mai (Woche 20) zu hören sind. Sie möchten nur Arten berücksichtigen, die in dieser Region und Jahreszeit plausibel vorkommen.

```python
from pathlib import Path
from birdnet.acoustic.models.v2_4.model import AcousticModelV2_4
from birdnet.acoustic.models.v2_4.backends.pb import AcousticPBBackendV2_4
from birdnet.geo.models.v2_4.model import GeoModelV2_4
from birdnet.geo.models.v2_4.backends.pb import GeoPBBackendV2_4

# Schritt 1: Geografische Vorhersage
print("Lade geografisches Modell...")
geo_model = GeoModelV2_4.load(
    lang="de",
    backend_type=GeoPBBackendV2_4,
    backend_kwargs={}
)

print("Berechne wahrscheinliche Arten für den Standort...")
geo_prediction = geo_model.predict(
    latitude=51.1657,
    longitude=10.4515,
    week=20,
    min_confidence=0.05,  # Nur Arten mit >5% Wahrscheinlichkeit
    device="CPU"
)

# Extrahiere Liste der wahrscheinlichen Arten
likely_species = set(
    geo_prediction.species_list[~geo_prediction.species_masked]
)
print(f"Geografisch plausible Arten: {len(likely_species)}")

# Schritt 2: Akustische Modell laden
print("\nLade akustisches Modell...")
acoustic_model = AcousticModelV2_4.load(
    lang="de",
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={}
)

# Schritt 3: Audiodateien sammeln
audio_dir = Path("/pfad/zu/aufnahmen")
audio_files = list(audio_dir.glob("*.wav"))
print(f"Gefundene Audiodateien: {len(audio_files)}")

# Schritt 4: Akustische Analyse mit geografischer Filterung
print("\nStarte Analyse...")
acoustic_result = acoustic_model.predict(
    audio_files,
    custom_species_list=likely_species,  # Nur geografisch plausible Arten
    top_k=5,
    overlap_duration_s=1.5,  # Hohe zeitliche Auflösung
    apply_sigmoid=True,
    sigmoid_sensitivity=1.2,  # Etwas konservativere Vorhersagen
    default_confidence_threshold=0.25,
    n_producers=2,
    n_workers=4,
    batch_size=32,
    device="GPU:0",
    show_stats="progress"
)

# Schritt 5: Ergebnisse exportieren und analysieren
acoustic_result.to_csv("erkennungen_mai.csv")
acoustic_result.save("erkennungen_mai.npz", compress=True)

print(f"\nAnalyse abgeschlossen!")
print(f"Gesamtanzahl Erkennungen: {len(acoustic_result.species_ids)}")
print(f"Analysierte Audio-Dauer: {acoustic_result.input_durations.sum() / 60:.1f} Minuten")

# Schritt 6: Top-Arten ermitteln
import pandas as pd

df = pd.read_csv("erkennungen_mai.csv")
top_species = df.groupby("species_name").size().sort_values(ascending=False).head(10)

print("\nTop 10 erkannte Arten:")
for species, count in top_species.items():
    print(f"  {species}: {count} Erkennungen")
```

**Erklärung des Workflows:**

Zunächst laden wir das geografische Modell und berechnen die Wahrscheinlichkeiten für alle Arten am gegebenen Standort und Zeitpunkt. Wir filtern auf Arten mit mindestens 5% Wahrscheinlichkeit, um eine realistische Kandidatenliste zu erhalten. Diese Liste übergeben wir dann als `custom_species_list` an das akustische Modell, sodass nur diese Arten in den Ergebnissen erscheinen können. Dies reduziert falsch-positive Erkennungen dramatisch – eine Nachtigall wird nicht fälschlicherweise als tropische Art identifiziert, die am Standort gar nicht vorkommt.

Die akustische Analyse verwendet eine moderate Überlappung für gute zeitliche Auflösung und eine leicht erhöhte Sigmoid-Sensitivität, um die Präzision zu erhöhen. Die parallele Verarbeitung mit GPU beschleunigt die Analyse erheblich. Am Ende exportieren wir die Ergebnisse als CSV für einfache Weiterverarbeitung und als NPZ für spätere Python-Analysen.

### Beispiel 2: Embedding-Extraktion für Clustering

**Szenario:** Sie möchten Audioaufnahmen automatisch nach akustischer Ähnlichkeit gruppieren, ohne auf Artenklassifikation angewiesen zu sein. Dazu extrahieren Sie Embeddings und führen Clustering durch.

```python
from pathlib import Path
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
from birdnet.acoustic.models.v2_4.model import AcousticModelV2_4
from birdnet.acoustic.models.v2_4.backends.pb import AcousticPBBackendV2_4

# Schritt 1: Modell laden
print("Lade akustisches Modell...")
model = AcousticModelV2_4.load(
    lang="de",
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={}
)

# Schritt 2: Audiodateien sammeln
audio_dir = Path("/pfad/zu/aufnahmen")
audio_files = list(audio_dir.glob("*.wav"))[:100]  # Nur erste 100 für Demo
print(f"Verarbeite {len(audio_files)} Dateien...")

# Schritt 3: Embeddings extrahieren
embedding_result = model.encode(
    audio_files,
    overlap_duration_s=0,  # Keine Überlappung für Clustering
    n_producers=2,
    n_workers=4,
    batch_size=32,
    device="GPU:0",
    show_stats="progress"
)

# Schritt 4: Embeddings aufbereiten
embeddings = embedding_result.embeddings  # Shape: (n_files, n_segments_max, 1024)
embeddings_masked = embedding_result.embeddings_masked  # Maske für gültige Embeddings

# Nur gültige Embeddings verwenden
valid_embeddings = embeddings[~embeddings_masked]
print(f"Gültige Embeddings: {valid_embeddings.shape[0]}")

# Optional: Dimensionsreduktion für Visualisierung (PCA auf 50 Dimensionen)
from sklearn.decomposition import PCA
pca = PCA(n_components=50, random_state=42)
embeddings_reduced = pca.fit_transform(valid_embeddings)
print(f"Varianz erklärt durch PCA: {pca.explained_variance_ratio_.sum():.2%}")

# Schritt 5: Clustering mit DBSCAN
print("\nFühre Clustering durch...")
scaler = StandardScaler()
embeddings_scaled = scaler.fit_transform(embeddings_reduced)

clustering = DBSCAN(eps=2.5, min_samples=5, metric='euclidean')
labels = clustering.fit_predict(embeddings_scaled)

n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
n_noise = list(labels).count(-1)

print(f"Gefundene Cluster: {n_clusters}")
print(f"Noise-Punkte: {n_noise}")

# Schritt 6: Cluster analysieren
cluster_sizes = {}
for label in set(labels):
    if label != -1:
        cluster_sizes[label] = (labels == label).sum()

print("\nCluster-Größen:")
for cluster_id, size in sorted(cluster_sizes.items(), key=lambda x: x[1], reverse=True):
    print(f"  Cluster {cluster_id}: {size} Segmente")

# Schritt 7: Visualisierung (optional)
# Hier könnten Sie t-SNE oder UMAP für 2D-Projektion verwenden
# und die Cluster visuell darstellen

# Schritt 8: Embeddings für spätere Verwendung speichern
embedding_result.save("embeddings_cluster.npz", compress=True)
```

**Erklärung des Workflows:**

Dieser Workflow demonstriert, wie Embeddings für unüberwachtes Lernen genutzt werden können. Nach dem Extrahieren der Embeddings wenden wir PCA zur Dimensionsreduktion an, was das Clustering beschleunigt und Rauschen reduziert. Das DBSCAN-Clustering gruppiert ähnliche Audio-Segmente automatisch, ohne dass wir vorher die Anzahl der Cluster festlegen müssen. Noise-Punkte (Label -1) sind Segmente, die keinem Cluster zugeordnet werden konnten, was oft Hintergrundgeräusche oder sehr seltene Laute sind.

Sie könnten diesen Workflow erweitern, indem Sie für jedes Cluster representative Samples auswählen und manuell annotieren, um die Cluster zu interpretieren. Oder Sie verwenden die Cluster als Input für ein Klassifikationsmodell, um seltene Arten zu identifizieren, die nicht im BirdNET-Trainingsdatensatz enthalten sind.

### Beispiel 3: Echtzeit-Monitoring mit Stream-Verarbeitung

**Szenario:** Sie möchten ein Live-Monitoring-System aufbauen, das einen kontinuierlichen Audio-Stream analysiert und Erkennungen in Echtzeit meldet.

```python
from pathlib import Path
import numpy as np
import sounddevice as sd
from collections import deque
from threading import Thread, Event
from birdnet.acoustic.models.v2_4.model import AcousticModelV2_4
from birdnet.acoustic.models.v2_4.backends.pb import AcousticPBBackendV2_4

# Konfiguration
SAMPLE_RATE = 48000
SEGMENT_DURATION_S = 3.0
SEGMENT_SAMPLES = int(SAMPLE_RATE * SEGMENT_DURATION_S)
MIN_CONFIDENCE = 0.3

# Audio-Buffer für eingehende Daten
audio_buffer = deque(maxlen=SEGMENT_SAMPLES * 2)
stop_event = Event()

# Schritt 1: Modell laden
print("Lade akustisches Modell...")
model = AcousticModelV2_4.load(
    lang="de",
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={}
)

# Schritt 2: Session für wiederholte Inferenz starten
print("Starte Prediction-Session...")
session = model.predict_session(
    top_k=3,
    overlap_duration_s=0,  # Keine Überlappung für minimale Latenz
    apply_sigmoid=True,
    default_confidence_threshold=MIN_CONFIDENCE,
    n_producers=1,
    n_workers=1,
    batch_size=1,
    device="GPU:0"  # Oder "CPU" falls keine GPU
)
session.__enter__()

# Schritt 3: Audio-Callback für Echtzeit-Aufnahme
def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Audio-Status: {status}")
    
    # Audio-Daten zum Buffer hinzufügen
    audio_buffer.extend(indata[:, 0])  # Mono-Channel

# Schritt 4: Verarbeitungs-Thread
def processing_thread():
    segment_count = 0
    
    while not stop_event.is_set():
        # Warte, bis genug Daten für ein Segment vorhanden sind
        if len(audio_buffer) < SEGMENT_SAMPLES:
            continue
        
        # Segment extrahieren
        segment = np.array(list(audio_buffer)[:SEGMENT_SAMPLES], dtype=np.float32)
        
        # Verarbeiten
        try:
            result = session.run_arrays([(segment, SAMPLE_RATE)])
            
            # Erkennungen ausgeben
            if result.n_predictions > 0:
                predictions = result.to_structured_array()
                for pred in predictions:
                    species = pred['species_name']
                    confidence = pred['confidence']
                    print(f"[Segment {segment_count}] Erkannt: {species} ({confidence:.2f})")
        
        except Exception as e:
            print(f"Fehler bei Verarbeitung: {e}")
        
        # Buffer leeren (Segmente überlappen sich nicht)
        for _ in range(SEGMENT_SAMPLES):
            if audio_buffer:
                audio_buffer.popleft()
        
        segment_count += 1

# Schritt 5: Starte Threads
processor = Thread(target=processing_thread, daemon=True)
processor.start()

# Schritt 6: Audio-Stream starten
print("\nStarte Audio-Aufnahme... (Strg+C zum Beenden)")
with sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=1,
    callback=audio_callback,
    blocksize=int(SAMPLE_RATE * 0.1)  # 100ms Blöcke
):
    try:
        while True:
            sd.sleep(1000)
    except KeyboardInterrupt:
        print("\nBeende...")
        stop_event.set()
        processor.join(timeout=5)
        session.__exit__(None, None, None)
        print("Beendet.")
```

**Erklärung des Workflows:**

Dieses Beispiel zeigt ein komplettes Echtzeit-Monitoring-System. Der `sounddevice`-Stream erfasst kontinuierlich Audio vom Mikrofon und schreibt es in einen Thread-sicheren Buffer (deque). Ein separater Verarbeitungs-Thread prüft ständig, ob genug Daten für ein 3-Sekunden-Segment vorhanden sind, und führt dann die Analyse durch. Die Verwendung einer Session stellt sicher, dass das Modell nur einmal geladen wird und zwischen den Inferenzen im Speicher bleibt, was die Latenz minimiert.

Wichtig ist die Konfiguration mit `batch_size=1` und `overlap_duration_s=0`, um die Latenz zu minimieren. In einem Produktiv-System würden Sie wahrscheinlich zusätzliche Funktionen wie Datenbank-Logging, Alarm-Benachrichtigungen oder Web-Dashboards hinzufügen.

---

## API-Referenz (Kompakt)

### AcousticModelV2_4

**Klassenmethoden:**

```python
AcousticModelV2_4.load(
    lang: str,
    backend_type: type[VersionedAcousticBackendProtocol],
    backend_kwargs: dict[str, Any],
    precision: MODEL_PRECISIONS = "fp32"  # (bitte prüfen, kann falsch sein)
) -> AcousticModelV2_4

AcousticModelV2_4.load_custom(
    model_path: Path,
    species_list: Path,
    backend_type: type[VersionedAcousticBackendProtocol],
    backend_kwargs: dict[str, Any],
    check_validity: bool = True
) -> AcousticModelV2_4

AcousticModelV2_4.get_segment_size_s() -> float  # 3.0
AcousticModelV2_4.get_sample_rate() -> int  # 48000
AcousticModelV2_4.get_sig_fmin() -> int  # 0
AcousticModelV2_4.get_sig_fmax() -> int  # 15000
AcousticModelV2_4.get_embeddings_dim() -> int  # 1024
```

**Instanz-Methoden:**

```python
model.predict(
    inp: Path | str | Iterable[Path | str],
    /,
    *,
    top_k: int | None = 5,
    n_producers: int = 1,
    n_workers: int | None = None,
    batch_size: int = 1,
    prefetch_ratio: int = 1,
    overlap_duration_s: float = 0,
    bandpass_fmin: int = 0,
    bandpass_fmax: int = 15_000,
    speed: float = 1.0,
    apply_sigmoid: bool = True,
    sigmoid_sensitivity: float | None = 1.0,
    default_confidence_threshold: float | None = 0.1,
    custom_confidence_thresholds: dict[str, float] | None = None,
    custom_species_list: str | Path | Collection[str] | None = None,
    half_precision: bool = False,
    max_audio_duration_min: float | None = None,
    device: str | list[str] = "CPU",
    show_stats: Literal["minimal", "progress", "benchmark"] | None = None,
    progress_callback: Callable[[AcousticProgressStats], None] | None = None,
) -> AcousticPredictionResultBase

model.predict_session(...) -> AcousticPredictionSession

model.encode(
    inp: Path | str | Iterable[Path | str],
    /,
    *,
    n_producers: int = 1,
    n_workers: int | None = None,
    batch_size: int = 1,
    prefetch_ratio: int = 1,
    overlap_duration_s: float = 0,
    speed: float = 1.0,
    bandpass_fmin: int = 0,
    bandpass_fmax: int = 15_000,
    half_precision: bool = False,
    max_audio_duration_min: float | None = None,
    device: str | list[str] = "CPU",
    show_stats: Literal["minimal", "progress", "benchmark"] | None = None,
    progress_callback: Callable[[AcousticProgressStats], None] | None = None,
) -> AcousticEncodingResultBase

model.encode_session(...) -> AcousticEncodingSession
```

### GeoModelV2_4

```python
GeoModelV2_4.load(
    lang: str,
    backend_type: type[VersionedGeoBackendProtocol],
    backend_kwargs: dict[str, Any]
) -> GeoModelV2_4

GeoModelV2_4.load_custom(
    model_path: Path,
    species_list: Path,
    backend_type: type[VersionedGeoBackendProtocol],
    backend_kwargs: dict[str, Any],
    check_validity: bool = True
) -> GeoModelV2_4

model.predict(
    latitude: float,
    longitude: float,
    /,
    *,
    week: int | None = None,
    min_confidence: float = 0.03,
    half_precision: bool = False,
    device: str = "CPU",
) -> GeoPredictionResult

model.predict_session(...) -> GeoPredictionSession
```

### Result-Objekte

**AcousticFilePredictionResult / AcousticDataPredictionResult:**

```python
result.n_inputs: int
result.n_species: int
result.n_predictions: int  # (bitte prüfen, kann falsch sein)
result.species_list: OrderedSet[str]
result.to_structured_array() -> np.ndarray
result.to_csv(path: Path, encoding: str = "utf-8", ...)
result.to_parquet(path: Path, ...)
result.save(path: Path, compress: bool = True)
AcousticFilePredictionResult.load(path: Path) -> Self
```

**AcousticFileEncodingResult / AcousticDataEncodingResult:**

```python
result.embeddings: np.ndarray  # Shape: (n_inputs, n_segments, emd_dim)
result.embeddings_masked: np.ndarray  # Bool-Maske
result.emd_dim: int
result.max_n_segments: int
result.save(path: Path, compress: bool = True)
AcousticFileEncodingResult.load(path: Path) -> Self
```

**GeoPredictionResult:**

```python
result.species_list: np.ndarray
result.species_probs: np.ndarray
result.species_masked: np.ndarray
result.latitude: float
result.longitude: float
result.week: int
result.save(path: Path, compress: bool = True)
GeoPredictionResult.load(path: Path) -> Self
```

### Sessions

**AcousticPredictionSession:**

```python
with model.predict_session(...) as session:
    result = session.run(files: Path | str | Iterable[Path | str])
    result = session.run_arrays(inputs: tuple[np.ndarray, int] | Iterable[tuple[np.ndarray, int]])
```

**AcousticEncodingSession:**

```python
with model.encode_session(...) as session:
    result = session.run(files: Path | str | Iterable[Path | str])
    result = session.run_arrays(inputs: tuple[np.ndarray, int] | Iterable[tuple[np.ndarray, int]])
```

**GeoPredictionSession:**

```python
with geo_model.predict_session(...) as session:
    result = session.run(latitude: float, longitude: float, week: int | None = None)
```

---

## Häufige Fehler und Troubleshooting

### Fehler: "No GPU found"

**Problem:** Sie haben `device="GPU:0"` angegeben, aber BirdNET findet keine GPU.

**Lösung:** 
- Stellen Sie sicher, dass CUDA installiert ist (für NVIDIA-GPUs).
- Prüfen Sie, ob TensorFlow GPU-Unterstützung hat: `python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"`
- Falls keine GPU verfügbar ist, verwenden Sie `device="CPU"`.

### Fehler: "ValueError: Model has X outputs, but species list has Y species"

**Problem:** Beim Laden eines benutzerdefinierten Modells stimmt die Anzahl der Ausgaben nicht mit der Artenliste überein.

**Lösung:**
- Prüfen Sie, ob die Artenliste vollständig ist und keine Duplikate enthält.
- Setzen Sie `check_validity=False`, um die Prüfung zu überspringen (nicht empfohlen, da dies zu inkonsistenten Ergebnissen führt).
- Regenerieren Sie die Artenliste aus dem Trainings-Datensatz.

### Fehler: "Out of Memory" während Inferenz

**Problem:** Der Speicher reicht nicht für die aktuelle Konfiguration.

**Lösung:**
- Reduzieren Sie `batch_size` (z.B. von 64 auf 16).
- Reduzieren Sie `n_workers` (weniger Modell-Kopien im Speicher).
- Reduzieren Sie `prefetch_ratio` (weniger Daten im Buffer).
- Setzen Sie `max_audio_duration_min` niedriger.
- Verwenden Sie `half_precision=True` für GPU-Inferenz.

### Audiodatei wird nicht verarbeitet

**Problem:** Eine spezifische Datei erscheint nicht in den Ergebnissen.

**Lösung:**
- Prüfen Sie, ob das Format unterstützt wird: `is_supported_audio_file(path)`.
- Prüfen Sie, ob die Datei korrupt ist (versuchen Sie sie in einem Audio-Player zu öffnen).
- Schauen Sie in `result.get_unprocessed_files()`, ob die Datei dort aufgelistet ist.
- Aktivieren Sie Debug-Logging: `init_package_logger(logging.DEBUG)` und prüfen Sie die Logs.

### Langsame Verarbeitung auf CPU

**Problem:** Die Analyse dauert sehr lange.

**Lösung:**
- Erhöhen Sie `n_workers` bis zur Anzahl Ihrer CPU-Kerne.
- Verwenden Sie INT8-Modelle für schnellere CPU-Inferenz.
- Reduzieren Sie `overlap_duration_s` (weniger Segmente).
- Erhöhen Sie `speed` (schnellere, weniger detaillierte Analyse).
- Erwägen Sie den Einsatz einer GPU.

### Inkonsistente Ergebnisse zwischen Durchläufen

**Problem:** Bei wiederholter Analyse derselben Datei ergeben sich unterschiedliche Ergebnisse.

**Ursache:** Dies kann bei FP16- oder INT8-Modellen auftreten, da numerische Rundungen nicht-deterministisch sein können, besonders bei paralleler Verarbeitung.

**Lösung:**
- Verwenden Sie FP32-Modelle für deterministische Ergebnisse.
- Setzen Sie `n_workers=1` für single-threaded Verarbeitung (langsamer, aber deterministisch).
- Akzeptieren Sie minimale Varianz als Trade-off für Performance.

---

## Zusammenfassung und Best Practices

**Wichtigste Erkenntnisse:**

1. **Backend-Wahl**: Protobuf (pb) für professionelle GPU-Nutzung, TFLite für CPU oder mobile Geräte.

2. **Parallelisierung**: Passen Sie `n_producers`, `n_workers`, `batch_size` und `prefetch_ratio` an Ihre Hardware und Datenstruktur an.

3. **Überlappung**: Höhere `overlap_duration_s` verbessert die zeitliche Auflösung, erhöht aber die Rechenzeit proportional.

4. **Konfidenz-Schwellwerte**: Wählen Sie höhere Werte für präzisere, niedrigere für sensitivere Erkennungen. Passen Sie Schwellwerte artspezifisch an.

5. **Geografische Filterung**: Kombinieren Sie Geo- und Acoustic-Modelle, um falsch-positive zu reduzieren.

6. **Embeddings**: Nutzen Sie Embeddings für Transfer Learning, Clustering oder Ähnlichkeitssuchen jenseits der Artenklassifikation.

7. **Sessions**: Verwenden Sie Sessions für wiederholte Inferenz mit denselben Parametern, um Initialisierungskosten zu sparen.

8. **Persistierung**: Speichern Sie Ergebnisse als NPZ für Python-Weiterverarbeitung oder als CSV/Parquet für externen Zugriff.

9. **Monitoring**: Nutzen Sie `show_stats` und `progress_callback` für Produktiv-Systeme.

10. **Fehlerbehandlung**: Prüfen Sie `get_unprocessed_files()` und aktivieren Sie Logging bei Problemen.

**Typische Workflow-Muster:**

- **Batch-Processing**: `model.predict(many_files, ...)` mit optimierter Parallelisierung.
- **Interaktive Analyse**: Session mit `run()` für einzelne Dateien und Zwischenergebnisse.
- **Echtzeit**: Session mit `run_arrays()` für Stream-Verarbeitung mit minimaler Latenz.
- **Exploration**: Embeddings extrahieren und mit Clustering/Dimensionsreduktion analysieren.

**Performance-Optimierung Checkliste:**

- [ ] Backend passend zur Hardware gewählt (pb für GPU, tf für CPU)
- [ ] `n_workers` an CPU-Kerne oder GPU-Anzahl angepasst
- [ ] `batch_size` für Hardware-Auslastung optimiert
- [ ] `overlap_duration_s` auf gewünschte zeitliche Auflösung eingestellt
- [ ] `prefetch_ratio` erhöht, wenn I/O-bound
- [ ] `half_precision=True` für GPU-Beschleunigung
- [ ] `max_audio_duration_min` gesetzt für große Dateien
- [ ] Geografische Filterung für relevante Regionen aktiviert
- [ ] Artenlisten auf Zielarten reduziert
- [ ] Benchmarking aktiviert zur Performance-Messung

---

## Erweiterte Themen

### Custom-Backends und Model-Anpassungen

Für fortgeschrittene Anwender, die eigene Modelle trainieren oder spezielle Hardware-Beschleuniger nutzen möchten, bietet BirdNET die Möglichkeit, eigene Backend-Implementierungen zu erstellen. Dies erfordert das Implementieren des `VersionedBackendProtocol`.

Ein Custom-Backend muss folgende Methoden implementieren:

- `load()`: Lädt das Modell in den Speicher
- `unload()`: Gibt Modell-Ressourcen frei
- `predict(batch)`: Führt Inferenz für einen Batch durch
- `encode(batch)`: Extrahiert Embeddings (optional)
- `copy_to_device(batch)`: Kopiert Daten auf das Zielgerät
- `copy_from_device(result)`: Kopiert Ergebnisse zurück
- `half_precision(result)`: Konvertiert zu FP16 (optional)

Zusätzlich werden Klassenmethoden benötigt:

- `supports_cow()`: Gibt an, ob Copy-on-Write unterstützt wird
- `supports_encoding()`: Gibt an, ob Embedding-Extraktion möglich ist
- `precision()`: Gibt die Modell-Präzision zurück
- `name()`: Backend-Name für Logging

Ein vereinfachtes Beispiel für ein hypothetisches ONNX-Backend könnte so aussehen:

```python
import onnxruntime as ort
import numpy as np
from pathlib import Path
from birdnet.core.backends import VersionedAcousticBackendProtocol

class ONNXAcousticBackendV2_4:
    def __init__(self, model_path: Path, device_name: str, **kwargs):
        self.model_path = model_path
        self.device_name = device_name
        self.session = None
    
    def load(self):
        providers = ['CPUExecutionProvider']
        if 'GPU' in self.device_name:
            providers.insert(0, 'CUDAExecutionProvider')
        
        self.session = ort.InferenceSession(
            str(self.model_path),
            providers=providers
        )
    
    def unload(self):
        self.session = None
    
    def predict(self, batch: np.ndarray) -> np.ndarray:
        input_name = self.session.get_inputs()[0].name
        output_name = self.session.get_outputs()[0].name
        result = self.session.run([output_name], {input_name: batch})
        return result[0]
    
    def encode(self, batch: np.ndarray) -> np.ndarray:
        # Annahme: Embedding-Output ist zweiter Output
        input_name = self.session.get_inputs()[0].name
        output_name = self.session.get_outputs()[1].name
        result = self.session.run([output_name], {input_name: batch})
        return result[0]
    
    @classmethod
    def supports_cow(cls) -> bool:
        return True
    
    @classmethod
    def supports_encoding(cls) -> bool:
        return True
    
    @property
    def n_species(self) -> int:
        return self.session.get_outputs()[0].shape[1]
    
    @classmethod
    def precision(cls) -> str:
        return "fp32"
    
    @classmethod
    def name(cls) -> str:
        return "onnx"
    
    def copy_to_device(self, batch: np.ndarray) -> np.ndarray:
        return batch
    
    def copy_from_device(self, result: np.ndarray) -> np.ndarray:
        return result
    
    def half_precision(self, result: np.ndarray) -> np.ndarray:
        return result.astype(np.float16)

# Verwendung:
model = AcousticModelV2_4.load_custom(
    model_path=Path("/pfad/zu/modell.onnx"),
    species_list=Path("/pfad/zu/arten.txt"),
    backend_type=ONNXAcousticBackendV2_4,
    backend_kwargs={},
    check_validity=True
)
```

*(Hinweis: Dieses Beispiel ist vereinfacht und vollständige Implementierungen erfordern zusätzliche Fehlerbehandlung und Optimierungen. Die genaue API-Kompatibilität sollte geprüft werden.)*

### Eigene Modelle trainieren

Wenn Sie BirdNET für spezielle Anwendungsfälle adaptieren möchten, können Sie Transfer Learning oder Fine-Tuning verwenden. Der typische Workflow sieht so aus:

1. **Embeddings extrahieren**: Nutzen Sie `model.encode()`, um Embeddings für Ihre Trainingsdaten zu erhalten.

2. **Classifier trainieren**: Trainieren Sie einen einfachen Classifier (z.B. logistische Regression, SVM oder ein kleines neuronales Netz) auf den Embeddings.

3. **Export**: Exportieren Sie das kombinierte Modell (Feature-Extractor + Classifier) in ein unterstütztes Format (TFLite oder SavedModel).

4. **Integration**: Laden Sie das Modell mit `load_custom()` und verwenden Sie es wie ein Standard-BirdNET-Modell.

Ein Beispiel für Transfer Learning mit scikit-learn:

```python
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
import numpy as np

# Schritt 1: Embeddings für Trainings-Audio extrahieren
training_files = [...]  # Liste Ihrer Trainings-Audiodateien
training_labels = [...]  # Entsprechende Labels

embedding_result = model.encode(training_files)
embeddings = embedding_result.embeddings

# Flatten: (n_files, n_segments, emd_dim) -> (n_files * n_segments, emd_dim)
X = embeddings.reshape(-1, embeddings.shape[-1])
# Labels für jedes Segment replizieren
y = np.repeat(training_labels, embeddings.shape[1])

# Schritt 2: Classifier trainieren
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
classifier = LogisticRegression(max_iter=1000)
classifier.fit(X_train, y_train)

accuracy = classifier.score(X_test, y_test)
print(f"Test-Accuracy: {accuracy:.2%}")

# Schritt 3: Für Inferenz verwenden
def predict_with_custom_classifier(audio_file):
    emb_result = model.encode([audio_file])
    emb = emb_result.embeddings.reshape(-1, 1024)
    predictions = classifier.predict_proba(emb)
    return predictions

# Alternativ: Export als ONNX für Integration in BirdNET-Pipeline
# (erfordert zusätzliche Schritte und ist backend-spezifisch)
```

### Verteilte Verarbeitung über mehrere Maschinen

Für sehr große Datensets können Sie die Verarbeitung über mehrere Rechner verteilen. BirdNET selbst bietet keine integrierte Cluster-Funktionalität, aber Sie können externe Tools wie Dask, Ray oder Apache Spark verwenden.

Ein einfaches Beispiel mit Python's `multiprocessing.Pool`:

```python
from multiprocessing import Pool
from pathlib import Path
from functools import partial

def process_chunk(files_chunk, model_params):
    # Laden Sie das Modell in jedem Worker-Prozess
    model = AcousticModelV2_4.load(**model_params)
    result = model.predict(files_chunk, ...)
    return result

# Haupt-Prozess
all_files = [...]  # Tausende von Dateien
chunk_size = 100
file_chunks = [all_files[i:i+chunk_size] for i in range(0, len(all_files), chunk_size)]

model_params = {
    'lang': 'de',
    'backend_type': AcousticPBBackendV2_4,
    'backend_kwargs': {}
}

with Pool(processes=8) as pool:
    results = pool.map(
        partial(process_chunk, model_params=model_params),
        file_chunks
    )

# Ergebnisse aggregieren
# (je nach Result-Typ unterschiedlich)
```

Für echte Cluster-Verarbeitung mit Dask würde der Code ähnlich aussehen, aber Dask würde die Verteilung über Netzwerk-Knoten übernehmen.

### Integration mit anderen ML-Frameworks

BirdNET-Ergebnisse können leicht in andere ML-Pipelines integriert werden. Hier einige Beispiele:

**Integration mit PyTorch:**

```python
import torch
from torch.utils.data import Dataset, DataLoader

class BirdNETEmbeddingDataset(Dataset):
    def __init__(self, audio_files, birdnet_model):
        self.files = audio_files
        self.model = birdnet_model
        self.embeddings = None
        self._extract_embeddings()
    
    def _extract_embeddings(self):
        result = self.model.encode(self.files)
        self.embeddings = torch.from_numpy(result.embeddings)
    
    def __len__(self):
        return len(self.embeddings)
    
    def __getitem__(self, idx):
        return self.embeddings[idx]

# Verwendung in PyTorch-Training
dataset = BirdNETEmbeddingDataset(audio_files, birdnet_model)
loader = DataLoader(dataset, batch_size=32, shuffle=True)

for batch in loader:
    # Trainieren Sie Ihr PyTorch-Modell
    pass
```

**Integration mit Pandas für Datenanalyse:**

```python
import pandas as pd

# BirdNET-Ergebnisse als DataFrame
result = model.predict(files, top_k=5)
result.to_parquet("temp.parquet")
df = pd.read_parquet("temp.parquet")

# Erweiterte Analysen
# 1. Zeitliche Verteilung
df['hour'] = df['start_time'] // 3600
hourly_counts = df.groupby('hour')['species_name'].value_counts()

# 2. Arten-Diversität pro Datei
diversity = df.groupby('input')['species_name'].nunique()

# 3. Korrelationen zwischen Arten
species_matrix = df.pivot_table(
    index='input',
    columns='species_name',
    values='confidence',
    aggfunc='max',
    fill_value=0
)
correlations = species_matrix.corr()

# 4. Zeitreihen-Analyse
df['datetime'] = pd.to_datetime(df['start_time'], unit='s', origin='unix')
timeseries = df.set_index('datetime').groupby('species_name').resample('1H').size()
```

### Arbeiten mit sehr langen Aufnahmen

Für Aufnahmen, die mehrere Stunden oder Tage dauern (z.B. kontinuierliche Monitoring-Stationen), gibt es spezielle Strategien:

**Strategie 1: Chunked Processing**

Teilen Sie die Datei vor der Verarbeitung in kleinere Chunks:

```python
import soundfile as sf

def split_audio_file(input_path, chunk_duration_s=3600):
    data, sr = sf.read(input_path)
    chunk_samples = int(chunk_duration_s * sr)
    chunks = []
    
    for i in range(0, len(data), chunk_samples):
        chunk = data[i:i+chunk_samples]
        chunk_path = f"temp_chunk_{i//chunk_samples}.wav"
        sf.write(chunk_path, chunk, sr)
        chunks.append(Path(chunk_path))
    
    return chunks

long_recording = Path("24h_recording.wav")
chunks = split_audio_file(long_recording, chunk_duration_s=3600)

results = []
for chunk in chunks:
    result = model.predict([chunk], ...)
    results.append(result)
    chunk.unlink()  # Temporären Chunk löschen

# Ergebnisse kombinieren
# (implementierungsabhängig)
```

**Strategie 2: Streaming-Verarbeitung**

Verarbeiten Sie die Datei in überlappenden Fenstern, ohne sie vollständig in den Speicher zu laden:

```python
import soundfile as sf

def process_large_file_streaming(file_path, model, window_size_s=300):
    """Verarbeitet große Datei in überlappenden Fenstern"""
    
    with sf.SoundFile(file_path) as f:
        sr = f.samplerate
        total_frames = len(f)
        window_frames = int(window_size_s * sr)
        
        results = []
        offset = 0
        
        while offset < total_frames:
            f.seek(offset)
            audio_chunk = f.read(window_frames)
            
            if len(audio_chunk) < sr * 3:  # Mindestens 3 Sekunden
                break
            
            # Verarbeite Chunk
            result = model.predict([(audio_chunk, sr)], ...)
            results.append(result)
            
            offset += window_frames // 2  # 50% Überlappung
        
        return results

results = process_large_file_streaming(
    Path("very_long_recording.wav"),
    model,
    window_size_s=300
)
```

### Optimierung für spezifische Hardware

**Apple Silicon (M1/M2/M3):**

Auf Apple Silicon Macs können Sie die Neural Engine nutzen:

```python
# Verwenden Sie das TFLite-Backend mit entsprechenden Optimierungen
model = AcousticModelV2_4.load(
    lang="de",
    backend_type=AcousticTFBackendV2_4,
    backend_kwargs={"inference_library": "tflite"}
)

result = model.predict(
    files,
    device="CPU",  # CPU auf M1/M2 nutzt automatisch Neural Engine
    n_workers=8,   # M1 hat 8 Performance-Kerne
    batch_size=16,
)
```

*(Hinweis: Die genaue Unterstützung für Neural Engine hängt von TensorFlow Lite und der macOS-Version ab. Bitte prüfen Sie die aktuelle Dokumentation.)*

**NVIDIA GPU mit Multi-Instance GPU (MIG):**

Für große NVIDIA GPUs mit MIG-Unterstützung können Sie mehrere logische GPUs definieren:

```python
# Annahme: MIG konfiguriert als 2 Instanzen
result = model.predict(
    files,
    n_workers=2,
    device=["GPU:0", "GPU:1"],  # MIG-Instanzen
    batch_size=128,
)
```

**AMD GPUs:**

Für AMD GPUs mit ROCm:

```python
# ROCm-Unterstützung erfordert spezielles TensorFlow-Build
# Verwenden Sie das Protobuf-Backend mit ROCm-TensorFlow
import os
os.environ['HIP_VISIBLE_DEVICES'] = '0'  # AMD GPU 0

model = AcousticModelV2_4.load(
    lang="de",
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={}
)

result = model.predict(
    files,
    device="GPU:0",
    n_workers=1,
    batch_size=64,
)
```

*(Hinweis: AMD GPU-Unterstützung erfordert spezialisierte TensorFlow-Builds und ist möglicherweise nicht in allen Konfigurationen verfügbar.)*

---

## Datenformate und Interoperabilität

### Export-Formate im Detail

**CSV-Format:**

Das CSV-Format ist das universellste für den Austausch mit anderen Tools. Die Struktur ist:

```csv
input,start_time,end_time,species_name,confidence
"/pfad/zu/datei1.wav","00:00:00.00","00:00:03.00","Amsel_Turdus merula",0.87
"/pfad/zu/datei1.wav","00:00:01.50","00:00:04.50","Kohlmeise_Parus major",0.76
...
```

Zeitstempel sind im Format `HH:MM:SS.CC` (Stunden:Minuten:Sekunden.Centisekunden).

**Parquet-Format:**

Parquet ist ein spaltenorientiertes Binärformat, das sehr effizient für große Datenmengen ist. Es unterstützt:

- Kompression (standardmäßig Snappy)
- Schnelle Filter-Operationen
- Schema-Definitionen mit Datentypen
- Partitionierung für verteilte Verarbeitung

Schema:

```python
import pyarrow.parquet as pq

table = pq.read_table("ergebnisse.parquet")
print(table.schema)
# input: string
# start_time: double (Sekunden als Float)
# end_time: double
# species_name: string
# confidence: float
```

Metadaten im Parquet-Schema enthalten zusätzliche Informationen wie Segment-Länge, Überlappung, Modellversion usw.

**NPZ-Format:**

Das NPZ-Format speichert alle NumPy-Arrays verlustfrei:

```python
result.save("result.npz", compress=True)

# Inhalt inspizieren
import numpy as np
with np.load("result.npz", allow_pickle=True) as data:
    print(data.files)
    # ['model_path', 'model_version', 'model_precision',
    #  'inputs', 'input_durations', 'segment_duration_s',
    #  'overlap_duration_s', 'speed', 'model_fmin', 'model_fmax',
    #  'model_sr', 'species_list', 'species_ids', 'species_probs',
    #  'file_indices', 'segment_indices', ...]
```

Dieses Format ist ideal, wenn Sie mit Python weiterarbeiten und alle Rohdaten benötigen.

### Import von Ergebnissen in Datenbanken

**PostgreSQL mit PostGIS:**

Für geografische Analysen können Sie Ergebnisse mit Standortdaten kombinieren:

```python
import pandas as pd
from sqlalchemy import create_engine

# Ergebnisse laden
df = pd.read_parquet("ergebnisse.parquet")

# Standortdaten hinzufügen (Beispiel)
site_locations = {
    "/pfad/zu/site1/": (51.5, 10.4),
    "/pfad/zu/site2/": (52.3, 11.2),
}

def get_location(filepath):
    for site, coords in site_locations.items():
        if site in filepath:
            return coords
    return (None, None)

df[['latitude', 'longitude']] = df['input'].apply(
    lambda x: pd.Series(get_location(x))
)

# In Datenbank schreiben
engine = create_engine('postgresql://user:pass@host/dbname')
df.to_sql('bird_detections', engine, if_exists='append', index=False)

# SQL-Abfrage mit geografischen Funktionen
# SELECT species_name, COUNT(*) 
# FROM bird_detections 
# WHERE ST_DWithin(
#     ST_Point(longitude, latitude)::geography,
#     ST_Point(10.0, 51.0)::geography,
#     10000  -- 10 km Radius
# )
# GROUP BY species_name;
```

**InfluxDB für Zeitreihen:**

Für zeitbasierte Analysen und Dashboards:

```python
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

client = InfluxDBClient(url="http://localhost:8086", token="mytoken", org="myorg")
write_api = client.write_api(write_options=SYNCHRONOUS)

df = pd.read_parquet("ergebnisse.parquet")

for _, row in df.iterrows():
    point = Point("bird_detection") \
        .tag("species", row['species_name']) \
        .tag("site", row['input']) \
        .field("confidence", row['confidence']) \
        .time(int(row['start_time'] * 1e9))  # Nanosekunden
    
    write_api.write(bucket="birds", record=point)

# Grafana-Dashboard kann dann Zeitreihen visualisieren
```

### Austausch mit R

Für statistische Analysen in R können Sie Parquet-Dateien nutzen:

```r
library(arrow)
library(dplyr)

# Ergebnisse laden
detections <- read_parquet("ergebnisse.parquet")

# Analyse
species_summary <- detections %>%
  group_by(species_name) %>%
  summarise(
    n = n(),
    mean_confidence = mean(confidence),
    sd_confidence = sd(confidence)
  ) %>%
  arrange(desc(n))

print(species_summary)

# Zeitreihen-Plot
library(ggplot2)

detections %>%
  mutate(hour = floor(start_time / 3600)) %>%
  group_by(hour, species_name) %>%
  summarise(count = n()) %>%
  ggplot(aes(x = hour, y = count, color = species_name)) +
  geom_line() +
  theme_minimal()
```

---

## Lizenz und rechtliche Hinweise

**BirdNET-Lizenz:**

BirdNET wird unter einer offenen Lizenz veröffentlicht (bitte prüfen Sie die genaue Lizenz im Repository). Die vortrainierten Modelle basieren auf Trainingsdaten aus verschiedenen Quellen mit unterschiedlichen Lizenzen.

**Kommerzielle Nutzung:**

Die kommerzielle Nutzung von BirdNET ist grundsätzlich möglich, aber Sie sollten die spezifischen Lizenzbedingungen prüfen. Einige Trainingsdatensätze (z.B. Xeno-Canto) haben Lizenzen, die kommerzielle Nutzung einschränken könnten.

**Daten-Veröffentlichung:**

Wenn Sie BirdNET-Ergebnisse veröffentlichen oder teilen:

- Zitieren Sie die Original-Publikation von BirdNET
- Geben Sie die Modellversion an
- Dokumentieren Sie die verwendeten Parameter
- Beachten Sie Datenschutz bei Standortdaten

**Wissenschaftliche Verwendung:**

Für wissenschaftliche Publikationen sollten Sie:

- Die Methodik detailliert beschreiben (Modellversion, Parameter, Hardware)
- Validierungsschritte dokumentieren (z.B. manuelle Überprüfung einer Stichprobe)
- Limitationen diskutieren (z.B. geografische Bias, saisonale Einschränkungen)
- Rohdaten und Code nach Möglichkeit teilen

**Zitation (Beispiel):**

```
Kahl, S., Wood, C. M., Eibl, M., & Klinck, H. (2021). BirdNET: A deep learning solution for avian diversity monitoring. Ecological Informatics, 61, 101236.
```

*(Hinweis: Bitte prüfen Sie die aktuelle Zitierempfehlung im offiziellen BirdNET-Repository.)*

---

## Weiterführende Ressourcen

**Offizielle Quellen:**

- **GitHub-Repository**: [github.com/kahst/BirdNET-Analyzer](https://github.com/kahst/BirdNET-Analyzer) (bitte prüfen)
- **Modell-Downloads**: [zenodo.org](https://zenodo.org) - Suche nach "BirdNET v2.4"
- **Publikationen**: Suche nach "BirdNET" in Google Scholar

**Community und Support:**

- **Issues**: GitHub Issues für Bug-Reports und Feature-Requests
- **Diskussionen**: GitHub Discussions für allgemeine Fragen
- **Mailinglisten**: *(Falls vorhanden - bitte prüfen)*

**Verwandte Tools:**

- **BirdNET-Pi**: Raspberry Pi-Distribution für Edge-Deployment
- **BirdNET-Analyzer**: Original-Implementierung mit GUI
- **Raven Pro**: Kommerzielle Software für Audio-Annotation
- **Audacity**: Open-Source Audio-Editor für manuelle Validierung

**Lernressourcen:**

- **Xeno-Canto**: Umfangreichste Datenbank für Vogelstimmen weltweit
- **eBird**: Citizen Science Plattform für Vogelbeobachtungen
- **Macaulay Library**: Archiv für naturbezogene Audio/Video
- **Cornell Lab of Ornithology**: Bildungsressourcen und Forschung

**Machine Learning Background:**

- **Transfer Learning**: Verwenden Sie vortrainierte Embeddings für eigene Aufgaben
- **Active Learning**: Optimieren Sie Annotation-Effort durch gezielte Sample-Auswahl
- **Few-Shot Learning**: Trainieren Sie Classifier für seltene Arten mit wenigen Beispielen

---

## Schlusswort

Diese Dokumentation hat Ihnen einen umfassenden Überblick über die BirdNET-API gegeben. Sie haben gelernt, wie die verschiedenen Module zusammenspielen, welche Parameter für unterschiedliche Anwendungsfälle optimal sind und wie Sie BirdNET in Ihre eigenen Workflows integrieren können.

BirdNET ist ein leistungsfähiges Werkzeug für die automatisierte Vogelartenerkennung, aber es ist wichtig zu verstehen, dass es sich um ein statistisches Modell handelt, das nicht perfekt ist. Falsch-positive und falsch-negative Erkennungen sind unvermeidlich, insbesondere bei seltenen Arten, schwierigen Aufnahmebedingungen oder Arten außerhalb der Trainingsverteilung. Eine manuelle Validierung einer Stichprobe wird für wissenschaftliche Anwendungen empfohlen.

Die kontinuierliche Weiterentwicklung von BirdNET bedeutet, dass neue Versionen verbesserte Modelle, zusätzliche Funktionen oder geänderte APIs bringen können. Konsultieren Sie regelmäßig die offizielle Dokumentation und das GitHub-Repository für Updates.

Wir hoffen, dass diese Dokumentation Ihnen hilft, BirdNET effektiv zu nutzen und wertvolle Erkenntnisse aus Ihren Audiodaten zu gewinnen. Viel Erfolg bei Ihren Projekten!

---

**Dokumentations-Version**: 1.0  
**Zuletzt aktualisiert**: Januar 2025  
**BirdNET-Version**: v2.4

*(Hinweis: Teile dieser Dokumentation wurden aus Quellcode-Analyse abgeleitet und könnten Ungenauigkeiten enthalten. Bei Unsicherheiten konsultieren Sie bitte die offizielle Dokumentation oder den Quellcode direkt.)*