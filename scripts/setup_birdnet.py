#!/usr/bin/env python3
"""
Setup script for BirdNET model download.

Downloads the BirdNET model with retry logic to handle rate limits.
Run this once before first use: python setup_birdnet.py
"""

import time
import sys
from loguru import logger


def setup_birdnet_model():
    """
    Download and setup BirdNET model with retry logic.
    
    Returns:
        bool: True if successful, False otherwise
    """
    import birdnet
    
    max_retries = 2
    base_wait = 60  # Start with 60 seconds
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Attempting to load BirdNET model (attempt {attempt}/{max_retries})...")
            model = birdnet.load("acoustic", "2.4", "tf")
            logger.success("BirdNET model loaded successfully!")
            return True
            
        except ValueError as e:
            if "403" in str(e):
                if attempt < max_retries:
                    wait_time = base_wait * (2 ** (attempt - 1))  # Exponential backoff
                    logger.warning(
                        f"Rate limit hit (403). Waiting {wait_time} seconds before retry..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error("Maximum retries reached. Rate limit persists.")
                    logger.info("\n" + "="*80)
                    logger.info("MANUAL INSTALLATION REQUIRED")
                    logger.info("="*80)
                    logger.info("Download manually with:")
                    logger.info("  cd /tmp")
                    logger.info("  wget https://zenodo.org/records/15050749/files/BirdNET_v2.4_protobuf.zip")
                    logger.info("  unzip -q BirdNET_v2.4_protobuf.zip -d birdnet_extract")
                    logger.info("")
                    logger.info("Then install with:")
                    logger.info("  mkdir -p ~/.local/share/birdnet/acoustic-models/v2.4/pb/")
               #     logger.info("  mkdir -p ~/.local/share/birdnet/acoustic-models/v2.4/pb/labels")
                    logger.info("  cp -r /tmp/birdnet_extract/audio-model ~/.local/share/birdnet/acoustic-models/v2.4/pb/model-fp32")
                    logger.info("  cp -r /tmp/birdnet_extract/labels ~/.local/share/birdnet/acoustic-models/v2.4/pb/labels")
                    logger.info("="*80)
                    return False
            else:
                logger.error(f"Unexpected error: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Unexpected error during model loading: {e}")
            return False
    
    return False


def main():
    """Main setup entry point."""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    logger.info("="*80)
    logger.info("BirdNET Model Setup")
    logger.info("="*80)
    logger.info("This will download the BirdNET acoustic model (~119 MB)")
    logger.info("The download may take several minutes depending on your connection.")
    logger.info("")
    
    success = setup_birdnet_model()
    
    if success:
        logger.info("")
        logger.success("Setup complete! You can now run the analyzer.")
        return 0
    else:
        logger.error("")
        logger.error("Setup failed. Please follow manual installation instructions above.")
        return 1


if __name__ == "__main__":
    exit(main())
