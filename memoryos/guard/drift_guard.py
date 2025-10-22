"""
DriftGuard - producer_actual vs expected 비교, L1~L3 결정

예상된 상태와 실제 상태를 비교하여 drift를 감지하고 레벨을 결정합니다.
자기적응 임계값과 producer 신뢰도 스코어링을 포함합니다.
"""

import time
import statistics
from typing import Dict, List
from enum import Enum
from collections import deque


class DriftLevel(Enum):
    """Drift 레벨 정의"""
    NONE = 0
    L1 = 1  # 경미한 drift - 로그 기록만
    L2 = 2  # 중간 drift - 자동 병합 시도
    L3 = 3  # 심각한 drift - 복원 + 격리


class DriftGuard:
    """
    Drift 감지 및 레벨 결정 클래스
    
    주요 기능:
    - producer_actual vs expected 비교
    - 시간 기반 staleness 검사
    - Drift 레벨 결정 (L1~L3)
    - 임계값 기반 분류
    - 자기적응 임계값 계산 (EMA + 백분위수)
    - Producer 신뢰도 스코어링
    """
    
    def __init__(self, thresholds: Dict = None):
        """
        DriftGuard 초기화
        
        Args:
            thresholds: drift 임계값 설정
        """
        self.thresholds = thresholds or {
            "l1_threshold": 30,    # 30초
            "l2_threshold": 300,   # 5분
            "l3_threshold": 1800   # 30분
        }
        
        # 자기적응 임계값을 위한 데이터 수집
        self.delta_times = deque(maxlen=1000)  # 최근 1000개 Δt 값
        self.producer_trust_scores = {}  # producer별 신뢰도 점수
        
        # EMA 파라미터
        self.ema_alpha = 0.1  # EMA 스무딩 팩터
        self.ema_delta_t = 0.0  # 현재 EMA 값
        
        # 백분위수 파라미터
        self.percentile_threshold = 95  # P95 사용
        
        # 워밍업 설정
        self.warmup_samples = 30  # 워밍업 샘플 수
        self.is_warmed_up = False
        
        # 통계 정보
        self.drift_history = []
        self.total_checks = 0
        self.drift_counts = {level.value: 0 for level in DriftLevel}
        
    def record_delta_time(self, delta_t: float) -> None:
        """
        Delta 시간 기록 및 EMA 업데이트
        
        Args:
            delta_t: Delta 시간 (초)
        """
        self.delta_times.append(delta_t)
        
        # EMA 업데이트
        if len(self.delta_times) == 1:
            self.ema_delta_t = delta_t
        else:
            self.ema_delta_t = self.ema_alpha * delta_t + (1 - self.ema_alpha) * self.ema_delta_t
            
        # 워밍업 상태 확인
        if len(self.delta_times) >= self.warmup_samples:
            self.is_warmed_up = True
            
    def calculate_adaptive_threshold(self) -> float:
        """
        자기적응 임계값 계산 (EMA + 백분위수 하이브리드)
        
        Returns:
            계산된 임계값 (초)
        """
        if not self.is_warmed_up:
            # 워밍업 구간에서는 보수적 상수값 사용
            return self.thresholds["l1_threshold"]
            
        if len(self.delta_times) < 2:
            return self.thresholds["l1_threshold"]
            
        # EMA 기반 임계값
        ema_threshold = self.ema_delta_t * 2.0  # EMA의 2배
        
        # 백분위수 기반 임계값
        percentile_value = statistics.quantiles(self.delta_times, n=100)[self.percentile_threshold - 1]
        percentile_threshold = percentile_value * 1.5  # P95의 1.5배
        
        # 하이브리드 임계값: max(EMA*α, P95*β)
        adaptive_threshold = max(ema_threshold, percentile_threshold)
        
        # 최소/최대 제한
        min_threshold = self.thresholds["l1_threshold"]
        max_threshold = self.thresholds["l3_threshold"]
        
        return max(min_threshold, min(adaptive_threshold, max_threshold))
        
    def calculate_producer_trust_score(self, producer_actual: str, 
                                     file_path: str = None) -> float:
        """
        Producer 신뢰도 점수 계산
        
        Args:
            producer_actual: 실제 producer
            file_path: 파일 경로 (선택사항)
            
        Returns:
            신뢰도 점수 (0.0 ~ 1.0)
        """
        if producer_actual not in self.producer_trust_scores:
            # 새로운 producer는 기본 신뢰도
            self.producer_trust_scores[producer_actual] = {
                "score": 0.5,
                "success_count": 0,
                "failure_count": 0,
                "last_seen": time.time()
            }
            
        trust_data = self.producer_trust_scores[producer_actual]
        
        # 기본 신뢰도 계산 (성공률 기반)
        total_attempts = trust_data["success_count"] + trust_data["failure_count"]
        if total_attempts > 0:
            success_rate = trust_data["success_count"] / total_attempts
        else:
            success_rate = 0.5  # 기본값
            
        # 시간 기반 감쇠 (오래된 producer는 신뢰도 감소)
        time_since_last_seen = time.time() - trust_data["last_seen"]
        time_decay = max(0.1, 1.0 - (time_since_last_seen / 3600))  # 1시간 기준
        
        # 최종 신뢰도 점수
        trust_score = success_rate * time_decay
        
        # 신뢰도 업데이트
        trust_data["score"] = trust_score
        trust_data["last_seen"] = time.time()
        
        return trust_score
        
    def update_producer_trust(self, producer_actual: str, success: bool) -> None:
        """
        Producer 신뢰도 업데이트
        
        Args:
            producer_actual: 실제 producer
            success: 성공 여부
        """
        if producer_actual not in self.producer_trust_scores:
            self.producer_trust_scores[producer_actual] = {
                "score": 0.5,
                "success_count": 0,
                "failure_count": 0,
                "last_seen": time.time()
            }
            
        trust_data = self.producer_trust_scores[producer_actual]
        
        if success:
            trust_data["success_count"] += 1
        else:
            trust_data["failure_count"] += 1
            
        # 신뢰도 점수 재계산
        self.calculate_producer_trust_score(producer_actual)
        
    def check_drift(self, file_path: str, producer_actual: str, 
                   producer_expected: str, last_updated: float,
                   update_interval: int = 30) -> Dict:
        """
        Drift 검사 수행 (자기적응 임계값 및 producer 신뢰도 반영)
        
        Args:
            file_path: 파일 경로
            producer_actual: 실제 생산자
            producer_expected: 예상 생산자
            last_updated: 마지막 업데이트 시간
            update_interval: 예상 업데이트 주기
            
        Returns:
            Drift 검사 결과
        """
        self.total_checks += 1
        current_time = time.time()
        
        # Delta 시간 계산 및 기록
        delta_t = current_time - last_updated if last_updated > 0 else float('inf')
        self.record_delta_time(delta_t)
        
        # 생산자 불일치 검사
        producer_mismatch = producer_actual != producer_expected
        
        # Producer 신뢰도 점수 계산
        trust_score = self.calculate_producer_trust_score(producer_actual, file_path)
        
        # 자기적응 임계값 계산
        adaptive_threshold = self.calculate_adaptive_threshold()
        
        # 시간 기반 staleness 검사 (신뢰도 반영)
        trust_adjusted_threshold = adaptive_threshold * (2.0 - trust_score)  # 신뢰도가 낮을수록 엄격
        time_drift = delta_t > trust_adjusted_threshold
        
        # Drift 레벨 결정 (신뢰도 반영)
        drift_level = self._determine_drift_level_adaptive(
            producer_mismatch, time_drift, delta_t, trust_score, adaptive_threshold
        )
        
        # 결과 구성
        result = {
            "file_path": file_path,
            "drift_detected": drift_level != DriftLevel.NONE,
            "drift_level": drift_level.value,
            "drift_level_name": drift_level.name,
            "producer_mismatch": producer_mismatch,
            "time_drift": time_drift,
            "time_since_update": delta_t,
            "producer_expected": producer_expected,
            "producer_actual": producer_actual,
            "trust_score": trust_score,
            "adaptive_threshold": adaptive_threshold,
            "trust_adjusted_threshold": trust_adjusted_threshold,
            "timestamp": current_time,
            "recommended_action": self._get_recommended_action(drift_level)
        }
        
        # 통계 업데이트
        self.drift_counts[drift_level.value] += 1
        self.drift_history.append(result)
        
        # 히스토리 크기 제한 (최근 1000개만 유지)
        if len(self.drift_history) > 1000:
            self.drift_history = self.drift_history[-1000:]
            
        return result
        
    def _determine_drift_level_adaptive(self, producer_mismatch: bool, 
                                      time_drift: bool, delta_t: float,
                                      trust_score: float, adaptive_threshold: float) -> DriftLevel:
        """
        신뢰도와 자기적응 임계값을 반영한 Drift 레벨 결정
        
        Args:
            producer_mismatch: 생산자 불일치 여부
            time_drift: 시간 drift 여부
            delta_t: 마지막 업데이트로부터 경과 시간
            trust_score: producer 신뢰도 점수
            adaptive_threshold: 자기적응 임계값
            
        Returns:
            결정된 drift 레벨
        """
        # 신뢰도가 낮은 producer는 더 엄격하게 판정
        trust_multiplier = 2.0 - trust_score  # 신뢰도 0.5 → 1.5배, 신뢰도 1.0 → 1.0배
        
        # 심각한 조건들 (L3)
        l3_threshold = self.thresholds["l3_threshold"] * trust_multiplier
        if producer_mismatch and delta_t > l3_threshold:
            return DriftLevel.L3
            
        # 중간 조건들 (L2)
        l2_threshold = self.thresholds["l2_threshold"] * trust_multiplier
        if (producer_mismatch and time_drift) or delta_t > l2_threshold:
            return DriftLevel.L2
            
        # 경미한 조건들 (L1)
        l1_threshold = adaptive_threshold * trust_multiplier
        if producer_mismatch or delta_t > l1_threshold:
            return DriftLevel.L1
            
        # 드리프트 없음
        return DriftLevel.NONE
        """
        Drift 레벨 결정
        
        Args:
            producer_mismatch: 생산자 불일치 여부
            time_drift: 시간 drift 여부
            time_since_update: 마지막 업데이트로부터 경과 시간
            
        Returns:
            결정된 drift 레벨
        """
        # 심각한 조건들 (L3)
        if producer_mismatch and time_since_update > self.thresholds["l3_threshold"]:
            return DriftLevel.L3
            
        # 중간 조건들 (L2)
        if (producer_mismatch and time_drift) or time_since_update > self.thresholds["l2_threshold"]:
            return DriftLevel.L2
            
        # 경미한 조건들 (L1)
        if producer_mismatch or time_drift:
            return DriftLevel.L1
            
        # 드리프트 없음
        return DriftLevel.NONE
        
    def _get_recommended_action(self, drift_level: DriftLevel) -> str:
        """
        Drift 레벨에 따른 권장 액션 반환
        
        Args:
            drift_level: Drift 레벨
            
        Returns:
            권장 액션
        """
        action_map = {
            DriftLevel.NONE: "none",
            DriftLevel.L1: "log_only",
            DriftLevel.L2: "auto_merge",
            DriftLevel.L3: "restore_and_quarantine"
        }
        
        return action_map.get(drift_level, "unknown")
        
    def batch_check_drift(self, files_info: List[Dict]) -> List[Dict]:
        """
        여러 파일에 대한 일괄 drift 검사
        
        Args:
            files_info: 파일 정보 목록
            
        Returns:
            각 파일의 drift 검사 결과 목록
        """
        results = []
        
        for file_info in files_info:
            result = self.check_drift(
                file_path=file_info.get("path", ""),
                producer_actual=file_info.get("producer_actual", "unknown"),
                producer_expected=file_info.get("producer_expected", "unknown"),
                last_updated=file_info.get("last_updated", 0),
                update_interval=file_info.get("update_interval", 30)
            )
            results.append(result)
            
        return results
        
    def get_drift_statistics(self) -> Dict:
        """Drift 통계 정보 반환"""
        total_drifts = sum(self.drift_counts.values()) - self.drift_counts[DriftLevel.NONE.value]
        
        return {
            "total_checks": self.total_checks,
            "total_drifts": total_drifts,
            "drift_rate": total_drifts / self.total_checks if self.total_checks > 0 else 0,
            "drift_counts": self.drift_counts,
            "recent_drifts": self.drift_history[-10:] if self.drift_history else [],
            "thresholds": self.thresholds
        }
        
    def get_files_by_drift_level(self, drift_level: DriftLevel) -> List[Dict]:
        """
        특정 drift 레벨의 파일들 조회
        
        Args:
            drift_level: 조회할 drift 레벨
            
        Returns:
            해당 레벨의 파일 목록
        """
        return [
            drift for drift in self.drift_history 
            if drift["drift_level"] == drift_level.value
        ]
        
    def update_thresholds(self, new_thresholds: Dict) -> None:
        """
        임계값 업데이트
        
        Args:
            new_thresholds: 새로운 임계값 설정
        """
        self.thresholds.update(new_thresholds)
        print(f"[DriftGuard] Thresholds updated: {self.thresholds}")
        
    def reset_statistics(self) -> None:
        """통계 정보 초기화"""
        self.drift_history = []
        self.total_checks = 0
        self.drift_counts = {level.value: 0 for level in DriftLevel}
        print("[DriftGuard] Statistics reset")
        
    def export_drift_report(self) -> Dict:
        """Drift 보고서 생성"""
        stats = self.get_drift_statistics()
        
        return {
            "report_generated_at": time.time(),
            "summary": {
                "total_files_checked": stats["total_checks"],
                "files_with_drift": stats["total_drifts"],
                "drift_rate_percentage": round(stats["drift_rate"] * 100, 2)
            },
            "drift_breakdown": {
                f"level_{level.value}": count 
                for level, count in zip(DriftLevel, stats["drift_counts"].values())
            },
            "recent_issues": stats["recent_drifts"],
            "thresholds_used": stats["thresholds"]
        }
