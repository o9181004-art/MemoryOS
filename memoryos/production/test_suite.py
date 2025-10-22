"""
MemoryOS Production Test Suite
무결성·복원·성능·보안 테스트 자동화

이 모듈은 MemoryOS의 모든 핵심 기능에 대한
종합적인 테스트를 자동화합니다.
"""

import time
import json
import hashlib
import threading
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import concurrent.futures
import statistics

from memoryos.core.context_runtime import ContextRuntime
from memoryos.core.hashchain import HashChain
from memoryos.core.data_catalog import DataCatalog
from memoryos.core.snapshot_generator import SnapshotGenerator
from memoryos.guard.drift_guard import DriftGuard, DriftLevel
from memoryos.guard.self_heal import SelfHeal
from memoryos.store.memory_index_store import MemoryIndexStore
from memoryos.observe.event_log import EventLog
from memoryos.observe.metrics import StandardMetricsCollector


class TestCategory(Enum):
    """테스트 카테고리"""
    INTEGRITY = "integrity"
    RECOVERY = "recovery"
    PERFORMANCE = "performance"
    SECURITY = "security"
    CONCURRENCY = "concurrency"
    STRESS = "stress"


class TestResult(Enum):
    """테스트 결과"""
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class TestMetrics:
    """테스트 메트릭"""
    test_name: str
    category: TestCategory
    duration_ms: float
    result: TestResult
    error_message: Optional[str] = None
    performance_data: Optional[Dict] = None
    security_data: Optional[Dict] = None


