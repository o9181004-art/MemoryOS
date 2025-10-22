"""
Unit tests for A/B Runner functionality
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
import json
import csv

from memoryos.examples.ab_runner import ABRunner, ABTestConfig, ABTestResult


class TestABRunner(unittest.TestCase):
    """A/B Runner 기능 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.temp_dir = tempfile.mkdtemp()
        
        # 테스트 설정
        self.config = ABTestConfig(
            test_name="Test AB Comparison",
            iterations=2,
            test_scenarios=[
                {
                    "name": "L1_Drift",
                    "producer_actual": "unknown_module",
                    "producer_expected": "config_manager",
                    "time_offset": -60,
                    "expected_level": 1
                }
            ]
        )
        
        self.runner = ABRunner(self.config)
    
    def tearDown(self):
        """테스트 정리"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.runner.cleanup()
    
    def test_ab_test_config_initialization(self):
        """ABTestConfig 초기화 테스트"""
        config = ABTestConfig(test_name="Test Config")
        
        self.assertEqual(config.test_name, "Test Config")
        self.assertEqual(config.iterations, 10)
        self.assertIsNotNone(config.policy_a_config)
        self.assertIsNotNone(config.policy_b_config)
        self.assertIsNotNone(config.test_scenarios)
        
        # 기본 정책 설정 확인
        self.assertEqual(config.policy_a_config["name"], "Conservative Policy")
        self.assertEqual(config.policy_b_config["name"], "Aggressive Policy")
        
        # 기본 시나리오 확인
        self.assertEqual(len(config.test_scenarios), 3)
        self.assertEqual(config.test_scenarios[0]["name"], "L1_Drift")
    
    def test_ab_runner_initialization(self):
        """ABRunner 초기화 테스트"""
        self.assertEqual(self.runner.config.test_name, "Test AB Comparison")
        self.assertEqual(self.runner.config.iterations, 2)
        self.assertEqual(len(self.runner.results), 0)
        
        # 디렉토리 생성 확인
        self.assertTrue(self.runner.results_dir.exists())
        self.assertTrue(self.runner.test_dir.exists())
    
    def test_create_test_file(self):
        """테스트 파일 생성 테스트"""
        filename = "test_file.json"
        content = '{"test": "data"}'
        
        test_file = self.runner.create_test_file(filename, content)
        
        self.assertTrue(test_file.exists())
        self.assertEqual(test_file.read_text(), content)
        self.assertEqual(test_file.name, filename)
    
    def test_create_test_file_default_content(self):
        """기본 내용으로 테스트 파일 생성 테스트"""
        filename = "default_test.json"
        
        test_file = self.runner.create_test_file(filename)
        
        self.assertTrue(test_file.exists())
        content = test_file.read_text()
        self.assertIn("test_data", content)
        self.assertIn("timestamp", content)
    
    def test_setup_policy_a(self):
        """Policy A 설정 테스트"""
        drift_guard, self_heal, policy = self.runner.setup_policy_a()
        
        self.assertIsNotNone(drift_guard)
        self.assertIsNotNone(self_heal)
        self.assertIsNotNone(policy)
        
        # Policy A 특성 확인
        self.assertEqual(self_heal.backup_dir.name, "ab_test_backups_a")
        self.assertEqual(self_heal.quarantine_dir.name, "ab_test_quarantine_a")
    
    def test_setup_policy_b(self):
        """Policy B 설정 테스트"""
        drift_guard, self_heal, policy = self.runner.setup_policy_b()
        
        self.assertIsNotNone(drift_guard)
        self.assertIsNotNone(self_heal)
        self.assertIsNotNone(policy)
        
        # Policy B 특성 확인
        self.assertEqual(self_heal.backup_dir.name, "ab_test_backups_b")
        self.assertEqual(self_heal.quarantine_dir.name, "ab_test_quarantine_b")
    
    @patch('memoryos.examples.ab_runner.DriftGuard')
    @patch('memoryos.examples.ab_runner.SelfHeal')
    @patch('memoryos.examples.ab_runner.Policy')
    def test_run_single_test_success(self, mock_policy, mock_self_heal, mock_drift_guard):
        """단일 테스트 성공 케이스 테스트"""
        # Mock 설정
        mock_drift_guard.return_value.check_drift.return_value = {
            "drift_detected": True,
            "drift_level": 1
        }
        mock_self_heal.return_value.execute_heal.return_value = {
            "success": True,
            "action": "log_only"
        }
        mock_self_heal.return_value.get_heal_statistics.return_value = {}
        mock_drift_guard.return_value.get_drift_statistics.return_value = {}
        
        scenario = self.config.test_scenarios[0]
        
        result = self.runner.run_single_test(
            policy_name="Test Policy",
            policy_setup_func=self.runner.setup_policy_a,
            scenario=scenario,
            iteration=1
        )
        
        # 결과 확인
        self.assertEqual(result.test_name, "Test AB Comparison")
        self.assertEqual(result.policy_name, "Test Policy")
        self.assertEqual(result.iteration, 1)
        self.assertEqual(result.scenario_name, "L1_Drift")
        self.assertTrue(result.drift_detected)
        self.assertEqual(result.drift_level, 1)
        self.assertTrue(result.heal_success)
        self.assertEqual(result.heal_action, "log_only")
        self.assertGreater(result.execution_time_ms, 0)
        self.assertEqual(result.error_count, 0)
    
    @patch('memoryos.examples.ab_runner.DriftGuard')
    @patch('memoryos.examples.ab_runner.SelfHeal')
    @patch('memoryos.examples.ab_runner.Policy')
    def test_run_single_test_error(self, mock_policy, mock_self_heal, mock_drift_guard):
        """단일 테스트 에러 케이스 테스트"""
        # Mock에서 예외 발생
        mock_drift_guard.return_value.check_drift.side_effect = Exception("Test error")
        
        scenario = self.config.test_scenarios[0]
        
        result = self.runner.run_single_test(
            policy_name="Test Policy",
            policy_setup_func=self.runner.setup_policy_a,
            scenario=scenario,
            iteration=1
        )
        
        # 에러 결과 확인
        self.assertEqual(result.policy_name, "Test Policy")
        self.assertFalse(result.drift_detected)
        self.assertEqual(result.drift_level, 0)
        self.assertFalse(result.heal_success)
        self.assertEqual(result.heal_action, "error")
        self.assertEqual(result.error_count, 1)
    
    def test_save_results_to_csv(self):
        """결과 CSV 저장 테스트"""
        # 테스트 결과 생성
        result1 = ABTestResult(
            test_name="Test",
            policy_name="Policy A",
            iteration=1,
            scenario_name="L1_Drift",
            drift_detected=True,
            drift_level=1,
            heal_success=True,
            heal_action="log_only",
            execution_time_ms=100.0,
            memory_usage_mb=10.0,
            error_count=0,
            timestamp="2024-01-01T00:00:00"
        )
        
        result2 = ABTestResult(
            test_name="Test",
            policy_name="Policy B",
            iteration=1,
            scenario_name="L1_Drift",
            drift_detected=True,
            drift_level=1,
            heal_success=False,
            heal_action="error",
            execution_time_ms=150.0,
            memory_usage_mb=12.0,
            error_count=1,
            timestamp="2024-01-01T00:01:00"
        )
        
        self.runner.results = [result1, result2]
        
        # CSV 저장
        csv_file = self.runner.save_results_to_csv()
        
        # 파일 존재 확인
        self.assertTrue(csv_file.exists())
        
        # CSV 내용 확인
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["policy_name"], "Policy A")
            self.assertEqual(rows[1]["policy_name"], "Policy B")
            self.assertEqual(rows[0]["heal_success"], "True")
            self.assertEqual(rows[1]["heal_success"], "False")
    
    def test_generate_summary_report(self):
        """요약 보고서 생성 테스트"""
        # 테스트 결과 생성
        results = [
            ABTestResult(
                test_name="Test",
                policy_name="Conservative Policy",
                iteration=1,
                scenario_name="L1_Drift",
                drift_detected=True,
                drift_level=1,
                heal_success=True,
                heal_action="log_only",
                execution_time_ms=100.0,
                memory_usage_mb=10.0,
                error_count=0,
                timestamp="2024-01-01T00:00:00"
            ),
            ABTestResult(
                test_name="Test",
                policy_name="Aggressive Policy",
                iteration=1,
                scenario_name="L1_Drift",
                drift_detected=True,
                drift_level=1,
                heal_success=True,
                heal_action="auto_merge",
                execution_time_ms=80.0,
                memory_usage_mb=8.0,
                error_count=0,
                timestamp="2024-01-01T00:01:00"
            )
        ]
        
        self.runner.results = results
        
        # 요약 보고서 생성
        summary = self.runner.generate_summary_report()
        
        # 요약 내용 확인
        self.assertEqual(summary["test_name"], "Test AB Comparison")
        self.assertEqual(summary["total_tests"], 2)
        self.assertEqual(summary["total_iterations"], 2)
        
        # Policy A 통계 확인
        policy_a = summary["policy_a"]
        self.assertEqual(policy_a["name"], "Conservative Policy")
        self.assertEqual(policy_a["total_tests"], 1)
        self.assertEqual(policy_a["avg_execution_time_ms"], 100.0)
        self.assertEqual(policy_a["success_rate"], 1.0)
        self.assertEqual(policy_a["drift_detection_rate"], 1.0)
        self.assertEqual(policy_a["error_rate"], 0.0)
        
        # Policy B 통계 확인
        policy_b = summary["policy_b"]
        self.assertEqual(policy_b["name"], "Aggressive Policy")
        self.assertEqual(policy_b["total_tests"], 1)
        self.assertEqual(policy_b["avg_execution_time_ms"], 80.0)
        self.assertEqual(policy_b["success_rate"], 1.0)
        self.assertEqual(policy_b["drift_detection_rate"], 1.0)
        self.assertEqual(policy_b["error_rate"], 0.0)
        
        # 성능 비교 확인
        self.assertIn("performance_comparison", summary)
        comp = summary["performance_comparison"]
        self.assertEqual(comp["execution_time_improvement"], 20.0)  # 20% 개선
        self.assertEqual(comp["success_rate_improvement"], 0.0)  # 동일
        self.assertEqual(comp["drift_detection_improvement"], 0.0)  # 동일
    
    def test_save_summary_report(self):
        """요약 보고서 JSON 저장 테스트"""
        summary = {
            "test_name": "Test Summary",
            "total_tests": 10,
            "policy_a": {"name": "Policy A", "success_rate": 0.8},
            "policy_b": {"name": "Policy B", "success_rate": 0.9}
        }
        
        # JSON 저장
        json_file = self.runner.save_summary_report(summary)
        
        # 파일 존재 확인
        self.assertTrue(json_file.exists())
        
        # JSON 내용 확인
        with open(json_file, 'r', encoding='utf-8') as f:
            loaded_summary = json.load(f)
            
            self.assertEqual(loaded_summary["test_name"], "Test Summary")
            self.assertEqual(loaded_summary["total_tests"], 10)
            self.assertEqual(loaded_summary["policy_a"]["name"], "Policy A")
            self.assertEqual(loaded_summary["policy_b"]["name"], "Policy B")
    
    def test_print_summary(self):
        """요약 출력 테스트"""
        summary = {
            "test_name": "Test Summary",
            "total_tests": 10,
            "total_iterations": 5,
            "total_scenarios": 2,
            "policy_a": {
                "name": "Conservative Policy",
                "success_rate": 0.8,
                "avg_execution_time_ms": 100.0,
                "drift_detection_rate": 0.9,
                "error_rate": 0.1
            },
            "policy_b": {
                "name": "Aggressive Policy",
                "success_rate": 0.9,
                "avg_execution_time_ms": 80.0,
                "drift_detection_rate": 0.95,
                "error_rate": 0.05
            },
            "performance_comparison": {
                "execution_time_improvement": 20.0,
                "success_rate_improvement": 10.0,
                "drift_detection_improvement": 5.0
            }
        }
        
        # 출력 테스트 (실제로는 출력을 캡처해야 함)
        try:
            self.runner.print_summary(summary)
        except Exception as e:
            self.fail(f"print_summary failed: {e}")
    
    def test_cleanup(self):
        """정리 테스트"""
        # 테스트 디렉토리 생성
        test_file = self.runner.test_dir / "test.txt"
        test_file.write_text("test")
        
        # 정리 실행
        self.runner.cleanup()
        
        # 디렉토리가 정리되었는지 확인
        self.assertFalse(self.runner.test_dir.exists())
    
    def test_get_memory_usage(self):
        """메모리 사용량 측정 테스트"""
        memory_usage = self.runner._get_memory_usage()
        
        # 메모리 사용량은 0 이상이어야 함
        self.assertGreaterEqual(memory_usage, 0.0)
    
    def test_empty_results_summary(self):
        """빈 결과 요약 테스트"""
        self.runner.results = []
        
        summary = self.runner.generate_summary_report()
        
        # 빈 결과에 대한 요약은 빈 딕셔너리
        self.assertEqual(summary, {})


if __name__ == "__main__":
    unittest.main()

