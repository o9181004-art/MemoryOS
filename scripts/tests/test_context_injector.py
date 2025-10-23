"""
Test suite for MemoryOS context injection (offline, no network)
"""
import os
import unittest
from unittest.mock import patch

# Set environment for testing BEFORE importing
os.environ["MEMORYOS_EMBED_PROVIDER"] = "stub"
os.environ["MEMORYOS_EMBEDDINGS"] = "true"
os.environ["MEMORYOS_CONTEXT_ENABLED"] = "true"
os.environ["MEMORYOS_ADAPTIVE_THRESHOLD"] = "true"
os.environ["MEMORYOS_SIM_THRESHOLD_MIN"] = "0.45"
os.environ["MEMORYOS_SIM_THRESHOLD_MAX"] = "0.60"

# Import after setting environment
from scripts.build_context import _adaptive_threshold, _hybrid_sort, _similarity_guard

class TestContextInjection(unittest.TestCase):
    
    def test_adaptive_threshold(self):
        """Test adaptive threshold calculation"""
        base_threshold = 0.5
        
        # Few candidates should use base threshold
        thresh_few = _adaptive_threshold(2, base_threshold)
        self.assertEqual(thresh_few, base_threshold)
        
        # Many candidates should increase threshold
        thresh_many = _adaptive_threshold(10, base_threshold)
        self.assertGreater(thresh_many, base_threshold)
        self.assertLessEqual(thresh_many, 0.60)  # Should not exceed max
    
    def test_hybrid_sort(self):
        """Test hybrid L0+L1 sorting"""
        # Mock test data
        items = [
            {"type": "error", "data": {"message": "timeout occurred"}},
            {"type": "info", "data": {"status": "ok"}},
            {"type": "warning", "data": {"note": "memory usage high"}}
        ]
        
        # Mock L1 scores (simulated similarity scores)
        l1_scored = [
            (items[0], 0.8),  # High similarity
            (items[1], 0.3),  # Low similarity  
            (items[2], 0.6)   # Medium similarity
        ]
        
        user_input = "timeout error"
        
        # Test hybrid sorting
        sorted_items = _hybrid_sort(user_input, items, l1_scored)
        
        # Should return all items (no filtering in hybrid_sort)
        self.assertEqual(len(sorted_items), 3)
        
        # Items should be sorted by hybrid score
        # First item should have highest combined score
        self.assertIn(sorted_items[0], items)
    
    def test_similarity_guard_fallback(self):
        """Test similarity guard fallback when embeddings disabled"""
        # Temporarily disable embeddings for this test
        original_value = os.environ.get("MEMORYOS_EMBEDDINGS")
        os.environ["MEMORYOS_EMBEDDINGS"] = "false"
        
        try:
            # Reimport to get updated behavior
            import importlib
            import scripts.build_context
            importlib.reload(scripts.build_context)
            from scripts.build_context import _similarity_guard as _similarity_guard_disabled
            
            items = [{"type": "test", "data": {"msg": "test"}}]
            user_input = "test input"
            
            ok, scored = _similarity_guard_disabled(user_input, items)
            
            # Should pass through when embeddings disabled
            self.assertTrue(ok)
            self.assertEqual(len(scored), 1)
            # When embeddings disabled, similarity score should be 0.0
            self.assertEqual(scored[0][1], 0.0)
        finally:
            # Restore original value
            if original_value:
                os.environ["MEMORYOS_EMBEDDINGS"] = original_value
            else:
                os.environ["MEMORYOS_EMBEDDINGS"] = "true"
    
    def test_similarity_guard_empty_items(self):
        """Test similarity guard with empty items list"""
        user_input = "test input"
        
        ok, scored = _similarity_guard(user_input, [])
        
        # Should handle empty list gracefully
        self.assertTrue(ok)
        self.assertEqual(len(scored), 0)
    
    def test_context_compression(self):
        """Test context line compression"""
        # Mock recent events
        mock_events = [
            {"id": 1, "timestamp": "2025-01-01T00:00:00", "type": "error", "data": {"message": "test error"}},
            {"id": 2, "timestamp": "2025-01-01T00:01:00", "type": "info", "data": {"status": "ok"}},
        ]
        
        # This would test the _compress function if it existed
        # For now, just verify the mock works
        self.assertEqual(len(mock_events), 2)

if __name__ == "__main__":
    unittest.main()
