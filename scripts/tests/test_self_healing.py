"""
Test suite for MemoryOS Self-Healing Graph System (offline, no network)
"""
import os
import unittest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta

# Set environment for testing
os.environ["MEMORYOS_HEALING_DECAY_HOURS"] = "24"
os.environ["MEMORYOS_CONF_MIN"] = "0.3"
os.environ["MEMORYOS_CONF_MAX"] = "1.0"
os.environ["MEMORYOS_HEAL_THRESHOLD"] = "0.4"
os.environ["MEMORYOS_HEALING_ENABLED"] = "true"
os.environ["MEMORYOS_HEAL_PROBABILITY"] = "0.1"  # Higher for testing

# Import after setting environment
from scripts.self_healing_graph import (
    _load_graph, _save_graph, integrity_scan, reweight_confidence,
    prune_low_confidence, heal_missing_links, run_full_healing_cycle, get_healing_stats
)

class TestSelfHealingGraph(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_graph_file = Path(self.temp_dir) / "test_graph.json"
        
        # Set environment variable for test graph file
        os.environ["MEMORYOS_GRAPH_PATH"] = str(self.test_graph_file)
        
        # Ensure healing is enabled for most tests
        os.environ["MEMORYOS_HEALING_ENABLED"] = "true"
    
    def tearDown(self):
        """Clean up test environment"""
        if self.test_graph_file.exists():
            self.test_graph_file.unlink()
    
    def test_load_graph_empty_file(self):
        """Test loading from non-existent file"""
        result = _load_graph()
        
        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertIn("metadata", result)
        self.assertEqual(len(result["nodes"]), 0)
        self.assertEqual(len(result["edges"]), 0)
    
    def test_load_graph_valid_data(self):
        """Test loading valid graph data"""
        test_data = {
            "nodes": {
                "drift": {"count": 2},
                "system": {"count": 1}
            },
            "edges": [
                {"src": "drift", "tgt": "system", "confidence": 0.8, "ts": "2025-01-01T10:00:00"}
            ],
            "metadata": {"last_heal": "2025-01-01T10:00:00"}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = _load_graph()
        
        self.assertEqual(len(result["nodes"]), 2)
        self.assertEqual(len(result["edges"]), 1)
        self.assertIn("drift", result["nodes"])
        self.assertIn("system", result["nodes"])
    
    def test_save_graph(self):
        """Test saving graph data"""
        test_data = {
            "nodes": {"test": {"count": 1}},
            "edges": [],
            "metadata": {"test": True}
        }
        
        success = _save_graph(test_data)
        self.assertTrue(success)
        self.assertTrue(self.test_graph_file.exists())
        
        # Verify saved content
        with open(self.test_graph_file, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
        
        self.assertEqual(saved_data["nodes"]["test"]["count"], 1)
        self.assertTrue(saved_data["metadata"]["test"])
    
    def test_integrity_scan_clean_graph(self):
        """Test integrity scan with clean graph"""
        test_data = {
            "nodes": {
                "drift": {"count": 2},
                "system": {"count": 1}
            },
            "edges": [
                {"src": "drift", "tgt": "system", "confidence": 0.8}
            ],
            "metadata": {}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = integrity_scan()
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["edges_retained"], 1)
        self.assertEqual(result["edges_removed"], 0)
        self.assertGreater(result["scan_time_ms"], 0)
    
    def test_integrity_scan_damaged_graph(self):
        """Test integrity scan with damaged graph"""
        test_data = {
            "nodes": {
                "drift": {"count": 2},
                "system": {"count": 1}
            },
            "edges": [
                {"src": "drift", "tgt": "system", "confidence": 0.8},
                {"src": "missing", "tgt": "system", "confidence": 0.8},  # Missing node
                {"src": "drift", "tgt": "missing", "confidence": 0.8}     # Missing node
            ],
            "metadata": {}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = integrity_scan()
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["edges_retained"], 1)  # Only valid edge retained
        self.assertEqual(result["edges_removed"], 2)  # Two invalid edges removed
    
    def test_reweight_confidence(self):
        """Test confidence reweighting"""
        # Create graph with old timestamps
        old_time = (datetime.now() - timedelta(hours=48)).isoformat()
        test_data = {
            "nodes": {
                "drift": {"count": 2},
                "system": {"count": 1}
            },
            "edges": [
                {"src": "drift", "tgt": "system", "ts": old_time}
            ],
            "metadata": {}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = reweight_confidence()
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["reweighted"], 1)
        self.assertGreater(result["avg_confidence"], 0)
        self.assertLessEqual(result["avg_confidence"], 1.0)
        self.assertGreater(result["reweight_time_ms"], 0)
    
    def test_reweight_confidence_no_edges(self):
        """Test confidence reweighting with no edges"""
        test_data = {
            "nodes": {"test": {"count": 1}},
            "edges": [],
            "metadata": {}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = reweight_confidence()
        
        self.assertEqual(result["status"], "no_edges")
        self.assertEqual(result["reweighted"], 0)
    
    def test_prune_low_confidence(self):
        """Test pruning low confidence edges"""
        test_data = {
            "nodes": {
                "drift": {"count": 2},
                "system": {"count": 1},
                "error": {"count": 1}
            },
            "edges": [
                {"src": "drift", "tgt": "system", "confidence": 0.8},
                {"src": "drift", "tgt": "error", "confidence": 0.2},  # Low confidence
                {"src": "system", "tgt": "error", "confidence": 0.1}  # Low confidence
            ],
            "metadata": {}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = prune_low_confidence(threshold=0.5)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["removed"], 2)  # Two low confidence edges removed
        self.assertEqual(result["remaining"], 1)  # One high confidence edge retained
        self.assertEqual(result["threshold"], 0.5)
    
    def test_prune_low_confidence_no_edges(self):
        """Test pruning with no edges"""
        test_data = {
            "nodes": {"test": {"count": 1}},
            "edges": [],
            "metadata": {}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = prune_low_confidence()
        
        self.assertEqual(result["status"], "no_edges")
        self.assertEqual(result["removed"], 0)
    
    def test_heal_missing_links(self):
        """Test healing missing links"""
        test_data = {
            "nodes": {
                "drift": {"count": 2},
                "system": {"count": 1},
                "error": {"count": 1}
            },
            "edges": [
                {"src": "drift", "tgt": "system", "confidence": 0.8}
            ],
            "metadata": {}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = heal_missing_links()
        
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["healed"], 0)  # May or may not heal based on probability
        self.assertGreaterEqual(result["total_edges"], 1)  # At least original edge
        self.assertGreater(result["heal_time_ms"], 0)
    
    def test_heal_missing_links_insufficient_nodes(self):
        """Test healing with insufficient nodes"""
        test_data = {
            "nodes": {"drift": {"count": 1}},
            "edges": [],
            "metadata": {}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = heal_missing_links()
        
        self.assertEqual(result["status"], "insufficient_nodes")
        self.assertEqual(result["healed"], 0)
    
    def test_run_full_healing_cycle(self):
        """Test complete healing cycle"""
        # Create graph with some issues
        old_time = (datetime.now() - timedelta(hours=48)).isoformat()
        test_data = {
            "nodes": {
                "drift": {"count": 2},
                "system": {"count": 1},
                "error": {"count": 1}
            },
            "edges": [
                {"src": "drift", "tgt": "system", "confidence": 0.8, "ts": old_time},
                {"src": "drift", "tgt": "error", "confidence": 0.2, "ts": old_time},  # Low confidence
                {"src": "missing", "tgt": "system", "confidence": 0.8}  # Missing node
            ],
            "metadata": {}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = run_full_healing_cycle()
        
        self.assertEqual(result["status"], "success")
        self.assertIn("scan", result)
        self.assertIn("reweight", result)
        self.assertIn("prune", result)
        self.assertIn("heal", result)
        self.assertGreater(result["cycle_time_ms"], 0)
    
    def test_get_healing_stats(self):
        """Test getting healing statistics"""
        stats = get_healing_stats()
        
        self.assertIn("enabled", stats)
        self.assertIn("total_nodes", stats)
        self.assertIn("total_edges", stats)
        self.assertIn("last_heal", stats)
        self.assertIn("avg_confidence", stats)
        self.assertIn("decay_hours", stats)
        self.assertIn("conf_min", stats)
        self.assertIn("conf_max", stats)
        self.assertIn("heal_threshold", stats)
        
        self.assertTrue(stats["enabled"])
        self.assertEqual(stats["decay_hours"], 24)
        self.assertEqual(stats["conf_min"], 0.3)
        self.assertEqual(stats["conf_max"], 1.0)
        self.assertEqual(stats["heal_threshold"], 0.4)
    
    def test_healing_disabled(self):
        """Test healing functionality when disabled"""
        # Set disabled state
        os.environ["MEMORYOS_HEALING_ENABLED"] = "false"
        
        test_data = {
            "nodes": {"test": {"count": 1}},
            "edges": [],
            "metadata": {}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        
        # All healing functions should return disabled status
        scan_result = integrity_scan()
        self.assertEqual(scan_result["status"], "disabled")
        
        reweight_result = reweight_confidence()
        self.assertEqual(reweight_result["status"], "disabled")
        
        prune_result = prune_low_confidence()
        self.assertEqual(prune_result["status"], "disabled")
        
        heal_result = heal_missing_links()
        self.assertEqual(heal_result["status"], "disabled")
        
        cycle_result = run_full_healing_cycle()
        self.assertEqual(cycle_result["status"], "disabled")
        
        stats = get_healing_stats()
        self.assertFalse(stats["enabled"])
        
        # Restore enabled state
        os.environ["MEMORYOS_HEALING_ENABLED"] = "true"
    
    def test_graph_file_persistence(self):
        """Test that healing operations persist changes to file"""
        test_data = {
            "nodes": {
                "drift": {"count": 2},
                "system": {"count": 1}
            },
            "edges": [
                {"src": "drift", "tgt": "system", "confidence": 0.8, "ts": "2025-01-01T10:00:00"}
            ],
            "metadata": {}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        
        # Run healing cycle
        run_full_healing_cycle()
        
        # Check that file was updated
        self.assertTrue(self.test_graph_file.exists())
        
        with open(self.test_graph_file, 'r', encoding='utf-8') as f:
            updated_data = json.load(f)
        
        self.assertIn("metadata", updated_data)
        self.assertIn("last_heal", updated_data["metadata"])

if __name__ == "__main__":
    unittest.main()