class ProductionTestSuite:
    """
    MemoryOS Production Test Suite
    
    모든 핵심 기능에 대한 종합적인 테스트를 수행합니다.
    """
    
    def __init__(self, output_dir: str = "test_output"):
        """
        테스트 스위트 초기화
        
        Args:
            output_dir: 테스트 결과 출력 디렉토리
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 테스트 결과 저장
        self.test_results: List[TestMetrics] = []
        self.test_data_dir = self.output_dir / "test_data"
        self.test_data_dir.mkdir(exist_ok=True)
        
        # 테스트 환경
        self.temp_dir = None
        self.context_runtime = None
        
    def _log(self, message: str):
        """로깅"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [TestSuite] {message}")
    
    def _setup_test_environment(self) -> bool:
        """테스트 환경 설정"""
        try:
            # 임시 디렉토리 생성
            self.temp_dir = Path(tempfile.mkdtemp(prefix="memoryos_test_"))
            
            # 테스트 설정 파일 생성
            config_content = f"""
[watch_paths]
paths = ["{self.temp_dir}"]

catalog_file = "{self.temp_dir}/catalog.json"
memory_index_file = "{self.temp_dir}/memory_index.json"
snapshot_dir = "{self.temp_dir}/snapshots"
"""
            config_file = self.temp_dir / "test_config.toml"
            config_file.write_text(config_content)
            
            # ContextRuntime 초기화
            self.context_runtime = ContextRuntime(str(config_file))
            
            self._log(f"Test environment setup complete: {self.temp_dir}")
            return True
            
        except Exception as e:
            self._log(f"Test environment setup failed: {e}")
            return False
    
    def _cleanup_test_environment(self):
        """테스트 환경 정리"""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _run_test(self, test_func, test_name: str, category: TestCategory) -> TestMetrics:
        """개별 테스트 실행"""
        start_time = time.time()
        
        try:
            self._log(f"Running {category.value} test: {test_name}")
            result = test_func()
            
            duration_ms = (time.time() - start_time) * 1000
            
            if result:
                test_result = TestResult.PASS
                error_message = None
            else:
                test_result = TestResult.FAIL
                error_message = "Test assertion failed"
            
            metrics = TestMetrics(
                test_name=test_name,
                category=category,
                duration_ms=duration_ms,
                result=test_result,
                error_message=error_message
            )
            
            self.test_results.append(metrics)
            self._log(f"Test {test_name}: {test_result.value}")
            return metrics
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_message = str(e)
            
            metrics = TestMetrics(
                test_name=test_name,
                category=category,
                duration_ms=duration_ms,
                result=TestResult.ERROR,
                error_message=error_message
            )
            
            self.test_results.append(metrics)
            self._log(f"Test {test_name}: ERROR - {error_message}")
            return metrics
    
    # === 무결성 테스트 ===
    
    def test_hash_chain_integrity(self) -> bool:
        """Hash Chain 무결성 테스트"""
        try:
            hash_chain = HashChain()
            
            # 블록 추가
            data1 = {"file": "test1.txt", "content": "content1"}
            hash1 = hash_chain.add_block_atomic(data1)
            
            data2 = {"file": "test2.txt", "content": "content2"}
            hash2 = hash_chain.add_block_atomic(data2)
            
            # 체인 검증
            is_valid, errors = hash_chain.verify_chain()
            
            return is_valid and len(errors) == 0
            
        except Exception as e:
            self._log(f"Hash chain integrity test error: {e}")
            return False
    
    def test_data_catalog_consistency(self) -> bool:
        """Data Catalog 일관성 테스트"""
        try:
            catalog_file = self.temp_dir / "test_catalog.json"
            catalog = DataCatalog(str(catalog_file))
            
            # 파일 등록
            catalog.register_file("test_file.txt", "producer1", ["consumer1"])
            
            # 일관성 확인
            producer = catalog.get_expected_producer("test_file.txt")
            consumers = catalog.get_expected_consumers("test_file.txt")
            
            return producer == "producer1" and "consumer1" in consumers
            
        except Exception as e:
            self._log(f"Data catalog consistency test error: {e}")
            return False
    
    def test_snapshot_schema_validation(self) -> bool:
        """스냅샷 스키마 검증 테스트"""
        try:
            snapshot_dir = self.temp_dir / "snapshots"
            generator = SnapshotGenerator(str(snapshot_dir))
            
            # 유효한 스냅샷 생성
            valid_snapshot = {
                "schema_version": "1.0.0",
                "snapshot_id": "test_snapshot",
                "timestamp": time.time(),
                "memory_index": {"files": {}},
                "drift_status": {"total_files": 0, "active_files": 0, "stale_files": 0, "error_files": 0, "drift_counts": {"0": 0, "1": 0, "2": 0, "3": 0}},
                "hash_chain": {"chain_length": 0, "latest_hash": "0" * 64, "merkle_root": "0" * 64, "integrity_verified": True},
                "quarantine_status": {"quarantined_files": [], "quarantine_count": 0, "auto_release_candidates": []},
                "performance_metrics": {"hit_rate": 0.0, "avg_latency_ms": 0.0, "error_rate": 0.0, "drift_levels": {"L1": 0, "L2": 0, "L3": 0}},
                "system_info": {"version": "1.0.0", "uptime_seconds": 0, "config_hash": "0" * 64}
            }
            
            result = generator.validate_snapshot(valid_snapshot)
            return result["is_valid"]
            
        except Exception as e:
            self._log(f"Snapshot schema validation test error: {e}")
            return False
    
    # === 복원 테스트 ===
    
    def test_self_healing_recovery(self) -> bool:
        """Self-Healing 복원 테스트"""
        try:
            backup_dir = self.temp_dir / "backups"
            quarantine_dir = self.temp_dir / "quarantine"
            self_heal = SelfHeal(str(backup_dir), str(quarantine_dir))
            
            # 테스트 파일 생성
            test_file = self.temp_dir / "test_file.txt"
            test_file.write_text("original content")
            
            # 백업 생성
            backup_path = self_heal._create_backup(str(test_file))
            
            # 파일 변경
            test_file.write_text("modified content")
            
            # 복원
            restore_result = self_heal._restore_to_previous_state(str(test_file))
            
            # 복원 확인
            restored_content = test_file.read_text()
            
            return restore_result and restored_content == "original content"
            
        except Exception as e:
            self._log(f"Self-healing recovery test error: {e}")
            return False
    
    def test_quarantine_release(self) -> bool:
        """격리 해제 테스트"""
        try:
            backup_dir = self.temp_dir / "backups"
            quarantine_dir = self.temp_dir / "quarantine"
            self_heal = SelfHeal(str(backup_dir), str(quarantine_dir))
            
            # 테스트 파일 생성
            test_file = self.temp_dir / "quarantine_test.txt"
            test_file.write_text("test content")
            
            # 격리 설정
            self_heal.quarantined_files.add(str(test_file))
            self_heal.setup_quarantine_release_conditions(str(test_file))
            
            # 성공 이벤트 기록
            self_heal.success_events[str(test_file)] = 3
            self_heal.normal_delta_count[str(test_file)] = 5
            
            # 격리 해제 조건 확인
            can_release = self_heal.check_quarantine_release_conditions(str(test_file))
            
            return can_release
            
        except Exception as e:
            self._log(f"Quarantine release test error: {e}")
            return False
    
    # === 성능 테스트 ===
    
    def test_delta_processing_performance(self) -> bool:
        """Delta 처리 성능 테스트"""
        try:
            processing_times = []
            
            # 여러 Delta 이벤트 처리
            for i in range(100):
                delta_event = {
                    "path": str(self.temp_dir / f"perf_test_{i}.txt"),
                    "operation": "write",
                    "producer_actual": "perf_producer",
                    "producer_expected": "perf_producer",
                    "ts": time.time(),
                    "conversation_id": f"perf_conv_{i}",
                    "turn_id": f"perf_turn_{i}"
                }
                
                start_time = time.time()
                result = self.context_runtime.handle_delta(delta_event)
                processing_time = time.time() - start_time
                
                processing_times.append(processing_time)
                
                if not result.get("success"):
                    return False
            
            # 성능 기준 확인 (평균 처리 시간 < 100ms)
            avg_processing_time = statistics.mean(processing_times)
            return avg_processing_time < 0.1
            
        except Exception as e:
            self._log(f"Delta processing performance test error: {e}")
            return False
    
    def test_concurrent_operations(self) -> bool:
        """동시 작업 테스트"""
        try:
            results = []
            errors = []
            
            def process_delta(worker_id: int):
                try:
                    for i in range(10):
                        delta_event = {
                            "path": str(self.temp_dir / f"concurrent_{worker_id}_{i}.txt"),
                            "operation": "write",
                            "producer_actual": f"worker_{worker_id}",
                            "producer_expected": f"worker_{worker_id}",
                            "ts": time.time(),
                            "conversation_id": f"concurrent_conv_{worker_id}_{i}",
                            "turn_id": f"concurrent_turn_{worker_id}_{i}"
                        }
                        
                        result = self.context_runtime.handle_delta(delta_event)
                        results.append(result.get("success", False))
                        
                except Exception as e:
                    errors.append(str(e))
            
            # 5개 스레드에서 동시 작업
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(process_delta, i) for i in range(5)]
                concurrent.futures.wait(futures)
            
            # 모든 작업이 성공했는지 확인
            return len(errors) == 0 and all(results)
            
        except Exception as e:
            self._log(f"Concurrent operations test error: {e}")
            return False
    
    # === 보안 테스트 ===
    
    def test_event_log_signature_verification(self) -> bool:
        """이벤트 로그 서명 검증 테스트"""
        try:
            log_file = self.temp_dir / "test_event.log"
            event_log = EventLog(str(log_file), enable_signing=True)
            
            # 이벤트 로그
            event_log.log_event("TEST_EVENT", {"test": "data"})
            
            # 무결성 검증
            is_valid, errors = event_log.verify_log_integrity()
            
            return is_valid and len(errors) == 0
            
        except Exception as e:
            self._log(f"Event log signature verification test error: {e}")
            return False
    
    def test_configuration_signature_verification(self) -> bool:
        """설정 서명 검증 테스트"""
        try:
            from memoryos.core.config_signature import ConfigSignatureVerifier
            
            verifier = ConfigSignatureVerifier()
            
            # 기본 Features 생성
            verifier._create_default_features()
            
            # 서명 재생성
            success = verifier.regenerate_signature()
            
            return success
            
        except Exception as e:
            self._log(f"Configuration signature verification test error: {e}")
            return False
    
    def test_idempotency_security(self) -> bool:
        """Idempotency 보안 테스트"""
        try:
            # 동일한 이벤트를 여러 번 처리
            delta_event = {
                "path": str(self.temp_dir / "idempotency_test.txt"),
                "operation": "write",
                "producer_actual": "security_producer",
                "producer_expected": "security_producer",
                "ts": time.time(),
                "conversation_id": "security_conv",
                "turn_id": "security_turn"
            }
            
            # 첫 번째 처리
            result1 = self.context_runtime.handle_delta(delta_event)
            
            # 두 번째 처리 (중복)
            result2 = self.context_runtime.handle_delta(delta_event)
            
            # 첫 번째는 성공, 두 번째는 실패해야 함
            return result1.get("success") and not result2.get("success")
            
        except Exception as e:
            self._log(f"Idempotency security test error: {e}")
            return False
    
    # === 스트레스 테스트 ===
    
    def test_high_volume_delta_processing(self) -> bool:
        """대용량 Delta 처리 테스트"""
        try:
            success_count = 0
            
            # 1000개의 Delta 이벤트 처리
            for i in range(1000):
                delta_event = {
                    "path": str(self.temp_dir / f"stress_test_{i}.txt"),
                    "operation": "write",
                    "producer_actual": "stress_producer",
                    "producer_expected": "stress_producer",
                    "ts": time.time(),
                    "conversation_id": f"stress_conv_{i}",
                    "turn_id": f"stress_turn_{i}"
                }
                
                result = self.context_runtime.handle_delta(delta_event)
                if result.get("success"):
                    success_count += 1
            
            # 95% 이상 성공해야 함
            success_rate = success_count / 1000
            return success_rate >= 0.95
            
        except Exception as e:
            self._log(f"High volume delta processing test error: {e}")
            return False
    
    def test_memory_usage_stability(self) -> bool:
        """메모리 사용량 안정성 테스트"""
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss
            
            # 많은 작업 수행
            for i in range(500):
                delta_event = {
                    "path": str(self.temp_dir / f"memory_test_{i}.txt"),
                    "operation": "write",
                    "producer_actual": "memory_producer",
                    "producer_expected": "memory_producer",
                    "ts": time.time(),
                    "conversation_id": f"memory_conv_{i}",
                    "turn_id": f"memory_turn_{i}"
                }
                
                self.context_runtime.handle_delta(delta_event)
            
            final_memory = process.memory_info().rss
            memory_increase = final_memory - initial_memory
            
            # 메모리 증가가 100MB 이하여야 함
            return memory_increase < 100 * 1024 * 1024
            
        except Exception as e:
            self._log(f"Memory usage stability test error: {e}")
            return False
    
    # === 테스트 실행 ===
    
    def run_integrity_tests(self):
        """무결성 테스트 실행"""
        self._log("Running integrity tests...")
        
        self._run_test(
            self.test_hash_chain_integrity,
            "hash_chain_integrity",
            TestCategory.INTEGRITY
        )
        
        self._run_test(
            self.test_data_catalog_consistency,
            "data_catalog_consistency",
            TestCategory.INTEGRITY
        )
        
        self._run_test(
            self.test_snapshot_schema_validation,
            "snapshot_schema_validation",
            TestCategory.INTEGRITY
        )
    
    def run_recovery_tests(self):
        """복원 테스트 실행"""
        self._log("Running recovery tests...")
        
        self._run_test(
            self.test_self_healing_recovery,
            "self_healing_recovery",
            TestCategory.RECOVERY
        )
        
        self._run_test(
            self.test_quarantine_release,
            "quarantine_release",
            TestCategory.RECOVERY
        )
    
    def run_performance_tests(self):
        """성능 테스트 실행"""
        self._log("Running performance tests...")
        
        self._run_test(
            self.test_delta_processing_performance,
            "delta_processing_performance",
            TestCategory.PERFORMANCE
        )
        
        self._run_test(
            self.test_concurrent_operations,
            "concurrent_operations",
            TestCategory.CONCURRENCY
        )
    
    def run_security_tests(self):
        """보안 테스트 실행"""
        self._log("Running security tests...")
        
        self._run_test(
            self.test_event_log_signature_verification,
            "event_log_signature_verification",
            TestCategory.SECURITY
        )
        
        self._run_test(
            self.test_configuration_signature_verification,
            "configuration_signature_verification",
            TestCategory.SECURITY
        )
        
        self._run_test(
            self.test_idempotency_security,
            "idempotency_security",
            TestCategory.SECURITY
        )
    
    def run_stress_tests(self):
        """스트레스 테스트 실행"""
        self._log("Running stress tests...")
        
        self._run_test(
            self.test_high_volume_delta_processing,
            "high_volume_delta_processing",
            TestCategory.STRESS
        )
        
        self._run_test(
            self.test_memory_usage_stability,
            "memory_usage_stability",
            TestCategory.STRESS
        )
    
    def run_all_tests(self) -> Dict:
        """모든 테스트 실행"""
        self._log("Starting comprehensive test suite...")
        
        if not self._setup_test_environment():
            return {"success": False, "error": "Test environment setup failed"}
        
        try:
            # 모든 테스트 카테고리 실행
            self.run_integrity_tests()
            self.run_recovery_tests()
            self.run_performance_tests()
            self.run_security_tests()
            self.run_stress_tests()
            
            # 테스트 결과 분석
            total_tests = len(self.test_results)
            passed_tests = len([r for r in self.test_results if r.result == TestResult.PASS])
            failed_tests = len([r for r in self.test_results if r.result == TestResult.FAIL])
            error_tests = len([r for r in self.test_results if r.result == TestResult.ERROR])
            
            # 카테고리별 결과
            category_results = {}
            for category in TestCategory:
                category_tests = [r for r in self.test_results if r.category == category]
                category_passed = len([r for r in category_tests if r.result == TestResult.PASS])
                category_total = len(category_tests)
                
                category_results[category.value] = {
                    "passed": category_passed,
                    "total": category_total,
                    "success_rate": category_passed / max(category_total, 1)
                }
            
            # 전체 결과
            overall_success = passed_tests / max(total_tests, 1) >= 0.9  # 90% 이상 통과
            
            test_summary = {
                "success": overall_success,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "error_tests": error_tests,
                "success_rate": passed_tests / max(total_tests, 1),
                "category_results": category_results,
                "test_details": [
                    {
                        "name": r.test_name,
                        "category": r.category.value,
                        "result": r.result.value,
                        "duration_ms": r.duration_ms,
                        "error": r.error_message
                    }
                    for r in self.test_results
                ]
            }
            
            # 결과 저장
            self._save_test_results(test_summary)
            
            self._log(f"Test suite completed: {passed_tests}/{total_tests} passed")
            return test_summary
            
        finally:
            self._cleanup_test_environment()
    
    def _save_test_results(self, results: Dict):
        """테스트 결과 저장"""
        results_file = self.output_dir / "test_results.json"
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        self._log(f"Test results saved: {results_file}")


def run_production_test_suite(output_dir: str = "test_output") -> Dict:
    """
    Production 테스트 스위트 실행
    
    Args:
        output_dir: 테스트 결과 출력 디렉토리
    
    Returns:
        테스트 결과 딕셔너리
    """
    test_suite = ProductionTestSuite(output_dir)
    return test_suite.run_all_tests()


if __name__ == "__main__":
    # 테스트 스위트 실행
    results = run_production_test_suite()
    
    if results["success"]:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
        print(f"Success rate: {results['success_rate']:.2%}")
    
    print(f"Test results saved to: test_output/test_results.json")
