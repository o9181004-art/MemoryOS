"""
Test suite for MemoryOS Memory Aging (offline, no network)
"""
import os
import unittest
from datetime import datetime, timedelta

# Set environment for testing
os.environ["MEMORYOS_AGING_DECAY_RATE"] = "0.95"
os.environ["MEMORYOS_AGING_INTERVAL"] = "60"

# Import after setting environment
from scripts.memory_aging import age_memory, apply_aging_to_items

class TestMemoryAging(unittest.TestCase):
    
    def test_age_memory_fresh(self):
        """Test that fresh memories retain original weight"""
        # Fresh memory (within threshold)
        fresh_timestamp = datetime.now().isoformat()
        weight = 1.0
        
        aged_weight = age_memory(fresh_timestamp, weight)
        self.assertEqual(aged_weight, weight, "Fresh memory should retain original weight")
    
    def test_age_memory_old(self):
        """Test that old memories get reduced weight"""
        # Old memory (beyond threshold)
        old_timestamp = (datetime.now() - timedelta(hours=2)).isoformat()
        weight = 1.0
        
        aged_weight = age_memory(old_timestamp, weight)
        self.assertLess(aged_weight, weight, "Old memory should have reduced weight")
        self.assertGreater(aged_weight, 0, "Weight should not go below zero")
    
    def test_age_memory_invalid_timestamp(self):
        """Test handling of invalid timestamps"""
        invalid_timestamp = "invalid-timestamp"
        weight = 1.0
        
        aged_weight = age_memory(invalid_timestamp, weight)
        self.assertEqual(aged_weight, weight, "Invalid timestamp should return original weight")
    
    def test_apply_aging_to_items(self):
        """Test applying aging to a list of items"""
        items = [
            {
                "id": 1,
                "timestamp": datetime.now().isoformat(),
                "type": "fresh_event",
                "data": {"message": "fresh"}
            },
            {
                "id": 2,
                "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
                "type": "old_event", 
                "data": {"message": "old"}
            }
        ]
        
        aged_items = apply_aging_to_items(items, default_weight=1.0)
        
        self.assertEqual(len(aged_items), 2)
        self.assertIn("weight", aged_items[0])
        self.assertIn("weight", aged_items[1])
        
        # Fresh item should have higher weight
        self.assertGreater(aged_items[0]["weight"], aged_items[1]["weight"])
    
    def test_apply_aging_no_timestamp(self):
        """Test applying aging to items without timestamps"""
        items = [
            {
                "id": 1,
                "type": "no_timestamp_event",
                "data": {"message": "no timestamp"}
            }
        ]
        
        aged_items = apply_aging_to_items(items, default_weight=1.0)
        
        self.assertEqual(len(aged_items), 1)
        self.assertEqual(aged_items[0]["weight"], 1.0)

if __name__ == "__main__":
    unittest.main()
