# -*- coding: utf-8 -*-
"""
State Bridge - Connect multiple sessions and maintain memory consistency.
"""
import json
import os
from typing import Dict
from pathlib import Path

# Configuration
STATE_BRIDGE_ENABLED = os.environ.get("MEMORYOS_STATE_BRIDGE_ENABLED", "true").lower() == "true"
STATE_FILE = Path(os.environ.get("MEMORYOS_STATE_FILE", "./data/session_state.json"))

class StateBridge:
    """State Bridge for storing and retrieving memory across sessions"""
    
    def __init__(self):
        self.state = {}
        self._load_state()
    
    def _load_state(self) -> None:
        """Load state from persistent storage"""
        if not STATE_BRIDGE_ENABLED or not STATE_FILE.exists():
            return
        
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                self.state = json.load(f)
        except (json.JSONDecodeError, OSError, IOError):
            self.state = {}
    
    def _save_state(self) -> None:
        """Save state to persistent storage"""
        if not STATE_BRIDGE_ENABLED:
            return
        
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except (OSError, IOError):
            pass  # Silently fail if can't save state
    
    def save_state(self, session_id: str, context: str) -> None:
        """Save the context of the session"""
        if not STATE_BRIDGE_ENABLED:
            return
        
        self.state[session_id] = {
            "context": context,
            "timestamp": str(os.environ.get("MEMORYOS_SESSION_TIMESTAMP", ""))
        }
        self._save_state()
    
    def get_state(self, session_id: str) -> str:
        """Retrieve the saved context for the session"""
        if not STATE_BRIDGE_ENABLED:
            return ""
        
        session_data = self.state.get(session_id, {})
        return session_data.get("context", "")
    
    def clear_state(self, session_id: str) -> None:
        """Clear saved context for the session"""
        if not STATE_BRIDGE_ENABLED:
            return
        
        if session_id in self.state:
            del self.state[session_id]
            self._save_state()
    
    def get_all_sessions(self) -> Dict[str, Dict]:
        """Get all active sessions"""
        return self.state.copy()
    
    def cleanup_old_sessions(self, max_age_hours: int = 24) -> None:
        """Clean up sessions older than max_age_hours"""
        if not STATE_BRIDGE_ENABLED:
            return
        
        import time
        current_time = time.time()
        sessions_to_remove = []
        
        for session_id, session_data in self.state.items():
            timestamp_str = session_data.get("timestamp", "")
            if timestamp_str:
                try:
                    session_time = float(timestamp_str)
                    if current_time - session_time > max_age_hours * 3600:
                        sessions_to_remove.append(session_id)
                except (ValueError, TypeError):
                    sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            del self.state[session_id]
        
        if sessions_to_remove:
            self._save_state()

# Global instance
_state_bridge = None

def get_state_bridge() -> StateBridge:
    """Get the global StateBridge instance"""
    global _state_bridge
    if _state_bridge is None:
        _state_bridge = StateBridge()
    return _state_bridge
