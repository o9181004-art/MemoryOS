"""
Test suite for MemoryOS Context Reinjection System (offline, no network)
"""
import os
import unittest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta

# Set environment for testing
os.environ["MEMORYOS_REINJECT_TOPK"] = "3"
os.environ["MEMORYOS_REINJECT_MAXAGE_MIN"] = "720"
os.environ["MEMORYOS_REINJECT_MIN_SCORE"] = "0.55"
os.environ["MEMORYOS_REINJECTION_ENABLED"] = "true"

# Import after setting environment
from scripts.context_reinjection import (
    _load_approved, _filter_recent, _score_relevance, 
    _format_reinjected_item, reinject_context, get_reinjection_stats
)

class TestContextReinjection(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_cache_file = Path(self.temp_dir) / "test_approvals.json"
        
        # Set environment variable for test cache file
        os.environ["MEMORYOS_APPROVED_CACHE"] = str(self.test_cache_file)
        
        # Clear any existing cache file
        if self.test_cache_file.exists():
            self.test_cache_file.unlink()
    
    def tearDown(self):
        """Clean up test environment"""
        if self.test_cache_file.exists():
            self.test_cache_file.unlink()
    
    def test_load_approved_empty_file(self):
        """Test loading from non-existent file"""
        # Ensure file doesn't exist
        if self.test_cache_file.exists():
            self.test_cache_file.unlink()
        
        result = _load_approved()
        self.assertEqual(result, [])
    
    def test_load_approved_valid_data(self):
        """Test loading valid approval data"""
        test_data = [
            {
                "timestamp": "2025-01-01T10:00:00",
                "proposal": {"text": "test proposal"},
                "validation_result": {"valid": True}
            }
        ]
        
        self.test_cache_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = _load_approved()
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["proposal"]["text"], "test proposal")
    
    def test_load_approved_wrapped_format(self):
        """Test loading wrapped format data"""
        test_data = {
            "queue": [
                {
                    "timestamp": "2025-01-01T10:00:00",
                    "proposal": {"text": "wrapped proposal"}
                }
            ]
        }
        
        self.test_cache_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = _load_approved()
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["proposal"]["text"], "wrapped proposal")
    
    def test_filter_recent_items(self):
        """Test filtering recent items"""
        now = datetime.now()
        recent_time = now - timedelta(minutes=30)
        old_time = now - timedelta(hours=15)  # Beyond 12h limit
        
        items = [
            {
                "timestamp": recent_time.isoformat(),
                "proposal": {"text": "recent item"}
            },
            {
                "timestamp": old_time.isoformat(),
                "proposal": {"text": "old item"}
            }
        ]
        
        filtered = _filter_recent(items)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["proposal"]["text"], "recent item")
    
    def test_score_relevance_high_match(self):
        """Test relevance scoring with high match"""
        user_input = "drift error timeout"
        item = {
            "proposal": {
                "text": "System drift detected and resolved",
                "message": "timeout error occurred"
            }
        }
        
        score = _score_relevance(user_input, item)
        
        self.assertGreater(score, 0.5)  # Should have high relevance
        self.assertLessEqual(score, 1.0)
    
    def test_score_relevance_low_match(self):
        """Test relevance scoring with low match"""
        user_input = "completely different topic"
        item = {
            "proposal": {
                "text": "System drift detected and resolved",
                "message": "timeout error occurred"
            }
        }
        
        score = _score_relevance(user_input, item)
        
        self.assertLess(score, 0.5)  # Should have low relevance
    
    def test_score_relevance_empty_input(self):
        """Test relevance scoring with empty input"""
        user_input = ""
        item = {"proposal": {"text": "test"}}
        
        score = _score_relevance(user_input, item)
        
        self.assertEqual(score, 0.0)
    
    def test_format_reinjected_item(self):
        """Test formatting reinjected item"""
        item = {
            "timestamp": "2025-01-01T10:00:00",
            "proposal": {
                "text": "System drift resolved successfully"
            }
        }
        
        formatted = _format_reinjected_item(item)
        
        self.assertIn("2025-01-01T10:00:00", formatted)
        self.assertIn("System drift resolved", formatted)
        self.assertTrue(formatted.startswith("- "))
    
    def test_reinject_context_no_data(self):
        """Test reinjection with no approved data"""
        result = reinject_context("test input")
        self.assertEqual(result, "")
    
    def test_reinject_context_with_data(self):
        """Test reinjection with relevant data"""
        # Create test data
        test_data = [
            {
                "timestamp": datetime.now().isoformat(),
                "proposal": {
                    "text": "System drift detected and resolved",
                    "message": "timeout error occurred"
                },
                "validation_result": {
                    "valid": True,
                    "consistency_score": 0.9
                }
            }
        ]
        
        self.test_cache_file.write_text(json.dumps(test_data), encoding='utf-8')
        
        result = reinject_context("drift timeout")
        
        self.assertIn("[REINJECTED CONTEXT]", result)
        self.assertIn("System drift detected", result)
    
    def test_reinject_context_filters_by_relevance(self):
        """Test that reinjection filters by relevance score"""
        # Create test data with mixed relevance
        test_data = [
            {
                "timestamp": datetime.now().isoformat(),
                "proposal": {"text": "drift error timeout"},  # High relevance
                "validation_result": {"valid": True}
            },
            {
                "timestamp": datetime.now().isoformat(),
                "proposal": {"text": "completely unrelated topic"},  # Low relevance
                "validation_result": {"valid": True}
            }
        ]
        
        self.test_cache_file.write_text(json.dumps(test_data), encoding='utf-8')
        
        result = reinject_context("drift timeout")
        
        self.assertIn("[REINJECTED CONTEXT]", result)
        self.assertIn("drift error timeout", result)
        self.assertNotIn("unrelated topic", result)
    
    def test_reinject_context_respects_topk_limit(self):
        """Test that reinjection respects TOPK limit"""
        # Create more items than TOPK limit
        test_data = []
        for i in range(5):  # More than default TOPK of 3
            test_data.append({
                "timestamp": datetime.now().isoformat(),
                "proposal": {"text": f"drift error {i}"},
                "validation_result": {"valid": True}
            })
        
        self.test_cache_file.write_text(json.dumps(test_data), encoding='utf-8')
        
        result = reinject_context("drift error")
        
        # Count lines in result (excluding header)
        lines = result.split('\n')
        content_lines = [line for line in lines if line.startswith('- ')]
        
        self.assertLessEqual(len(content_lines), 3)  # Should respect TOPK limit
    
    def test_get_reinjection_stats(self):
        """Test getting reinjection statistics"""
        stats = get_reinjection_stats()
        
        self.assertIn("total_approved", stats)
        self.assertIn("recent_approved", stats)
        self.assertIn("max_reinject", stats)
        self.assertIn("max_age_minutes", stats)
        self.assertIn("min_relevance", stats)
        self.assertIn("enabled", stats)
        
        self.assertEqual(stats["max_reinject"], 3)
        self.assertEqual(stats["max_age_minutes"], 720)
        self.assertEqual(stats["min_relevance"], 0.55)
        self.assertTrue(stats["enabled"])
    
    def test_reinjection_disabled(self):
        """Test reinjection when disabled"""
        os.environ["MEMORYOS_REINJECTION_ENABLED"] = "false"
        
        # Create test data
        test_data = [
            {
                "timestamp": datetime.now().isoformat(),
                "proposal": {"text": "test data"},
                "validation_result": {"valid": True}
            }
        ]
        
        self.test_cache_file.write_text(json.dumps(test_data), encoding='utf-8')
        
        result = reinject_context("test")
        
        self.assertEqual(result, "")
        
        # Restore enabled state
        os.environ["MEMORYOS_REINJECTION_ENABLED"] = "true"

if __name__ == "__main__":
    unittest.main()
