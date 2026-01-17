# birdnet-audio-walker
Simple solution for statistical analysis of bird song recordings with birdnet.

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