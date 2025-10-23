# -*- coding: utf-8 -*-
"""
Context Reinjection Engine (L6)
Reinject previously validated memories into new prompts.
"""
import os
import json
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

# Configuration
CACHE_PATH = Path(os.environ.get("MEMORYOS_APPROVED_CACHE", "./data_ollama/approvals.json"))
MAX_REINJECT = int(os.environ.get("MEMORYOS_REINJECT_TOPK", "3"))
MAX_AGE_MIN = int(os.environ.get("MEMORYOS_REINJECT_MAXAGE_MIN", "720"))  # 12h
MIN_RELEVANCE = float(os.environ.get("MEMORYOS_REINJECT_MIN_SCORE", "0.55"))
REINJECTION_ENABLED = os.environ.get("MEMORYOS_REINJECTION_ENABLED", "true").lower() == "true"

def _load_approved() -> List[Dict]:
    """Load approved memories from cache"""
    if not CACHE_PATH.exists():
        return []
    try:
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Handle both direct list and wrapped format
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "queue" in data:
                return data["queue"]
            else:
                return []
    except (json.JSONDecodeError, OSError, IOError):
        return []

def _filter_recent(items: List[Dict]) -> List[Dict]:
    """Filter items to only include recent ones within MAX_AGE_MIN"""
    if not items:
        return []
    
    now = datetime.now()
    recent_items = []
    
    for item in items:
        try:
            # Try to get timestamp from various possible fields
            timestamp_str = None
            for field in ["timestamp", "ts", "processed_at"]:
                if field in item:
                    timestamp_str = item[field]
                    break
            
            if not timestamp_str:
                continue
                
            # Parse timestamp (handle both with and without timezone)
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str[:-1]
            
            ts = datetime.fromisoformat(timestamp_str)
            age_diff = now - ts
            
            if age_diff < timedelta(minutes=MAX_AGE_MIN):
                recent_items.append(item)
                
        except (ValueError, TypeError):
            # Skip items with invalid timestamps
            continue
    
    return recent_items

def _score_relevance(user_input: str, item: Dict) -> float:
    """Calculate lightweight keyword overlap relevance score"""
    if not user_input or not item:
        return 0.0
    
    try:
        # Extract keywords from user input
        keys = [w.lower() for w in re.findall(r"[A-Za-z0-9가-힣_]+", user_input) if len(w) >= 2]
        
        if not keys:
            return 0.0
        
        # Convert item to searchable text
        searchable_text = ""
        
        # Include proposal text if available
        if "proposal" in item:
            proposal = item["proposal"]
            if isinstance(proposal, dict):
                searchable_text += json.dumps(proposal, ensure_ascii=False).lower()
            else:
                searchable_text += str(proposal).lower()
        
        # Include validation result summary
        if "validation_result" in item:
            validation = item["validation_result"]
            if isinstance(validation, dict):
                searchable_text += json.dumps(validation, ensure_ascii=False).lower()
        
        # Include any summary or note fields
        for field in ["summary", "note", "message", "text"]:
            if field in item:
                searchable_text += str(item[field]).lower()
        
        if not searchable_text:
            return 0.0
        
        # Calculate overlap score
        overlap = sum(1 for key in keys if key in searchable_text)
        relevance_score = min(1.0, overlap / len(keys))
        
        return relevance_score
        
    except Exception:
        return 0.0

def _format_reinjected_item(item: Dict) -> str:
    """Format a single reinjected item for display"""
    try:
        # Get timestamp
        timestamp = "Unknown"
        for field in ["timestamp", "ts", "processed_at"]:
            if field in item:
                timestamp = item[field]
                break
        
        # Get summary text
        summary = ""
        
        # Try to extract meaningful summary from proposal
        if "proposal" in item:
            proposal = item["proposal"]
            if isinstance(proposal, dict):
                # Look for key fields in proposal
                for field in ["text", "message", "summary", "note"]:
                    if field in proposal:
                        summary = str(proposal[field])
                        break
            else:
                summary = str(proposal)
        
        # Fallback to validation result
        if not summary and "validation_result" in item:
            validation = item["validation_result"]
            if isinstance(validation, dict):
                reasons = validation.get("reasons", [])
                if reasons:
                    summary = "; ".join(reasons[:2])  # Take first 2 reasons
        
        # Fallback to generic summary
        if not summary:
            summary = "Validated memory"
        
        # Truncate if too long
        if len(summary) > 100:
            summary = summary[:97] + "..."
        
        return f"- {timestamp} | {summary}"
        
    except Exception:
        return f"- {item.get('timestamp', 'Unknown')} | Validated memory"

def reinject_context(user_input: str) -> str:
    """
    Return summarized validated memories related to current input
    
    Args:
        user_input: Current user input to match against
        
    Returns:
        Formatted reinjected context string or empty string
    """
    if not REINJECTION_ENABLED or not user_input:
        return ""
    
    start_time = time.perf_counter()
    
    try:
        # Load and filter approved memories
        all_items = _load_approved()
        recent_items = _filter_recent(all_items)
        
        if not recent_items:
            return ""
        
        # Score relevance for each item
        scored_items = []
        for item in recent_items:
            score = _score_relevance(user_input, item)
            if score >= MIN_RELEVANCE:
                scored_items.append((item, score))
        
        # Sort by relevance score (descending)
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        # Take top items
        relevant_items = [item for item, score in scored_items[:MAX_REINJECT]]
        
        if not relevant_items:
            return ""
        
        # Format reinjected context
        lines = []
        for item in relevant_items:
            formatted_line = _format_reinjected_item(item)
            lines.append(formatted_line)
        
        reinjected_text = "\n".join(lines)
        
        # Log telemetry
        try:
            avg_score = sum(score for _, score in scored_items[:MAX_REINJECT]) / len(relevant_items)
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            from pathlib import Path as PathLib
            PathLib("./logs").mkdir(exist_ok=True)
            PathLib("./logs/memoryos_metrics.log").write_text(
                f"[{time.time():.0f}] reinject used={len(relevant_items)} avg_score={avg_score:.2f} latency={latency_ms:.1f}ms\n",
                encoding="utf-8"
            )
        except Exception:
            pass
        
        return f"[REINJECTED CONTEXT]\n{reinjected_text}"
        
    except Exception:
        return ""

def get_reinjection_stats() -> Dict:
    """Get reinjection statistics"""
    try:
        all_items = _load_approved()
        recent_items = _filter_recent(all_items)
        
        return {
            "total_approved": len(all_items),
            "recent_approved": len(recent_items),
            "max_reinject": MAX_REINJECT,
            "max_age_minutes": MAX_AGE_MIN,
            "min_relevance": MIN_RELEVANCE,
            "enabled": REINJECTION_ENABLED
        }
    except Exception:
        return {
            "total_approved": 0,
            "recent_approved": 0,
            "max_reinject": MAX_REINJECT,
            "max_age_minutes": MAX_AGE_MIN,
            "min_relevance": MIN_RELEVANCE,
            "enabled": REINJECTION_ENABLED
        }
