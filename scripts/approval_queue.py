# -*- coding: utf-8 -*-
"""
Approval Queue - Validation Queue and Approval Log Management
Manages approved proposals and maintains audit logs
"""
import os
import json
import time
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime, timedelta

# Configuration
APPROVAL_RETENTION_HR = int(os.getenv("MEMORYOS_APPROVAL_RETENTION_HR", "12"))
VALIDATOR_LOGLEVEL = os.getenv("MEMORYOS_VALIDATOR_LOGLEVEL", "info")
APPROVAL_QUEUE_FILE = Path(os.getenv("MEMORYOS_APPROVAL_QUEUE_FILE", "./data_ollama/approvals.json"))
AUDIT_LOG_FILE = Path(os.getenv("MEMORYOS_AUDIT_LOG_FILE", "./logs/validator_audit.log"))

class ApprovalQueue:
    """Manages approved proposals and audit logging"""
    
    def __init__(self):
        self.queue = []
        self._load_queue()
        self._ensure_log_directory()
    
    def _ensure_log_directory(self):
        """Ensure log directory exists"""
        try:
            AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            APPROVAL_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    
    def _load_queue(self):
        """Load approval queue from persistent storage"""
        if not APPROVAL_QUEUE_FILE.exists():
            self.queue = []
            return
        
        try:
            with open(APPROVAL_QUEUE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.queue = data.get("queue", [])
        except (json.JSONDecodeError, OSError, IOError):
            self.queue = []
    
    def _save_queue(self):
        """Save approval queue to persistent storage"""
        try:
            data = {
                "queue": self.queue,
                "last_updated": datetime.now().isoformat()
            }
            with open(APPROVAL_QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (OSError, IOError):
            pass
    
    def _log_audit(self, level: str, message: str, data: Optional[Dict] = None):
        """Log audit information"""
        try:
            timestamp = datetime.now().isoformat()
            log_entry = {
                "timestamp": timestamp,
                "level": level,
                "message": message,
                "data": data or {}
            }
            
            # Write to audit log file
            with open(AUDIT_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
                
        except Exception:
            pass
    
    def enqueue_approval(self, proposal: Dict, validation_result: Dict) -> bool:
        """
        Add approved proposal to queue
        
        Args:
            proposal: Original LLM proposal
            validation_result: Validation result from fact_checker
            
        Returns:
            True if successfully queued, False otherwise
        """
        try:
            approval_entry = {
                "id": f"approval_{int(time.time() * 1000)}",
                "timestamp": datetime.now().isoformat(),
                "proposal": proposal,
                "validation_result": validation_result,
                "status": "queued"
            }
            
            self.queue.append(approval_entry)
            self._save_queue()
            
            # Log approval
            self._log_audit("info", "Proposal approved and queued", {
                "approval_id": approval_entry["id"],
                "consistency_score": validation_result.get("consistency_score", 0.0)
            })
            
            return True
            
        except Exception as e:
            self._log_audit("error", f"Failed to queue approval: {str(e)}")
            return False
    
    def log_reject(self, proposal: Dict, validation_result: Dict):
        """
        Log rejected proposal
        
        Args:
            proposal: Original LLM proposal
            validation_result: Validation result from fact_checker
        """
        try:
            self._log_audit("warn", "Proposal rejected", {
                "proposal": proposal,
                "validation_result": validation_result,
                "reasons": validation_result.get("reasons", [])
            })
        except Exception:
            pass
    
    def get_pending_approvals(self) -> List[Dict]:
        """Get all pending approvals"""
        return [entry for entry in self.queue if entry.get("status") == "queued"]
    
    def mark_processed(self, approval_id: str) -> bool:
        """
        Mark approval as processed
        
        Args:
            approval_id: ID of approval to mark as processed
            
        Returns:
            True if found and marked, False otherwise
        """
        try:
            for entry in self.queue:
                if entry.get("id") == approval_id:
                    entry["status"] = "processed"
                    entry["processed_at"] = datetime.now().isoformat()
                    self._save_queue()
                    
                    self._log_audit("info", f"Approval {approval_id} marked as processed")
                    return True
            
            return False
            
        except Exception as e:
            self._log_audit("error", f"Failed to mark approval as processed: {str(e)}")
            return False
    
    def cleanup_old_approvals(self):
        """Remove old approvals based on retention policy"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=APPROVAL_RETENTION_HR)
            cutoff_str = cutoff_time.isoformat()
            
            original_count = len(self.queue)
            self.queue = [
                entry for entry in self.queue 
                if entry.get("timestamp", "") > cutoff_str
            ]
            
            removed_count = original_count - len(self.queue)
            if removed_count > 0:
                self._save_queue()
                self._log_audit("info", f"Cleaned up {removed_count} old approvals")
                
        except Exception as e:
            self._log_audit("error", f"Failed to cleanup old approvals: {str(e)}")
    
    def get_queue_stats(self) -> Dict:
        """Get queue statistics"""
        try:
            queued_count = len([e for e in self.queue if e.get("status") == "queued"])
            processed_count = len([e for e in self.queue if e.get("status") == "processed"])
            
            return {
                "total_approvals": len(self.queue),
                "queued": queued_count,
                "processed": processed_count,
                "retention_hours": APPROVAL_RETENTION_HR
            }
        except Exception:
            return {"total_approvals": 0, "queued": 0, "processed": 0, "retention_hours": APPROVAL_RETENTION_HR}

# Global instance
_approval_queue = None

def get_approval_queue() -> ApprovalQueue:
    """Get the global ApprovalQueue instance"""
    global _approval_queue
    if _approval_queue is None:
        _approval_queue = ApprovalQueue()
    return _approval_queue

def enqueue_approval(proposal: Dict, validation_result: Dict) -> bool:
    """Convenience function to enqueue approval"""
    queue = get_approval_queue()
    return queue.enqueue_approval(proposal, validation_result)

def log_reject(proposal: Dict, validation_result: Dict):
    """Convenience function to log rejection"""
    queue = get_approval_queue()
    queue.log_reject(proposal, validation_result)
