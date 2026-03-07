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


def initialize_session_state_from_args():
    """
    Initialize session state from command line arguments.
    Called once at app startup.
    
    Returns:
        True if initialization successful, False otherwise
    """
    import sys
    import streamlit as st
    
    if 'db_path' in st.session_state:
        # Already initialized
        return True
    
    # Check command line arguments
    if len(sys.argv) < 2:
        st.session_state['db_path'] = None
        st.session_state['root_path'] = None
        st.session_state['read_only'] = False
        return False

    # Check for read-only flag
    st.session_state['read_only'] = '--read-only' in sys.argv
    
    input_path = Path(sys.argv[1])
    
    # Check if it's a database file or directory
    if input_path.is_file() and input_path.name == 'birdnet_analysis.db':
        # Direct database file
        st.session_state['db_path'] = input_path
        st.session_state['root_path'] = input_path.parent
        return True
        
    elif input_path.is_dir():
        # Directory - search for databases
        st.session_state['root_path'] = input_path
        # Find first database as initial selection
        available_dbs = find_databases_recursive(input_path)
        if available_dbs:
            st.session_state['db_path'] = available_dbs[0]
            return True
        else:
            st.session_state['db_path'] = None
            return False
            
    else:
        st.session_state['db_path'] = None
        st.session_state['root_path'] = None
        return False
