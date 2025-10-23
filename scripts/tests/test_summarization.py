"""
Test suite for MemoryOS Summarization Layer (offline, no network)
"""
import os
import unittest

# Set environment for testing
os.environ["MEMORYOS_MAX_SUMMARY_LENGTH"] = "300"
os.environ["MEMORYOS_COMPRESSION_THRESHOLD"] = "5"

# Import after setting environment
from scripts.snapshot_summarizer import summarize_event_chain, apply_summary_to_chain, should_compress

class TestSummarization(unittest.TestCase):
    
    def test_summarize_event_chain_empty(self):
        """Test summarizing empty event chain"""
        result = summarize_event_chain([])
        self.assertEqual(result, "")
    
    def test_summarize_event_chain_single_event(self):
        """Test summarizing single event"""
        items = [
            {
                "type": "error",
                "data": {"message": "Test error occurred"}
            }
        ]
        
        result = summarize_event_chain(items)
        self.assertIn("ERROR", result)
        self.assertIn("Test error occurred", result)
    
    def test_summarize_event_chain_multiple_events(self):
        """Test summarizing multiple events of same type"""
        items = [
            {"type": "error", "data": {"message": "Error 1"}},
            {"type": "error", "data": {"message": "Error 2"}},
            {"type": "error", "data": {"message": "Error 3"}}
        ]
        
        result = summarize_event_chain(items)
        self.assertIn("ERROR", result)
        self.assertIn("3 events occurred", result)
    
    def test_summarize_event_chain_mixed_types(self):
        """Test summarizing mixed event types"""
        items = [
            {"type": "error", "data": {"message": "Error occurred"}},
            {"type": "info", "data": {"message": "Info message"}},
            {"type": "warning", "data": {"message": "Warning message"}}
        ]
        
        result = summarize_event_chain(items)
        self.assertIn("ERROR", result)
        self.assertIn("INFO", result)
        self.assertIn("WARNING", result)
    
    def test_apply_summary_to_chain_below_threshold(self):
        """Test that compression is not applied below threshold"""
        items = [
            {"type": "error", "data": {"message": "Error 1"}},
            {"type": "error", "data": {"message": "Error 2"}}
        ]
        
        result = apply_summary_to_chain(items)
        self.assertEqual(result, "", "Should not compress below threshold")
    
    def test_apply_summary_to_chain_above_threshold(self):
        """Test that compression is applied above threshold"""
        items = [
            {"type": "error", "data": {"message": f"Error {i}"}}
            for i in range(10)  # Above threshold of 5
        ]
        
        result = apply_summary_to_chain(items)
        self.assertNotEqual(result, "", "Should compress above threshold")
        self.assertIn("ERROR", result)
    
    def test_should_compress(self):
        """Test compression threshold logic"""
        # Below threshold
        few_items = [{"type": "test"} for _ in range(3)]
        self.assertFalse(should_compress(few_items))
        
        # Above threshold
        many_items = [{"type": "test"} for _ in range(10)]
        self.assertTrue(should_compress(many_items))
    
    def test_summary_length_limit(self):
        """Test that summary respects length limit"""
        # Create many events to test length limiting
        items = [
            {"type": "error", "data": {"message": f"Very long error message {i} that should be truncated when summary gets too long"}}
            for i in range(20)
        ]
        
        result = summarize_event_chain(items, max_summary_length=100)
        self.assertLessEqual(len(result), 100, "Summary should respect length limit")

if __name__ == "__main__":
    unittest.main()
