"""
MemoryOS Context Injector v1.0
Immutable Architecture – One-Way Feed Design
Author: LeeSG
Date: 2025-10-23
Purpose: Provide read-only contextual recall to LLM without allowing reverse writes.

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
- STRICT READ-ONLY MODE: No writes to event_chain
"""

import os
import sqlite3
import json
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

# Enforce strict read-only mode
READ_ONLY = True


# Environment configuration with safe defaults
CONTEXT_ENABLED = os.getenv("MEMORYOS_CONTEXT_ENABLED", "false").lower() == "true"
LAST_MINUTES = int(os.getenv("MEMORYOS_CONTEXT_LAST_MIN", "30"))
LAST_K_EVENTS = int(os.getenv("MEMORYOS_CONTEXT_LAST_K", "50"))
TOP_K_RESULTS = int(os.getenv("MEMORYOS_CONTEXT_TOPK", "5"))
MAX_CHARS = int(os.getenv("MEMORYOS_CONTEXT_MAXCHARS", "1200"))
EMBEDDINGS_ENABLED = os.getenv("MEMORYOS_EMBEDDINGS", "false").lower() == "true"
SIM_THRESHOLD = float(os.getenv("MEMORYOS_SIM_THRESHOLD", "0.5"))
DB_PATH = os.getenv("MEMORYOS_DB", "./data_ollama/memoryos.db")

# L1 Activation & Hybrid Scoring Configuration
L1_WEIGHT = float(os.getenv("MEMORYOS_L1_WEIGHT", "0.65"))   # 0~1
L0_WEIGHT = 1.0 - L1_WEIGHT
ADAPTIVE_ON = os.getenv("MEMORYOS_ADAPTIVE_THRESHOLD", "true").lower()=="true"
MIN_SIM = float(os.getenv("MEMORYOS_SIM_THRESHOLD_MIN", "0.45"))
MAX_SIM = float(os.getenv("MEMORYOS_SIM_THRESHOLD_MAX", "0.60"))

# Round-5: Memory Aging & Summarization Configuration
MEMORY_AGING_ENABLED = os.getenv("MEMORYOS_MEMORY_AGING_ENABLED", "true").lower() == "true"
SUMMARIZATION_ENABLED = os.getenv("MEMORYOS_SUMMARIZATION_ENABLED", "true").lower() == "true"
STATE_BRIDGE_ENABLED = os.getenv("MEMORYOS_STATE_BRIDGE_ENABLED", "true").lower() == "true"

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
    Build context string for LLM prompt injection (L0 - no embeddings) with Reinjection (Round-7).
    
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
    
    # Round-7: Add Context Reinjection
    reinjected_context = ""
    if REINJECTION_ENABLED:
        try:
            from scripts.context_reinjection import reinject_context
            reinjected_context = reinject_context(user_input)
        except ImportError:
            pass  # Graceful fallback if module not available
    
    # Round-8: Add Memory Graph Related Topics
    related_context = ""
    if GRAPH_ENABLED:
        try:
            from scripts.memory_graph import get_related_context
            related_context = get_related_context(user_input)
        except ImportError:
            pass  # Graceful fallback if module not available
    
    # Combine contexts
    full_context = context_body
    if reinjected_context:
        full_context += "\n\n" + reinjected_context
    if related_context:
        full_context += "\n\n" + related_context
    
    return f"[CONTEXT WINDOW]\n{full_context}\n[END CONTEXT]"


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors using the embeddings module.
    
    Args:
        vec1: First vector
        vec2: Second vector
        
    Returns:
        Cosine similarity score (0.0 to 1.0)
    """
    try:
        from scripts.embeddings import cosine_sim
        return cosine_sim(vec1, vec2)
    except ImportError:
        # Fallback implementation
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
    Get embedding vector for text using the embeddings module.
    
    Args:
        text: Input text
        
    Returns:
        Embedding vector or None if embeddings are disabled
    """
    if not EMBEDDINGS_ENABLED:
        return None
    
    try:
        from scripts.embeddings import get_emb
        return get_emb(text)
    except ImportError:
        print(f"[ContextInjector] Embeddings module not available for: {text[:50]}...")
        return None


