"""
Shared utility functions for Streamlit pages.
"""

from pathlib import Path
from typing import List
from loguru import logger


def find_databases_recursive(root_path: Path, max_results: int = 100) -> List[Path]:
    """
    Find all birdnet_analysis.db files recursively under root_path.
    
    Args:
        root_path: Root directory to search
        max_results: Maximum number of databases to find (default: 100)
        
    Returns:
        Sorted list of database paths
    """
    databases = []
    
    try:
        # Use rglob to recursively find all birdnet_analysis.db files
        for db_path in root_path.rglob("birdnet_analysis.db"):
            databases.append(db_path)
            if len(databases) >= max_results:
                logger.warning(f"Reached maximum of {max_results} databases, stopping search")
                break
        
        return sorted(databases)
        
    except Exception as e:
        logger.error(f"Error searching for databases: {e}")
        return []

