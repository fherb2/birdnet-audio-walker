# Birdnet-Audio-Walker

A walker in two senses:

 - Walks through your audio folders and indexes BirdNET bird call recognition in one database per folder.
 - You can browse through these databases and explore the bird song recognition data.

Solution for statistical analysis and acoustic evaluation of bird song recordings based on BirdNET recognition.

# Project state

- ready to use Docker images (audio file analysis with birdnet only thith CUDA/GPU; other tooling don't need CUDA)
- mass analysis into SQLite databases (productive)
- acoutic validating of database entries (development; cli and with an audio announcement of the audio snippet currently being played)
    - use via Streamlit interface

# The pure walker

Goes to the input folder (recursive is default) and creates SQLite databases for each folder content.

```poetry run birdnet-walker INPUT_FOLDER```

or 

```
poetry shell
birdnet-walker INPUT_FOLDER
```

Do

```poetry run birdnet-walker -h```

to get all options.