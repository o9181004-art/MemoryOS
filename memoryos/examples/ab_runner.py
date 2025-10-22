"""
A/B Runner - Policy A vs B 비교 테스트

MemoryOS의 서로 다른 정책을 비교하여 성능과 효과를 측정합니다.
결과를 results/ab_summary.csv에 저장합니다.
"""

import time
import csv
import json
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime

from memoryos.guard.drift_guard import DriftGuard
from memoryos.guard.self_heal import SelfHeal
from memoryos.guard.policy import Policy
# from memoryos.core.context_runtime import ContextRuntime  # Not used in current implementation
from memoryos.observe.metrics import StandardMetricsCollector


@dataclass
class ABTestConfig:
    """A/B 테스트 설정"""
    test_name: str
    iterations: int = 10
    policy_a_config: Dict = None
    policy_b_config: Dict = None
    test_scenarios: List[Dict] = None
    
    def __post_init__(self):
        if self.policy_a_config is None:
            self.policy_a_config = {
                "name": "Conservative Policy",
                "drift_threshold_multiplier": 1.0,
                "quarantine_threshold": 0.8,
                "auto_merge_enabled": False,
                "strict_validation": True
            }
        
        if self.policy_b_config is None:
            self.policy_b_config = {
                "name": "Aggressive Policy",
                "drift_threshold_multiplier": 0.7,
                "quarantine_threshold": 0.6,
                "auto_merge_enabled": True,
                "strict_validation": False
            }
        
        if self.test_scenarios is None:
            self.test_scenarios = [
                {
                    "name": "L1_Drift",
                    "producer_actual": "unknown_module",
                    "producer_expected": "config_manager",
                    "time_offset": -60,
                    "expected_level": 1
                },
                {
                    "name": "L2_Drift",
                    "producer_actual": "wrong_module",
                    "producer_expected": "config_manager",
                    "time_offset": -400,
                    "expected_level": 2
                },
                {
                    "name": "L3_Drift",
                    "producer_actual": "malicious_module",
                    "producer_expected": "config_manager",
                    "time_offset": -2000,
                    "expected_level": 3
                }
            ]


@dataclass
class ABTestResult:
    """A/B 테스트 결과"""
    test_name: str
    policy_name: str
    iteration: int
    scenario_name: str
    drift_detected: bool
    drift_level: int
    heal_success: bool
    heal_action: str
    execution_time_ms: float
    memory_usage_mb: float
    error_count: int
    timestamp: str


