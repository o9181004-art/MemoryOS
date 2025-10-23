"""
Test suite for MemoryOS Governance & Safety Layer (offline, no network)
"""
import os
import unittest
import tempfile
import json
from pathlib import Path

# Set environment for testing
os.environ["MEMORYOS_GOVERNANCE_ENABLED"] = "true"
os.environ["MEMORYOS_POLICY_MODE"] = "strict"
os.environ["MEMORYOS_AUDIT_PATH"] = "./logs/governance_audit.log"

# Import after setting environment
from scripts.governance_layer import (
    check_ethics, check_safety, check_privacy, anonymize_sensitive_info,
    mask_privacy_info, governance_filter, governance_scan_context,
    get_governance_stats, governance_telemetry
)

class TestGovernanceLayer(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_audit_file = Path(self.temp_dir) / "test_audit.log"
        
        # Set environment variable for test audit file
        os.environ["MEMORYOS_AUDIT_PATH"] = str(self.test_audit_file)
        
        # Ensure governance is enabled for most tests
        os.environ["MEMORYOS_GOVERNANCE_ENABLED"] = "true"
    
    def tearDown(self):
        """Clean up test environment"""
        if self.test_audit_file.exists():
            self.test_audit_file.unlink()
    
    def test_check_ethics_clean_text(self):
        """Test ethics check with clean text"""
        clean_text = "This is a normal system message about performance optimization."
        is_ethical, violations = check_ethics(clean_text)
        
        self.assertTrue(is_ethical)
        self.assertEqual(len(violations), 0)
    
    def test_check_ethics_unethical_content(self):
        """Test ethics check with unethical content"""
        unethical_text = "This contains hate speech and violence."
        is_ethical, violations = check_ethics(unethical_text)
        
        self.assertFalse(is_ethical)
        self.assertGreater(len(violations), 0)
        self.assertTrue(any("hate" in v.lower() for v in violations))
    
    def test_check_ethics_empty_text(self):
        """Test ethics check with empty text"""
        is_ethical, violations = check_ethics("")
        
        self.assertTrue(is_ethical)
        self.assertEqual(len(violations), 0)
    
    def test_check_ethics_none_text(self):
        """Test ethics check with None text"""
        is_ethical, violations = check_ethics(None)
        
        self.assertTrue(is_ethical)
        self.assertEqual(len(violations), 0)
    
    def test_check_safety_clean_text(self):
        """Test safety check with clean text"""
        clean_text = "System performance is optimal."
        is_safe, sensitive_items = check_safety(clean_text)
        
        self.assertTrue(is_safe)
        self.assertEqual(len(sensitive_items), 0)
    
    def test_check_safety_phone_number(self):
        """Test safety check with phone number"""
        phone_text = "Contact us at 010-1234-5678 for support."
        is_safe, sensitive_items = check_safety(phone_text)
        
        self.assertFalse(is_safe)
        self.assertGreater(len(sensitive_items), 0)
        self.assertTrue(any("010-1234-5678" in item for item in sensitive_items))
    
    def test_check_safety_email_address(self):
        """Test safety check with email address"""
        email_text = "Send feedback to test@example.com"
        is_safe, sensitive_items = check_safety(email_text)
        
        self.assertFalse(is_safe)
        self.assertGreater(len(sensitive_items), 0)
        self.assertTrue(any("test@example.com" in item for item in sensitive_items))
    
    def test_check_safety_credit_card(self):
        """Test safety check with credit card number"""
        card_text = "Payment card: 1234-5678-9012-3456"
        is_safe, sensitive_items = check_safety(card_text)
        
        self.assertFalse(is_safe)
        self.assertGreater(len(sensitive_items), 0)
    
    def test_check_privacy_clean_text(self):
        """Test privacy check with clean text"""
        clean_text = "System status is normal."
        is_private, privacy_concerns = check_privacy(clean_text)
        
        self.assertTrue(is_private)
        self.assertEqual(len(privacy_concerns), 0)
    
    def test_check_privacy_sensitive_terms(self):
        """Test privacy check with sensitive terms"""
        sensitive_text = "User password is confidential and private."
        is_private, privacy_concerns = check_privacy(sensitive_text)
        
        self.assertFalse(is_private)
        self.assertGreater(len(privacy_concerns), 0)
        self.assertTrue(any("password" in c.lower() for c in privacy_concerns))
    
    def test_anonymize_sensitive_info_phone(self):
        """Test anonymization of phone numbers"""
        text = "Call 010-1234-5678 for support."
        anonymized = anonymize_sensitive_info(text)
        
        self.assertIn("[PHONE]", anonymized)
        self.assertNotIn("010-1234-5678", anonymized)
    
    def test_anonymize_sensitive_info_email(self):
        """Test anonymization of email addresses"""
        text = "Email us at test@example.com"
        anonymized = anonymize_sensitive_info(text)
        
        self.assertIn("[EMAIL]", anonymized)
        self.assertNotIn("test@example.com", anonymized)
    
    def test_anonymize_sensitive_info_multiple(self):
        """Test anonymization of multiple sensitive items"""
        text = "Contact 010-1234-5678 or test@example.com for help."
        anonymized = anonymize_sensitive_info(text)
        
        self.assertIn("[PHONE]", anonymized)
        self.assertIn("[EMAIL]", anonymized)
        self.assertNotIn("010-1234-5678", anonymized)
        self.assertNotIn("test@example.com", anonymized)
    
    def test_mask_privacy_info(self):
        """Test masking of privacy-related information"""
        text = "The password is secret and confidential."
        masked = mask_privacy_info(text)
        
        self.assertIn("[PASSWORD]", masked)
        self.assertIn("[SECRET]", masked)
        self.assertIn("[CONFIDENTIAL]", masked)
    
    def test_governance_filter_clean_text(self):
        """Test governance filter with clean text"""
        clean_text = "System performance is optimal."
        filtered = governance_filter(clean_text)
        
        self.assertEqual(filtered, clean_text)
    
    def test_governance_filter_unethical_content(self):
        """Test governance filter with unethical content"""
        unethical_text = "This contains hate speech."
        filtered = governance_filter(unethical_text)
        
        self.assertIn("[BLOCKED", filtered)
        self.assertIn("unethical", filtered)
    
    def test_governance_filter_sensitive_content(self):
        """Test governance filter with sensitive content"""
        sensitive_text = "Contact 010-1234-5678 for help."
        filtered = governance_filter(sensitive_text)
        
        self.assertIn("[PHONE]", filtered)
        self.assertNotIn("010-1234-5678", filtered)
    
    def test_governance_filter_privacy_content(self):
        """Test governance filter with privacy content"""
        privacy_text = "The password is secret."
        filtered = governance_filter(privacy_text)
        
        self.assertIn("[PASSWORD]", filtered)
        self.assertIn("[SECRET]", filtered)
    
    def test_governance_filter_empty_text(self):
        """Test governance filter with empty text"""
        filtered = governance_filter("")
        
        self.assertEqual(filtered, "")
    
    def test_governance_filter_none_text(self):
        """Test governance filter with None text"""
        filtered = governance_filter(None)
        
        self.assertEqual(filtered, None)
    
    def test_governance_scan_context_clean(self):
        """Test governance scan with clean context"""
        clean_context = "System status is normal."
        result = governance_scan_context(clean_context)
        
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["scanned"])
        self.assertTrue(result["is_ethical"])
        self.assertTrue(result["is_safe"])
        self.assertTrue(result["is_private"])
    
    def test_governance_scan_context_unethical(self):
        """Test governance scan with unethical context"""
        unethical_context = "This contains violence and hate."
        result = governance_scan_context(unethical_context)
        
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["scanned"])
        self.assertFalse(result["is_ethical"])
        self.assertGreater(len(result["ethics_violations"]), 0)
    
    def test_governance_scan_context_sensitive(self):
        """Test governance scan with sensitive context"""
        sensitive_context = "Contact 010-1234-5678 or test@example.com"
        result = governance_scan_context(sensitive_context)
        
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["scanned"])
        self.assertFalse(result["is_safe"])
        self.assertGreater(len(result["sensitive_items"]), 0)
    
    def test_governance_scan_context_empty(self):
        """Test governance scan with empty context"""
        result = governance_scan_context("")
        
        self.assertEqual(result["status"], "empty")
        self.assertTrue(result["scanned"])
    
    def test_governance_scan_context_none(self):
        """Test governance scan with None context"""
        result = governance_scan_context(None)
        
        self.assertEqual(result["status"], "empty")
        self.assertTrue(result["scanned"])
    
    def test_get_governance_stats(self):
        """Test getting governance statistics"""
        stats = get_governance_stats()
        
        self.assertIn("enabled", stats)
        self.assertIn("policy_mode", stats)
        self.assertIn("ethics_patterns", stats)
        self.assertIn("sensitive_patterns", stats)
        self.assertIn("privacy_patterns", stats)
        self.assertIn("audit_log_path", stats)
        
        self.assertTrue(stats["enabled"])
        self.assertEqual(stats["policy_mode"], "strict")
        self.assertGreater(stats["ethics_patterns"], 0)
        self.assertGreater(stats["sensitive_patterns"], 0)
        self.assertGreater(stats["privacy_patterns"], 0)
    
    def test_governance_disabled(self):
        """Test governance functionality when disabled"""
        os.environ["MEMORYOS_GOVERNANCE_ENABLED"] = "false"
        
        # All governance functions should return original content when disabled
        unethical_text = "This contains hate speech."
        filtered = governance_filter(unethical_text)
        self.assertEqual(filtered, unethical_text)  # Should not be filtered
        
        sensitive_text = "Contact 010-1234-5678"
        filtered = governance_filter(sensitive_text)
        self.assertEqual(filtered, sensitive_text)  # Should not be filtered
        
        scan_result = governance_scan_context("test context")
        self.assertEqual(scan_result["status"], "disabled")
        
        stats = get_governance_stats()
        self.assertFalse(stats["enabled"])
        
        # Restore enabled state
        os.environ["MEMORYOS_GOVERNANCE_ENABLED"] = "true"
    
    def test_audit_logging(self):
        """Test that governance actions are logged to audit file"""
        # Clear any existing audit log
        if self.test_audit_file.exists():
            self.test_audit_file.unlink()
        
        # Trigger governance actions
        governance_filter("This contains hate speech.")
        governance_filter("Contact 010-1234-5678")
        
        # Check that audit log was created and contains entries
        self.assertTrue(self.test_audit_file.exists())
        
        with open(self.test_audit_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
        
        # Should contain audit entries
        self.assertIn("block", log_content)
        self.assertIn("anonymize", log_content)
        self.assertIn("unethical", log_content)
        self.assertIn("sensitive", log_content)
    
    def test_governance_telemetry(self):
        """Test governance telemetry logging"""
        # This test verifies that telemetry function doesn't crash
        # The actual metrics logging is tested indirectly through other tests
        try:
            governance_telemetry()
            # If no exception is raised, test passes
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"governance_telemetry raised an exception: {e}")
    
    def test_comprehensive_governance_workflow(self):
        """Test complete governance workflow"""
        # Test text with multiple issues
        problematic_text = "Contact 010-1234-5678 for hate speech support at test@example.com"
        
        # Apply governance filter
        filtered = governance_filter(problematic_text)
        
        # Should anonymize sensitive info but not block (no ethics violations)
        self.assertIn("[PHONE]", filtered)
        self.assertIn("[EMAIL]", filtered)
        self.assertNotIn("010-1234-5678", filtered)
        self.assertNotIn("test@example.com", filtered)
        
        # Test with actual ethics violation
        unethical_text = "This contains violence and hate speech."
        filtered_unethical = governance_filter(unethical_text)
        
        # Should be blocked
        self.assertIn("[BLOCKED", filtered_unethical)
        self.assertIn("unethical", filtered_unethical)

if __name__ == "__main__":
    unittest.main()
