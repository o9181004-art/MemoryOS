"""
Test suite for MemoryOS Validator System (offline, no network)
"""
import os
import unittest
import tempfile
from pathlib import Path

# Set environment for testing
os.environ["MEMORYOS_VALIDATION_SENSITIVITY"] = "0.8"
os.environ["MEMORYOS_VALIDATOR_ENABLED"] = "true"
os.environ["MEMORYOS_APPROVAL_RETENTION_HR"] = "1"  # Short retention for tests

# Import after setting environment
from scripts.fact_checker import verify_consistency, check_for_duplicates, validate_proposal
from scripts.approval_queue import ApprovalQueue
from scripts.validator_gate import validate_and_approve, check_proposal_consistency, get_approval_stats

class TestFactChecker(unittest.TestCase):
    
    def test_verify_consistency_no_events(self):
        """Test consistency verification with no recent events"""
        proposal = {"status": "ok", "message": "test message"}
        
        is_consistent, score, reason = verify_consistency(proposal)
        
        # Should be consistent if no recent events
        self.assertTrue(is_consistent)
        self.assertEqual(score, 1.0)
        self.assertIn("Consistent", reason)
    
    def test_check_for_duplicates_no_events(self):
        """Test duplicate checking with no recent events"""
        proposal = {"status": "ok", "message": "test message"}
        
        is_duplicate, reason = check_for_duplicates(proposal)
        
        self.assertFalse(is_duplicate)
        self.assertIn("No duplicates", reason)
    
    def test_validate_proposal_valid(self):
        """Test validation of valid proposal"""
        proposal = {"status": "ok", "message": "test message"}
        
        result = validate_proposal(proposal)
        
        self.assertIn("proposal", result)
        self.assertIn("valid", result)
        self.assertIn("consistency_score", result)
        self.assertIn("reasons", result)
    
    def test_validate_proposal_structure(self):
        """Test validation result structure"""
        proposal = {"test": "data"}
        
        result = validate_proposal(proposal)
        
        required_fields = ["proposal", "timestamp", "valid", "consistency_score", "is_duplicate", "reasons"]
        for field in required_fields:
            self.assertIn(field, result)

class TestApprovalQueue(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_queue_file = Path(self.temp_dir) / "test_approvals.json"
        self.test_audit_file = Path(self.temp_dir) / "test_audit.log"
        
        # Set environment variables for test files
        os.environ["MEMORYOS_APPROVAL_QUEUE_FILE"] = str(self.test_queue_file)
        os.environ["MEMORYOS_AUDIT_LOG_FILE"] = str(self.test_audit_file)
    
    def tearDown(self):
        """Clean up test environment"""
        if self.test_queue_file.exists():
            self.test_queue_file.unlink()
        if self.test_audit_file.exists():
            self.test_audit_file.unlink()
    
    def test_approval_queue_creation(self):
        """Test approval queue creation"""
        queue = ApprovalQueue()
        
        self.assertIsInstance(queue.queue, list)
        self.assertEqual(len(queue.queue), 0)
    
    def test_enqueue_approval(self):
        """Test enqueueing approval"""
        queue = ApprovalQueue()
        proposal = {"status": "ok", "message": "test"}
        validation_result = {"valid": True, "consistency_score": 0.9}
        
        success = queue.enqueue_approval(proposal, validation_result)
        
        self.assertTrue(success)
        self.assertEqual(len(queue.queue), 1)
        
        # Check queue entry structure
        entry = queue.queue[0]
        self.assertIn("id", entry)
        self.assertIn("timestamp", entry)
        self.assertIn("proposal", entry)
        self.assertIn("validation_result", entry)
        self.assertEqual(entry["status"], "queued")
    
    def test_log_reject(self):
        """Test logging rejection"""
        queue = ApprovalQueue()
        proposal = {"status": "error", "message": "test"}
        validation_result = {"valid": False, "reasons": ["test reason"]}
        
        # Should not raise exception
        queue.log_reject(proposal, validation_result)
        
        # Check if audit log was created
        self.assertTrue(self.test_audit_file.exists())
    
    def test_get_pending_approvals(self):
        """Test getting pending approvals"""
        queue = ApprovalQueue()
        
        # Add some approvals
        proposal1 = {"test": "data1"}
        proposal2 = {"test": "data2"}
        validation_result = {"valid": True}
        
        queue.enqueue_approval(proposal1, validation_result)
        queue.enqueue_approval(proposal2, validation_result)
        
        pending = queue.get_pending_approvals()
        
        self.assertEqual(len(pending), 2)
        for approval in pending:
            self.assertEqual(approval["status"], "queued")
    
    def test_mark_processed(self):
        """Test marking approval as processed"""
        queue = ApprovalQueue()
        proposal = {"test": "data"}
        validation_result = {"valid": True}
        
        queue.enqueue_approval(proposal, validation_result)
        approval_id = queue.queue[0]["id"]
        
        success = queue.mark_processed(approval_id)
        
        self.assertTrue(success)
        self.assertEqual(queue.queue[0]["status"], "processed")
        self.assertIn("processed_at", queue.queue[0])
    
    def test_get_queue_stats(self):
        """Test getting queue statistics"""
        queue = ApprovalQueue()
        
        # Add some approvals
        proposal = {"test": "data"}
        validation_result = {"valid": True}
        
        queue.enqueue_approval(proposal, validation_result)
        
        stats = queue.get_queue_stats()
        
        self.assertIn("total_approvals", stats)
        self.assertIn("queued", stats)
        self.assertIn("processed", stats)
        self.assertIn("retention_hours", stats)

class TestValidatorGate(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_queue_file = Path(self.temp_dir) / "test_approvals.json"
        self.test_audit_file = Path(self.temp_dir) / "test_audit.log"
        
        # Set environment variables for test files
        os.environ["MEMORYOS_APPROVAL_QUEUE_FILE"] = str(self.test_queue_file)
        os.environ["MEMORYOS_AUDIT_LOG_FILE"] = str(self.test_audit_file)
    
    def tearDown(self):
        """Clean up test environment"""
        if self.test_queue_file.exists():
            self.test_queue_file.unlink()
        if self.test_audit_file.exists():
            self.test_audit_file.unlink()
    
    def test_validate_and_approve_valid_proposal(self):
        """Test validating and approving valid proposal"""
        proposal = {"status": "ok", "message": "test message"}
        
        is_approved, reason, validation_result = validate_and_approve(proposal)
        
        # Should be approved since no recent events to conflict with
        self.assertTrue(is_approved)
        self.assertIn("approved", reason.lower())
        self.assertIsNotNone(validation_result)
    
    def test_check_proposal_consistency(self):
        """Test checking proposal consistency"""
        proposal = {"status": "ok", "message": "test"}
        
        is_consistent, score, reason = check_proposal_consistency(proposal)
        
        self.assertIsInstance(is_consistent, bool)
        self.assertIsInstance(score, float)
        self.assertIsInstance(reason, str)
    
    def test_get_approval_stats(self):
        """Test getting approval statistics"""
        stats = get_approval_stats()
        
        self.assertIsInstance(stats, dict)
        self.assertIn("total_approvals", stats)

if __name__ == "__main__":
    unittest.main()