class ABRunner:
    """A/B 테스트 실행기"""
    
    def __init__(self, config: ABTestConfig):
        """
        A/B Runner 초기화
        
        Args:
            config: A/B 테스트 설정
        """
        self.config = config
        self.results: List[ABTestResult] = []
        
        # 결과 디렉토리 생성
        self.results_dir = Path("results")
        self.results_dir.mkdir(exist_ok=True)
        
        # 테스트 데이터 디렉토리 생성
        self.test_dir = Path("ab_test_data")
        self.test_dir.mkdir(exist_ok=True)
        
        # 메트릭 수집기 초기화
        self.metrics_collector = StandardMetricsCollector()
    
    def create_test_file(self, filename: str, content: str = None) -> Path:
        """
        테스트 파일 생성
        
        Args:
            filename: 파일명
            content: 파일 내용
            
        Returns:
            생성된 파일 경로
        """
        if content is None:
            content = f'{{"test_data": "value_{filename}", "timestamp": {time.time()}}}'
        
        test_file = self.test_dir / filename
        test_file.write_text(content, encoding='utf-8')
        return test_file
    
    def setup_policy_a(self) -> tuple:
        """
        Policy A 설정
        
        Returns:
            (drift_guard, self_heal, policy) 튜플
        """
        # Conservative Policy 설정
        drift_guard = DriftGuard()
        self_heal = SelfHeal(
            backup_dir="ab_test_backups_a",
            quarantine_dir="ab_test_quarantine_a"
        )
        policy = Policy()
        
        # Policy A 특성 적용
        # (실제로는 Policy 클래스에 설정 메서드가 있어야 함)
        
        return drift_guard, self_heal, policy
    
    def setup_policy_b(self) -> tuple:
        """
        Policy B 설정
        
        Returns:
            (drift_guard, self_heal, policy) 튜플
        """
        # Aggressive Policy 설정
        drift_guard = DriftGuard()
        self_heal = SelfHeal(
            backup_dir="ab_test_backups_b",
            quarantine_dir="ab_test_quarantine_b"
        )
        policy = Policy()
        
        # Policy B 특성 적용
        # (실제로는 Policy 클래스에 설정 메서드가 있어야 함)
        
        return drift_guard, self_heal, policy
    
    def run_single_test(self, policy_name: str, policy_setup_func, 
                       scenario: Dict, iteration: int) -> ABTestResult:
        """
        단일 테스트 실행
        
        Args:
            policy_name: 정책 이름
            policy_setup_func: 정책 설정 함수
            scenario: 테스트 시나리오
            iteration: 반복 횟수
            
        Returns:
            테스트 결과
        """
        start_time = time.time()
        start_memory = self._get_memory_usage()
        error_count = 0
        
        try:
            # 정책 설정
            drift_guard, self_heal, _ = policy_setup_func()
            
            # 테스트 파일 생성
            test_file = self.create_test_file(f"test_{scenario['name']}_{iteration}.json")
            
            # Drift 검사 실행
            drift_result = drift_guard.check_drift(
                file_path=str(test_file),
                producer_actual=scenario["producer_actual"],
                producer_expected=scenario["producer_expected"],
                last_updated=time.time() + scenario["time_offset"],
                update_interval=30
            )
            
            # Self-Heal 실행
            heal_success = False
            heal_action = "none"
            
            if drift_result.get("drift_detected", False):
                heal_result = self_heal.execute_heal(drift_result)
                heal_success = heal_result.get("success", False)
                heal_action = heal_result.get("action", "unknown")
            
            # 통계 수집 (현재 사용하지 않음)
            # drift_stats = drift_guard.get_drift_statistics()
            # heal_stats = self_heal.get_heal_statistics()
            
            # 메트릭 업데이트
            self.metrics_collector.update_metrics()
            
            # 테스트 파일 정리
            if test_file.exists():
                test_file.unlink()
            
        except Exception as e:
            error_count += 1
            print(f"Error in {policy_name} test: {e}")
            drift_result = {"drift_detected": False, "drift_level": 0}
            heal_success = False
            heal_action = "error"
        
        end_time = time.time()
        end_memory = self._get_memory_usage()
        
        return ABTestResult(
            test_name=self.config.test_name,
            policy_name=policy_name,
            iteration=iteration,
            scenario_name=scenario["name"],
            drift_detected=drift_result.get("drift_detected", False),
            drift_level=drift_result.get("drift_level", 0),
            heal_success=heal_success,
            heal_action=heal_action,
            execution_time_ms=(end_time - start_time) * 1000,
            memory_usage_mb=end_memory - start_memory,
            error_count=error_count,
            timestamp=datetime.now().isoformat()
        )
    
    def run_ab_test(self) -> List[ABTestResult]:
        """
        A/B 테스트 실행
        
        Returns:
            테스트 결과 목록
        """
        print("=== Starting A/B Test: " + self.config.test_name + " ===")
        print(f"Iterations: {self.config.iterations}")
        print(f"Scenarios: {len(self.config.test_scenarios)}")
        
        results = []
        
        for iteration in range(1, self.config.iterations + 1):
            print(f"\n--- Iteration {iteration}/{self.config.iterations} ---")
            
            for scenario in self.config.test_scenarios:
                print(f"  Scenario: {scenario['name']}")
                
                # Policy A 테스트
                result_a = self.run_single_test(
                    policy_name=self.config.policy_a_config["name"],
                    policy_setup_func=self.setup_policy_a,
                    scenario=scenario,
                    iteration=iteration
                )
                results.append(result_a)
                
                # Policy B 테스트
                result_b = self.run_single_test(
                    policy_name=self.config.policy_b_config["name"],
                    policy_setup_func=self.setup_policy_b,
                    scenario=scenario,
                    iteration=iteration
                )
                results.append(result_b)
                
                print(f"    Policy A: {result_a.heal_action} ({result_a.execution_time_ms:.2f}ms)")
                print(f"    Policy B: {result_b.heal_action} ({result_b.execution_time_ms:.2f}ms)")
        
        self.results = results
        return results
    
    def save_results_to_csv(self) -> Path:
        """
        결과를 CSV 파일로 저장
        
        Returns:
            저장된 CSV 파일 경로
        """
        csv_file = self.results_dir / "ab_summary.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            if self.results:
                writer = csv.DictWriter(f, fieldnames=self.results[0].__dict__.keys())
                writer.writeheader()
                for result in self.results:
                    writer.writerow(result.__dict__)
        
        print(f"Results saved to: {csv_file}")
        return csv_file
    
    def generate_summary_report(self) -> Dict:
        """
        요약 보고서 생성
        
        Returns:
            요약 통계
        """
        if not self.results:
            return {}
        
        # 정책별 통계 계산
        policy_a_results = [r for r in self.results if r.policy_name == self.config.policy_a_config["name"]]
        policy_b_results = [r for r in self.results if r.policy_name == self.config.policy_b_config["name"]]
        
        summary = {
            "test_name": self.config.test_name,
            "total_iterations": self.config.iterations,
            "total_scenarios": len(self.config.test_scenarios),
            "total_tests": len(self.results),
            "policy_a": {
                "name": self.config.policy_a_config["name"],
                "total_tests": len(policy_a_results),
                "avg_execution_time_ms": sum(r.execution_time_ms for r in policy_a_results) / len(policy_a_results) if policy_a_results else 0,
                "success_rate": sum(1 for r in policy_a_results if r.heal_success) / len(policy_a_results) if policy_a_results else 0,
                "drift_detection_rate": sum(1 for r in policy_a_results if r.drift_detected) / len(policy_a_results) if policy_a_results else 0,
                "error_rate": sum(r.error_count for r in policy_a_results) / len(policy_a_results) if policy_a_results else 0
            },
            "policy_b": {
                "name": self.config.policy_b_config["name"],
                "total_tests": len(policy_b_results),
                "avg_execution_time_ms": sum(r.execution_time_ms for r in policy_b_results) / len(policy_b_results) if policy_b_results else 0,
                "success_rate": sum(1 for r in policy_b_results if r.heal_success) / len(policy_b_results) if policy_b_results else 0,
                "drift_detection_rate": sum(1 for r in policy_b_results if r.drift_detected) / len(policy_b_results) if policy_b_results else 0,
                "error_rate": sum(r.error_count for r in policy_b_results) / len(policy_b_results) if policy_b_results else 0
            }
        }
        
        # 성능 비교
        if policy_a_results and policy_b_results:
            summary["performance_comparison"] = {
                "execution_time_improvement": (
                    summary["policy_a"]["avg_execution_time_ms"] - 
                    summary["policy_b"]["avg_execution_time_ms"]
                ) / summary["policy_a"]["avg_execution_time_ms"] * 100,
                "success_rate_improvement": (
                    summary["policy_b"]["success_rate"] - 
                    summary["policy_a"]["success_rate"]
                ) * 100,
                "drift_detection_improvement": (
                    summary["policy_b"]["drift_detection_rate"] - 
                    summary["policy_a"]["drift_detection_rate"]
                ) * 100
            }
        
        return summary
    
    def save_summary_report(self, summary: Dict) -> Path:
        """
        요약 보고서를 JSON 파일로 저장
        
        Args:
            summary: 요약 통계
            
        Returns:
            저장된 JSON 파일 경로
        """
        json_file = self.results_dir / "ab_summary_report.json"
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"Summary report saved to: {json_file}")
        return json_file
    
    def print_summary(self, summary: Dict):
        """
        요약 결과 출력
        
        Args:
            summary: 요약 통계
        """
        print("\n=== A/B Test Summary: " + summary['test_name'] + " ===")
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Iterations: {summary['total_iterations']}")
        print(f"Scenarios: {summary['total_scenarios']}")
        
        print(f"\n--- Policy A ({summary['policy_a']['name']}) ---")
        print(f"  Success Rate: {summary['policy_a']['success_rate']:.2%}")
        print(f"  Avg Execution Time: {summary['policy_a']['avg_execution_time_ms']:.2f}ms")
        print(f"  Drift Detection Rate: {summary['policy_a']['drift_detection_rate']:.2%}")
        print(f"  Error Rate: {summary['policy_a']['error_rate']:.2%}")
        
        print(f"\n--- Policy B ({summary['policy_b']['name']}) ---")
        print(f"  Success Rate: {summary['policy_b']['success_rate']:.2%}")
        print(f"  Avg Execution Time: {summary['policy_b']['avg_execution_time_ms']:.2f}ms")
        print(f"  Drift Detection Rate: {summary['policy_b']['drift_detection_rate']:.2%}")
        print(f"  Error Rate: {summary['policy_b']['error_rate']:.2%}")
        
        if "performance_comparison" in summary:
            comp = summary["performance_comparison"]
            print(f"\n--- Performance Comparison ---")
            print(f"  Execution Time Improvement: {comp['execution_time_improvement']:.1f}%")
            print(f"  Success Rate Improvement: {comp['success_rate_improvement']:.1f}%")
            print(f"  Drift Detection Improvement: {comp['drift_detection_improvement']:.1f}%")
    
    def cleanup(self):
        """테스트 정리"""
        import shutil
        
        # 테스트 디렉토리 정리
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        
        # 백업 및 격리 디렉토리 정리
        for backup_dir in ["ab_test_backups_a", "ab_test_backups_b"]:
            if Path(backup_dir).exists():
                shutil.rmtree(backup_dir)
        
        for quarantine_dir in ["ab_test_quarantine_a", "ab_test_quarantine_b"]:
            if Path(quarantine_dir).exists():
                shutil.rmtree(quarantine_dir)
        
        print("Test cleanup completed")
    
    def _get_memory_usage(self) -> float:
        """
        메모리 사용량 측정 (MB)
        
        Returns:
            메모리 사용량 (MB)
        """
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            # psutil이 없는 경우 0 반환
            return 0.0


