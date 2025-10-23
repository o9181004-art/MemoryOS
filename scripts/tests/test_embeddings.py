"""
Test suite for MemoryOS embeddings module (offline, no network)
"""
import os
import unittest

# Set environment for stub provider
os.environ["MEMORYOS_EMBED_PROVIDER"] = "stub"
os.environ["MEMORYOS_EMBED_CACHE"] = "false"  # Disable cache for tests

# Import after setting environment
from scripts.embeddings import get_emb, cosine_sim, _stub_embed, _normalize

class TestEmbeddings(unittest.TestCase):
    
    def test_stub_deterministic(self):
        """Test that stub embeddings are deterministic"""
        v1 = get_emb("abc")
        v2 = get_emb("abc")
        v3 = get_emb("abcd")
        
        self.assertEqual(v1, v2, "Same input should produce same embedding")
        self.assertNotEqual(v1, v3, "Different input should produce different embedding")
    
    def test_cosine_similarity(self):
        """Test cosine similarity calculation"""
        v1 = get_emb("test")
        v2 = get_emb("test")
        v3 = get_emb("different")
        
        # Same text should have high similarity
        sim_same = cosine_sim(v1, v2)
        self.assertGreater(sim_same, 0.9, "Same text should have high similarity")
        
        # Different text should have lower similarity
        sim_diff = cosine_sim(v1, v3)
        self.assertLess(sim_diff, sim_same, "Different text should have lower similarity")
    
    def test_normalization(self):
        """Test vector normalization"""
        raw_vec = [3.0, 4.0, 0.0]
        norm_vec = _normalize(raw_vec)
        
        # Check magnitude is 1.0
        magnitude = sum(x*x for x in norm_vec) ** 0.5
        self.assertAlmostEqual(magnitude, 1.0, places=5, msg="Normalized vector should have magnitude 1.0")
    
    def test_stub_embedding_dimensions(self):
        """Test that stub embeddings have consistent dimensions"""
        vec = _stub_embed("test")
        self.assertEqual(len(vec), 64, "Stub embeddings should be 64-dimensional")
        
        # All values should be normalized
        magnitude = sum(x*x for x in vec) ** 0.5
        self.assertAlmostEqual(magnitude, 1.0, places=5, msg="Stub embeddings should be normalized")
    
    def test_empty_input_handling(self):
        """Test handling of empty or invalid inputs"""
        # Empty string should not crash
        vec = get_emb("")
        self.assertIsInstance(vec, list)
        self.assertEqual(len(vec), 64)
        
        # Very long string should be truncated
        long_text = "x" * 3000
        vec = get_emb(long_text)
        self.assertIsInstance(vec, list)
        self.assertEqual(len(vec), 64)

if __name__ == "__main__":
    unittest.main()
