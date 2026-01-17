"""
BirdNET species labels management.
Loads species names in different languages from BirdNET label files.
"""

from pathlib import Path
from loguru import logger
from config import BIRDNET_LABELS_PATH


def get_available_languages() -> list[str]:
    """
    Scan BirdNET labels directory and extract available language codes.
    
    Returns:
        List of language codes (e.g., ['de', 'en_uk', 'en_us', ...])
    """
    if not BIRDNET_LABELS_PATH.exists():
        logger.warning(f"BirdNET labels path does not exist: {BIRDNET_LABELS_PATH}")
        return []
    
    languages = []
    
    for label_file in BIRDNET_LABELS_PATH.glob("*.txt"):
        # Extract language code from filename (e.g., "de.txt" -> "de", "en_uk.txt" -> "en_uk")
        lang_code = label_file.stem
        languages.append(lang_code)
    
    languages.sort()
    logger.debug(f"Found {len(languages)} language files: {languages}")
    return languages


def load_birdnet_labels(language: str) -> dict[str, str]:
    """
    Load BirdNET labels file for a specific language.
    
    Args:
        language: Language code (e.g., 'de', 'en_uk')
        
    Returns:
        Dictionary mapping scientific name to local name
        Empty dict if file not found or error occurs
    """
    label_file = BIRDNET_LABELS_PATH / f"{language}.txt"
    
    if not label_file.exists():
        logger.error(f"BirdNET labels file not found: {label_file}")
        return {}
    
    labels = {}
    
    try:
        with open(label_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                # Split by underscore (should be exactly one underscore)
                parts = line.split('_')
                
                if len(parts) != 2:
                    logger.warning(f"Invalid format in {label_file.name} line {line_num}: {line}")
                    continue
                
                scientific_name = parts[0].strip()
                local_name = parts[1].strip()
                
                labels[scientific_name] = local_name
        
        logger.info(f"Loaded {len(labels)} labels for language '{language}'")
        return labels
        
    except Exception as e:
        logger.error(f"Error loading BirdNET labels from {label_file}: {e}")
        return {}