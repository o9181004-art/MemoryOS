"""
ContextRuntime - 전체 파이프라인 조정 (entrypoint)

MemoryOS의 전체 파이프라인을 조정하고 관리하는 메인 런타임 클래스입니다.
"""

import time
from typing import Dict
from pathlib import Path

from .io_probe import IoProbe
from .data_catalog import DataCatalog
from .memory_sync import MemorySync
from .hashchain import HashChain
from .snapshot_generator import SnapshotGenerator
from .config_signature import ConfigSignatureVerifier
from ..observe.event_log import EventLog


class ContextRuntime:
    """
    MemoryOS 전체 파이프라인 조정 클래스
    
    주요 기능:
    - 전체 파이프라인 조정 및 관리
    - delta 이벤트 처리
    - drift 감지 및 복원
    - 스냅샷 생성 및 export
    """
    
    def __init__(self, config_path: str = "config/default.toml"):
        """
        ContextRuntime 초기화
        
        Args:
            config_path: 설정 파일 경로
        """
        self.config_path = config_path
        self.config = self._load_config()
        
        # Configuration Signature Verification 초기화
        config_dir = Path(config_path).parent
        self.config_verifier = ConfigSignatureVerifier(str(config_dir))
        
        # Event Log 초기화 (Correlation ID 관리)
        self.event_log = EventLog(
            log_file=self.config.get("log_file", "logs/event_log.jsonl"),
            enable_signing=self.config.get("signing", {}).get("enable_signing", False)
        )
        
        # Feature Flag 기반 컴포넌트 초기화
        self.io_probe = IoProbe(
            watch_paths=self.config.get("watch_paths", ["data/"]),
            callback=self._on_delta_detected
        )
        
        self.data_catalog = DataCatalog(
            catalog_file=str(self.config.get("catalog_file", "data/catalog.json"))
        )
        
        self.memory_sync = MemorySync(
            memory_index_file=str(self.config.get("memory_index_file", "data/memory_index.json"))
        )
        
        self.hash_chain = HashChain()
        
        self.snapshot_generator = SnapshotGenerator(
            snapshot_dir=str(self.config.get("snapshot_dir", "snapshots"))
        )
        
        # 상태 관리
        self.is_running = False
        self.last_delta_time = 0
        self.delta_count = 0
        
        # Idempotency 보장을 위한 처리된 이벤트 추적
        self.processed_events = set()  # (conversation_id, turn_id) 튜플 저장
        self.event_store = {}  # 이벤트 결과 캐시
        
        # Configuration Signature 상태 확인
        self._check_configuration_status()
        
    def _check_configuration_status(self) -> None:
        """Configuration Signature 상태 확인 및 로깅"""
        status = self.config_verifier.get_feature_status()
        
        if status["read_only_mode"]:
            print("[ContextRuntime] Running in READ-ONLY mode due to configuration signature verification failure")
            print("[ContextRuntime] Some features may be disabled for security")
        else:
            print("[ContextRuntime] Configuration signature verified successfully")
            
        print(f"[ContextRuntime] Active features: {[k for k, v in status['features'].items() if v]}")
        
    def is_feature_enabled(self, feature_name: str) -> bool:
        """
        Feature Flag 상태 확인
        
        Args:
            feature_name: 확인할 feature 이름
            
        Returns:
            Feature 활성화 여부
        """
        return self.config_verifier.is_feature_enabled(feature_name)
        
    def get_configuration_status(self) -> Dict:
        """
        Configuration 상태 정보 반환
        
        Returns:
            Configuration 상태 정보
        """
        return self.config_verifier.get_feature_status()
        
    def update_feature_flag(self, feature_name: str, enabled: bool) -> bool:
        """
        Feature Flag 업데이트
        
        Args:
            feature_name: 업데이트할 feature 이름
            enabled: 활성화 여부
            
        Returns:
            업데이트 성공 여부
        """
        return self.config_verifier.update_feature(feature_name, enabled)
        
    def _load_config(self) -> Dict:
        """설정 파일 로드"""
        try:
            config_path = Path(self.config_path)
            if config_path.exists():
                import toml
                with open(config_path, 'r', encoding='utf-8') as f:
                    return toml.load(f)
        except Exception as e:
            print(f"[ContextRuntime] Failed to load config: {e}")
            
        # 기본 설정
        return {
            "watch_paths": ["data/"],
            "catalog_file": "data/catalog.json",
            "memory_index_file": "data/memory_index.json",
            "snapshot_dir": "snapshots",
            "drift_thresholds": {
                "l1_threshold": 30,
                "l2_threshold": 300,
                "l3_threshold": 1800
            },
            "monitoring": {
                "enabled": True,
                "interval": 1.0
            }
        }
        
    def _on_delta_detected(self, delta: Dict) -> None:
        """
        Delta 이벤트 감지 시 콜백
        
        Args:
            delta: 감지된 delta 이벤트
        """
        print(f"[ContextRuntime] Delta detected: {delta}")
        self.handle_delta(delta)
        
    def handle_delta(self, delta: Dict) -> Dict:
        """
        Delta 이벤트 처리 (Idempotency 보장, Feature Flag 검사, Correlation ID 전파)
        
        Args:
            delta: 처리할 delta 이벤트
            
        Returns:
            처리 결과
        """
        # Feature Flag 검사
        if not self.is_feature_enabled("enable_drift_detection"):
            return {
                "success": False,
                "error": "Drift detection disabled by feature flag",
                "read_only_mode": self.config_verifier.read_only_mode
            }
        
        # Idempotency 키 생성
        conversation_id = delta.get("conversation_id", "default")
        turn_id = delta.get("turn_id", delta.get("ts", time.time()))
        idempotency_key = (conversation_id, turn_id)
        
        # 이미 처리된 이벤트인지 확인
        if idempotency_key in self.processed_events:
            print(f"[ContextRuntime] Duplicate event detected: {idempotency_key}")
            return {
                "success": False,
                "error": "Event already processed",
                "idempotency_key": idempotency_key
            }
        
        file_path = delta.get("path")
        if not file_path:
            return {"success": False, "error": "No file path in delta"}
        
        # Correlation ID 전파
        correlation_id = delta.get("correlation_id")
        if not correlation_id:
            correlation_id = self.event_log.propagate_correlation_id(delta)
        
        # 이벤트 로그 기록
        self.event_log.log_event(
            event_type="DELTA_PROCESSING",
            event_data={
                "file_path": file_path,
                "operation": delta.get("operation", "unknown"),
                "producer_actual": delta.get("producer_actual", "unknown"),
                "conversation_id": conversation_id,
                "turn_id": turn_id
            },
            correlation_id=correlation_id
        )
            
        # 카탈로그에서 파일 정보 조회
        catalog_info = {
            "producer_expected": self.data_catalog.get_expected_producer(file_path),
            "consumer_expected": self.data_catalog.get_expected_consumers(file_path),
            "update_interval": self.data_catalog.get_update_interval(file_path)
        }
        
        # 메모리 동기화
        sync_result = self.memory_sync.sync_delta(delta, catalog_info)
        
        if not sync_result["success"]:
            # 실패 이벤트 로그 기록
            self.event_log.log_event(
                event_type="SYNC_FAILURE",
                event_data={
                    "file_path": file_path,
                    "error": sync_result.get("error", "Unknown error"),
                    "sync_result": sync_result
                },
                correlation_id=correlation_id
            )
            return sync_result
            
        # Hash Chain에 추가 (Feature Flag 검사)
        if self.is_feature_enabled("enable_atomic_transactions"):
            chain_hash = self.hash_chain.add_block_atomic({
                "timestamp": delta.get("ts", time.time()),
                "delta": delta,
                "sync_result": sync_result,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "correlation_id": correlation_id
            })
        else:
            chain_hash = self.hash_chain.add_block({
                "timestamp": delta.get("ts", time.time()),
                "delta": delta,
                "sync_result": sync_result,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "correlation_id": correlation_id
            })
        
        # 카탈로그 상태 업데이트
        self.data_catalog.update_file_status(
            file_path, 
            delta.get("producer_actual", "unknown"),
            delta.get("ts", time.time())
        )
        
        # 통계 업데이트
        self.delta_count += 1
        self.last_delta_time = delta.get("ts", time.time())
        
        result = {
            "success": True,
            "file_path": file_path,
            "sync_result": sync_result,
            "chain_hash": chain_hash,
            "delta_count": self.delta_count,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
            "run_id": self.event_log.get_current_run_id(),
            "feature_flags": {
                "drift_detection": self.is_feature_enabled("enable_drift_detection"),
                "atomic_transactions": self.is_feature_enabled("enable_atomic_transactions"),
                "read_only_mode": self.config_verifier.read_only_mode
            }
        }
        
        # 성공 이벤트 로그 기록
        self.event_log.log_event(
            event_type="DELTA_SUCCESS",
            event_data={
                "file_path": file_path,
                "chain_hash": chain_hash,
                "delta_count": self.delta_count
            },
            correlation_id=correlation_id
        )
        
        # 처리된 이벤트로 기록
        self.processed_events.add(idempotency_key)
        self.event_store[idempotency_key] = result
        
        print(f"[ContextRuntime] Delta processed successfully: {file_path} (correlation_id: {correlation_id})")
        return result
        
    def check_drift_and_heal(self, delta: Dict) -> Dict:
        """
        Drift 감지 및 복원 수행
        
        Args:
            delta: 검사할 delta 이벤트
            
        Returns:
            drift 검사 및 복원 결과
        """
        file_path = delta.get("path")
        producer_actual = delta.get("producer_actual", "unknown")
        timestamp = delta.get("ts", time.time())
        
        # Drift 검사
        drift_result = self.data_catalog.check_drift(file_path, producer_actual, timestamp)
        
        if not drift_result["drift_detected"]:
            return {
                "drift_detected": False,
                "level": 0,
                "action": "none"
            }
            
        # Drift 레벨에 따른 처리
        level = drift_result["level"]
        
        if level == 1:
            # L1: 로그 기록만
            action = "log_only"
            success = True
            
        elif level == 2:
            # L2: 자동 병합 시도
            action = "auto_merge"
            success = self._attempt_auto_merge(file_path, delta)
            
        elif level == 3:
            # L3: 복원 + 쓰기 차단 + 격리 모드
            action = "restore_and_quarantine"
            success = self._perform_restore_and_quarantine(file_path, delta)
            
        else:
            action = "unknown"
            success = False
            
        result = {
            "drift_detected": True,
            "level": level,
            "action": action,
            "success": success,
            "drift_details": drift_result
        }
        
        print(f"[ContextRuntime] Drift check completed: Level={level}, Action={action}, Success={success}")
        return result
        
    def _attempt_auto_merge(self, file_path: str, _delta: Dict) -> bool:
        """
        자동 병합 시도
        
        Args:
            file_path: 파일 경로
            delta: delta 이벤트
            
        Returns:
            병합 성공 여부
        """
        try:
            # 간단한 병합 로직 (실제로는 더 복잡한 로직 필요)
            print(f"[ContextRuntime] Attempting auto merge for {file_path}")
            
            # 병합 성공으로 가정
            return True
            
        except Exception as e:
            print(f"[ContextRuntime] Auto merge failed: {e}")
            return False
            
    def _perform_restore_and_quarantine(self, file_path: str, _delta: Dict) -> bool:
        """
        복원 및 격리 수행
        
        Args:
            file_path: 파일 경로
            delta: delta 이벤트
            
        Returns:
            복원 및 격리 성공 여부
        """
        try:
            print(f"[ContextRuntime] Performing restore and quarantine for {file_path}")
            
            # 이전 상태로 복원 (실제로는 Hash Chain에서 이전 상태 조회)
            # 여기서는 간단히 성공으로 처리
            
            # 격리 모드 진입
            self._enter_quarantine_mode(file_path)
            
            return True
            
        except Exception as e:
            print(f"[ContextRuntime] Restore and quarantine failed: {e}")
            return False
            
    def _enter_quarantine_mode(self, file_path: str) -> None:
        """
        격리 모드 진입
        
        Args:
            file_path: 격리할 파일 경로
        """
        print(f"[ContextRuntime] Entering quarantine mode for {file_path}")
        # 실제 구현에서는 파일 접근 제한 등의 로직 필요
        
    def export_snapshot(self) -> str:
        """
        현재 상태의 스냅샷 생성 및 export
        
        Returns:
            생성된 스냅샷 파일 경로
        """
        # 최근 delta 이벤트 수집
        recent_deltas = []
        if hasattr(self.memory_sync, 'hash_chain'):
            recent_deltas = self.memory_sync.get_hash_chain(limit=10)
            
        # 카탈로그 요약 정보
        catalog_summary = self.data_catalog.get_catalog_summary()
        
        # 스냅샷 생성
        try:
            snapshot = self.snapshot_generator.generate_snapshot(
                memory_index=self.memory_sync.memory_index,
                hash_chain=self.hash_chain.chain,
                recent_deltas=recent_deltas,
                catalog_summary=catalog_summary
            )
        except Exception as e:
            print(f"[ContextRuntime] Snapshot generation failed: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # 스냅샷 저장
        snapshot_path = self.snapshot_generator.save_snapshot(snapshot)
        
        print(f"[ContextRuntime] Snapshot exported: {snapshot_path}")
        return snapshot_path
        
    def start_monitoring(self) -> None:
        """모니터링 시작"""
        if self.is_running:
            print("[ContextRuntime] Monitoring already running")
            return
            
        self.is_running = True
        self.io_probe.start_monitoring()
        
        print("[ContextRuntime] Monitoring started")
        
    def stop_monitoring(self) -> None:
        """모니터링 중지"""
        if not self.is_running:
            print("[ContextRuntime] Monitoring not running")
            return
            
        self.is_running = False
        self.io_probe.stop_monitoring()
        
        print("[ContextRuntime] Monitoring stopped")
        
    def get_runtime_status(self) -> Dict:
        """런타임 상태 조회"""
        return {
            "is_running": self.is_running,
            "delta_count": self.delta_count,
            "last_delta_time": self.last_delta_time,
            "memory_summary": self.memory_sync.get_memory_summary(),
            "catalog_summary": self.data_catalog.get_catalog_summary(),
            "chain_summary": self.hash_chain.get_chain_summary()
        }
        
    def simulate_workflow(self) -> Dict:
        """
        전체 워크플로우 시뮬레이션
        
        Returns:
            시뮬레이션 결과
        """
        print("[ContextRuntime] Starting workflow simulation...")
        
        # Step 1: Delta 이벤트 시뮬레이션
        delta = self.io_probe.simulate_delta(
            path="data/example.txt",
            operation="write",
            producer="module_A"
        )
        
        # Step 2: Delta 처리
        handle_result = self.handle_delta(delta)
        
        # Step 3: Drift 검사 및 복원
        drift_result = self.check_drift_and_heal(delta)
        
        # Step 4: 스냅샷 생성
        snapshot_path = self.export_snapshot()
        
        result = {
            "delta": delta,
            "handle_result": handle_result,
            "drift_result": drift_result,
            "snapshot_path": snapshot_path,
            "runtime_status": self.get_runtime_status()
        }
        
        print("[ContextRuntime] Workflow simulation completed")
        return result
