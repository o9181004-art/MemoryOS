"""
Test suite for MemoryOS Adaptive Reasoning System (offline, no network)
"""
import os
import unittest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta

# Set environment for testing
os.environ["MEMORYOS_INSIGHT_MAX"] = "5"
os.environ["MEMORYOS_TREND_FACTOR"] = "1.5"
os.environ["MEMORYOS_ANOMALY_THRESHOLD"] = "1"
os.environ["MEMORYOS_REASONING_ENABLED"] = "true"
os.environ["MEMORYOS_INSIGHT_INTERVAL"] = "50"

# Import after setting environment
from scripts.adaptive_reasoning import (
    _load_graph, _log_insight, extract_trends, detect_anomalies,
    analyze_patterns, generate_insights, summarize_insights, 
    get_reasoning_stats, analyze_user_context
)

class TestAdaptiveReasoning(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_graph_file = Path(self.temp_dir) / "test_graph.json"
        self.test_insight_file = Path(self.temp_dir) / "test_insights.log"
        
        # Set environment variables for test files
        os.environ["MEMORYOS_GRAPH_PATH"] = str(self.test_graph_file)
        os.environ["MEMORYOS_INSIGHT_LOG"] = str(self.test_insight_file)
        
        # Ensure reasoning is enabled for most tests
        os.environ["MEMORYOS_REASONING_ENABLED"] = "true"
    
    def tearDown(self):
        """Clean up test environment"""
        if self.test_graph_file.exists():
            self.test_graph_file.unlink()
        if self.test_insight_file.exists():
            self.test_insight_file.unlink()
    
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
                "drift": {"count": 5},
                "system": {"count": 2},
                "error": {"count": 1}
            },
            "edges": [
                {"src": "drift", "tgt": "system", "confidence": 0.8}
            ],
            "metadata": {"last_heal": "2025-01-01T10:00:00"}
        }
        
        self.test_graph_file.write_text(json.dumps(test_data), encoding='utf-8')
        result = _load_graph()
        
        self.assertEqual(len(result["nodes"]), 3)
        self.assertEqual(len(result["edges"]), 1)
        self.assertIn("drift", result["nodes"])
        self.assertIn("system", result["nodes"])
        self.assertIn("error", result["nodes"])
    
    def test_log_insight(self):
        """Test insight logging"""
        test_text = "Test insight message"
        _log_insight(test_text)
        
        # Check if log file was created
        self.assertTrue(self.test_insight_file.exists())
        
        # Check log content
        with open(self.test_insight_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
        
        self.assertIn(test_text, log_content)
        self.assertIn("2025-", log_content)  # Should contain timestamp
    
    def test_extract_trends_no_data(self):
        """Test trend extraction with no data"""
        graph = {"nodes": {}, "edges": []}
        trends = extract_trends(graph)
        
        self.assertEqual(trends, [])
    
    def test_extract_trends_with_data(self):
        """Test trend extraction with valid data"""
        graph = {
            "nodes": {
                "drift": {"count": 10},  # High activity (avg=5, 10 > 5*1.5=7.5)
                "system": {"count": 2},  # Low activity
                "error": {"count": 3}     # Low activity
            },
            "edges": []
        }
        
        trends = extract_trends(graph)
        
        # Should detect trending topics (above 1.5x average)
        self.assertGreater(len(trends), 0)
        self.assertTrue(any("drift" in trend for trend in trends))
    
    def test_extract_trends_no_trends(self):
        """Test trend extraction with no trending topics"""
        graph = {
            "nodes": {
                "topic1": {"count": 2},
                "topic2": {"count": 2},
                "topic3": {"count": 2}
            },
            "edges": []
        }
        
        trends = extract_trends(graph)
        
        # No topics should be trending (all equal)
        self.assertEqual(len(trends), 0)
    
    def test_detect_anomalies_no_data(self):
        """Test anomaly detection with no data"""
        graph = {"nodes": {}, "edges": []}
        anomalies = detect_anomalies(graph)
        
        self.assertEqual(anomalies, [])
    
    def test_detect_anomalies_inactive_nodes(self):
        """Test anomaly detection with inactive nodes"""
        graph = {
            "nodes": {
                "active": {"count": 5},
                "inactive1": {"count": 0},  # Below threshold
                "inactive2": {"count": 1},   # At threshold
                "normal": {"count": 3}
            },
            "edges": []
        }
        
        anomalies = detect_anomalies(graph)
        
        # Should detect inactive nodes
        self.assertGreater(len(anomalies), 0)
        self.assertTrue(any("inactive1" in anomaly for anomaly in anomalies))
    
    def test_detect_anomalies_isolated_nodes(self):
        """Test anomaly detection with isolated nodes"""
        graph = {
            "nodes": {
                "connected": {"count": 5},
                "isolated": {"count": 2}
            },
            "edges": [
                {"src": "connected", "tgt": "connected", "confidence": 0.8},
                {"src": "connected", "tgt": "connected", "confidence": 0.8},
                {"src": "connected", "tgt": "connected", "confidence": 0.8}
            ]
        }
        
        anomalies = detect_anomalies(graph)
        
        # Should detect isolated nodes
        self.assertGreater(len(anomalies), 0)
    
    def test_analyze_patterns_no_data(self):
        """Test pattern analysis with no data"""
        graph = {"nodes": {}, "edges": []}
        patterns = analyze_patterns(graph)
        
        self.assertEqual(patterns, [])
    
    def test_analyze_patterns_high_connectivity(self):
        """Test pattern analysis with high connectivity"""
        graph = {
            "nodes": {
                "a": {"count": 1},
                "b": {"count": 1},
                "c": {"count": 1}
            },
            "edges": [
                {"src": "a", "tgt": "b", "confidence": 0.8},
                {"src": "b", "tgt": "c", "confidence": 0.8},
                {"src": "a", "tgt": "c", "confidence": 0.8}
            ]
        }
        
        patterns = analyze_patterns(graph)
        
        # Should detect high connectivity
        self.assertGreater(len(patterns), 0)
        self.assertTrue(any("connectivity" in pattern.lower() for pattern in patterns))
    
    def test_analyze_patterns_high_confidence(self):
        """Test pattern analysis with high confidence"""
        graph = {
            "nodes": {
                "a": {"count": 1},
                "b": {"count": 1}
            },
            "edges": [
                {"src": "a", "tgt": "b", "confidence": 0.9},
                {"src": "b", "tgt": "a", "confidence": 0.95}
            ]
        }
        
        patterns = analyze_patterns(graph)
        
        # Should detect high confidence
        self.assertGreater(len(patterns), 0)
        self.assertTrue(any("confidence" in pattern.lower() for pattern in patterns))
    
    def test_generate_insights_no_data(self):
        """Test insight generation with no data"""
        graph = {"nodes": {}, "edges": []}
        
        # Mock the _load_graph function
        import scripts.adaptive_reasoning
        original_load = scripts.adaptive_reasoning._load_graph
        scripts.adaptive_reasoning._load_graph = lambda: graph
        
        try:
            result = generate_insights()
            self.assertEqual(result["status"], "no_data")
            self.assertEqual(len(result["insights"]), 0)
        finally:
            scripts.adaptive_reasoning._load_graph = original_load
    
    def test_generate_insights_with_data(self):
        """Test insight generation with valid data"""
        graph = {
            "nodes": {
                "trending": {"count": 10},
                "inactive": {"count": 0},
                "normal": {"count": 3}
            },
            "edges": [
                {"src": "trending", "tgt": "normal", "confidence": 0.8}
            ]
        }
        
        # Mock the _load_graph function
        import scripts.adaptive_reasoning
        original_load = scripts.adaptive_reasoning._load_graph
        scripts.adaptive_reasoning._load_graph = lambda: graph
        
        try:
            result = generate_insights()
            
            self.assertEqual(result["status"], "success")
            self.assertGreater(len(result["insights"]), 0)
            self.assertGreater(result["trends"], 0)
            self.assertGreater(result["anomalies"], 0)
            self.assertGreater(result["generation_time_ms"], 0)
        finally:
            scripts.adaptive_reasoning._load_graph = original_load
    
    def test_summarize_insights_no_data(self):
        """Test insight summarization with no data"""
        graph = {"nodes": {}, "edges": []}
        
        # Mock the _load_graph function
        import scripts.adaptive_reasoning
        original_load = scripts.adaptive_reasoning._load_graph
        scripts.adaptive_reasoning._load_graph = lambda: graph
        
        try:
            result = summarize_insights()
            self.assertEqual(result, "")
        finally:
            scripts.adaptive_reasoning._load_graph = original_load
    
    def test_summarize_insights_with_data(self):
        """Test insight summarization with valid data"""
        graph = {
            "nodes": {
                "trending": {"count": 10},
                "inactive": {"count": 0}
            },
            "edges": []
        }
        
        # Mock the _load_graph function
        import scripts.adaptive_reasoning
        original_load = scripts.adaptive_reasoning._load_graph
        scripts.adaptive_reasoning._load_graph = lambda: graph
        
        try:
            result = summarize_insights()
            
            self.assertIn("[ADAPTIVE INSIGHTS]", result)
            self.assertIn("trending", result)
            self.assertIn("inactive", result)
        finally:
            scripts.adaptive_reasoning._load_graph = original_load
    
    def test_get_reasoning_stats(self):
        """Test getting reasoning statistics"""
        stats = get_reasoning_stats()
        
        self.assertIn("enabled", stats)
        self.assertIn("total_nodes", stats)
        self.assertIn("total_edges", stats)
        self.assertIn("insight_max", stats)
        self.assertIn("trend_factor", stats)
        self.assertIn("anomaly_threshold", stats)
        self.assertIn("insight_interval", stats)
        
        self.assertTrue(stats["enabled"])
        self.assertEqual(stats["insight_max"], 5)
        self.assertEqual(stats["trend_factor"], 1.5)
        self.assertEqual(stats["anomaly_threshold"], 1)
        self.assertEqual(stats["insight_interval"], 50)
    
    def test_analyze_user_context_empty_input(self):
        """Test user context analysis with empty input"""
        result = analyze_user_context("")
        self.assertEqual(result, "")
        
        result = analyze_user_context(None)
        self.assertEqual(result, "")
    
    def test_analyze_user_context_with_keywords(self):
        """Test user context analysis with keywords"""
        graph = {
            "nodes": {
                "drift": {"count": 5},
                "system": {"count": 2},
                "unrelated": {"count": 1}
            },
            "edges": []
        }
        
        # Mock the _load_graph function
        import scripts.adaptive_reasoning
        original_load = scripts.adaptive_reasoning._load_graph
        scripts.adaptive_reasoning._load_graph = lambda: graph
        
        try:
            result = analyze_user_context("drift system analysis")
            
            self.assertIn("[CONTEXT INSIGHTS]", result)
            self.assertIn("drift", result)
            self.assertIn("system", result)
        finally:
            scripts.adaptive_reasoning._load_graph = original_load
    
    def test_reasoning_disabled(self):
        """Test reasoning functionality when disabled"""
        os.environ["MEMORYOS_REASONING_ENABLED"] = "false"
        
        graph = {
            "nodes": {"test": {"count": 1}},
            "edges": []
        }
        
        # Mock the _load_graph function
        import scripts.adaptive_reasoning
        original_load = scripts.adaptive_reasoning._load_graph
        scripts.adaptive_reasoning._load_graph = lambda: graph
        
        try:
            # All reasoning functions should return empty/disabled results
            result = generate_insights()
            self.assertEqual(result["status"], "disabled")
            
            summary = summarize_insights()
            self.assertEqual(summary, "")
            
            context = analyze_user_context("test")
            self.assertEqual(context, "")
            
            stats = get_reasoning_stats()
            self.assertFalse(stats["enabled"])
        finally:
            scripts.adaptive_reasoning._load_graph = original_load
            os.environ["MEMORYOS_REASONING_ENABLED"] = "true"

if __name__ == "__main__":
    unittest.main()