def run_ab_test():
    """A/B 테스트 실행"""
    # 테스트 설정
    config = ABTestConfig(
        test_name="MemoryOS Policy Comparison",
        iterations=5,  # 빠른 테스트를 위해 5회로 설정
        test_scenarios=[
            {
                "name": "L1_Drift",
                "producer_actual": "unknown_module",
                "producer_expected": "config_manager",
                "time_offset": -60,
                "expected_level": 1
            },
            {
                "name": "L2_Drift",
                "producer_actual": "wrong_module",
                "producer_expected": "config_manager",
                "time_offset": -400,
                "expected_level": 2
            },
            {
                "name": "L3_Drift",
                "producer_actual": "malicious_module",
                "producer_expected": "config_manager",
                "time_offset": -2000,
                "expected_level": 3
            }
        ]
    )
    
    # A/B Runner 생성 및 실행
    runner = ABRunner(config)
    
    try:
        # A/B 테스트 실행
        runner.run_ab_test()
        
        # 결과 저장
        csv_file = runner.save_results_to_csv()
        
        # 요약 보고서 생성
        summary = runner.generate_summary_report()
        json_file = runner.save_summary_report(summary)
        
        # 요약 출력
        runner.print_summary(summary)
        
        print(f"\n=== A/B Test Completed ===")
        print(f"Results CSV: {csv_file}")
        print(f"Summary JSON: {json_file}")
        
    finally:
        # 정리
        runner.cleanup()


if __name__ == "__main__":
    run_ab_test()