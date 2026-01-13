"""
Species name translation table management.
Downloads and caches translation table from karlincam.cz.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
from config import SPECIES_CACHE_DIR, SPECIES_CACHE_MAX_AGE_DAYS, SPECIES_TABLE_URL


def download_species_table(cache_dir: str = SPECIES_CACHE_DIR) -> pd.DataFrame:
    """
    Download species name translation table from karlincam.cz.
    
    Caches result in cache_dir/species_names.csv. If cache exists and is 
    younger than SPECIES_CACHE_MAX_AGE_DAYS, loads from cache.
    
    Args:
        cache_dir: Directory for caching
        
    Returns:
        DataFrame with columns: ['scientific', 'en', 'de', 'cs']
    """
    cache_path = Path(cache_dir) / "species_names.csv"
    
    # Check if cache exists and is recent
    if cache_path.exists():
        cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        if cache_age < timedelta(days=SPECIES_CACHE_MAX_AGE_DAYS):
            logger.info(f"Loading species table from cache: {cache_path}")
            return pd.read_csv(cache_path)
        else:
            logger.info(f"Cache outdated (age: {cache_age.days} days), downloading fresh table")
    
    # Download and parse HTML table
    try:
        logger.info(f"Downloading species table from {SPECIES_TABLE_URL}")
        response = requests.get(SPECIES_TABLE_URL, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the table
        table = soup.find('table')
        if not table:
            raise ValueError("No table found in HTML")
        
        # Parse table headers and rows
        headers = []
        header_row = table.find('tr')
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all('td')]
        
        # Expected headers: Scientific name, en, de, cs
        if not headers or len(headers) < 4:
            raise ValueError(f"Unexpected table headers: {headers}")
        
        # Parse data rows
        data = []
        for row in table.find_all('tr')[1:]:  # Skip header row
            cols = row.find_all('td')
            if len(cols) >= 4:
                data.append([
                    cols[0].get_text(strip=True),  # Scientific name
                    cols[1].get_text(strip=True),  # en
                    cols[2].get_text(strip=True),  # de
                    cols[3].get_text(strip=True)   # cs
                ])
        
        if not data:
            raise ValueError("No data rows found in table")
        
        # Create DataFrame
        df = pd.DataFrame(data, columns=['scientific', 'en', 'de', 'cs'])
        
        # Save to cache
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_path, index=False)
        logger.info(f"Species table cached: {len(df)} entries in {cache_path}")
        
        return df
        
    except Exception as e:
        logger.error(f"Error downloading species table: {e}")
        
        # Try to load from cache even if outdated
        if cache_path.exists():
            logger.warning("Using outdated cache as fallback")
            return pd.read_csv(cache_path)
        else:
            logger.error("No cache available, returning empty DataFrame")
            return pd.DataFrame(columns=['scientific', 'en', 'de', 'cs'])


def translate_species_name(
    scientific_name: str,
    translation_table: pd.DataFrame
) -> dict:
    """
    Translate scientific name to German and Czech.
    
    Args:
        scientific_name: Scientific species name (e.g., "Parus major")
        translation_table: Translation DataFrame
        
    Returns:
        dict with keys: 'scientific', 'en', 'de', 'cs'
        If not found, 'en', 'de', 'cs' are set to scientific_name
    """
    # Look up in translation table
    match = translation_table[translation_table['scientific'] == scientific_name]
    
    if not match.empty:
        row = match.iloc[0]
        return {
            'scientific': scientific_name,
            'en': row['en'],
            'de': row['de'],
            'cs': row['cs']
        }
    else:
        # Not found - use scientific name for all
        logger.debug(f"Species not found in translation table: {scientific_name}")
        return {
            'scientific': scientific_name,
            'en': scientific_name,
            'de': scientific_name,
            'cs': scientific_name
        }
