"""
Bird species name translation for BirdNET Play.

Loads label files from:
  1. BIRD_LANGUAGES_PATH  (local overrides, priority)
  2. BIRDNET_LABELS_PATH  (bundled with BirdNET model)

Label file format:  <scientific_name>_<local_name>  (one entry per line)
File naming:        <language_code>.txt  (e.g. de.txt, en_uk.txt)

Loaded dicts are cached at module level – files are read only once per
language per process lifetime.
"""

from pathlib import Path
from loguru import logger

from .config import BIRDNET_LABELS_PATH, BIRD_LANGUAGES_PATH


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_label_cache: dict[str, dict[str, str]] = {}
# Key: language code, Value: {scientific_name: local_name}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_available_languages() -> list[str]:
    """
    Return sorted list of all available language codes.

    Union of *.txt files found in BIRD_LANGUAGES_PATH and BIRDNET_LABELS_PATH.
    Files must follow the naming convention  <language_code>.txt.

    Returns:
        Sorted list of language code strings (e.g. ['cs', 'de', 'en_uk', ...]).
        Empty list if neither directory exists.
    """
    codes: set[str] = set()

    for label_dir in (BIRD_LANGUAGES_PATH, BIRDNET_LABELS_PATH):
        if label_dir is not None and label_dir.exists():
            for f in label_dir.glob("*.txt"):
                codes.add(f.stem)
        elif label_dir is not None:
            logger.debug(f"Label directory not found: {label_dir}")

    languages = sorted(codes)
    logger.debug(f"Available bird-name languages: {languages}")
    return languages


def load_labels(language: str) -> dict[str, str]:
    """
    Load labels for a language. Result is cached after the first call.

    Local BIRD_LANGUAGES_PATH takes priority over BIRDNET_LABELS_PATH.
    Falls back to 'de' with a warning if the requested language is not found
    in either location.

    Args:
        language: Language code (e.g. 'de', 'en_uk', 'cs').

    Returns:
        Dict mapping scientific_name → local_name.
        Empty dict if even the fallback language cannot be loaded.
    """
    if language in _label_cache:
        return _label_cache[language]

    labels = _load_from_dirs(language)

    if not labels and language != 'de':
        logger.warning(
            f"Bird-name language '{language}' not found – falling back to 'de'"
        )
        labels = _load_from_dirs('de')
        # Cache under both keys so the caller's language also hits the cache
        _label_cache['de'] = labels
        _label_cache[language] = labels
        return labels

    _label_cache[language] = labels
    return labels


def translate(scientific_name: str, language: str) -> str:
    """
    Translate a scientific species name to the target language.

    Args:
        scientific_name: Scientific name (e.g. 'Parus major').
        language:        Language code (e.g. 'de').

    Returns:
        Local name if found, otherwise scientific_name as fallback.
    """
    labels = load_labels(language)
    return labels.get(scientific_name, scientific_name)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_from_dirs(language: str) -> dict[str, str]:
    """
    Try to load a label file for *language* from the configured directories.

    BIRD_LANGUAGES_PATH is checked first (local overrides).
    Falls through to BIRDNET_LABELS_PATH if not found there.

    Returns:
        Parsed label dict, or empty dict if not found in either location.
    """
    search_dirs = []
    if BIRD_LANGUAGES_PATH is not None:
        search_dirs.append(BIRD_LANGUAGES_PATH)
    if BIRDNET_LABELS_PATH is not None:
        search_dirs.append(BIRDNET_LABELS_PATH)

    for label_dir in search_dirs:
        label_file = label_dir / f"{language}.txt"
        if label_file.exists():
            result = _parse_label_file(label_file)
            if result:
                logger.info(
                    f"Loaded {len(result)} labels for '{language}' "
                    f"from {label_dir.name}/"
                )
                return result

    logger.error(f"No label file found for language '{language}' in any configured directory")
    return {}


def _parse_label_file(label_file: Path) -> dict[str, str]:
    """
    Parse a BirdNET label file.

    Expected line format:  <scientific_name>_<local_name>
    Lines that do not contain exactly one underscore separator are skipped
    with a warning.

    Args:
        label_file: Path to the .txt label file.

    Returns:
        Dict {scientific_name: local_name}.  Empty dict on read error.
    """
    labels: dict[str, str] = {}

    try:
        with open(label_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                # Split on underscore – exactly one separator expected
                parts = line.split('_', 1)
                if len(parts) != 2:
                    logger.warning(
                        f"{label_file.name} line {line_num}: "
                        f"unexpected format, skipping: {line!r}"
                    )
                    continue

                scientific_name = parts[0].strip()
                local_name      = parts[1].strip()

                if scientific_name:
                    labels[scientific_name] = local_name

    except Exception as e:
        logger.error(f"Error reading label file {label_file}: {e}")
        return {}

    return labels
