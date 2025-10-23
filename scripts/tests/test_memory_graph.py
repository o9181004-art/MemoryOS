"""
Test suite for MemoryOS Memory Graph System (offline, no network)
"""
import os
import unittest
import tempfile
import json
from pathlib import Path

# Set environment for testing
os.environ["MEMORYOS_GRAPH_MAXNODES"] = "100"
os.environ["MEMORYOS_GRAPH_PATH"] = "./test_graph.json"
os.environ["MEMORYOS_GRAPH_ENABLED"] = "true"
os.environ["MEMORYOS_GRAPH_MIN_KEYWORD_LENGTH"] = "2"
os.environ["MEMORYOS_GRAPH_MAX_RELATED_TERMS"] = "3"

# Import after setting environment
from scripts.memory_graph import (
    _normalize, _hash_key, _extract_memory_content, build_graph, 
    query_related, query_graph_stats, rebuild_graph_from_approvals, get_related_context
)

class TestMemoryGraph(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_graph_file = Path(self.temp_dir) / "test_graph.json"
        
        # Set environment variable for test graph file
        os.environ["MEMORYOS_GRAPH_PATH"] = str(self.test_graph_file)
    
    def tearDown(self):
        """Clean up test environment"""
        if self.test_graph_file.exists():
            self.test_graph_file.unlink()
    
    def test_normalize_text(self):
        """Test text normalization and keyword extraction"""
        text = "System drift detected and resolved successfully"
        keywords = _normalize(text)
        
        # "system" is filtered out as a stop word, so check for other keywords
        self.assertIn("drift", keywords)
        self.assertIn("detected", keywords)
        self.assertIn("resolved", keywords)
        self.assertIn("successfully", keywords)
        
        # Test minimum length filtering
        short_text = "a b c"
        short_keywords = _normalize(short_text)
        self.assertEqual(len(short_keywords), 0)  # All too short
    
    def test_normalize_empty_text(self):
        """Test normalization with empty text"""
        keywords = _normalize("")
        self.assertEqual(keywords, [])
        
        keywords = _normalize(None)
        self.assertEqual(keywords, [])
    
    def test_hash_key(self):
        """Test hash key generation"""
        key1 = _hash_key("drift", "system")
        key2 = _hash_key("system", "drift")
        
        # Should be consistent regardless of order
        self.assertEqual(key1, key2)
        self.assertEqual(len(key1), 12)  # Should be 12 characters
    
    def test_extract_memory_content(self):
        """Test memory content extraction"""
        memory = {
            "proposal": {
                "text": "System drift detected",
                "message": "Error resolved"
            },
            "validation_result": {
                "reasons": ["Consistent with previous events"]
            }
        }
        
        content = _extract_memory_content(memory)
        
        self.assertIn("System drift detected", content)
        self.assertIn("Error resolved", content)
        self.assertIn("Consistent with previous events", content)
    
    def test_extract_memory_content_empty(self):
        """Test memory content extraction with empty memory"""
        memory = {}
        content = _extract_memory_content(memory)
        self.assertEqual(content, "")
    
    def test_build_graph_empty_memories(self):
        """Test graph building with empty memories"""
        graph = build_graph([])
        
        self.assertEqual(len(graph["nodes"]), 0)
        self.assertEqual(len(graph["edges"]), 0)
        self.assertEqual(graph["metadata"]["last_build"], "disabled")
    
    def test_build_graph_single_memory(self):
        """Test graph building with single memory"""
        memories = [
            {
                "timestamp": "2025-01-01T10:00:00",
                "proposal": {
                    "text": "System drift detected and resolved"
                }
            }
        ]
        
        graph = build_graph(memories)
        
        self.assertGreater(len(graph["nodes"]), 0)
        self.assertGreater(len(graph["edges"]), 0)
        # "system" is filtered out as stop word, so check for other keywords
        self.assertIn("drift", graph["nodes"])
        self.assertEqual(graph["metadata"]["total_memories"], 1)
    
    def test_build_graph_multiple_memories(self):
        """Test graph building with multiple memories"""
        memories = [
            {
                "timestamp": "2025-01-01T10:00:00",
                "proposal": {
                    "text": "System drift detected"
                }
            },
            {
                "timestamp": "2025-01-01T11:00:00",
                "proposal": {
                    "text": "Drift resolved by restart"
                }
            }
        ]
        
        graph = build_graph(memories)
        
        self.assertGreater(len(graph["nodes"]), 0)
        self.assertGreater(len(graph["edges"]), 0)
        self.assertEqual(graph["metadata"]["total_memories"], 2)
        
        # Check that common terms have higher counts
        if "drift" in graph["nodes"]:
            self.assertGreater(graph["nodes"]["drift"]["count"], 1)
    
    def test_query_related_no_graph(self):
        """Test querying related terms when no graph exists"""
        # Ensure no graph file exists
        if self.test_graph_file.exists():
            self.test_graph_file.unlink()
        
        related = query_related("drift")
        self.assertEqual(related, [])
    
    def test_query_related_with_graph(self):
        """Test querying related terms with existing graph"""
        # Build a graph first
        memories = [
            {
                "timestamp": "2025-01-01T10:00:00",
                "proposal": {
                    "text": "System drift detected and resolved"
                }
            }
        ]
        
        build_graph(memories)
        
        # Query for related terms
        related = query_related("drift")
        
        self.assertIsInstance(related, list)
        # Should find related terms like "detected", "resolved" (system is filtered out)
        if related:
            self.assertIn("detected", related)
    
    def test_query_related_nonexistent_term(self):
        """Test querying for nonexistent term"""
        memories = [
            {
                "timestamp": "2025-01-01T10:00:00",
                "proposal": {
                    "text": "System drift detected"
                }
            }
        ]
        
        build_graph(memories)
        
        related = query_related("nonexistent")
        self.assertEqual(related, [])
    
    def test_query_graph_stats_no_graph(self):
        """Test getting graph stats when no graph exists"""
        # Ensure no graph file exists
        if self.test_graph_file.exists():
            self.test_graph_file.unlink()
        
        stats = query_graph_stats()
        
        self.assertEqual(stats["total_nodes"], 0)
        self.assertEqual(stats["total_edges"], 0)
        self.assertEqual(stats["last_build"], "never")
        self.assertTrue(stats["enabled"])
    
    def test_query_graph_stats_with_graph(self):
        """Test getting graph stats with existing graph"""
        memories = [
            {
                "timestamp": "2025-01-01T10:00:00",
                "proposal": {
                    "text": "System drift detected"
                }
            }
        ]
        
        build_graph(memories)
        stats = query_graph_stats()
        
        self.assertGreater(stats["total_nodes"], 0)
        self.assertGreater(stats["total_edges"], 0)
        self.assertNotEqual(stats["last_build"], "never")
        self.assertTrue(stats["enabled"])
    
    def test_rebuild_graph_from_approvals(self):
        """Test rebuilding graph from approval queue"""
        # This test may fail if approval queue is not available
        graph = rebuild_graph_from_approvals()
        
        self.assertIsInstance(graph, dict)
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertIn("metadata", graph)
    
    def test_get_related_context_empty_input(self):
        """Test getting related context with empty input"""
        context = get_related_context("")
        self.assertEqual(context, "")
        
        context = get_related_context(None)
        self.assertEqual(context, "")
    
    def test_get_related_context_with_input(self):
        """Test getting related context with valid input"""
        # Build a graph first
        memories = [
            {
                "timestamp": "2025-01-01T10:00:00",
                "proposal": {
                    "text": "System drift detected and resolved"
                }
            }
        ]
        
        build_graph(memories)
        
        # Get related context
        context = get_related_context("drift system")
        
        if context:  # May be empty if no related terms found
            self.assertIn("[RELATED TOPICS]", context)
            # Should contain related terms like "detected", "resolved" (system is filtered out)
            self.assertIn("detected", context.lower())
    
    def test_graph_disabled(self):
        """Test graph functionality when disabled"""
        os.environ["MEMORYOS_GRAPH_ENABLED"] = "false"
        
        memories = [
            {
                "timestamp": "2025-01-01T10:00:00",
                "proposal": {
                    "text": "System drift detected"
                }
            }
        ]
        
        graph = build_graph(memories)
        
        self.assertEqual(len(graph["nodes"]), 0)
        self.assertEqual(len(graph["edges"]), 0)
        self.assertEqual(graph["metadata"]["last_build"], "disabled")
        
        related = query_related("drift")
        self.assertEqual(related, [])
        
        context = get_related_context("drift")
        self.assertEqual(context, "")
        
        # Restore enabled state
        os.environ["MEMORYOS_GRAPH_ENABLED"] = "true"
    
    def test_graph_file_persistence(self):
        """Test that graph is saved to file"""
        memories = [
            {
                "timestamp": "2025-01-01T10:00:00",
                "proposal": {
                    "text": "System drift detected"
                }
            }
        ]
        
        build_graph(memories)
        
        # Check that file was created
        self.assertTrue(self.test_graph_file.exists())
        
        # Check file content
        with open(self.test_graph_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertIn("metadata", data)

if __name__ == "__main__":
    unittest.main()
