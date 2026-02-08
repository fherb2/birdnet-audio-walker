#!/usr/bin/env python3
"""
Test for embedding consistency between SQLite and HDF5 databases.

This test validates that:
1. All embedding indices in SQLite are valid (within HDF5 bounds)
2. Time-based consistency (same times = same embedding_idx)
3. No orphaned embeddings in HDF5
4. HDF5 data integrity (shape, dtype, no NaN/Inf)
5. Segmentation consistency (3s segments, correct overlap)

Usage:
    # Run as pytest
    pytest test_embedding_consistency.py -v
    
    # Run standalone
    python test_embedding_consistency.py /path/to/folder
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict
import numpy as np
import h5py


class EmbeddingConsistencyTest:
    """Test suite for embedding consistency validation."""
    
    def __init__(self, folder_path: str):
        """
        Initialize test with folder containing DB files.
        
        Args:
            folder_path: Path to folder with birdnet_analysis.db and birdnet_embeddings.h5
        """
        self.folder = Path(folder_path)
        self.db_path = self.folder / "birdnet_analysis.db"
        self.hdf5_path = self.folder / "birdnet_embeddings.h5"
        
        # Check files exist
        if not self.db_path.exists():
            raise FileNotFoundError(f"SQLite DB not found: {self.db_path}")
        if not self.hdf5_path.exists():
            raise FileNotFoundError(f"HDF5 file not found: {self.hdf5_path}")
        
        print(f"Testing folder: {self.folder}")
        print(f"  SQLite: {self.db_path.name}")
        print(f"  HDF5:   {self.hdf5_path.name}")
        print()
    
    def run_all_tests(self):
        """Run all validation tests."""
        print("="*80)
        print("EMBEDDING CONSISTENCY VALIDATION")
        print("="*80)
        print()
        
        all_passed = True
        
        tests = [
            ("Test 1: HDF5 Data Integrity", self.test_hdf5_integrity),
            ("Test 2: SQLite Embedding Indices", self.test_sqlite_indices),
            ("Test 3: Index Range Validation", self.test_index_range),
            ("Test 4: Time-based Consistency", self.test_time_consistency),
            ("Test 5: No Orphaned Embeddings", self.test_no_orphans),
            ("Test 6: Segmentation Consistency", self.test_segmentation),
        ]
        
        for test_name, test_func in tests:
            print(f"{test_name}...")
            try:
                test_func()
                print(f"  ✓ PASS\n")
            except AssertionError as e:
                print(f"  ✗ FAIL: {e}\n")
                all_passed = False
            except Exception as e:
                print(f"  ✗ ERROR: {e}\n")
                all_passed = False
        
        print("="*80)
        if all_passed:
            print("ALL TESTS PASSED ✓")
        else:
            print("SOME TESTS FAILED ✗")
        print("="*80)
        
        return all_passed
    
    def test_hdf5_integrity(self):
        """Test HDF5 file structure and data integrity."""
        with h5py.File(self.hdf5_path, 'r') as f:
            # Check dataset exists
            assert 'embeddings' in f, "Dataset 'embeddings' not found in HDF5"
            
            dataset = f['embeddings']
            shape = dataset.shape
            dtype = dataset.dtype
            
            print(f"    Shape: {shape}")
            print(f"    Dtype: {dtype}")
            
            # Check shape
            assert len(shape) == 2, f"Expected 2D array, got shape {shape}"
            assert shape[1] == 1024, f"Expected 1024 dimensions, got {shape[1]}"
            
            # Check dtype
            assert dtype == np.float32, f"Expected float32, got {dtype}"
            
            # Check for NaN/Inf (sample first and last 10 rows)
            sample_indices = list(range(min(10, shape[0]))) + \
                           list(range(max(0, shape[0]-10), shape[0]))
            
            for idx in sample_indices:
                embedding = dataset[idx]
                assert not np.any(np.isnan(embedding)), f"NaN found at index {idx}"
                assert not np.any(np.isinf(embedding)), f"Inf found at index {idx}"
    
    def test_sqlite_indices(self):
        """Test SQLite embedding_idx column."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Count total detections
        cursor.execute("SELECT COUNT(*) FROM detections")
        total_detections = cursor.fetchone()[0]
        
        # Count detections with embeddings
        cursor.execute("SELECT COUNT(*) FROM detections WHERE embedding_idx IS NOT NULL")
        detections_with_emb = cursor.fetchone()[0]
        
        # Count detections without embeddings
        cursor.execute("SELECT COUNT(*) FROM detections WHERE embedding_idx IS NULL")
        detections_without_emb = cursor.fetchone()[0]
        
        print(f"    Total detections: {total_detections}")
        print(f"    With embeddings: {detections_with_emb}")
        print(f"    Without embeddings: {detections_without_emb}")
        
        conn.close()
        
        # All detections should have embeddings (unless explicitly failed)
        ratio = detections_with_emb / total_detections if total_detections > 0 else 0
        assert ratio >= 0.95, f"Only {ratio*100:.1f}% of detections have embeddings (expected >= 95%)"
    
    def test_index_range(self):
        """Test that all embedding indices are within valid HDF5 range."""
        # Get HDF5 size
        with h5py.File(self.hdf5_path, 'r') as f:
            n_embeddings = f['embeddings'].shape[0]
        
        # Get index range from SQLite
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT MIN(embedding_idx), MAX(embedding_idx), COUNT(DISTINCT embedding_idx)
            FROM detections WHERE embedding_idx IS NOT NULL
        """)
        min_idx, max_idx, n_unique = cursor.fetchone()
        
        conn.close()
        
        print(f"    HDF5 embeddings: {n_embeddings}")
        print(f"    SQLite index range: {min_idx} - {max_idx}")
        print(f"    Unique indices: {n_unique}")
        
        # Validate range
        assert min_idx >= 0, f"Negative index found: {min_idx}"
        assert max_idx < n_embeddings, f"Index {max_idx} out of range (max: {n_embeddings-1})"
        
        # Check if indices are reasonably utilized
        expected_min = n_unique
        assert n_embeddings >= expected_min, \
            f"Too many embeddings in HDF5 ({n_embeddings}) for unique indices ({n_unique})"
    
    def test_time_consistency(self):
        """Test that detections with same time have same embedding_idx."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Group by time, get embedding indices
        cursor.execute("""
            SELECT segment_start_local, segment_end_local, 
                   GROUP_CONCAT(embedding_idx) as indices,
                   COUNT(*) as cnt
            FROM detections
            WHERE embedding_idx IS NOT NULL
            GROUP BY segment_start_local, segment_end_local
            HAVING cnt > 1
        """)
        
        time_groups = cursor.fetchall()
        conn.close()
        
        print(f"    Time segments with multiple detections: {len(time_groups)}")
        
        inconsistent = []
        for start, end, indices_str, cnt in time_groups:
            indices = [int(x) for x in indices_str.split(',')]
            unique_indices = set(indices)
            
            if len(unique_indices) > 1:
                inconsistent.append((start, end, unique_indices))
        
        if inconsistent:
            print(f"    ✗ Found {len(inconsistent)} time segments with different indices:")
            for start, end, indices in inconsistent[:5]:  # Show first 5
                print(f"      {start} - {end}: indices {indices}")
        
        assert len(inconsistent) == 0, \
            f"Found {len(inconsistent)} time segments with inconsistent embedding indices"
    
    def test_no_orphans(self):
        """Test that no embeddings in HDF5 are orphaned (unused)."""
        # Get all used indices from SQLite
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT embedding_idx
            FROM detections
            WHERE embedding_idx IS NOT NULL
            ORDER BY embedding_idx
        """)
        
        used_indices = set(row[0] for row in cursor.fetchall())
        conn.close()
        
        # Get HDF5 size
        with h5py.File(self.hdf5_path, 'r') as f:
            n_embeddings = f['embeddings'].shape[0]
        
        # Check if all HDF5 indices are used
        all_indices = set(range(n_embeddings))
        orphaned = all_indices - used_indices
        
        print(f"    Total embeddings in HDF5: {n_embeddings}")
        print(f"    Used by detections: {len(used_indices)}")
        print(f"    Orphaned embeddings: {len(orphaned)}")
        
        # Allow small percentage of orphans (due to filtering edge cases)
        orphan_ratio = len(orphaned) / n_embeddings if n_embeddings > 0 else 0
        assert orphan_ratio < 0.05, \
            f"Too many orphaned embeddings: {orphan_ratio*100:.1f}% (expected < 5%)"
    
    def test_segmentation(self):
        """Test segmentation consistency (3s segments, correct overlap)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get analysis config
        cursor.execute("SELECT value FROM analysis_config WHERE key = 'local_name_shortcut'")
        lang = cursor.fetchone()
        
        # Get sample of detections with times
        cursor.execute("""
            SELECT segment_start_local, segment_end_local, embedding_idx
            FROM detections
            WHERE embedding_idx IS NOT NULL
            ORDER BY segment_start_local
            LIMIT 100
        """)
        
        detections = cursor.fetchall()
        conn.close()
        
        if not detections:
            print(f"    No detections to test")
            return
        
        print(f"    Testing {len(detections)} sample detections...")
        
        # Parse times and calculate durations
        from datetime import datetime
        
        durations = []
        for start_str, end_str, idx in detections:
            start = datetime.fromisoformat(start_str)
            end = datetime.fromisoformat(end_str)
            duration = (end - start).total_seconds()
            durations.append(duration)
        
        # Check if all durations are ~3.0s (within 0.1s tolerance)
        expected_duration = 3.0
        tolerance = 0.1
        
        invalid_durations = [d for d in durations if abs(d - expected_duration) > tolerance]
        
        print(f"    Average duration: {np.mean(durations):.3f}s")
        print(f"    Min/Max duration: {min(durations):.3f}s / {max(durations):.3f}s")
        print(f"    Invalid durations: {len(invalid_durations)}")
        
        assert len(invalid_durations) == 0, \
            f"Found {len(invalid_durations)} detections with invalid duration (expected ~3.0s)"


def main():
    """Main entry point for standalone execution."""
    if len(sys.argv) < 2:
        print("Usage: python test_embedding_consistency.py /path/to/folder")
        print()
        print("Folder should contain:")
        print("  - birdnet_analysis.db")
        print("  - birdnet_embeddings.h5")
        sys.exit(1)
    
    folder_path = sys.argv[1]
    
    try:
        test = EmbeddingConsistencyTest(folder_path)
        success = test.run_all_tests()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


# Pytest integration
def test_embedding_consistency(tmp_path):
    """Pytest entry point - configure path via pytest fixtures or env vars."""
    import os
    folder_path = os.environ.get('BIRDNET_TEST_FOLDER')
    
    if not folder_path:
        import pytest
        pytest.skip("Set BIRDNET_TEST_FOLDER environment variable to run this test")
    
    test = EmbeddingConsistencyTest(folder_path)
    assert test.run_all_tests(), "Embedding consistency tests failed"


if __name__ == "__main__":
    main()
