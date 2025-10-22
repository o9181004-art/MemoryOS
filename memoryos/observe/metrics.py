"""
Metrics - 표준 메트릭 수집기

시스템 성능 및 상태 메트릭을 계산하고 모니터링합니다.
hit_rate, token_saving, avg_latency_ms, error_rate, drift_levels를 포함한 표준 메트릭 수집
1분 롤업 JSONL 및 상관관계 ID를 포함합니다.
"""

import time
import statistics
import json
from typing import Dict, List, Tuple
from collections import deque, defaultdict
from pathlib import Path
from datetime import datetime


class StandardMetricsCollector:
    """
    표준 메트릭 수집기
    
    주요 기능:
    - hit_rate: 캐시 히트율 계산
    - token_saving: 토큰 절약량 계산 (placeholder)
    - avg_latency_ms: 평균 지연시간 계산
    - error_rate: 오류율 계산
    - drift_levels: L1, L2, L3 drift 레벨별 통계
    - 1분 롤업 JSONL 저장
    """
    
    def __init__(self, metrics_dir: str = "metrics", window_size: int = 1000, rollup_interval: int = 60):
        """
        StandardMetricsCollector 초기화
        
        Args:
            metrics_dir: 메트릭 저장 디렉토리
            window_size: 메트릭 계산 윈도우 크기
            rollup_interval: 롤업 간격 (초)
        """
        self.metrics_dir = Path(metrics_dir)
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        self.window_size = window_size
        self.rollup_interval = rollup_interval
        
        # 메트릭 데이터 저장소
        self.delta_times = deque(maxlen=window_size)  # Δt 값들
        self.drift_events = deque(maxlen=window_size)  # Drift 이벤트들
        self.operation_times = deque(maxlen=window_size)  # 작업 시간들
        self.cache_hits = deque(maxlen=window_size)  # 캐시 히트 이벤트들
        self.error_events = deque(maxlen=window_size)  # 오류 이벤트들
        
        # 통계 데이터
        self.metrics_history = []
        self.rollup_data = []  # 1분 롤업 데이터
        self.last_calculation_time = time.time()
        self.last_rollup_time = time.time()
        
        # 표준 메트릭
        self.current_metrics = {
            "hit_rate": 0.0,
            "token_saving": 0.0,  # Placeholder
            "avg_latency_ms": 0.0,
            "error_rate": 0.0,
            "drift_levels": {"L1": 0, "L2": 0, "L3": 0},
            "timestamp": time.time()
        }
        
        # 롤업 파일 경로
        self.rollup_file = Path("metrics.jsonl")
        
    def record_cache_hit(self, cache_type: str = "memory") -> None:
        """
        캐시 히트 이벤트 기록
        
        Args:
            cache_type: 캐시 유형
        """
        self.cache_hits.append({
            "timestamp": time.time(),
            "cache_type": cache_type,
            "hit": True
        })
        
    def record_cache_miss(self, cache_type: str = "memory") -> None:
        """
        캐시 미스 이벤트 기록
        
        Args:
            cache_type: 캐시 유형
        """
        self.cache_hits.append({
            "timestamp": time.time(),
            "cache_type": cache_type,
            "hit": False
        })
        
    def record_error(self, error_type: str, error_message: str) -> None:
        """
        오류 이벤트 기록
        
        Args:
            error_type: 오류 유형
            error_message: 오류 메시지
        """
        self.error_events.append({
            "timestamp": time.time(),
            "error_type": error_type,
            "error_message": error_message
        })
        
    def calculate_hit_rate(self, time_window: int = 300) -> float:
        """
        캐시 히트율 계산
        
        Args:
            time_window: 계산할 시간 윈도우 (초)
            
        Returns:
            히트율 (0.0 ~ 1.0)
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        # 시간 윈도우 내의 캐시 이벤트들 필터링
        recent_cache_events = [
            entry for entry in self.cache_hits
            if entry["timestamp"] >= cutoff_time
        ]
        
        if not recent_cache_events:
            return 0.0
            
        hits = sum(1 for entry in recent_cache_events if entry["hit"])
        total = len(recent_cache_events)
        
        return hits / total if total > 0 else 0.0
        
    def calculate_token_saving(self, time_window: int = 300) -> float:
        """
        토큰 절약량 계산 (Placeholder)
        
        Args:
            time_window: 계산할 시간 윈도우 (초)
            
        Returns:
            토큰 절약량 (placeholder)
        """
        # 실제 구현에서는 캐시 히트율과 토큰 사용량을 기반으로 계산
        hit_rate = self.calculate_hit_rate(time_window)
        # Placeholder: 히트율에 비례한 토큰 절약량 계산
        return hit_rate * 1000  # 예시: 최대 1000 토큰 절약
        
    def calculate_avg_latency_ms(self, time_window: int = 300) -> float:
        """
        평균 지연시간 계산 (밀리초)
        
        Args:
            time_window: 계산할 시간 윈도우 (초)
            
        Returns:
            평균 지연시간 (밀리초)
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        # 시간 윈도우 내의 작업 시간들 필터링
        recent_operations = [
            entry["duration"] for entry in self.operation_times
            if entry["timestamp"] >= cutoff_time
        ]
        
        if not recent_operations:
            return 0.0
            
        avg_duration = statistics.mean(recent_operations)
        return avg_duration * 1000  # 초를 밀리초로 변환
        
    def calculate_error_rate(self, time_window: int = 300) -> float:
        """
        오류율 계산
        
        Args:
            time_window: 계산할 시간 윈도우 (초)
            
        Returns:
            오류율 (0.0 ~ 1.0)
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        # 시간 윈도우 내의 오류 이벤트들 필터링
        recent_errors = [
            entry for entry in self.error_events
            if entry["timestamp"] >= cutoff_time
        ]
        
        # 전체 작업 수 계산 (오류 + 성공)
        recent_operations = [
            entry for entry in self.operation_times
            if entry["timestamp"] >= cutoff_time
        ]
        
        total_operations = len(recent_operations) + len(recent_errors)
        
        if total_operations == 0:
            return 0.0
            
        return len(recent_errors) / total_operations
        
    def calculate_drift_levels(self, time_window: int = 300) -> Dict[str, int]:
        """
        Drift 레벨별 통계 계산
        
        Args:
            time_window: 계산할 시간 윈도우 (초)
            
        Returns:
            L1, L2, L3 drift 레벨별 카운트
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        # 시간 윈도우 내의 drift 이벤트들 필터링
        recent_drifts = [
            entry for entry in self.drift_events
            if entry["timestamp"] >= cutoff_time
        ]
        
        drift_counts = {"L1": 0, "L2": 0, "L3": 0}
        
        for entry in recent_drifts:
            drift_level = entry["drift_level"]
            if drift_level == 1:
                drift_counts["L1"] += 1
            elif drift_level == 2:
                drift_counts["L2"] += 1
            elif drift_level == 3:
                drift_counts["L3"] += 1
                
        return drift_counts
        
    def record_delta_time(self, delta_t: float) -> None:
        """
        Delta 시간 기록
        
        Args:
            delta_t: Delta 시간 (초)
        """
        self.delta_times.append({
            "timestamp": time.time(),
            "delta_t": delta_t
        })
        
    def record_drift_event(self, drift_level: int, file_path: str) -> None:
        """
        Drift 이벤트 기록
        
        Args:
            drift_level: Drift 레벨 (1, 2, 3)
            file_path: 파일 경로
        """
        self.drift_events.append({
            "timestamp": time.time(),
            "drift_level": drift_level,
            "file_path": file_path
        })
        
    def record_operation_time(self, operation_type: str, duration: float) -> None:
        """
        작업 시간 기록
        
        Args:
            operation_type: 작업 유형
            duration: 작업 소요 시간 (초)
        """
        self.operation_times.append({
            "timestamp": time.time(),
            "operation_type": operation_type,
            "duration": duration
        })
        
    def calculate_avg_delta_t(self, time_window: int = 300) -> float:
        """
        평균 Delta 시간 계산
        
        Args:
            time_window: 계산할 시간 윈도우 (초)
            
        Returns:
            평균 Delta 시간
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        # 시간 윈도우 내의 delta_t 값들 필터링
        recent_deltas = [
            entry["delta_t"] for entry in self.delta_times
            if entry["timestamp"] >= cutoff_time
        ]
        
        if not recent_deltas:
            return 0.0
            
        return statistics.mean(recent_deltas)
        
    def calculate_drift_rate(self, time_window: int = 300) -> float:
        """
        Drift율 계산
        
        Args:
            time_window: 계산할 시간 윈도우 (초)
            
        Returns:
            Drift율 (0.0 ~ 1.0)
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        # 시간 윈도우 내의 drift 이벤트들 필터링
        recent_drifts = [
            entry for entry in self.drift_events
            if entry["timestamp"] >= cutoff_time
        ]
        
        if not recent_drifts:
            return 0.0
            
        # 전체 파일 수 대비 drift 발생 비율 계산
        # 실제로는 전체 파일 수를 별도로 추적해야 함
        total_files = len(set(entry["file_path"] for entry in recent_drifts))
        drift_files = len(set(entry["file_path"] for entry in recent_drifts))
        
        return drift_files / total_files if total_files > 0 else 0.0
        
    def calculate_operation_rate(self, time_window: int = 300) -> float:
        """
        작업율 계산 (초당 작업 수)
        
        Args:
            time_window: 계산할 시간 윈도우 (초)
            
        Returns:
            초당 작업 수
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        # 시간 윈도우 내의 작업들 필터링
        recent_operations = [
            entry for entry in self.operation_times
            if entry["timestamp"] >= cutoff_time
        ]
        
        if not recent_operations:
            return 0.0
            
        return len(recent_operations) / time_window
        
    def calculate_system_health(self) -> float:
        """
        시스템 건강도 계산
        
        Returns:
            시스템 건강도 (0.0 ~ 100.0)
        """
        health_score = 100.0
        
        # Drift율에 따른 건강도 감소
        drift_rate = self.calculate_drift_rate()
        health_score -= drift_rate * 50  # Drift율 1%당 0.5점 감소
        
        # 작업 시간이 너무 오래 걸리는 경우 건강도 감소
        avg_operation_time = self._calculate_avg_operation_time()
        if avg_operation_time > 5.0:  # 5초 이상
            health_score -= min(20, (avg_operation_time - 5) * 2)
            
        # Delta 시간이 불규칙한 경우 건강도 감소
        delta_t_variance = self._calculate_delta_t_variance()
        if delta_t_variance > 100:  # 분산이 큰 경우
            health_score -= min(15, delta_t_variance / 10)
            
        return max(0.0, health_score)
        
    def _calculate_avg_operation_time(self) -> float:
        """평균 작업 시간 계산"""
        if not self.operation_times:
            return 0.0
            
        durations = [entry["duration"] for entry in self.operation_times]
        return statistics.mean(durations)
        
    def _calculate_delta_t_variance(self) -> float:
        """Delta 시간 분산 계산"""
        if len(self.delta_times) < 2:
            return 0.0
            
        delta_t_values = [entry["delta_t"] for entry in self.delta_times]
        return statistics.variance(delta_t_values) if len(delta_t_values) > 1 else 0.0
        
    def update_metrics(self) -> Dict:
        """
        모든 표준 메트릭 업데이트
        
        Returns:
            업데이트된 메트릭 딕셔너리
        """
        current_time = time.time()
        
        # 표준 메트릭 계산
        hit_rate = self.calculate_hit_rate()
        token_saving = self.calculate_token_saving()
        avg_latency_ms = self.calculate_avg_latency_ms()
        error_rate = self.calculate_error_rate()
        drift_levels = self.calculate_drift_levels()
        
        # 현재 메트릭 업데이트
        self.current_metrics = {
            "hit_rate": hit_rate,
            "token_saving": token_saving,
            "avg_latency_ms": avg_latency_ms,
            "error_rate": error_rate,
            "drift_levels": drift_levels,
            "timestamp": current_time
        }
        
        # 메트릭 히스토리에 추가
        self.metrics_history.append(self.current_metrics.copy())
        
        # 히스토리 크기 제한
        if len(self.metrics_history) > self.window_size:
            self.metrics_history = self.metrics_history[-self.window_size:]
            
        self.last_calculation_time = current_time
        
        # 1분 롤업 체크
        self._check_and_perform_rollup()
        
        return self.current_metrics
        
    def _check_and_perform_rollup(self) -> None:
        """
        1분 롤업 수행 체크 및 실행
        """
        current_time = time.time()
        
        if current_time - self.last_rollup_time >= self.rollup_interval:
            self._perform_rollup()
            self.last_rollup_time = current_time
            
    def _perform_rollup(self) -> None:
        """
        1분 롤업 수행 및 JSONL 저장
        """
        try:
            # 롤업 데이터 생성
            rollup_entry = {
                "timestamp": time.time(),
                "iso_timestamp": datetime.now().isoformat(),
                "metrics": self.current_metrics.copy(),
                "summary": {
                    "total_cache_events": len(self.cache_hits),
                    "total_drift_events": len(self.drift_events),
                    "total_operations": len(self.operation_times),
                    "total_errors": len(self.error_events),
                    "window_size": self.window_size
                }
            }
            
            # 롤업 데이터에 추가
            self.rollup_data.append(rollup_entry)
            
            # JSONL 파일에 저장
            with open(self.rollup_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rollup_entry, ensure_ascii=False) + '\n')
                
            print(f"[StandardMetricsCollector] Rollup performed at {rollup_entry['iso_timestamp']}")
            
        except Exception as e:
            print(f"[StandardMetricsCollector] Failed to perform rollup: {e}")
            
    def get_rollup_data(self, time_window: int = 3600) -> List[Dict]:
        """
        롤업 데이터 조회
        
        Args:
            time_window: 조회할 시간 윈도우 (초)
            
        Returns:
            롤업 데이터 목록
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        return [
            entry for entry in self.rollup_data
            if entry["timestamp"] >= cutoff_time
        ]
        
    def load_rollup_from_file(self) -> None:
        """
        JSONL 파일에서 롤업 데이터 로드
        """
        try:
            if not self.rollup_file.exists():
                return
                
            with open(self.rollup_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rollup_entry = json.loads(line)
                            self.rollup_data.append(rollup_entry)
                        except json.JSONDecodeError:
                            continue
                            
            print(f"[StandardMetricsCollector] Loaded {len(self.rollup_data)} rollup entries from file")
            
        except Exception as e:
            print(f"[StandardMetricsCollector] Failed to load rollup data: {e}")
            
    def export_rollup_data(self, output_file: str) -> bool:
        """
        롤업 데이터 내보내기
        
        Args:
            output_file: 출력 파일 경로
            
        Returns:
            내보내기 성공 여부
        """
        try:
            export_data = {
                "exported_at": time.time(),
                "rollup_entries": self.rollup_data,
                "total_entries": len(self.rollup_data)
            }
            
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
                
            print(f"[StandardMetricsCollector] Exported rollup data to {output_file}")
            return True
            
        except Exception as e:
            print(f"[StandardMetricsCollector] Failed to export rollup data: {e}")
            return False
        
    def get_metrics_summary(self) -> Dict:
        """표준 메트릭 요약 정보 반환"""
        return {
            "current_metrics": self.current_metrics,
            "total_cache_events": len(self.cache_hits),
            "total_drift_events": len(self.drift_events),
            "total_operations": len(self.operation_times),
            "total_errors": len(self.error_events),
            "metrics_history_length": len(self.metrics_history),
            "rollup_entries_count": len(self.rollup_data),
            "last_calculation": self.last_calculation_time,
            "last_rollup": self.last_rollup_time
        }
        
    def get_metrics_trend(self, metric_name: str, time_window: int = 3600) -> List[Tuple[float, float]]:
        """
        특정 메트릭의 트렌드 조회
        
        Args:
            metric_name: 메트릭 이름
            time_window: 시간 윈도우 (초)
            
        Returns:
            (timestamp, value) 튜플 목록
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        trend_data = []
        for metrics_entry in self.metrics_history:
            if metrics_entry["timestamp"] >= cutoff_time:
                if metric_name in metrics_entry:
                    trend_data.append((
                        metrics_entry["timestamp"],
                        metrics_entry[metric_name]
                    ))
                    
        return trend_data
        
    def detect_anomalies(self) -> List[Dict]:
        """
        이상 현상 감지
        
        Returns:
            감지된 이상 현상 목록
        """
        anomalies = []
        
        # Drift율 급증 감지
        recent_drift_rate = self.calculate_drift_rate(time_window=60)  # 최근 1분
        historical_drift_rate = self.calculate_drift_rate(time_window=3600)  # 최근 1시간
        
        if recent_drift_rate > historical_drift_rate * 2:
            anomalies.append({
                "type": "drift_rate_spike",
                "severity": "high",
                "description": f"Drift rate spiked from {historical_drift_rate:.2%} to {recent_drift_rate:.2%}",
                "timestamp": time.time()
            })
            
        # 작업 시간 급증 감지
        avg_operation_time = self._calculate_avg_operation_time()
        if avg_operation_time > 10.0:  # 10초 이상
            anomalies.append({
                "type": "operation_time_spike",
                "severity": "medium",
                "description": f"Average operation time increased to {avg_operation_time:.2f} seconds",
                "timestamp": time.time()
            })
            
        # 시스템 건강도 급감 감지
        if self.current_metrics["system_health"] < 50:
            anomalies.append({
                "type": "system_health_degradation",
                "severity": "critical",
                "description": f"System health dropped to {self.current_metrics['system_health']:.1f}%",
                "timestamp": time.time()
            })
            
        return anomalies
        
    def export_metrics(self, output_file: str) -> bool:
        """
        메트릭 데이터 내보내기
        
        Args:
            output_file: 출력 파일 경로
            
        Returns:
            내보내기 성공 여부
        """
        try:
            import json
            from pathlib import Path
            
            export_data = {
                "exported_at": time.time(),
                "current_metrics": self.current_metrics,
                "metrics_history": self.metrics_history,
                "summary": self.get_metrics_summary()
            }
            
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
                
            print(f"[Metrics] Exported metrics to {output_file}")
            return True
            
        except Exception as e:
            print(f"[Metrics] Failed to export metrics: {e}")
            return False
            
    def reset_metrics(self) -> None:
        """표준 메트릭 데이터 초기화"""
        self.delta_times.clear()
        self.drift_events.clear()
        self.operation_times.clear()
        self.cache_hits.clear()
        self.error_events.clear()
        self.metrics_history.clear()
        self.rollup_data.clear()
        
        self.current_metrics = {
            "hit_rate": 0.0,
            "token_saving": 0.0,
            "avg_latency_ms": 0.0,
            "error_rate": 0.0,
            "drift_levels": {"L1": 0, "L2": 0, "L3": 0},
            "timestamp": time.time()
        }
        
        print("[StandardMetricsCollector] Standard metrics data reset")
