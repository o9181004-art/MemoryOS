"""
MemoryOS Context Injector - Low-latency context building for LLM prompts

This module provides intelligent context injection based on recent system events,
user patterns, and semantic similarity. Designed for minimal latency impact
while maintaining high relevance.

Key Features:
- L0: Fast time-based filtering (no embeddings)
- L1: Semantic similarity with embeddings (optional)
- Automatic masking of sensitive data
- Hard caps to prevent prompt bloat
- Graceful fallback when disabled
"""

import os
import sqlite3
import json
import time
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta


# Environment configuration with safe defaults
CONTEXT_ENABLED = os.getenv("MEMORYOS_CONTEXT_ENABLED", "false").lower() == "true"
LAST_MINUTES = int(os.getenv("MEMORYOS_CONTEXT_LAST_MIN", "30"))
LAST_K_EVENTS = int(os.getenv("MEMORYOS_CONTEXT_LAST_K", "50"))
TOP_K_RESULTS = int(os.getenv("MEMORYOS_CONTEXT_TOPK", "5"))
MAX_CHARS = int(os.getenv("MEMORYOS_CONTEXT_MAXCHARS", "1200"))
EMBEDDINGS_ENABLED = os.getenv("MEMORYOS_EMBEDDINGS", "false").lower() == "true"
SIM_THRESHOLD = float(os.getenv("MEMORYOS_SIM_THRESHOLD", "0.5"))
DB_PATH = os.getenv("MEMORYOS_DB", "./data_ollama/memoryos.db")

# Sensitive data masking patterns
MASK_PATTERNS = [
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),
    (r'\b01[0-9]-[0-9]{4}-[0-9]{4}\b', '[PHONE_KR]'),
    (r'\b010-[0-9]{4}-[0-9]{4}\b', '[PHONE_KR]'),
    (r'\b[0-9]{3}-[0-9]{4}-[0-9]{4}\b', '[PHONE]'),
]


def mask_sensitive_data(text: str) -> str:
    """Mask sensitive information in text using predefined patterns."""
    masked = text
    for pattern, replacement in MASK_PATTERNS:
        masked = re.sub(pattern, replacement, masked)
    return masked


def get_recent_events(db_path: str, minutes: int = LAST_MINUTES, limit: int = LAST_K_EVENTS) -> List[Dict]:
    """
    Retrieve recent events from the event_chain table.
    
    Args:
        db_path: Path to SQLite database
        minutes: Look back N minutes
        limit: Maximum number of events to retrieve
        
    Returns:
        List of event dictionaries sorted by timestamp (newest first)
    """
    if not os.path.exists(db_path):
        return []
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Calculate cutoff time
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        cutoff_str = cutoff_time.isoformat()
        
        # Query recent events
        query = """
        SELECT id, ts, type, data_json 
        FROM event_chain 
        WHERE ts >= ? 
        ORDER BY ts DESC 
        LIMIT ?
        """
        
        cursor.execute(query, (cutoff_str, limit))
        rows = cursor.fetchall()
        
        events = []
        for row in rows:
            event_id, timestamp, event_type, data_json = row
            try:
                data = json.loads(data_json) if data_json else {}
            except json.JSONDecodeError:
                data = {"raw": data_json}
            
            events.append({
                "id": event_id,
                "timestamp": timestamp,
                "type": event_type,
                "data": data
            })
        
        conn.close()
        return events
        
    except Exception as e:
        print(f"[ContextInjector] Error retrieving events: {e}")
        return []


def filter_relevant_events(events: List[Dict], user_input: str) -> List[Dict]:
    """
    Filter events based on relevance to user input.
    
    Args:
        events: List of recent events
        user_input: User's current input
        
    Returns:
        Filtered list of relevant events
    """
    if not events:
        return []
    
    # Simple keyword-based filtering for L0
    user_lower = user_input.lower()
    relevant_events = []
    
    # Priority event types (always include if recent)
    priority_types = {'error', 'timeout', 'self_heal', 'drift'}
    
    for event in events:
        event_type = event.get('type', '').lower()
        event_data = event.get('data', {})
        
        # Always include priority events
        if event_type in priority_types:
            relevant_events.append(event)
            continue
        
        # Check for keyword matches in event data
        event_text = json.dumps(event_data).lower()
        if any(keyword in event_text for keyword in user_lower.split()):
            relevant_events.append(event)
            continue
        
        # Check for common technical terms
        tech_terms = ['memory', 'cache', 'database', 'api', 'request', 'response', 'latency', 'error']
        if any(term in user_lower for term in tech_terms) and any(term in event_text for term in tech_terms):
            relevant_events.append(event)
    
    return relevant_events[:TOP_K_RESULTS]


