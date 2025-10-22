"""
MemoryOS Autonomous Optimization System
자율 최적화 시스템 - MemoryOS가 스스로 성능을 향상시키는 시스템

이 모듈은 ProductionTestSuite를 기반으로 하여:
1. 실패한 테스트의 패턴을 학습하고 자동 재시도
2. 시스템 파라미터를 자동으로 재조정
3. 안정성 95% 이상 달성 시 Stable State 로깅
"""

import time
import json
import random
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import statistics
from collections import defaultdict, deque

from memoryos.production.test_suite import ProductionTestSuite, TestCategory, TestResult, TestMetrics
from memoryos.production.simulation_engine import ProductionSimulationEngine, SimulationConfig


class OptimizationPhase(Enum):
    """최적화 단계"""
    INITIAL_BASELINE = "initial_baseline"
    FAILURE_ANALYSIS = "failure_analysis"
    PARAMETER_ADJUSTMENT = "parameter_adjustment"
    VALIDATION_TESTING = "validation_testing"
    STABLE_STATE = "stable_state"
    CONTINUOUS_MONITORING = "continuous_monitoring"


class ParameterType(Enum):
    """파라미터 타입"""
    DRIFT_THRESHOLD = "drift_threshold"
    HEAL_TIMEOUT = "heal_timeout"
    QUARANTINE_DURATION = "quarantine_duration"
    BATCH_SIZE = "batch_size"
    RETRY_COUNT = "retry_count"
    CIRCUIT_BREAKER_THRESHOLD = "circuit_breaker_threshold"


@dataclass
class FailurePattern:
    """실패 패턴"""
    test_name: str
    category: TestCategory
    failure_count: int
    last_failure_time: float
    failure_reasons: List[str]
    parameter_context: Dict[str, Any]
    
    @property
    def failure_rate(self) -> float:
        return self.failure_count / max(self.last_failure_time - self.first_failure_time, 1) if hasattr(self, 'first_failure_time') else 1.0


@dataclass
class ParameterConfig:
    """파라미터 설정"""
    param_type: ParameterType
    current_value: float
    min_value: float
    max_value: float
    step_size: float
    adjustment_history: List[Tuple[float, float, bool]]  # (old_value, new_value, success)
    
    def adjust(self, direction: str, success_rate: float) -> float:
        """파라미터 조정"""
        if direction == "increase":
            new_value = min(self.current_value + self.step_size, self.max_value)
        else:
            new_value = max(self.current_value - self.step_size, self.min_value)
        
        # 성공률에 따른 스텝 크기 조정
        if success_rate > 0.8:
            self.step_size *= 1.1  # 성공 시 더 큰 스텝
        elif success_rate < 0.5:
            self.step_size *= 0.9  # 실패 시 더 작은 스텝
        
        self.step_size = max(0.01, min(1.0, self.step_size))  # 스텝 크기 제한
        
        old_value = self.current_value
        self.current_value = new_value
        
        return old_value, new_value


@dataclass
class OptimizationMetrics:
    """최적화 메트릭"""
    iteration: int
    timestamp: float
    phase: OptimizationPhase
    overall_success_rate: float
    category_success_rates: Dict[str, float]
    parameter_adjustments: Dict[str, Tuple[float, float]]
    failure_patterns: List[FailurePattern]
    stability_score: float
    convergence_rate: float


