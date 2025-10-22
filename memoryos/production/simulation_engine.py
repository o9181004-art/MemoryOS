"""
MemoryOS Production Simulation Engine
완전한 Drift-Heal-Snapshot 시뮬레이션 루프 자동화

이 모듈은 MemoryOS의 핵심 기능들을 통합하여
실제 운영 환경과 유사한 시뮬레이션을 수행합니다.
"""

import time
import json
import random
import threading
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from memoryos.core.context_runtime import ContextRuntime
from memoryos.guard.drift_guard import DriftGuard, DriftLevel
from memoryos.guard.self_heal import SelfHeal
from memoryos.observe.metrics import StandardMetricsCollector
from memoryos.core.snapshot_generator import SnapshotGenerator


class SimulationPhase(Enum):
    """시뮬레이션 단계"""
    INITIALIZATION = "initialization"
    NORMAL_OPERATION = "normal_operation"
    DRIFT_DETECTION = "drift_detection"
    SELF_HEALING = "self_healing"
    QUARANTINE = "quarantine"
    RECOVERY = "recovery"
    SNAPSHOT_EXPORT = "snapshot_export"
    CLEANUP = "cleanup"


@dataclass
class SimulationConfig:
    """시뮬레이션 설정"""
    duration_minutes: int = 30
    delta_interval_ms: int = 1000
    drift_probability: float = 0.1
    heal_probability: float = 0.8
    snapshot_interval_minutes: int = 5
    max_concurrent_files: int = 10
    enable_metrics: bool = True
    enable_snapshots: bool = True
    enable_quarantine: bool = True
    log_level: str = "INFO"


@dataclass
class SimulationMetrics:
    """시뮬레이션 메트릭"""
    total_deltas: int = 0
    drift_events: int = 0
    heal_events: int = 0
    quarantine_events: int = 0
    snapshot_events: int = 0
    error_events: int = 0
    start_time: float = 0
    end_time: float = 0
    
    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time
    
    @property
    def delta_rate_per_minute(self) -> float:
        return (self.total_deltas / self.duration_seconds) * 60 if self.duration_seconds > 0 else 0


