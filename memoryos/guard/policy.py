"""
Policy - 복구정책 레벨 및 임계값 관리

Drift 복구 정책과 임계값을 관리합니다.
"""

from typing import Dict, List
from enum import Enum
import json
from pathlib import Path


class PolicyType(Enum):
    """정책 유형 정의"""
    LOG_ONLY = "log_only"
    AUTO_MERGE = "auto_merge"
    RESTORE_QUARANTINE = "restore_quarantine"
    CUSTOM = "custom"


class PolicyLevel(Enum):
    """정책 레벨 정의"""
    L1 = 1
    L2 = 2
    L3 = 3


class Policy:
    """
    복구 정책 관리 클래스
    
    주요 기능:
    - Drift 레벨별 정책 정의
    - 임계값 설정 및 관리
    - 정책 실행 조건 검사
    - 정책 성능 모니터링
    """
    
    def __init__(self, policy_file: str = "config/policy.json"):
        """
        Policy 초기화
        
        Args:
            policy_file: 정책 설정 파일 경로
        """
        self.policy_file = policy_file
        self.policies = self._load_policies()
        self.execution_history = []
        
    def _load_policies(self) -> Dict:
        """정책 설정 로드"""
        try:
            policy_path = Path(self.policy_file)
            if policy_path.exists():
                with open(policy_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
            
        # 기본 정책 설정
        return {
            "thresholds": {
                "l1_threshold": 30,    # 30초
                "l2_threshold": 300,   # 5분
                "l3_threshold": 1800   # 30분
            },
            "policies": {
                "L1": {
                    "type": "log_only",
                    "enabled": True,
                    "actions": ["log", "notify"],
                    "parameters": {
                        "log_level": "info",
                        "notification_channels": ["console"]
                    }
                },
                "L2": {
                    "type": "auto_merge",
                    "enabled": True,
                    "actions": ["backup", "merge", "validate"],
                    "parameters": {
                        "backup_retention_days": 7,
                        "merge_strategy": "last_write_wins",
                        "validation_checks": ["hash", "size", "permissions"]
                    }
                },
                "L3": {
                    "type": "restore_quarantine",
                    "enabled": True,
                    "actions": ["backup", "restore", "quarantine", "notify"],
                    "parameters": {
                        "backup_retention_days": 30,
                        "quarantine_duration_hours": 24,
                        "notification_channels": ["console", "email"],
                        "restore_strategy": "previous_version"
                    }
                }
            },
            "global_settings": {
                "max_heal_attempts": 3,
                "heal_cooldown_seconds": 60,
                "enable_quarantine": True,
                "enable_backup": True
            }
        }
        
    def _save_policies(self) -> None:
        """정책 설정 저장"""
        try:
            policy_path = Path(self.policy_file)
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(policy_path, 'w', encoding='utf-8') as f:
                json.dump(self.policies, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Policy] Failed to save policies: {e}")
            
    def get_policy_for_level(self, level: int) -> Dict:
        """
        특정 레벨의 정책 조회
        
        Args:
            level: 정책 레벨 (1, 2, 3)
            
        Returns:
            해당 레벨의 정책 설정
        """
        level_key = f"L{level}"
        return self.policies.get("policies", {}).get(level_key, {})
        
    def get_threshold_for_level(self, level: int) -> int:
        """
        특정 레벨의 임계값 조회
        
        Args:
            level: 레벨 (1, 2, 3)
            
        Returns:
            해당 레벨의 임계값 (초)
        """
        threshold_key = f"l{level}_threshold"
        return self.policies.get("thresholds", {}).get(threshold_key, 30)
        
    def update_threshold(self, level: int, threshold: int) -> None:
        """
        특정 레벨의 임계값 업데이트
        
        Args:
            level: 레벨 (1, 2, 3)
            threshold: 새로운 임계값 (초)
        """
        threshold_key = f"l{level}_threshold"
        self.policies["thresholds"][threshold_key] = threshold
        self._save_policies()
        
        print(f"[Policy] Updated L{level} threshold to {threshold} seconds")
        
    def update_policy(self, level: int, policy_config: Dict) -> None:
        """
        특정 레벨의 정책 업데이트
        
        Args:
            level: 레벨 (1, 2, 3)
            policy_config: 새로운 정책 설정
        """
        level_key = f"L{level}"
        self.policies["policies"][level_key] = policy_config
        self._save_policies()
        
        print(f"[Policy] Updated L{level} policy configuration")
        
    def is_policy_enabled(self, level: int) -> bool:
        """
        특정 레벨의 정책 활성화 여부 확인
        
        Args:
            level: 레벨 (1, 2, 3)
            
        Returns:
            정책 활성화 여부
        """
        policy = self.get_policy_for_level(level)
        return policy.get("enabled", True)
        
    def get_policy_actions(self, level: int) -> List[str]:
        """
        특정 레벨의 정책 액션 목록 조회
        
        Args:
            level: 레벨 (1, 2, 3)
            
        Returns:
            액션 목록
        """
        policy = self.get_policy_for_level(level)
        return policy.get("actions", [])
        
    def get_policy_parameters(self, level: int) -> Dict:
        """
        특정 레벨의 정책 파라미터 조회
        
        Args:
            level: 레벨 (1, 2, 3)
            
        Returns:
            파라미터 딕셔너리
        """
        policy = self.get_policy_for_level(level)
        return policy.get("parameters", {})
        
    def should_execute_policy(self, level: int, file_path: str, 
                            recent_attempts: int = 0) -> bool:
        """
        정책 실행 여부 결정
        
        Args:
            level: 레벨 (1, 2, 3)
            file_path: 파일 경로
            recent_attempts: 최근 시도 횟수
            
        Returns:
            정책 실행 여부
        """
        # 정책 활성화 여부 확인
        if not self.is_policy_enabled(level):
            return False
            
        # 최대 시도 횟수 확인
        max_attempts = self.policies.get("global_settings", {}).get("max_heal_attempts", 3)
        if recent_attempts >= max_attempts:
            return False
            
        # 쿨다운 확인
        cooldown_seconds = self.policies.get("global_settings", {}).get("heal_cooldown_seconds", 60)
        if self._is_in_cooldown(file_path, cooldown_seconds):
            return False
            
        return True
        
    def _is_in_cooldown(self, file_path: str, cooldown_seconds: int) -> bool:
        """
        쿨다운 상태 확인
        
        Args:
            file_path: 파일 경로
            cooldown_seconds: 쿨다운 시간 (초)
            
        Returns:
            쿨다운 상태 여부
        """
        import time
        current_time = time.time()
        
        # 최근 실행 이력에서 해당 파일의 마지막 실행 시간 확인
        for entry in reversed(self.execution_history):
            if entry.get("file_path") == file_path:
                last_execution = entry.get("timestamp", 0)
                return (current_time - last_execution) < cooldown_seconds
                
        return False
        
    def record_policy_execution(self, level: int, file_path: str, 
                              success: bool, details: Dict = None) -> None:
        """
        정책 실행 기록
        
        Args:
            level: 레벨 (1, 2, 3)
            file_path: 파일 경로
            success: 실행 성공 여부
            details: 추가 세부사항
        """
        import time
        
        execution_record = {
            "timestamp": time.time(),
            "level": level,
            "file_path": file_path,
            "success": success,
            "details": details or {}
        }
        
        self.execution_history.append(execution_record)
        
        # 히스토리 크기 제한 (최근 1000개만 유지)
        if len(self.execution_history) > 1000:
            self.execution_history = self.execution_history[-1000:]
            
    def get_execution_statistics(self) -> Dict:
        """정책 실행 통계 조회"""
        total_executions = len(self.execution_history)
        successful_executions = sum(1 for entry in self.execution_history if entry["success"])
        
        # 레벨별 통계
        level_stats = {}
        for level in [1, 2, 3]:
            level_executions = [entry for entry in self.execution_history if entry["level"] == level]
            level_successful = sum(1 for entry in level_executions if entry["success"])
            
            level_stats[f"L{level}"] = {
                "total": len(level_executions),
                "successful": level_successful,
                "success_rate": (level_successful / len(level_executions) * 100) if level_executions else 0
            }
            
        return {
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "overall_success_rate": (successful_executions / total_executions * 100) if total_executions else 0,
            "level_statistics": level_stats,
            "recent_executions": self.execution_history[-10:] if self.execution_history else []
        }
        
    def get_policy_summary(self) -> Dict:
        """정책 요약 정보 반환"""
        return {
            "thresholds": self.policies.get("thresholds", {}),
            "enabled_policies": {
                f"L{level}": self.is_policy_enabled(level) 
                for level in [1, 2, 3]
            },
            "global_settings": self.policies.get("global_settings", {}),
            "execution_stats": self.get_execution_statistics()
        }
        
    def reset_policies_to_default(self) -> None:
        """정책을 기본값으로 초기화"""
        self.policies = self._load_policies()  # 기본 정책 다시 로드
        self.execution_history = []
        self._save_policies()
        
        print("[Policy] Policies reset to default values")
        
    def export_policy_config(self) -> Dict:
        """현재 정책 설정 내보내기"""
        import time
        return {
            "exported_at": time.time(),
            "policies": self.policies,
            "execution_history": self.execution_history[-100:],  # 최근 100개만
            "statistics": self.get_execution_statistics()
        }
