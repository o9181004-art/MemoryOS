# -*- coding: utf-8 -*-
"""
Snapshot Summarizer - Compress older memories into summaries.
"""
from typing import List, Dict
import os

# Configuration
MAX_SUMMARY_LENGTH = int(os.environ.get("MEMORYOS_MAX_SUMMARY_LENGTH", "300"))
COMPRESSION_THRESHOLD = int(os.environ.get("MEMORYOS_COMPRESSION_THRESHOLD", "10"))  # Compress if more than N items

def summarize_event_chain(items: List[Dict], max_summary_length: int = MAX_SUMMARY_LENGTH) -> str:
    """Summarize a list of event chain entries into a concise memory."""
    if not items:
        return ""
    
    summary = []
    total_length = 0
    
    # Group events by type for better summarization
    event_types = {}
    for item in items:
        event_type = item.get("type", "unknown")
        if event_type not in event_types:
            event_types[event_type] = []
        event_types[event_type].append(item)
    
    # Create summary for each event type
    for event_type, type_items in event_types.items():
        if total_length >= max_summary_length:
            break
            
        # Count occurrences of this event type
        count = len(type_items)
        if count == 1:
            # Single event - include details
            item = type_items[0]
            event = item.get("data", {})
            timestamp = item.get("timestamp", item.get("ts", ""))
            text = f"[{timestamp}] {event_type.upper()}: {event.get('message', event.get('note', 'N/A'))}"
        else:
            # Multiple events - summarize
            text = f"[{event_type.upper()}] {count} events occurred"
        
        # Check if adding this summary exceeds the limit
        if total_length + len(text) + 1 < max_summary_length:  # +1 for newline
            summary.append(text)
            total_length += len(text) + 1
        else:
            break
    
    return "\n".join(summary)

def apply_summary_to_chain(items: List[Dict]) -> str:
    """Compress and return a summarized version of the event chain"""
    if not items:
        return ""
    
    # Only compress if we have many items
    if len(items) <= COMPRESSION_THRESHOLD:
        return ""
    
    summary = summarize_event_chain(items)
    return summary

def should_compress(items: List[Dict]) -> bool:
    """Determine if the event chain should be compressed"""
    return len(items) > COMPRESSION_THRESHOLD