class ProductionSimulationEngine:
    """
    MemoryOS Production Simulation Engine
    
    완전한 운영 환경 시뮬레이션을 수행하여
    시스템의 안정성과 성능을 검증합니다.
    """
    
    def __init__(self, config: SimulationConfig, output_dir: str = "simulation_output"):
        """
        시뮬레이션 엔진 초기화
        
        Args:
            config: 시뮬레이션 설정
            output_dir: 출력 디렉토리
        """
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # MemoryOS 컴포넌트 초기화
        self.context_runtime = None
        self.drift_guard = None
        self.self_heal = None
        self.metrics_collector = None
        self.snapshot_generator = None
        
        # 시뮬레이션 상태
        self.is_running = False
        self.current_phase = SimulationPhase.INITIALIZATION
        self.metrics = SimulationMetrics()
        self.simulation_data = []
        
        # 콜백 함수들
        self.phase_callbacks: Dict[SimulationPhase, List[Callable]] = {
            phase: [] for phase in SimulationPhase
        }
        
        # 스레드 관리
        self.simulation_thread = None
        self.stop_event = threading.Event()
        
    def initialize_components(self) -> bool:
        """MemoryOS 컴포넌트 초기화"""
        try:
            # ContextRuntime 초기화
            config_file = "memoryos/config/default.toml"
            self.context_runtime = ContextRuntime(config_file)
            
            # Guard 컴포넌트들
            self.drift_guard = DriftGuard()
            self.self_heal = SelfHeal(
                backup_dir=str(self.output_dir / "backups"),
                quarantine_dir=str(self.output_dir / "quarantine")
            )
            
            # Observe 컴포넌트들
            if self.config.enable_metrics:
                self.metrics_collector = StandardMetricsCollector(
                    metrics_dir=str(self.output_dir / "metrics")
                )
            
            if self.config.enable_snapshots:
                self.snapshot_generator = SnapshotGenerator(
                    snapshot_dir=str(self.output_dir / "snapshots")
                )
            
            self._log("Components initialized successfully")
            return True
            
        except Exception as e:
            self._log(f"Component initialization failed: {e}")
            return False
    
    def register_phase_callback(self, phase: SimulationPhase, callback: Callable):
        """시뮬레이션 단계별 콜백 등록"""
        self.phase_callbacks[phase].append(callback)
    
    def _log(self, message: str):
        """로깅"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [SimulationEngine] {message}")
    
    def _execute_phase_callbacks(self, phase: SimulationPhase):
        """단계별 콜백 실행"""
        for callback in self.phase_callbacks[phase]:
            try:
                callback(self)
            except Exception as e:
                self._log(f"Phase callback error: {e}")
    
    def _generate_test_files(self, count: int) -> List[Path]:
        """테스트 파일 생성"""
        test_files = []
        test_dir = self.output_dir / "test_data"
        test_dir.mkdir(exist_ok=True)
        
        for i in range(count):
            file_path = test_dir / f"test_file_{i:03d}.txt"
            content = f"Test content for file {i}\nTimestamp: {time.time()}\n"
            file_path.write_text(content)
            test_files.append(file_path)
        
        return test_files
    
    def _simulate_delta_event(self, file_path: Path) -> Dict:
        """Delta 이벤트 시뮬레이션"""
        # 파일 내용 변경
        current_content = file_path.read_text()
        new_content = current_content + f"\nModified at: {time.time()}\n"
        file_path.write_text(new_content)
        
        # Delta 이벤트 생성
        delta_event = {
            "path": str(file_path),
            "operation": "write",
            "producer_actual": f"simulation_producer_{random.randint(1, 5)}",
            "producer_expected": "expected_producer",
            "ts": time.time(),
            "conversation_id": f"sim_{int(time.time())}",
            "turn_id": f"turn_{random.randint(1, 1000)}"
        }
        
        return delta_event
    
    def _simulate_drift_scenario(self, file_path: Path) -> Dict:
        """Drift 시나리오 시뮬레이션"""
        # 의도적으로 잘못된 producer로 변경
        delta_event = {
            "path": str(file_path),
            "operation": "write",
            "producer_actual": "malicious_producer",  # 의도적으로 잘못된 producer
            "producer_expected": "trusted_producer",
            "ts": time.time() - random.randint(60, 3600),  # 오래된 타임스탬프
            "conversation_id": f"drift_sim_{int(time.time())}",
            "turn_id": f"drift_turn_{random.randint(1, 1000)}"
        }
        
        return delta_event
    
    def _process_delta_with_metrics(self, delta_event: Dict) -> Dict:
        """메트릭 수집과 함께 Delta 처리"""
        start_time = time.time()
        
        try:
            result = self.context_runtime.handle_delta(delta_event)
            
            # 메트릭 수집
            if self.metrics_collector:
                processing_time = time.time() - start_time
                self.metrics_collector.record_operation_time("delta_processing", processing_time)
                
                if result.get("success"):
                    self.metrics_collector.record_cache_hit("delta_success")
                else:
                    self.metrics_collector.record_error("delta_failure")
            
            return result
            
        except Exception as e:
            self.metrics.error_events += 1
            if self.metrics_collector:
                self.metrics_collector.record_error("delta_exception")
            self._log(f"Delta processing error: {e}")
            return {"success": False, "error": str(e)}
    
    def _check_drift_and_heal(self, delta_event: Dict) -> Dict:
        """Drift 감지 및 Self-Healing"""
        file_path = delta_event["path"]
        
        try:
            # Drift 감지
            drift_result = self.drift_guard.check_drift(
                file_path=file_path,
                producer_actual=delta_event["producer_actual"],
                producer_expected=delta_event["producer_expected"],
                timestamp=delta_event["ts"]
            )
            
            if drift_result["drift_level"] > DriftLevel.L1.value:
                self.metrics.drift_events += 1
                
                # Self-Healing 실행
                heal_result = self.self_heal.execute_healing(
                    file_path=file_path,
                    drift_level=drift_result["drift_level"],
                    drift_info=drift_result
                )
                
                if heal_result.get("success"):
                    self.metrics.heal_events += 1
                    
                    # Quarantine 확인
                    if drift_result["drift_level"] >= DriftLevel.L3.value:
                        self.metrics.quarantine_events += 1
                
                return {
                    "drift_detected": True,
                    "drift_level": drift_result["drift_level"],
                    "heal_result": heal_result
                }
            
            return {"drift_detected": False}
            
        except Exception as e:
            self._log(f"Drift/Heal processing error: {e}")
            return {"drift_detected": False, "error": str(e)}
    
    def _generate_snapshot(self) -> Optional[str]:
        """스냅샷 생성"""
        if not self.snapshot_generator:
            return None
        
        try:
            snapshot_data = self.snapshot_generator.generate_snapshot(
                memory_index=self.context_runtime.memory_sync.memory_index,
                hash_chain=self.context_runtime.hash_chain,
                drift_status=self.drift_guard.get_drift_status(),
                quarantine_status=self.self_heal.get_quarantine_status()
            )
            
            snapshot_path = self.snapshot_generator.save_snapshot(snapshot_data)
            self.metrics.snapshot_events += 1
            
            return snapshot_path
            
        except Exception as e:
            self._log(f"Snapshot generation error: {e}")
            return None
    
    def _simulation_loop(self):
        """메인 시뮬레이션 루프"""
        self.metrics.start_time = time.time()
        self.current_phase = SimulationPhase.NORMAL_OPERATION
        self._execute_phase_callbacks(self.current_phase)
        
        # 테스트 파일 생성
        test_files = self._generate_test_files(self.config.max_concurrent_files)
        last_snapshot_time = time.time()
        
        while not self.stop_event.is_set():
            try:
                # Delta 이벤트 생성 및 처리
                file_path = random.choice(test_files)
                
                # Drift 시나리오 확률적 실행
                if random.random() < self.config.drift_probability:
                    delta_event = self._simulate_drift_scenario(file_path)
                    self.current_phase = SimulationPhase.DRIFT_DETECTION
                else:
                    delta_event = self._simulate_delta_event(file_path)
                    self.current_phase = SimulationPhase.NORMAL_OPERATION
                
                # Delta 처리
                delta_result = self._process_delta_with_metrics(delta_event)
                self.metrics.total_deltas += 1
                
                # Drift 감지 및 Self-Healing
                if delta_result.get("success"):
                    drift_result = self._check_drift_and_heal(delta_event)
                    
                    if drift_result.get("drift_detected"):
                        self.current_phase = SimulationPhase.SELF_HEALING
                        if drift_result.get("drift_level", 0) >= DriftLevel.L3.value:
                            self.current_phase = SimulationPhase.QUARANTINE
                
                # 주기적 스냅샷 생성
                current_time = time.time()
                if (self.config.enable_snapshots and 
                    current_time - last_snapshot_time >= self.config.snapshot_interval_minutes * 60):
                    
                    self.current_phase = SimulationPhase.SNAPSHOT_EXPORT
                    snapshot_path = self._generate_snapshot()
                    if snapshot_path:
                        self._log(f"Snapshot generated: {snapshot_path}")
                    last_snapshot_time = current_time
                
                # 시뮬레이션 데이터 기록
                self.simulation_data.append({
                    "timestamp": current_time,
                    "phase": self.current_phase.value,
                    "delta_event": delta_event,
                    "delta_result": delta_result,
                    "drift_result": drift_result if delta_result.get("success") else None
                })
                
                # 단계별 콜백 실행
                self._execute_phase_callbacks(self.current_phase)
                
                # 대기
                time.sleep(self.config.delta_interval_ms / 1000.0)
                
                # 시뮬레이션 종료 조건 확인
                if current_time - self.metrics.start_time >= self.config.duration_minutes * 60:
                    break
                    
            except Exception as e:
                self._log(f"Simulation loop error: {e}")
                self.metrics.error_events += 1
                time.sleep(1)  # 에러 시 잠시 대기
        
        self.metrics.end_time = time.time()
        self.current_phase = SimulationPhase.CLEANUP
        self._execute_phase_callbacks(self.current_phase)
    
    def start_simulation(self) -> bool:
        """시뮬레이션 시작"""
        if self.is_running:
            self._log("Simulation is already running")
            return False
        
        if not self.initialize_components():
            return False
        
        self.is_running = True
        self.stop_event.clear()
        
        # 시뮬레이션 스레드 시작
        self.simulation_thread = threading.Thread(target=self._simulation_loop)
        self.simulation_thread.start()
        
        self._log(f"Simulation started (duration: {self.config.duration_minutes} minutes)")
        return True
    
    def stop_simulation(self):
        """시뮬레이션 중지"""
        if not self.is_running:
            return
        
        self.stop_event.set()
        if self.simulation_thread:
            self.simulation_thread.join(timeout=10)
        
        self.is_running = False
        self._log("Simulation stopped")
    
    def wait_for_completion(self, timeout: Optional[float] = None):
        """시뮬레이션 완료 대기"""
        if self.simulation_thread:
            self.simulation_thread.join(timeout=timeout)
    
    def get_simulation_report(self) -> Dict:
        """시뮬레이션 리포트 생성"""
        report = {
            "config": {
                "duration_minutes": self.config.duration_minutes,
                "delta_interval_ms": self.config.delta_interval_ms,
                "drift_probability": self.config.drift_probability,
                "heal_probability": self.config.heal_probability,
                "snapshot_interval_minutes": self.config.snapshot_interval_minutes,
                "max_concurrent_files": self.config.max_concurrent_files
            },
            "metrics": {
                "total_deltas": self.metrics.total_deltas,
                "drift_events": self.metrics.drift_events,
                "heal_events": self.metrics.heal_events,
                "quarantine_events": self.metrics.quarantine_events,
                "snapshot_events": self.metrics.snapshot_events,
                "error_events": self.metrics.error_events,
                "duration_seconds": self.metrics.duration_seconds,
                "delta_rate_per_minute": self.metrics.delta_rate_per_minute
            },
            "performance": {
                "drift_detection_rate": self.metrics.drift_events / max(self.metrics.total_deltas, 1),
                "healing_success_rate": self.metrics.heal_events / max(self.metrics.drift_events, 1),
                "error_rate": self.metrics.error_events / max(self.metrics.total_deltas, 1)
            },
            "output_directory": str(self.output_dir),
            "simulation_data_count": len(self.simulation_data)
        }
        
        return report
    
    def save_simulation_report(self, filename: str = "simulation_report.json"):
        """시뮬레이션 리포트 저장"""
        report = self.get_simulation_report()
        report_path = self.output_dir / filename
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self._log(f"Simulation report saved: {report_path}")
        return report_path


def create_production_simulation(
    duration_minutes: int = 30,
    drift_probability: float = 0.1,
    output_dir: str = "simulation_output"
) -> ProductionSimulationEngine:
    """
    Production 시뮬레이션 엔진 생성
    
    Args:
        duration_minutes: 시뮬레이션 지속 시간 (분)
        drift_probability: Drift 발생 확률
        output_dir: 출력 디렉토리
    
    Returns:
        ProductionSimulationEngine 인스턴스
    """
    config = SimulationConfig(
        duration_minutes=duration_minutes,
        drift_probability=drift_probability,
        enable_metrics=True,
        enable_snapshots=True,
        enable_quarantine=True
    )
    
    return ProductionSimulationEngine(config, output_dir)


if __name__ == "__main__":
    # 기본 시뮬레이션 실행
    engine = create_production_simulation(duration_minutes=5, drift_probability=0.2)
    
    # 단계별 콜백 등록 예시
    def on_drift_detection(engine):
        print(f"[Callback] Drift detected at {time.time()}")
    
    def on_quarantine(engine):
        print(f"[Callback] Quarantine activated at {time.time()}")
    
    engine.register_phase_callback(SimulationPhase.DRIFT_DETECTION, on_drift_detection)
    engine.register_phase_callback(SimulationPhase.QUARANTINE, on_quarantine)
    
    # 시뮬레이션 실행
    if engine.start_simulation():
        engine.wait_for_completion()
        report_path = engine.save_simulation_report()
        print(f"Simulation completed. Report: {report_path}")
    else:
        print("Simulation failed to start")
