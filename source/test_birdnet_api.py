#!/usr/bin/env python3
"""Quick test of BirdNET API"""

import birdnet
import sys

# Test 1: Load model
print("Loading model...")
model = birdnet.load("acoustic", "2.4", "pb")
print(f"Model type: {type(model)}")

# Test 2: Check if we have a WAV file
if len(sys.argv) < 2:
    print("Usage: python test_birdnet_api.py <path_to_wav_file>")
    sys.exit(1)

wav_file = sys.argv[1]

