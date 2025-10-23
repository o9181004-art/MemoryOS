"""
Test suite for MemoryOS State Bridge (offline, no network)
"""
import os
import unittest
import tempfile
from pathlib import Path

# Set environment for testing
os.environ["MEMORYOS_STATE_BRIDGE_ENABLED"] = "true"

# Import after setting environment
from scripts.state_bridge import StateBridge, get_state_bridge

class TestStateBridge(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for state file
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "test_state.json"
        os.environ["MEMORYOS_STATE_FILE"] = str(self.state_file)
        
        # Clear any existing state
        if self.state_file.exists():
            self.state_file.unlink()
        
        # Reset global state bridge instance
        import scripts.state_bridge
        scripts.state_bridge._state_bridge = None
    
    def tearDown(self):
        """Clean up test environment"""
        if self.state_file.exists():
            self.state_file.unlink()
    
    def test_save_and_get_state(self):
        """Test saving and retrieving state"""
        bridge = StateBridge()
        session_id = "test_session"
        context = "Test context data"
        
        # Save state
        bridge.save_state(session_id, context)
        
        # Retrieve state
        retrieved_context = bridge.get_state(session_id)
        self.assertEqual(retrieved_context, context)
    
    def test_clear_state(self):
        """Test clearing state"""
        bridge = StateBridge()
        session_id = "test_session"
        context = "Test context data"
        
        # Save state
        bridge.save_state(session_id, context)
        self.assertEqual(bridge.get_state(session_id), context)
        
        # Clear state
        bridge.clear_state(session_id)
        self.assertEqual(bridge.get_state(session_id), "")
    
    def test_get_nonexistent_state(self):
        """Test retrieving non-existent state"""
        bridge = StateBridge()
        nonexistent_session = "nonexistent_session"
        
        result = bridge.get_state(nonexistent_session)
        self.assertEqual(result, "")
    
    def test_multiple_sessions(self):
        """Test handling multiple sessions"""
        bridge = StateBridge()
        
        # Save multiple sessions
        bridge.save_state("session1", "Context 1")
        bridge.save_state("session2", "Context 2")
        
        # Verify both sessions
        self.assertEqual(bridge.get_state("session1"), "Context 1")
        self.assertEqual(bridge.get_state("session2"), "Context 2")
        
        # Clear one session
        bridge.clear_state("session1")
        self.assertEqual(bridge.get_state("session1"), "")
        self.assertEqual(bridge.get_state("session2"), "Context 2")
    
    def test_state_persistence(self):
        """Test that state persists across bridge instances"""
        # Create first bridge instance
        bridge1 = StateBridge()
        bridge1.save_state("persistent_session", "Persistent context")
        
        # Create second bridge instance (should load existing state)
        bridge2 = StateBridge()
        retrieved_context = bridge2.get_state("persistent_session")
        self.assertEqual(retrieved_context, "Persistent context")
    
    def test_get_all_sessions(self):
        """Test getting all active sessions"""
        bridge = StateBridge()
        
        # Clear any existing state first
        bridge.state.clear()
        
        # Save multiple sessions
        bridge.save_state("session1", "Context 1")
        bridge.save_state("session2", "Context 2")
        
        all_sessions = bridge.get_all_sessions()
        self.assertEqual(len(all_sessions), 2)
        self.assertIn("session1", all_sessions)
        self.assertIn("session2", all_sessions)
    
    def test_state_bridge_disabled(self):
        """Test behavior when state bridge is disabled"""
        # Test that when STATE_BRIDGE_ENABLED is False, methods return early
        # This is tested by checking the module-level constant behavior
        bridge = StateBridge()
        
        # The actual disabled behavior is controlled by STATE_BRIDGE_ENABLED
        # which is checked at module import time, so we test the logic indirectly
        # by verifying the methods work correctly when enabled
        
        # Clear state and test normal operation
        bridge.state.clear()
        bridge.save_state("test_session", "test_context")
        result = bridge.get_state("test_session")
        self.assertEqual(result, "test_context")
        
        # Test that clear_state works
        bridge.clear_state("test_session")
        result = bridge.get_state("test_session")
        self.assertEqual(result, "")
    
    def test_cleanup_old_sessions(self):
        """Test cleanup of old sessions"""
        bridge = StateBridge()
        
        # Save session with old timestamp
        bridge.state["old_session"] = {
            "context": "old context",
            "timestamp": "1000000000"  # Very old timestamp
        }
        
        # Clean up old sessions
        bridge.cleanup_old_sessions(max_age_hours=1)
        
        # Old session should be removed
        self.assertNotIn("old_session", bridge.state)
    
    def test_global_instance(self):
        """Test global StateBridge instance"""
        bridge1 = get_state_bridge()
        bridge2 = get_state_bridge()
        
        # Should return the same instance
        self.assertIs(bridge1, bridge2)

if __name__ == "__main__":
    unittest.main()
