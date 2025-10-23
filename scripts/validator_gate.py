# -*- coding: utf-8 -*-
"""
MemoryOS Validator Gate - Fact-Consistency & Approval Layer (Round-6)
Receives LLM outputs, performs factual and consistency checks
before any data can be written into event_chain.
"""
import os
from typing import Dict, Tuple, Optional, List

# Configuration
VALIDATOR_ENABLED = os.getenv("MEMORYOS_VALIDATOR_ENABLED", "true").lower() == "true"
AUTO_APPROVE_THRESHOLD = float(os.getenv("MEMORYOS_AUTO_APPROVE_THRESHOLD", "0.9"))

def validate_and_approve(proposal: Dict) -> Tuple[bool, str, Optional[Dict]]:
    """
    Validate new LLM proposal and approve if consistent.
    
    Args:
        proposal: LLM proposal data to validate
        
    Returns:
        Tuple of (is_approved, reason, validation_result)
    """
    if not VALIDATOR_ENABLED:
        return False, "Validator disabled", None
    
    try:
        # Import validation modules
        from scripts.fact_checker import validate_proposal
        from scripts.approval_queue import enqueue_approval, log_reject
        
        # Validate proposal
        validation_result = validate_proposal(proposal)
        
        if validation_result.get("valid", False):
            # Proposal is valid - queue for approval
            success = enqueue_approval(proposal, validation_result)
            if success:
                return True, "Proposal approved and queued", validation_result
            else:
                return False, "Failed to queue approved proposal", validation_result
        else:
            # Proposal is invalid - log rejection
            log_reject(proposal, validation_result)
            reasons = validation_result.get("reasons", ["Unknown validation failure"])
            return False, f"Proposal rejected: {'; '.join(reasons)}", validation_result
            
    except ImportError as e:
        return False, f"Validation modules not available: {str(e)}", None
    except Exception as e:
        return False, f"Validation error: {str(e)}", None

def validate_llm_suggestion(data: Dict) -> bool:
    """
    Legacy function for backward compatibility.
    Validate any LLM-proposed memory before event_chain insertion.
    
    Args:
        data: LLM suggestion data
        
    Returns:
        True if approved, False if rejected
    """
    is_approved, _, _ = validate_and_approve(data)
    return is_approved

def check_proposal_consistency(proposal: Dict) -> Tuple[bool, float, str]:
    """
    Check consistency of proposal against recent events.
    
    Args:
        proposal: LLM proposal to check
        
    Returns:
        Tuple of (is_consistent, consistency_score, reason)
    """
    try:
        from scripts.fact_checker import verify_consistency
        return verify_consistency(proposal)
    except ImportError:
        return False, 0.0, "Fact checker not available"
    except Exception as e:
        return False, 0.0, f"Consistency check error: {str(e)}"

def get_approval_stats() -> Dict:
    """Get approval queue statistics"""
    try:
        from scripts.approval_queue import get_approval_queue
        queue = get_approval_queue()
        return queue.get_queue_stats()
    except ImportError:
        return {"error": "Approval queue not available"}
    except Exception as e:
        return {"error": f"Failed to get stats: {str(e)}"}

def cleanup_approvals():
    """Clean up old approvals"""
    try:
        from scripts.approval_queue import get_approval_queue
        queue = get_approval_queue()
        queue.cleanup_old_approvals()
    except ImportError:
        pass
    except Exception:
        pass

def process_approved_proposals() -> List[Dict]:
    """
    Process approved proposals and return them for event_chain insertion.
    
    Returns:
        List of approved proposals ready for event_chain
    """
    try:
        from scripts.approval_queue import get_approval_queue
        queue = get_approval_queue()
        
        pending_approvals = queue.get_pending_approvals()
        processed_proposals = []
        
        for approval in pending_approvals:
            proposal = approval.get("proposal", {})
            if proposal:
                processed_proposals.append(proposal)
                # Mark as processed
                queue.mark_processed(approval.get("id", ""))
        
        return processed_proposals
        
    except ImportError:
        return []
    except Exception:
        return []