def _adaptive_threshold(k:int, base:float)->float:
    """
    Simple heuristic: more candidates → require slightly higher confidence
    """
    if not ADAPTIVE_ON: return base
    adj = min(MAX_SIM, max(MIN_SIM, base + 0.02 * max(0, k-3)))
    return adj

def _similarity_guard(user_input:str, items:List[Dict])->Tuple[bool, List[Tuple[Dict,float]]]:
    """
    L1 similarity guard with adaptive thresholding
    """
    if not EMBEDDINGS_ENABLED or not items:
        return True, [(it, 0.0) for it in items]
    try:
        from scripts.embeddings import cosine_sim, get_emb
        qv = get_emb(user_input)
        scored = []
        for it in items:
            text = json.dumps(it.get("data", {}) or {}, ensure_ascii=False)[:512]
            sim = cosine_sim(qv, get_emb(text))
            scored.append((it, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        threshold = _adaptive_threshold(len(items), SIM_THRESHOLD)
        ok = scored[0][1] >= threshold
        return ok, scored
    except Exception:
        return True, [(it, 0.0) for it in items]

def _hybrid_sort(user_input:str, items:List[Dict], l1_scored:List[Tuple[Dict,float]])->List[Dict]:
    """
    L0+L1 hybrid scoring for final sorting
    """
    # L0 score: keyword-based scoring
    keys = [w for w in re.findall(r"[A-Za-z0-9가-힣_]+", user_input) if len(w)>=2][:3]
    def l0_score(it:Dict)->int:
        dj = it.get("data", {})
        hay = (it.get("type","") + " " + json.dumps(dj, ensure_ascii=False)).lower()
        return sum(1 for k in keys if k.lower() in hay)
    
    l1_map = {id(it): sim for it, sim in l1_scored}
    enriched = []
    for it in items:
        s0 = l0_score(it)
        s1 = l1_map.get(id(it), 0.0)
        hybrid = L0_WEIGHT * s0 + L1_WEIGHT * s1
        enriched.append((hybrid, it))
    enriched.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in enriched]

def _fetch_candidates(user_input: str) -> List[Dict]:
    """Fetch candidate events for context building"""
    # Get recent events
    events = get_recent_events(DB_PATH, LAST_MINUTES, LAST_K_EVENTS)
    if not events:
        return []
    
    # Apply similarity guard with adaptive thresholding
    if EMBEDDINGS_ENABLED:
        ok, l1_scored = _similarity_guard(user_input, events)
        if not ok: 
            return []
        
        # Apply hybrid L0+L1 sorting
        events = _hybrid_sort(user_input, events, l1_scored)
    else:
        # Use L0 filtering only
        events = filter_relevant_events(events, user_input)
    
    return events[:TOP_K_RESULTS]

def build_context_with_embeddings(user_input: str) -> Optional[str]:
    """
    Enhanced context building with hybrid L0+L1 scoring, adaptive thresholding,
    Memory Aging, Summarization (Round-5), and Context Reinjection (Round-7).
    
    Args:
        user_input: User's input text
        
    Returns:
        Context string or None
    """
    if not EMBEDDINGS_ENABLED:
        return build_context_l0(user_input)
    
    # Fetch candidate events
    items = _fetch_candidates(user_input)
    if not items:
        return None
    
    # Round-5: Apply Memory Aging
    if MEMORY_AGING_ENABLED:
        try:
            from scripts.memory_aging import apply_aging_to_items
            items = apply_aging_to_items(items, default_weight=1.0)
        except ImportError:
            pass  # Graceful fallback if module not available
    
    # Round-5: Apply Summarization if needed
    summarized_context = ""
    if SUMMARIZATION_ENABLED:
        try:
            from scripts.snapshot_summarizer import apply_summary_to_chain, should_compress
            if should_compress(items):
                summarized_context = apply_summary_to_chain(items)
        except ImportError:
            pass  # Graceful fallback if module not available
    
    # Use summarized context if available, otherwise format individual events
    if summarized_context:
        context_body = summarized_context
    else:
        # Format individual event summaries
        context_lines = []
        for event in items:
            summary = format_event_summary(event)
            if summary and len(summary) <= 200:
                context_lines.append(summary)
        
        context_lines = context_lines[:8]
        if not context_lines:
            return None
        
        context_body = '\n'.join(context_lines)
    
    # Hard cap on total character count
    if len(context_body) > MAX_CHARS:
        context_body = context_body[:MAX_CHARS] + "..."
    
    # Round-7: Add Context Reinjection
    reinjected_context = ""
    if REINJECTION_ENABLED:
        try:
            from scripts.context_reinjection import reinject_context
            reinjected_context = reinject_context(user_input)
        except ImportError:
            pass  # Graceful fallback if module not available
    
    # Round-8: Add Memory Graph Related Topics
    related_context = ""
    if GRAPH_ENABLED:
        try:
            from scripts.memory_graph import get_related_context
            related_context = get_related_context(user_input)
        except ImportError:
            pass  # Graceful fallback if module not available
    
    # Combine contexts
    full_context = context_body
    if reinjected_context:
        full_context += "\n\n" + reinjected_context
    if related_context:
        full_context += "\n\n" + related_context
    
    # Log telemetry
    try:
        import time
        from pathlib import Path as PathLib
        PathLib("./logs").mkdir(exist_ok=True)
        PathLib("./logs/memoryos_metrics.log").write_text(
            f"[{time.time():.0f}] l1=on aging={'on' if MEMORY_AGING_ENABLED else 'off'} summary={'on' if SUMMARIZATION_ENABLED else 'off'} reinject={'on' if REINJECTION_ENABLED else 'off'} graph={'on' if GRAPH_ENABLED else 'off'}\n", 
            encoding="utf-8"
        )
    except Exception:
        pass
    
    return f"[CONTEXT WINDOW]\n{full_context}\n[END CONTEXT]"


# Main entry point - automatically chooses L0 or L1 based on configuration
# Round-6: Validator Integration Configuration
VALIDATOR_ENABLED = os.getenv("MEMORYOS_VALIDATOR_ENABLED", "true").lower() == "true"
PROPOSAL_PREFIX = os.getenv("MEMORYOS_PROPOSAL_PREFIX", "suggestion:")

# Round-7: Context Reinjection Configuration
REINJECTION_ENABLED = os.getenv("MEMORYOS_REINJECTION_ENABLED", "true").lower() == "true"

# Round-8: Memory Graph Configuration
GRAPH_ENABLED = os.getenv("MEMORYOS_GRAPH_ENABLED", "true").lower() == "true"

def process_llm_proposal(proposal_text: str, user_input: str) -> Tuple[bool, str]:
    """
    Process LLM proposal through validator gate.
    
    Args:
        proposal_text: LLM proposal text
        user_input: Original user input for context
        
    Returns:
        Tuple of (is_approved, reason)
    """
    if not VALIDATOR_ENABLED:
        return False, "Validator disabled"
    
    try:
        from scripts.validator_gate import validate_and_approve
        
        # Parse proposal into structured data
        proposal_data = {
            "text": proposal_text,
            "user_input": user_input,
            "timestamp": datetime.now().isoformat(),
            "type": "llm_proposal"
        }
        
        # Validate through validator gate
        is_approved, reason, _ = validate_and_approve(proposal_data)
        
        return is_approved, reason
        
    except ImportError:
        return False, "Validator modules not available"
    except Exception as e:
        return False, f"Proposal processing error: {str(e)}"

def get_approved_proposals() -> List[Dict]:
    """
    Get approved proposals ready for event_chain insertion.
    
    Returns:
        List of approved proposals
    """
    if not VALIDATOR_ENABLED:
        return []
    
    try:
        from scripts.validator_gate import process_approved_proposals
        return process_approved_proposals()
    except ImportError:
        return []
    except Exception:
        return []

def detect_proposal_prefix(text: str) -> bool:
    """
    Detect if text contains LLM proposal prefix.
    
    Args:
        text: Text to check
        
    Returns:
        True if proposal detected, False otherwise
    """
    return text.strip().lower().startswith(PROPOSAL_PREFIX.lower())

def extract_proposal_content(text: str) -> str:
    """
    Extract proposal content after prefix.
    
    Args:
        text: Text with proposal prefix
        
    Returns:
        Proposal content without prefix
    """
    if detect_proposal_prefix(text):
        return text[len(PROPOSAL_PREFIX):].strip()
    return text.strip()

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
