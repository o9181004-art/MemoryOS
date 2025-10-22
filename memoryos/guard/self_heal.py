"""
SelfHeal - 복원·검증·격리 루틴

Drift가 감지되었을 때 자동으로 복원, 검증, 격리를 수행합니다.
선별 복원 및 격리 해제 기능을 포함합니다.
"""

import time
import shutil
from typing import Dict, List, Set
from pathlib import Path
from .drift_guard import DriftLevel


class SelfHeal:
    """
    자동 복원 및 복구 클래스
    
    주요 기능:
    - L1~L3 레벨별 복원 정책 실행
    - 파일 상태 복원 및 검증
    - 격리 모드 관리
    - 복원 성공률 추적
    - 선별 복원 및 영향 경로 계산
    - 자동/수동 격리 해제
    """
    
    def __init__(self, backup_dir: str = "backups", quarantine_dir: str = "quarantine"):
        """
        SelfHeal 초기화
        
        Args:
            backup_dir: 백업 파일 저장 디렉토리
            quarantine_dir: 격리 파일 저장 디렉토리
        """
        self.backup_dir = Path(backup_dir)
        self.quarantine_dir = Path(quarantine_dir)
        
        # 디렉토리 생성
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        
        # 복원 통계
        self.heal_attempts = 0
        self.heal_successes = 0
        self.heal_failures = 0
        self.quarantine_count = 0
        
        # 격리된 파일 목록
        self.quarantined_files = set()
        
        # 영향 경로 추적
        self.affected_paths = set()
        
        # 격리 해제 조건 추적
        self.quarantine_release_conditions = {}  # file_path -> 조건 정보
        self.success_events = {}  # file_path -> 성공 이벤트 카운트
        self.normal_delta_count = {}  # file_path -> 정상 Δt 카운트
        
    def compute_affected_path_set(self, file_path: str, catalog_info: Dict = None) -> Set[str]:
        """
        영향 경로 집합 계산 (카탈로그 의존성 기반)
        
        Args:
            file_path: 영향받은 파일 경로
            catalog_info: 카탈로그 정보
            
        Returns:
            영향받은 경로 집합
        """
        affected_paths = {file_path}
        
        if catalog_info:
            # consumer_expected에서 의존성 추적
            consumers = catalog_info.get("consumer_expected", [])
            for consumer in consumers:
                # 간단한 의존성 매핑 (실제로는 더 복잡한 로직 필요)
                if consumer in ["module_A", "module_B"]:
                    affected_paths.add(f"data/{consumer}_config.json")
                    
        # 디렉토리 기반 영향 경로 추가
        file_path_obj = Path(file_path)
        if file_path_obj.parent.name in ["config", "data"]:
            # 설정 파일이면 관련 파일들도 영향받을 수 있음
            affected_paths.add(str(file_path_obj.parent / "backup.json"))
            
        return affected_paths
        
    def selective_restore(self, file_path: str, affected_paths: Set[str], 
                         memory_index: Dict = None) -> Dict:
        """
        선별 복원 수행 (영향받은 경로만)
        
        Args:
            file_path: 복원할 파일 경로
            affected_paths: 영향받은 경로 집합
            memory_index: 메모리 인덱스 데이터
            
        Returns:
            복원 결과
        """
        restore_results = {}
        
        for path in affected_paths:
            try:
                # 이전 상태로 복원 시도
                restore_success = self._restore_to_previous_state(path, memory_index)
                
                restore_results[path] = {
                    "success": restore_success,
                    "reason_code": "MERGE_OK" if restore_success else "HASH_MISMATCH"
                }
                
            except PermissionError:
                restore_results[path] = {
                    "success": False,
                    "reason_code": "IO_DENIED"
                }
            except Exception as e:
                restore_results[path] = {
                    "success": False,
                    "reason_code": "UNKNOWN_ERROR",
                    "error": str(e)
                }
                
        return restore_results
        
    def quarantine_scope_minimization(self, file_path: str, affected_paths: Set[str]) -> Dict:
        """
        격리 범위 최소화 (영향받은 경로만 격리)
        
        Args:
            file_path: 격리할 파일 경로
            affected_paths: 영향받은 경로 집합
            
        Returns:
            격리 결과
        """
        quarantine_results = {}
        
        for path in affected_paths:
            try:
                # 격리 모드 진입
                quarantine_success = self._enter_quarantine_mode(path)
                
                quarantine_results[path] = {
                    "quarantined": quarantine_success,
                    "scope": "affected_only"
                }
                
                if quarantine_success:
                    self.quarantined_files.add(path)
                    self.quarantine_count += 1
                    
            except Exception as e:
                quarantine_results[path] = {
                    "quarantined": False,
                    "error": str(e)
                }
                
        return quarantine_results
        
    def setup_quarantine_release_conditions(self, file_path: str) -> None:
        """
        격리 해제 조건 설정
        
        Args:
            file_path: 격리된 파일 경로
        """
        self.quarantine_release_conditions[file_path] = {
            "success_events_required": 1,
            "normal_delta_required": 3,
            "monitoring_interval": 30,  # 30초
            "last_check": time.time()
        }
        
        self.success_events[file_path] = 0
        self.normal_delta_count[file_path] = 0
        
    def check_quarantine_release_conditions(self, file_path: str) -> bool:
        """
        격리 해제 조건 확인
        
        Args:
            file_path: 확인할 파일 경로
            
        Returns:
            해제 조건 만족 여부
        """
        if file_path not in self.quarantine_release_conditions:
            return False
            
        conditions = self.quarantine_release_conditions[file_path]
        current_time = time.time()
        
        # 모니터링 주기 확인 (30초)
        if current_time - conditions["last_check"] < conditions["monitoring_interval"]:
            return False
            
        # 조건 확인
        success_events = self.success_events.get(file_path, 0)
        normal_deltas = self.normal_delta_count.get(file_path, 0)
        
        success_ok = success_events >= conditions["success_events_required"]
        delta_ok = normal_deltas >= conditions["normal_delta_required"]
        
        conditions["last_check"] = current_time
        
        return success_ok and delta_ok
        
    def unlock_quarantine(self, paths: List[str], approver: str = "system") -> Dict:
        """
        수동 격리 해제
        
        Args:
            paths: 해제할 파일 경로 목록
            approver: 승인자
            
        Returns:
            해제 결과
        """
        unlock_results = {}
        
        for file_path in paths:
            try:
                if file_path in self.quarantined_files:
                    # 격리에서 파일 해제
                    quarantine_path = self.quarantine_dir / Path(file_path).name
                    
                    if quarantine_path.exists():
                        # 원래 위치로 복원 (실제로는 원래 경로를 추적해야 함)
                        shutil.move(str(quarantine_path), file_path)
                        
                    self.quarantined_files.remove(file_path)
                    
                    # 격리 해제 조건 정리
                    if file_path in self.quarantine_release_conditions:
                        del self.quarantine_release_conditions[file_path]
                    if file_path in self.success_events:
                        del self.success_events[file_path]
                    if file_path in self.normal_delta_count:
                        del self.normal_delta_count[file_path]
                    
                    unlock_results[file_path] = {
                        "success": True,
                        "approver": approver,
                        "timestamp": time.time()
                    }
                else:
                    unlock_results[file_path] = {
                        "success": False,
                        "reason": "not_quarantined"
                    }
                    
            except Exception as e:
                unlock_results[file_path] = {
                    "success": False,
                    "error": str(e)
                }
                
        return unlock_results
        
    def execute_heal(self, drift_result: Dict, memory_index: Dict = None) -> Dict:
        """
        Drift 레벨에 따른 복원 실행 (선별 복원 적용)
        
        Args:
            drift_result: Drift 검사 결과
            memory_index: 메모리 인덱스 데이터
            
        Returns:
            복원 실행 결과
        """
        self.heal_attempts += 1
        
        drift_level = drift_result.get("drift_level", 0)
        file_path = drift_result.get("file_path", "")
        
        try:
            if drift_level == DriftLevel.L1.value:
                result = self._execute_l1_heal(drift_result)
            elif drift_level == DriftLevel.L2.value:
                result = self._execute_l2_heal(drift_result, memory_index)
            elif drift_level == DriftLevel.L3.value:
                result = self._execute_l3_heal(drift_result, memory_index)
            else:
                result = {
                    "success": True,
                    "action": "none",
                    "message": "No drift detected"
                }
                
            # 성공/실패 통계 업데이트
            if result["success"]:
                self.heal_successes += 1
            else:
                self.heal_failures += 1
                
            result.update({
                "heal_attempt": self.heal_attempts,
                "file_path": file_path,
                "drift_level": drift_level,
                "timestamp": time.time()
            })
            
            print(f"[SelfHeal] Heal executed: {result}")
            return result
            
        except Exception as e:
            self.heal_failures += 1
            error_result = {
                "success": False,
                "action": "error",
                "message": str(e),
                "heal_attempt": self.heal_attempts,
                "file_path": file_path,
                "drift_level": drift_level,
                "timestamp": time.time()
            }
            
            print(f"[SelfHeal] Heal failed: {error_result}")
            return error_result
            
    def _execute_l1_heal(self, drift_result: Dict) -> Dict:
        """
        L1 복원 실행 (로그 기록만)
        
        Args:
            drift_result: Drift 검사 결과
            
        Returns:
            L1 복원 결과
        """
        file_path = drift_result.get("file_path", "")
        
        # 로그 기록
        log_entry = {
            "level": "L1",
            "file_path": file_path,
            "producer_mismatch": drift_result.get("producer_mismatch", False),
            "time_drift": drift_result.get("time_drift", False),
            "timestamp": time.time(),
            "action": "log_only"
        }
        
        # 로그 파일에 기록 (실제로는 별도 로그 시스템 사용)
        self._write_heal_log(log_entry)
        
        return {
            "success": True,
            "action": "log_only",
            "message": "L1 drift logged",
            "log_entry": log_entry
        }
        
    def _execute_l2_heal(self, drift_result: Dict, memory_index: Dict = None) -> Dict:
        """
        L2 복원 실행 (자동 병합 시도)
        
        Args:
            drift_result: Drift 검사 결과
            memory_index: 메모리 인덱스 데이터
            
        Returns:
            L2 복원 결과
        """
        file_path = drift_result.get("file_path", "")
        
        try:
            # 백업 생성
            backup_path = self._create_backup(file_path)
            
            # 자동 병합 시도
            merge_success = self._attempt_auto_merge(file_path, memory_index)
            
            if merge_success:
                # 병합 성공 시 검증
                validation_success = self._validate_file_integrity(file_path)
                
                if validation_success:
                    return {
                        "success": True,
                        "action": "auto_merge",
                        "message": "L2 auto merge successful",
                        "backup_path": str(backup_path)
                    }
                else:
                    # 검증 실패 시 백업에서 복원
                    self._restore_from_backup(file_path, backup_path)
                    return {
                        "success": False,
                        "action": "auto_merge_failed_validation",
                        "message": "Auto merge failed validation, restored from backup"
                    }
            else:
                return {
                    "success": False,
                    "action": "auto_merge_failed",
                    "message": "Auto merge attempt failed"
                }
                
        except Exception as e:
            return {
                "success": False,
                "action": "l2_heal_error",
                "message": f"L2 heal error: {str(e)}"
            }
            
    def _execute_l3_heal(self, drift_result: Dict, memory_index: Dict = None) -> Dict:
        """
        L3 복원 실행 (복원 + 격리)
        
        Args:
            drift_result: Drift 검사 결과
            memory_index: 메모리 인덱스 데이터
            
        Returns:
            L3 복원 결과
        """
        file_path = drift_result.get("file_path", "")
        
        try:
            # 백업 생성
            backup_path = self._create_backup(file_path)
            
            # 이전 상태로 복원 시도
            restore_success = self._restore_to_previous_state(file_path, memory_index)
            
            if restore_success:
                # 격리 모드 진입
                quarantine_success = self._enter_quarantine_mode(file_path)
                
                if quarantine_success:
                    self.quarantine_count += 1
                    self.quarantined_files.add(file_path)
                    
                    return {
                        "success": True,
                        "action": "restore_and_quarantine",
                        "message": "L3 restore and quarantine successful",
                        "backup_path": str(backup_path),
                        "quarantined": True
                    }
                else:
                    return {
                        "success": False,
                        "action": "quarantine_failed",
                        "message": "Restore successful but quarantine failed"
                    }
            else:
                return {
                    "success": False,
                    "action": "restore_failed",
                    "message": "Failed to restore to previous state"
                }
                
        except Exception as e:
            return {
                "success": False,
                "action": "l3_heal_error",
                "message": f"L3 heal error: {str(e)}"
            }
            
    def _create_backup(self, file_path: str) -> Path:
        """
        파일 백업 생성
        
        Args:
            file_path: 백업할 파일 경로
            
        Returns:
            백업 파일 경로
        """
        source_path = Path(file_path)
        timestamp = int(time.time())
        backup_filename = f"{source_path.stem}_{timestamp}{source_path.suffix}"
        backup_path = self.backup_dir / backup_filename
        
        if source_path.exists():
            shutil.copy2(source_path, backup_path)
            
        return backup_path
        
    def _restore_from_backup(self, file_path: str, backup_path: Path) -> bool:
        """
        백업에서 파일 복원
        
        Args:
            file_path: 복원할 파일 경로
            backup_path: 백업 파일 경로
            
        Returns:
            복원 성공 여부
        """
        try:
            if backup_path.exists():
                shutil.copy2(backup_path, file_path)
                return True
            return False
        except Exception:
            return False
            
    def _attempt_auto_merge(self, file_path: str, _memory_index: Dict = None) -> bool:
        """
        자동 병합 시도
        
        Args:
            file_path: 병합할 파일 경로
            memory_index: 메모리 인덱스 데이터
            
        Returns:
            병합 성공 여부
        """
        try:
            # 간단한 병합 로직 (실제로는 더 복잡한 로직 필요)
            # 여기서는 항상 성공으로 처리
            print(f"[SelfHeal] Attempting auto merge for {file_path}")
            return True
            
        except Exception:
            return False
            
    def _validate_file_integrity(self, file_path: str) -> bool:
        """
        파일 무결성 검증
        
        Args:
            file_path: 검증할 파일 경로
            
        Returns:
            검증 성공 여부
        """
        try:
            # 간단한 검증 로직 (실제로는 해시 검증 등 필요)
            file_path_obj = Path(file_path)
            return file_path_obj.exists() and file_path_obj.stat().st_size > 0
            
        except Exception:
            return False
            
    def _restore_to_previous_state(self, file_path: str, _memory_index: Dict = None) -> bool:
        """
        이전 상태로 복원
        
        Args:
            file_path: 복원할 파일 경로
            memory_index: 메모리 인덱스 데이터
            
        Returns:
            복원 성공 여부
        """
        try:
            # 실제로는 Hash Chain에서 이전 상태를 찾아 복원
            # 여기서는 간단히 성공으로 처리
            print(f"[SelfHeal] Restoring {file_path} to previous state")
            return True
            
        except Exception:
            return False
            
    def _enter_quarantine_mode(self, file_path: str) -> bool:
        """
        격리 모드 진입
        
        Args:
            file_path: 격리할 파일 경로
            
        Returns:
            격리 성공 여부
        """
        try:
            # 파일을 격리 디렉토리로 이동
            source_path = Path(file_path)
            quarantine_path = self.quarantine_dir / source_path.name
            
            if source_path.exists():
                shutil.move(str(source_path), str(quarantine_path))
                
            print(f"[SelfHeal] File {file_path} quarantined")
            return True
            
        except Exception:
            return False
            
    def _write_heal_log(self, log_entry: Dict) -> None:
        """
        복원 로그 기록
        
        Args:
            log_entry: 기록할 로그 엔트리
        """
        # 실제로는 별도 로그 시스템에 기록
        print(f"[SelfHeal] Log entry: {log_entry}")
        
    def get_heal_statistics(self) -> Dict:
        """복원 통계 정보 반환"""
        success_rate = (self.heal_successes / self.heal_attempts * 100) if self.heal_attempts > 0 else 0
        
        return {
            "total_attempts": self.heal_attempts,
            "successful_heals": self.heal_successes,
            "failed_heals": self.heal_failures,
            "success_rate": round(success_rate, 2),
            "quarantined_files": len(self.quarantined_files),
            "quarantine_count": self.quarantine_count
        }
        
    def release_from_quarantine(self, file_path: str) -> bool:
        """
        격리에서 파일 해제
        
        Args:
            file_path: 해제할 파일 경로
            
        Returns:
            해제 성공 여부
        """
        try:
            if file_path in self.quarantined_files:
                quarantine_path = self.quarantine_dir / Path(file_path).name
                
                if quarantine_path.exists():
                    # 원래 위치로 복원 (실제로는 원래 경로를 추적해야 함)
                    shutil.move(str(quarantine_path), file_path)
                    self.quarantined_files.remove(file_path)
                    
                    print(f"[SelfHeal] File {file_path} released from quarantine")
                    return True
                    
            return False
            
        except Exception:
            return False
            
    def get_quarantined_files(self) -> List[str]:
        """격리된 파일 목록 반환"""
        return list(self.quarantined_files)