class AdaptiveTestScheduler:
    """
    적응형 테스트 스케줄러
    
    실패한 테스트를 분석하고 자동으로 재시도하며
    시스템 파라미터를 조정합니다.
    """
    
    def __init__(self, output_dir: str = "auto_opt_output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 테스트 스케줄링
        self.test_queue = deque()
        self.failed_tests = defaultdict(int)
        self.test_priorities = defaultdict(float)
        
        # 실패 패턴 학습
        self.failure_patterns: Dict[str, FailurePattern] = {}
        self.failure_memory = deque(maxlen=1000)  # 최근 1000개 실패 기록
        
        # 파라미터 관리
        self.parameter_configs = self._initialize_parameters()
        self.parameter_history = deque(maxlen=100)
        
        # 최적화 상태
        self.current_phase = OptimizationPhase.INITIAL_BASELINE
        self.iteration = 0
        self.stable_state_count = 0
        self.last_stable_time = 0
        
        # 메트릭 수집
        self.metrics_file = self.output_dir / "metrics" / "auto_opt.jsonl"
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 안정성 기준
        self.stability_threshold = 0.95
        self.min_stable_iterations = 5
        
    def _initialize_parameters(self) -> Dict[ParameterType, ParameterConfig]:
        """파라미터 초기화"""
        return {
            ParameterType.DRIFT_THRESHOLD: ParameterConfig(
                param_type=ParameterType.DRIFT_THRESHOLD,
                current_value=0.1,
                min_value=0.01,
                max_value=0.5,
                step_size=0.05,
                adjustment_history=[]
            ),
            ParameterType.HEAL_TIMEOUT: ParameterConfig(
                param_type=ParameterType.HEAL_TIMEOUT,
                current_value=30.0,
                min_value=5.0,
                max_value=120.0,
                step_size=10.0,
                adjustment_history=[]
            ),
            ParameterType.QUARANTINE_DURATION: ParameterConfig(
                param_type=ParameterType.QUARANTINE_DURATION,
                current_value=300.0,
                min_value=60.0,
                max_value=1800.0,
                step_size=60.0,
                adjustment_history=[]
            ),
            ParameterType.BATCH_SIZE: ParameterConfig(
                param_type=ParameterType.BATCH_SIZE,
                current_value=10.0,
                min_value=1.0,
                max_value=50.0,
                step_size=5.0,
                adjustment_history=[]
            ),
            ParameterType.RETRY_COUNT: ParameterConfig(
                param_type=ParameterType.RETRY_COUNT,
                current_value=3.0,
                min_value=1.0,
                max_value=10.0,
                step_size=1.0,
                adjustment_history=[]
            ),
            ParameterType.CIRCUIT_BREAKER_THRESHOLD: ParameterConfig(
                param_type=ParameterType.CIRCUIT_BREAKER_THRESHOLD,
                current_value=0.5,
                min_value=0.1,
                max_value=0.9,
                step_size=0.1,
                adjustment_history=[]
            )
        }
    
    def _log(self, message: str):
        """로깅"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [AdaptiveTestScheduler] {message}")
    
    def analyze_failure_patterns(self, test_results: List[TestMetrics]) -> List[FailurePattern]:
        """실패 패턴 분석"""
        patterns = []
        
        for result in test_results:
            if result.result == TestResult.FAIL:
                test_name = result.test_name
                
                if test_name not in self.failure_patterns:
                    self.failure_patterns[test_name] = FailurePattern(
                        test_name=test_name,
                        category=result.category,
                        failure_count=0,
                        last_failure_time=time.time(),
                        failure_reasons=[],
                        parameter_context={}
                    )
                
                pattern = self.failure_patterns[test_name]
                pattern.failure_count += 1
                pattern.last_failure_time = time.time()
                pattern.failure_reasons.append(result.error_message or "Unknown error")
                
                # 현재 파라미터 컨텍스트 저장
                pattern.parameter_context = {
                    param_type.value: config.current_value
                    for param_type, config in self.parameter_configs.items()
                }
                
                patterns.append(pattern)
                
                # 실패 메모리에 추가
                self.failure_memory.append({
                    "test_name": test_name,
                    "timestamp": time.time(),
                    "error": result.error_message,
                    "parameters": pattern.parameter_context
                })
        
        return patterns
    
    def calculate_test_priorities(self, test_results: List[TestMetrics]) -> Dict[str, float]:
        """테스트 우선순위 계산"""
        priorities = {}
        
        for result in test_results:
            test_name = result.test_name
            
            # 기본 우선순위 (카테고리별)
            base_priority = {
                TestCategory.INTEGRITY: 1.0,
                TestCategory.SECURITY: 0.9,
                TestCategory.RECOVERY: 0.8,
                TestCategory.PERFORMANCE: 0.7,
                TestCategory.CONCURRENCY: 0.6,
                TestCategory.STRESS: 0.5
            }.get(result.category, 0.5)
            
            # 실패 횟수에 따른 가중치
            failure_weight = 1.0 + (self.failed_tests[test_name] * 0.1)
            
            # 최근 실패 시간에 따른 가중치
            if test_name in self.failure_patterns:
                time_since_failure = time.time() - self.failure_patterns[test_name].last_failure_time
                recency_weight = max(0.5, 1.0 - (time_since_failure / 3600))  # 1시간 기준
            else:
                recency_weight = 1.0
            
            priorities[test_name] = base_priority * failure_weight * recency_weight
        
        return priorities
    
    def adjust_parameters(self, test_results: List[TestMetrics]) -> Dict[str, Tuple[float, float]]:
        """파라미터 자동 조정"""
        adjustments = {}
        
        # 카테고리별 성공률 계산
        category_success_rates = defaultdict(list)
        for result in test_results:
            category_success_rates[result.category.value].append(
                1.0 if result.result == TestResult.PASS else 0.0
            )
        
        category_avg_success = {
            category: statistics.mean(successes) if successes else 0.0
            for category, successes in category_success_rates.items()
        }
        
        # 파라미터별 조정 전략
        for param_type, config in self.parameter_configs.items():
            old_value = config.current_value
            
            # 카테고리별 성공률에 따른 조정 방향 결정
            if param_type == ParameterType.DRIFT_THRESHOLD:
                # 무결성 테스트 실패 시 임계값 낮추기
                integrity_rate = category_avg_success.get("integrity", 0.5)
                if integrity_rate < 0.7:
                    direction = "decrease"
                else:
                    direction = "increase"
                    
            elif param_type == ParameterType.HEAL_TIMEOUT:
                # 복원 테스트 실패 시 타임아웃 늘리기
                recovery_rate = category_avg_success.get("recovery", 0.5)
                if recovery_rate < 0.7:
                    direction = "increase"
                else:
                    direction = "decrease"
                    
            elif param_type == ParameterType.QUARANTINE_DURATION:
                # 보안 테스트 실패 시 격리 시간 늘리기
                security_rate = category_avg_success.get("security", 0.5)
                if security_rate < 0.7:
                    direction = "increase"
                else:
                    direction = "decrease"
                    
            elif param_type == ParameterType.BATCH_SIZE:
                # 성능 테스트 실패 시 배치 크기 줄이기
                performance_rate = category_avg_success.get("performance", 0.5)
                if performance_rate < 0.7:
                    direction = "decrease"
                else:
                    direction = "increase"
                    
            elif param_type == ParameterType.RETRY_COUNT:
                # 전체 성공률이 낮으면 재시도 횟수 늘리기
                overall_rate = statistics.mean(category_avg_success.values())
                if overall_rate < 0.7:
                    direction = "increase"
                else:
                    direction = "decrease"
                    
            elif param_type == ParameterType.CIRCUIT_BREAKER_THRESHOLD:
                # 동시성 테스트 실패 시 임계값 낮추기
                concurrency_rate = category_avg_success.get("concurrency", 0.5)
                if concurrency_rate < 0.7:
                    direction = "decrease"
                else:
                    direction = "increase"
            
            else:
                continue
            
            # 파라미터 조정
            old_val, new_val = config.adjust(direction, overall_rate)
            adjustments[param_type.value] = (old_val, new_val)
            
            # 조정 기록 저장
            config.adjustment_history.append((old_val, new_val, overall_rate > 0.7))
            self.parameter_history.append({
                "param_type": param_type.value,
                "old_value": old_val,
                "new_value": new_val,
                "direction": direction,
                "timestamp": time.time(),
                "overall_success_rate": overall_rate
            })
        
        return adjustments
    
    def schedule_adaptive_tests(self, test_results: List[TestMetrics]) -> List[str]:
        """적응형 테스트 스케줄링"""
        # 우선순위 계산
        priorities = self.calculate_test_priorities(test_results)
        
        # 실패한 테스트 우선 스케줄링
        failed_tests = [r.test_name for r in test_results if r.result == TestResult.FAIL]
        passed_tests = [r.test_name for r in test_results if r.result == TestResult.PASS]
        
        # 다음 테스트 큐 구성
        next_tests = []
        
        # 실패한 테스트들을 우선순위 순으로 추가
        failed_with_priority = [(name, priorities.get(name, 0.5)) for name in failed_tests]
        failed_with_priority.sort(key=lambda x: x[1], reverse=True)
        
        for test_name, _ in failed_with_priority:
            next_tests.append(test_name)
        
        # 일부 통과한 테스트도 추가 (검증용)
        if passed_tests:
            validation_tests = random.sample(passed_tests, min(3, len(passed_tests)))
            next_tests.extend(validation_tests)
        
        return next_tests
    
    def calculate_stability_score(self, test_results: List[TestMetrics]) -> float:
        """안정성 점수 계산"""
        if not test_results:
            return 0.0
        
        # 전체 성공률
        overall_success_rate = len([r for r in test_results if r.result == TestResult.PASS]) / len(test_results)
        
        # 카테고리별 성공률의 일관성
        category_success_rates = defaultdict(list)
        for result in test_results:
            category_success_rates[result.category.value].append(
                1.0 if result.result == TestResult.PASS else 0.0
            )
        
        category_avg_success = [
            statistics.mean(successes) if successes else 0.0
            for successes in category_success_rates.values()
        ]
        
        # 카테고리 간 일관성 (표준편차가 낮을수록 좋음)
        consistency = 1.0 - statistics.stdev(category_avg_success) if len(category_avg_success) > 1 else 1.0
        
        # 파라미터 조정의 안정성
        recent_adjustments = list(self.parameter_history)[-10:]  # 최근 10개 조정
        adjustment_stability = 1.0
        if recent_adjustments:
            # 최근 조정이 적을수록 안정적
            adjustment_frequency = len(recent_adjustments) / 10.0
            adjustment_stability = max(0.0, 1.0 - adjustment_frequency)
        
        # 종합 안정성 점수
        stability_score = (
            overall_success_rate * 0.5 +
            consistency * 0.3 +
            adjustment_stability * 0.2
        )
        
        return stability_score
    
    def detect_stable_state(self, stability_score: float) -> bool:
        """안정 상태 감지"""
        if stability_score >= self.stability_threshold:
            self.stable_state_count += 1
            if self.stable_state_count >= self.min_stable_iterations:
                self.last_stable_time = time.time()
                return True
        else:
            self.stable_state_count = 0
        
        return False
    
    def log_optimization_metrics(self, metrics: OptimizationMetrics):
        """최적화 메트릭 로깅"""
        metrics_dict = asdict(metrics)
        metrics_dict["timestamp"] = time.time()
        
        with open(self.metrics_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(metrics_dict, ensure_ascii=False) + '\n')
    
    def run_optimization_iteration(self) -> OptimizationMetrics:
        """최적화 반복 실행"""
        self.iteration += 1
        start_time = time.time()
        
        self._log(f"Starting optimization iteration {self.iteration}")
        
        # 테스트 실행
        test_suite = ProductionTestSuite(str(self.output_dir / f"iteration_{self.iteration}"))
        test_results_dict = test_suite.run_all_tests()
        
        if not test_results_dict.get("success", False):
            test_results = []
        else:
            test_results = [
                TestMetrics(
                    test_name=detail["name"],
                    category=TestCategory(detail["category"]),
                    duration_ms=detail["duration_ms"],
                    result=TestResult(detail["result"]),
                    error_message=detail["error"]
                )
                for detail in test_results_dict["test_details"]
            ]
        
        # 실패 패턴 분석
        failure_patterns = self.analyze_failure_patterns(test_results)
        
        # 파라미터 조정
        parameter_adjustments = self.adjust_parameters(test_results)
        
        # 안정성 점수 계산
        stability_score = self.calculate_stability_score(test_results)
        
        # 안정 상태 감지
        is_stable = self.detect_stable_state(stability_score)
        
        if is_stable:
            self.current_phase = OptimizationPhase.STABLE_STATE
            self._log(f"🎉 STABLE STATE ACHIEVED! Stability score: {stability_score:.3f}")
        else:
            self.current_phase = OptimizationPhase.CONTINUOUS_MONITORING
        
        # 카테고리별 성공률 계산
        category_success_rates = {}
        for category in TestCategory:
            category_tests = [r for r in test_results if r.category == category]
            if category_tests:
                success_rate = len([r for r in category_tests if r.result == TestResult.PASS]) / len(category_tests)
                category_success_rates[category.value] = success_rate
        
        # 수렴률 계산 (최근 반복에서의 개선 정도)
        convergence_rate = 0.0
        if len(self.parameter_history) >= 2:
            recent_adjustments = list(self.parameter_history)[-5:]
            if recent_adjustments:
                # 최근 조정의 효과 측정
                convergence_rate = stability_score - (stability_score * 0.9)  # 간단한 수렴률 계산
        
        # 메트릭 생성
        metrics = OptimizationMetrics(
            iteration=self.iteration,
            timestamp=time.time(),
            phase=self.current_phase,
            overall_success_rate=test_results_dict.get("success_rate", 0.0),
            category_success_rates=category_success_rates,
            parameter_adjustments=parameter_adjustments,
            failure_patterns=failure_patterns,
            stability_score=stability_score,
            convergence_rate=convergence_rate
        )
        
        # 메트릭 로깅
        self.log_optimization_metrics(metrics)
        
        # 다음 테스트 스케줄링
        next_tests = self.schedule_adaptive_tests(test_results)
        
        self._log(f"Iteration {self.iteration} completed:")
        self._log(f"  Overall success rate: {metrics.overall_success_rate:.3f}")
        self._log(f"  Stability score: {stability_score:.3f}")
        self._log(f"  Parameter adjustments: {len(parameter_adjustments)}")
        self._log(f"  Failure patterns: {len(failure_patterns)}")
        self._log(f"  Next tests: {next_tests}")
        
        return metrics


class AutonomousOptimizer:
    """
    자율 최적화 시스템
    
    MemoryOS가 스스로 성능을 향상시키는 메인 시스템
    """
    
    def __init__(self, output_dir: str = "auto_opt_output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 컴포넌트 초기화
        self.test_scheduler = AdaptiveTestScheduler(str(self.output_dir))
        
        # 최적화 상태
        self.is_running = False
        self.max_iterations = 50
        self.target_stability = 0.95
        
        # 스레드 관리
        self.optimization_thread = None
        self.stop_event = threading.Event()
        
    def _log(self, message: str):
        """로깅"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [AutonomousOptimizer] {message}")
    
    def start_optimization(self) -> bool:
        """최적화 시작"""
        if self.is_running:
            self._log("Optimization is already running")
            return False
        
        self.is_running = True
        self.stop_event.clear()
        
        # 최적화 스레드 시작
        self.optimization_thread = threading.Thread(target=self._optimization_loop)
        self.optimization_thread.start()
        
        self._log("Autonomous optimization started")
        return True
    
    def stop_optimization(self):
        """최적화 중지"""
        if not self.is_running:
            return
        
        self.stop_event.set()
        if self.optimization_thread:
            self.optimization_thread.join(timeout=30)
        
        self.is_running = False
        self._log("Autonomous optimization stopped")
    
    def _optimization_loop(self):
        """최적화 루프"""
        iteration = 0
        
        while not self.stop_event.is_set() and iteration < self.max_iterations:
            try:
                iteration += 1
                self._log(f"Starting optimization iteration {iteration}")
                
                # 최적화 반복 실행
                metrics = self.test_scheduler.run_optimization_iteration()
                
                # 안정 상태 달성 확인
                if metrics.phase == OptimizationPhase.STABLE_STATE:
                    self._log(f"🎉 STABLE STATE ACHIEVED!")
                    self._log(f"   Iteration: {iteration}")
                    self._log(f"   Stability score: {metrics.stability_score:.3f}")
                    self._log(f"   Overall success rate: {metrics.overall_success_rate:.3f}")
                    
                    # 안정 상태 로깅
                    self._log_stable_state(metrics)
                    break
                
                # 진행 상황 로깅
                self._log(f"Iteration {iteration} completed:")
                self._log(f"  Phase: {metrics.phase.value}")
                self._log(f"  Success rate: {metrics.overall_success_rate:.3f}")
                self._log(f"  Stability score: {metrics.stability_score:.3f}")
                
                # 대기 (다음 반복 전)
                time.sleep(5)
                
            except Exception as e:
                self._log(f"Optimization iteration error: {e}")
                time.sleep(10)  # 에러 시 더 긴 대기
        
        self._log(f"Optimization completed after {iteration} iterations")
    
    def _log_stable_state(self, metrics: OptimizationMetrics):
        """안정 상태 로깅"""
        stable_state_log = {
            "timestamp": time.time(),
            "iteration": metrics.iteration,
            "stability_score": metrics.stability_score,
            "overall_success_rate": metrics.overall_success_rate,
            "category_success_rates": metrics.category_success_rates,
            "final_parameters": {
                param_type.value: config.current_value
                for param_type, config in self.test_scheduler.parameter_configs.items()
            },
            "optimization_summary": {
                "total_iterations": metrics.iteration,
                "parameter_adjustments": len(metrics.parameter_adjustments),
                "failure_patterns_learned": len(metrics.failure_patterns),
                "convergence_rate": metrics.convergence_rate
            }
        }
        
        stable_log_file = self.output_dir / "stable_state.json"
        with open(stable_log_file, 'w', encoding='utf-8') as f:
            json.dump(stable_state_log, f, indent=2, ensure_ascii=False)
        
        self._log(f"Stable state logged to: {stable_log_file}")
    
    def get_optimization_status(self) -> Dict:
        """최적화 상태 조회"""
        return {
            "is_running": self.is_running,
            "current_iteration": self.test_scheduler.iteration,
            "current_phase": self.test_scheduler.current_phase.value,
            "stability_score": self.test_scheduler.calculate_stability_score([]),
            "parameter_configs": {
                param_type.value: {
                    "current_value": config.current_value,
                    "min_value": config.min_value,
                    "max_value": config.max_value,
                    "step_size": config.step_size
                }
                for param_type, config in self.test_scheduler.parameter_configs.items()
            },
            "failure_patterns_count": len(self.test_scheduler.failure_patterns),
            "stable_state_achieved": self.test_scheduler.stable_state_count >= self.test_scheduler.min_stable_iterations
        }


def create_autonomous_optimizer(output_dir: str = "auto_opt_output") -> AutonomousOptimizer:
    """
    자율 최적화 시스템 생성
    
    Args:
        output_dir: 출력 디렉토리
    
    Returns:
        AutonomousOptimizer 인스턴스
    """
    return AutonomousOptimizer(output_dir)


if __name__ == "__main__":
    # 자율 최적화 시스템 실행
    optimizer = create_autonomous_optimizer()
    
    print("=== MemoryOS Autonomous Optimization ===")
    print("Starting autonomous optimization...")
    
    if optimizer.start_optimization():
        try:
            # 최적화 완료까지 대기
            optimizer.optimization_thread.join()
            
            # 최종 상태 출력
            status = optimizer.get_optimization_status()
            print("\n=== Optimization Complete ===")
            print(f"Final iteration: {status['current_iteration']}")
            print(f"Final phase: {status['current_phase']}")
            print(f"Stability achieved: {status['stable_state_achieved']}")
            
        except KeyboardInterrupt:
            print("\nOptimization interrupted by user")
            optimizer.stop_optimization()
    else:
        print("Failed to start optimization")
