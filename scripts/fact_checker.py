# -*- coding: utf-8 -*-
"""
Fact Checker - LLM Response Consistency Verification Engine
Validates LLM proposals against recent event_chain for consistency
"""
import os
import json
import sqlite3
import hashlib
from typing import Dict, List, Tuple
from datetime import datetime

# Configuration
VALIDATION_SENSITIVITY = float(os.getenv("MEMORYOS_VALIDATION_SENSITIVITY", "0.8"))
DB_PATH = os.getenv("MEMORYOS_DB", "./data_ollama/memoryos.db")
RECENT_EVENTS_LIMIT = int(os.getenv("MEMORYOS_FACT_CHECK_LIMIT", "20"))
CONFLICT_THRESHOLD = float(os.getenv("MEMORYOS_CONFLICT_THRESHOLD", "0.7"))

def get_recent_events_for_validation(limit: int = RECENT_EVENTS_LIMIT) -> List[Dict]:
    """Get recent events for consistency checking"""
    if not os.path.exists(DB_PATH):
        return []
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        query = """
        SELECT id, ts, type, data_json 
        FROM event_chain 
        ORDER BY ts DESC 
        LIMIT ?
        """
        
        cursor.execute(query, (limit,))
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
        
    except Exception:
        return []

def extract_key_fields(event_data: Dict) -> Dict[str, str]:
    """Extract key fields for consistency checking"""
    key_fields = {}
    
    # Extract common key fields
    for field in ["status", "message", "error", "component", "level", "operation"]:
        if field in event_data:
            key_fields[field] = str(event_data[field]).lower()
    
    # Extract hash of full data for exact matching
    data_str = json.dumps(event_data, sort_keys=True, ensure_ascii=False)
    key_fields["data_hash"] = hashlib.sha256(data_str.encode()).hexdigest()[:16]
    
    return key_fields

def calculate_consistency_score(proposal: Dict, recent_events: List[Dict]) -> float:
    """Calculate consistency score between proposal and recent events"""
    if not recent_events:
        return 1.0  # No conflicts if no recent events
    
    proposal_fields = extract_key_fields(proposal)
    conflict_count = 0
    total_checks = 0
    
    for event in recent_events:
        event_fields = extract_key_fields(event.get("data", {}))
        
        # Check for direct conflicts
        for field in ["status", "message", "error", "component"]:
            if field in proposal_fields and field in event_fields:
                total_checks += 1
                if proposal_fields[field] != event_fields[field]:
                    # Check if this is a direct contradiction
                    if _is_direct_contradiction(field, proposal_fields[field], event_fields[field]):
                        conflict_count += 1
    
    if total_checks == 0:
        return 1.0
    
    consistency_score = 1.0 - (conflict_count / total_checks)
    return max(0.0, consistency_score)

def _is_direct_contradiction(field: str, proposal_value: str, event_value: str) -> bool:
    """Check if two values represent a direct contradiction"""
    contradictions = {
        "status": [("ok", "error"), ("success", "failed"), ("active", "inactive")],
        "message": [],  # Message contradictions are context-dependent
        "error": [],    # Error contradictions are context-dependent
        "component": []  # Component contradictions are context-dependent
    }
    
    if field in contradictions:
        for neg_pair in contradictions[field]:
            if (proposal_value in neg_pair and event_value in neg_pair and 
                proposal_value != event_value):
                return True
    
    return False

def verify_consistency(proposal: Dict) -> Tuple[bool, float, str]:
    """
    Verify consistency of LLM proposal against recent event_chain
    
    Args:
        proposal: LLM proposal data to validate
        
    Returns:
        Tuple of (is_consistent, consistency_score, reason)
    """
    try:
        # Get recent events for comparison
        recent_events = get_recent_events_for_validation()
        
        # Calculate consistency score
        consistency_score = calculate_consistency_score(proposal, recent_events)
        
        # Determine if proposal is consistent
        is_consistent = consistency_score >= VALIDATION_SENSITIVITY
        
        # Generate reason
        if is_consistent:
            reason = f"Consistent with recent events (score: {consistency_score:.2f})"
        else:
            reason = f"Inconsistent with recent events (score: {consistency_score:.2f}, threshold: {VALIDATION_SENSITIVITY})"
        
        return is_consistent, consistency_score, reason
        
    except Exception as e:
        # Safe fallback: reject on error
        return False, 0.0, f"Validation error: {str(e)}"

def check_for_duplicates(proposal: Dict) -> Tuple[bool, str]:
    """
    Check if proposal is a duplicate of recent events
    
    Args:
        proposal: LLM proposal data to check
        
    Returns:
        Tuple of (is_duplicate, reason)
    """
    try:
        recent_events = get_recent_events_for_validation()
        proposal_hash = extract_key_fields(proposal).get("data_hash", "")
        
        for event in recent_events:
            event_hash = extract_key_fields(event.get("data", {})).get("data_hash", "")
            if proposal_hash == event_hash:
                return True, f"Duplicate of event {event.get('id', 'unknown')}"
        
        return False, "No duplicates found"
        
    except Exception:
        return False, "Duplicate check failed"

def validate_proposal(proposal: Dict) -> Dict:
    """
    Comprehensive validation of LLM proposal
    
    Args:
        proposal: LLM proposal data to validate
        
    Returns:
        Validation result dictionary
    """
    result = {
        "proposal": proposal,
        "timestamp": datetime.now().isoformat(),
        "valid": False,
        "consistency_score": 0.0,
        "is_duplicate": False,
        "reasons": []
    }
    
    # Check for duplicates first
    is_duplicate, duplicate_reason = check_for_duplicates(proposal)
    result["is_duplicate"] = is_duplicate
    result["reasons"].append(duplicate_reason)
    
    if is_duplicate:
        result["reasons"].append("Rejected: Duplicate proposal")
        return result
    
    # Check consistency
    is_consistent, consistency_score, consistency_reason = verify_consistency(proposal)
    result["consistency_score"] = consistency_score
    result["reasons"].append(consistency_reason)
    
    if is_consistent:
        result["valid"] = True
        result["reasons"].append("Approved: Passed consistency check")
    else:
        result["reasons"].append("Rejected: Failed consistency check")
    
    return result