def format_event_summary(event: Dict) -> str:
    """
    Format a single event into a concise summary line.
    
    Args:
        event: Event dictionary
        
    Returns:
        Formatted summary string
    """
    event_type = event.get('type', 'unknown')
    timestamp = event.get('timestamp', '')
    data = event.get('data', {})
    
    # Extract key information based on event type
    if event_type == 'error':
        message = data.get('message', data.get('error', 'Unknown error'))
        return f"[{timestamp}] ERROR: {mask_sensitive_data(str(message))}"
    
    elif event_type == 'timeout':
        operation = data.get('operation', 'Unknown operation')
        duration = data.get('duration_ms', 'N/A')
        return f"[{timestamp}] TIMEOUT: {operation} ({duration}ms)"
    
    elif event_type == 'self_heal':
        action = data.get('action', 'Unknown action')
        success = data.get('success', False)
        status = "SUCCESS" if success else "FAILED"
        return f"[{timestamp}] SELF_HEAL: {action} ({status})"
    
    elif event_type == 'drift':
        level = data.get('level', 'Unknown')
        component = data.get('component', 'Unknown component')
        return f"[{timestamp}] DRIFT: {component} (L{level})"
    
    elif event_type == 'llm_call':
        status = data.get('status', 'Unknown')
        latency = data.get('latency_ms', 'N/A')
        iteration = data.get('iter', 'N/A')
        return f"[{timestamp}] LLM: Status {status} (Iter {iteration}, {latency}ms)"
    
    else:
        # Generic event formatting
        summary = data.get('summary', data.get('message', str(data)))
        return f"[{timestamp}] {event_type.upper()}: {mask_sensitive_data(str(summary))}"


def build_context_l0(user_input: str) -> Optional[str]:
    """
    Build context string for LLM prompt injection (L0 - no embeddings).
    
    Args:
        user_input: User's input text
        
    Returns:
        Context string to prepend to prompt, or None if no context should be injected
    """
    # Check if context injection is enabled (check each time for runtime changes)
    if os.getenv("MEMORYOS_CONTEXT_ENABLED", "false").lower() != "true":
        return None
    
    # Skip context for simple greetings and acknowledgments
    greeting_patterns = [
        r'^(hi|hello|hey|thanks?|thank you|ok|okay|yes|no|sure|got it)$',
        r'^(how are you|what\'s up|good morning|good afternoon|good evening)$'
    ]
    
    user_clean = user_input.strip().lower()
    if any(re.match(pattern, user_clean) for pattern in greeting_patterns):
        return None
    
    # Get recent events
    events = get_recent_events(DB_PATH, LAST_MINUTES, LAST_K_EVENTS)
    if not events:
        return None
    
    # Filter for relevant events
    relevant_events = filter_relevant_events(events, user_input)
    if not relevant_events:
        return None
    
    # Format event summaries
    context_lines = []
    for event in relevant_events:
        summary = format_event_summary(event)
        if summary and len(summary) <= 200:  # Individual line cap
            context_lines.append(summary)
    
    # Hard cap on number of lines
    context_lines = context_lines[:8]
    
    if not context_lines:
        return None
    
    # Build final context string
    context_body = '\n'.join(context_lines)
    
    # Hard cap on total character count
    if len(context_body) > MAX_CHARS:
        context_body = context_body[:MAX_CHARS] + "..."
    
    return f"[CONTEXT WINDOW]\n{context_body}\n[END CONTEXT]"


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        vec1: First vector
        vec2: Second vector
        
    Returns:
        Cosine similarity score (0.0 to 1.0)
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    
    import math
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(a * a for a in vec2))
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)


def get_embedding(text: str) -> Optional[List[float]]:
    """
    Get embedding vector for text (placeholder implementation).
    
    Args:
        text: Input text
        
    Returns:
        Embedding vector or None if embeddings are disabled
    """
    if not EMBEDDINGS_ENABLED:
        return None
    
    # TODO: Implement actual embedding generation
    # This is a placeholder that would integrate with your embedding service
    print(f"[ContextInjector] Embedding generation not implemented for: {text[:50]}...")
    return None


def build_context_with_embeddings(user_input: str) -> Optional[str]:
    """
    Enhanced context building with semantic similarity (L1).
    
    Args:
        user_input: User's input text
        
    Returns:
        Context string or None
    """
    if not EMBEDDINGS_ENABLED:
        return build_context_l0(user_input)
    
    # Get user input embedding
    user_embedding = get_embedding(user_input)
    if not user_embedding:
        return build_context_l0(user_input)  # Fallback to L0
    
    # Get recent events
    events = get_recent_events(DB_PATH, LAST_MINUTES, LAST_K_EVENTS)
    if not events:
        return None
    
    # Calculate similarity scores
    scored_events = []
    for event in events:
        event_text = json.dumps(event.get('data', {}))
        event_embedding = get_embedding(event_text)
        
        if event_embedding:
            similarity = cosine_similarity(user_embedding, event_embedding)
            if similarity >= SIM_THRESHOLD:
                scored_events.append((event, similarity))
    
    # Sort by similarity score
    scored_events.sort(key=lambda x: x[1], reverse=True)
    
    # Take top results
    relevant_events = [event for event, score in scored_events[:TOP_K_RESULTS]]
    
    if not relevant_events:
        return None
    
    # Format and return context
    context_lines = []
    for event in relevant_events:
        summary = format_event_summary(event)
        if summary and len(summary) <= 200:
            context_lines.append(summary)
    
    context_lines = context_lines[:8]
    
    if not context_lines:
        return None
    
    context_body = '\n'.join(context_lines)
    if len(context_body) > MAX_CHARS:
        context_body = context_body[:MAX_CHARS] + "..."
    
    return f"[CONTEXT WINDOW]\n{context_body}\n[END CONTEXT]"


# Main entry point - automatically chooses L0 or L1 based on configuration
def build_context_main(user_input: str) -> Optional[str]:
    """
    Main context building function with automatic L0/L1 selection.
    
    Args:
        user_input: User's input text
        
    Returns:
        Context string for prompt injection
    """
    if EMBEDDINGS_ENABLED:
        return build_context_with_embeddings(user_input)
    else:
        return build_context_l0(user_input)


# Export the main function (avoid recursion by using different name)
build_context = build_context_main
