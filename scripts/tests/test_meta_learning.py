"""
Test suite for MemoryOS Meta-Learning Layer (offline, no network)
"""
import os
import unittest
import tempfile
import json
from pathlib import Path
from datetime import datetime

# Set environment for testing
os.environ["MEMORYOS_META_LEARNING_ENABLED"] = "true"
os.environ["MEMORYOS_TUNING_MODE"] = "auto"
os.environ["MEMORYOS_LATENCY_TARGET"] = "2.5"
os.environ["MEMORYOS_POLICY_INTERVAL_MIN"] = "60"

# Import after setting environment
from scripts.meta_learning import (
    _load_metrics, _load_audit_log, _load_insight_log, analyze_metrics,
    analyze_audit_log, analyze_insights, detect_performance_drift,
    tune_policy, apply_policy, run_meta_learning, get_meta_learning_stats
)

class TestMetaLearning(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_metrics_file = Path(self.temp_dir) / "test_metrics.log"
        self.test_audit_file = Path(self.temp_dir) / "test_audit.log"
        self.test_insight_file = Path(self.temp_dir) / "test_insights.log"
        self.test_policy_file = Path(self.temp_dir) / "test_policy.json"
        
        # Set environment variables for test files
        os.environ["MEMORYOS_METRICS_PATH"] = str(self.test_metrics_file)
        os.environ["MEMORYOS_AUDIT_PATH"] = str(self.test_audit_file)
        os.environ["MEMORYOS_INSIGHT_LOG"] = str(self.test_insight_file)
        os.environ["MEMORYOS_POLICY_PATH"] = str(self.test_policy_file)
        
        # Ensure meta-learning is enabled for most tests
        os.environ["MEMORYOS_META_LEARNING_ENABLED"] = "true"
    
    def tearDown(self):
        """Clean up test environment"""
        for file_path in [self.test_metrics_file, self.test_audit_file, 
                         self.test_insight_file, self.test_policy_file]:
            if file_path.exists():
                file_path.unlink()
    
    def test_load_metrics_empty_file(self):
        """Test loading metrics from non-existent file"""
        result = _load_metrics()
        self.assertEqual(result, [])
    
    def test_load_metrics_valid_data(self):
        """Test loading metrics from valid file"""
        test_data = [
            "[1735000000] l1=on latency=2.1ms",
            "[1735000001] l1=on latency=2.3ms",
            "[1735000002] self_heal edges_removed=2",
            "[1735000003] insights generated=3"
        ]
        
        self.test_metrics_file.write_text("\n".join(test_data), encoding='utf-8')
        result = _load_metrics()
        
        self.assertEqual(len(result), 4)
        self.assertIn("latency=2.1ms", result[0])
        self.assertIn("self_heal", result[2])
    
    def test_load_audit_log_empty_file(self):
        """Test loading audit log from non-existent file"""
        result = _load_audit_log()
        self.assertEqual(result, [])
    
    def test_load_audit_log_valid_data(self):
        """Test loading audit log from valid file"""
        test_data = [
            '{"timestamp": "2025-01-01T10:00:00", "action": "block", "reason": "unethical"}',
            '{"timestamp": "2025-01-01T10:01:00", "action": "anonymize", "reason": "sensitive"}',
            '{"timestamp": "2025-01-01T10:02:00", "action": "processed", "reason": "governance_applied"}'
        ]
        
        self.test_audit_file.write_text("\n".join(test_data), encoding='utf-8')
        result = _load_audit_log()
        
        self.assertEqual(len(result), 3)
        self.assertIn("block", result[0])
        self.assertIn("anonymize", result[1])
    
    def test_load_insight_log_empty_file(self):
        """Test loading insight log from non-existent file"""
        result = _load_insight_log()
        self.assertEqual(result, [])
    
    def test_load_insight_log_valid_data(self):
        """Test loading insight log from valid file"""
        test_data = [
            "Topic 'drift' showing higher activity",
            "Topic 'system' appears inactive",
            "High connectivity detected in knowledge graph"
        ]
        
        self.test_insight_file.write_text("\n".join(test_data), encoding='utf-8')
        result = _load_insight_log()
        
        self.assertEqual(len(result), 3)
        self.assertIn("showing higher activity", result[0])
        self.assertIn("inactive", result[1])
    
    def test_analyze_metrics_no_data(self):
        """Test metrics analysis with no data"""
        result = analyze_metrics([])
        
        self.assertEqual(result["avg_latency"], 0)
        self.assertEqual(result["latency_samples"], 0)
        self.assertEqual(result["context_operations"], 0)
    
    def test_analyze_metrics_with_data(self):
        """Test metrics analysis with valid data"""
        test_data = [
            "[1735000000] l1=on latency=2.1ms",
            "[1735000001] l1=on latency=2.3ms",
            "[1735000002] l1=on latency=1.9ms",
            "[1735000003] self_heal edges_removed=2",
            "[1735000004] insights generated=3"
        ]
        
        result = analyze_metrics(test_data)
        
        self.assertGreater(result["avg_latency"], 0)
        self.assertEqual(result["latency_samples"], 3)
        self.assertEqual(result["context_operations"], 3)
        self.assertEqual(result["healing_operations"], 1)
        self.assertEqual(result["reasoning_operations"], 1)
    
    def test_analyze_audit_log_no_data(self):
        """Test audit log analysis with no data"""
        result = analyze_audit_log([])
        
        self.assertEqual(result["blocked_count"], 0)
        self.assertEqual(result["total_actions"], 0)
        self.assertEqual(result["block_rate"], 0)
    
    def test_analyze_audit_log_with_data(self):
        """Test audit log analysis with valid data"""
        test_data = [
            '{"action": "block", "reason": "unethical"}',
            '{"action": "anonymize", "reason": "sensitive"}',
            '{"action": "anonymize", "reason": "sensitive"}',
            '{"action": "processed", "reason": "governance_applied"}'
        ]
        
        result = analyze_audit_log(test_data)
        
        self.assertEqual(result["blocked_count"], 1)
        self.assertEqual(result["anonymized_count"], 2)
        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(result["total_actions"], 4)
        self.assertEqual(result["block_rate"], 0.25)
        self.assertEqual(result["anonymize_rate"], 0.5)
    
    def test_analyze_insights_no_data(self):
        """Test insight analysis with no data"""
        result = analyze_insights([])
        
        self.assertEqual(result["total_insights"], 0)
        self.assertEqual(result["trend_insights"], 0)
        self.assertEqual(result["anomaly_insights"], 0)
    
    def test_analyze_insights_with_data(self):
        """Test insight analysis with valid data"""
        test_data = [
            "Topic 'drift' showing higher activity",
            "Topic 'system' appears inactive",
            "Topic 'error' appears isolated",
            "High connectivity detected in knowledge graph",
            "High confidence relationships detected"
        ]
        
        result = analyze_insights(test_data)
        
        self.assertEqual(result["total_insights"], 5)
        self.assertEqual(result["trend_insights"], 1)
        self.assertEqual(result["anomaly_insights"], 2)
        self.assertEqual(result["pattern_insights"], 2)
    
    def test_detect_performance_drift_no_drift(self):
        """Test drift detection with no drift"""
        analysis = {
            "avg_latency": 2.0,
            "max_latency": 2.5,
            "latency_samples": 50,
            "block_rate": 0.02,
            "insight_rate": 0.05
        }
        
        drift_detected, description = detect_performance_drift(analysis)
        
        self.assertFalse(drift_detected)
        self.assertIn("No significant drift", description)
    
    def test_detect_performance_drift_high_latency(self):
        """Test drift detection with high latency"""
        analysis = {
            "avg_latency": 4.0,  # Above target * 1.5
            "max_latency": 5.0,
            "latency_samples": 50,
            "block_rate": 0.02,
            "insight_rate": 0.05
        }
        
        drift_detected, description = detect_performance_drift(analysis)
        
        self.assertTrue(drift_detected)
        self.assertIn("High average latency", description)
    
    def test_detect_performance_drift_high_block_rate(self):
        """Test drift detection with high block rate"""
        analysis = {
            "avg_latency": 2.0,
            "max_latency": 2.5,
            "latency_samples": 50,
            "block_rate": 0.15,  # Above 0.1
            "insight_rate": 0.05
        }
        
        drift_detected, description = detect_performance_drift(analysis)
        
        self.assertTrue(drift_detected)
        self.assertIn("High block rate", description)
    
    def test_tune_policy_performance_degradation(self):
        """Test policy tuning for performance degradation"""
        analysis = {
            "avg_latency": 4.0,  # High latency
            "block_rate": 0.02,
            "anonymize_rate": 0.05,
            "insight_rate": 0.05
        }
        
        policy = tune_policy(analysis)
        
        # Should reduce thresholds for better performance
        self.assertLess(policy["MEMORYOS_SIM_THRESHOLD"], 0.5)
        self.assertGreater(policy["MEMORYOS_AGING_DECAY_RATE"], 0.95)
        self.assertLessEqual(policy["MEMORYOS_REINJECT_TOPK"], 3)
    
    def test_tune_policy_performance_headroom(self):
        """Test policy tuning for performance headroom"""
        analysis = {
            "avg_latency": 1.5,  # Low latency
            "block_rate": 0.02,
            "anonymize_rate": 0.05,
            "insight_rate": 0.05
        }
        
        policy = tune_policy(analysis)
        
        # Should increase thresholds for better accuracy
        self.assertGreater(policy["MEMORYOS_SIM_THRESHOLD"], 0.5)
        self.assertLess(policy["MEMORYOS_AGING_DECAY_RATE"], 0.95)
        self.assertGreaterEqual(policy["MEMORYOS_REINJECT_TOPK"], 3)
    
    def test_tune_policy_high_block_rate(self):
        """Test policy tuning for high block rate"""
        analysis = {
            "avg_latency": 2.0,
            "block_rate": 0.08,  # High block rate
            "anonymize_rate": 0.05,
            "insight_rate": 0.05
        }
        
        policy = tune_policy(analysis)
        
        # Should reduce confidence minimum
        self.assertLess(policy["MEMORYOS_CONF_MIN"], 0.3)
    
    def test_tune_policy_low_insight_generation(self):
        """Test policy tuning for low insight generation"""
        analysis = {
            "avg_latency": 2.0,
            "block_rate": 0.02,
            "anonymize_rate": 0.05,
            "insight_rate": 0.01,  # Low insight rate
            "healing_operations": 10
        }
        
        policy = tune_policy(analysis)
        
        # Should increase insight generation
        self.assertLess(policy["MEMORYOS_INSIGHT_INTERVAL"], 50)
        self.assertLess(policy["MEMORYOS_TREND_FACTOR"], 1.5)
    
    def test_apply_policy(self):
        """Test applying policy to file and environment"""
        test_policy = {
            "MEMORYOS_SIM_THRESHOLD": 0.6,
            "MEMORYOS_AGING_DECAY_RATE": 0.96,
            "MEMORYOS_REINJECT_TOPK": 4
        }
        
        success = apply_policy(test_policy)
        
        self.assertTrue(success)
        self.assertTrue(self.test_policy_file.exists())
        
        # Check file content
        with open(self.test_policy_file, 'r', encoding='utf-8') as f:
            policy_data = json.load(f)
        
        self.assertIn("policy", policy_data)
        self.assertIn("metadata", policy_data)
        self.assertEqual(policy_data["policy"]["MEMORYOS_SIM_THRESHOLD"], 0.6)
        
        # Check environment variables
        self.assertEqual(os.environ.get("MEMORYOS_SIM_THRESHOLD"), "0.6")
        self.assertEqual(os.environ.get("MEMORYOS_AGING_DECAY_RATE"), "0.96")
    
    def test_run_meta_learning_no_data(self):
        """Test meta-learning with no metrics data"""
        result = run_meta_learning()
        
        self.assertEqual(result["status"], "no_data")
        self.assertIn("No metrics available", result["message"])
    
    def test_run_meta_learning_with_data(self):
        """Test meta-learning with valid data"""
        # Create test data files
        metrics_data = [
            "[1735000000] l1=on latency=2.1ms",
            "[1735000001] l1=on latency=2.3ms",
            "[1735000002] self_heal edges_removed=2"
        ]
        self.test_metrics_file.write_text("\n".join(metrics_data), encoding='utf-8')
        
        audit_data = [
            '{"action": "block", "reason": "unethical"}',
            '{"action": "anonymize", "reason": "sensitive"}'
        ]
        self.test_audit_file.write_text("\n".join(audit_data), encoding='utf-8')
        
        insight_data = [
            "Topic 'drift' showing higher activity",
            "Topic 'system' appears inactive"
        ]
        self.test_insight_file.write_text("\n".join(insight_data), encoding='utf-8')
        
        result = run_meta_learning()
        
        self.assertEqual(result["status"], "success")
        self.assertIn("updated_policy", result)
        self.assertIn("analysis", result)
        self.assertGreater(result["processing_time_ms"], 0)
    
    def test_get_meta_learning_stats(self):
        """Test getting meta-learning statistics"""
        stats = get_meta_learning_stats()
        
        self.assertIn("enabled", stats)
        self.assertIn("tuning_mode", stats)
        self.assertIn("latency_target", stats)
        self.assertIn("update_interval_min", stats)
        self.assertIn("current_policy", stats)
        self.assertIn("policy_file_exists", stats)
        
        self.assertTrue(stats["enabled"])
        self.assertEqual(stats["tuning_mode"], "auto")
        self.assertEqual(stats["latency_target"], 2.5)
        self.assertEqual(stats["update_interval_min"], 60)
    
    def test_meta_learning_disabled(self):
        """Test meta-learning functionality when disabled"""
        os.environ["MEMORYOS_META_LEARNING_ENABLED"] = "false"
        
        result = run_meta_learning()
        self.assertEqual(result["status"], "disabled")
        
        stats = get_meta_learning_stats()
        self.assertFalse(stats["enabled"])
        
        # Restore enabled state
        os.environ["MEMORYOS_META_LEARNING_ENABLED"] = "true"
    
    def test_comprehensive_meta_learning_workflow(self):
        """Test complete meta-learning workflow"""
        # Create comprehensive test data
        metrics_data = [
            "[1735000000] l1=on latency=3.5ms",  # High latency
            "[1735000001] l1=on latency=3.2ms",
            "[1735000002] l1=on latency=3.8ms",
            "[1735000003] self_heal edges_removed=5",
            "[1735000004] insights generated=2"
        ]
        self.test_metrics_file.write_text("\n".join(metrics_data), encoding='utf-8')
        
        audit_data = [
            '{"action": "block", "reason": "unethical"}',
            '{"action": "anonymize", "reason": "sensitive"}',
            '{"action": "anonymize", "reason": "sensitive"}',
            '{"action": "processed", "reason": "governance_applied"}'
        ]
        self.test_audit_file.write_text("\n".join(audit_data), encoding='utf-8')
        
        insight_data = [
            "Topic 'drift' showing higher activity",
            "Topic 'system' appears inactive"
        ]
        self.test_insight_file.write_text("\n".join(insight_data), encoding='utf-8')
        
        # Run meta-learning
        result = run_meta_learning()
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["policy_applied"])
        self.assertTrue(result["drift_detected"])  # Should detect high latency
        
        # Check that policy was tuned for performance
        updated_policy = result["updated_policy"]
        self.assertLess(updated_policy["MEMORYOS_SIM_THRESHOLD"], 0.5)
        self.assertGreater(updated_policy["MEMORYOS_AGING_DECAY_RATE"], 0.95)
        
        # Verify policy file was created
        self.assertTrue(self.test_policy_file.exists())

if __name__ == "__main__":
    unittest.main()
