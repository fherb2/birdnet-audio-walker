# birdnet-audio-walker
Solution for statistical analysis and acoustic evaluation of bird song recordings with birdnet.

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