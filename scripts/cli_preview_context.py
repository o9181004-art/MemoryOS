# -*- coding: utf-8 -*-
"""
MemoryOS Context Preview CLI Tool
Dry-run preview for context injection testing with Round-5 features
"""
import sys
import os
from scripts.build_context import build_context

def main():
    user_input = " ".join(sys.argv[1:]).strip()
    if not user_input:
        print("usage: python -m scripts.cli_preview_context \"your input here\"")
        print("Environment variables:")
        print("  MEMORYOS_CONTEXT_ENABLED=true")
        print("  MEMORYOS_EMBEDDINGS=true")
        print("  MEMORYOS_MEMORY_AGING_ENABLED=true")
        print("  MEMORYOS_SUMMARIZATION_ENABLED=true")
        print("  MEMORYOS_STATE_BRIDGE_ENABLED=true")
        sys.exit(1)
    
    # Test State Bridge functionality if enabled
    if os.environ.get("MEMORYOS_STATE_BRIDGE_ENABLED", "true").lower() == "true":
        try:
            from scripts.state_bridge import get_state_bridge
            bridge = get_state_bridge()
            
            # Save current context as test session
            test_session_id = "cli_test_session"
            bridge.save_state(test_session_id, f"CLI test context for: {user_input}")
            
            # Retrieve saved context
            saved_context = bridge.get_state(test_session_id)
            if saved_context:
                print(f"[State Bridge] Saved context: {saved_context}")
            
            # Clean up test session
            bridge.clear_state(test_session_id)
            
        except ImportError:
            print("[State Bridge] Module not available")
    
    # Build and display context
    ctx = build_context(user_input)
    print(ctx or "[no context injected]")

if __name__ == "__main__":
    main()
