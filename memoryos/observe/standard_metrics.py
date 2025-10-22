"""
표준 메트릭 수집기

hit_rate, token_saving, avg_latency_ms, error_rate, drift_levels{L1,L2,L3} 집계기.
1분 롤업 JSONL(metrics.jsonl) 추가.
"""

import time
import statistics
import json
from typing import Dict, List, Tuple
from collections import deque
from pathlib import Path


class StandardMetrics:
    """
    표준 메트릭 수집기 클래스
    
    주요 기능:
    - hit_rate, token_saving, avg_latency_ms, error_rate 계산
    - drift_levels{L1,L2,L3} 집계
    - 1분 롤업 JSONL 저장
    - 상관관계 ID 관리
    """
    
    def __init__(self, output_dir: str = "metrics"):
        """
        StandardMetrics 초기화
        
        Args:
            output_dir: 메트릭 출력 디렉토리
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 메트릭 데이터 저장소
        self.hit_rate_data = deque(maxlen=1000)
        self.latency_data = deque(maxlen=1000)
        self.error_data = deque(maxlen=1000)
        self.drift_data = deque(maxlen=1000)
        
        # 상관관계 ID 관리
        self.correlation_ids = {}
        self.run_id = self._generate_run_id()
        
        # 롤업 설정
        self.rollup_interval = 60  # 1분
        self.last_rollup_time = time.time()
        
        # 통계 정보
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        
    def _generate_run_id(self) -> str:
        """실행 ID 생성"""
        return f"run_{int(time.time())}_{id(self)}"
        
    def _generate_correlation_id(self, operation: str) -> str:
        """상관관계 ID 생성"""
        correlation_id = f"{self.run_id}_{operation}_{int(time.time() * 1000)}"
        self.correlation_ids[correlation_id] = {
            "operation": operation,
            "created_at": time.time(),
            "status": "active"
        }
        return correlation_id
        
    def record_hit(self, correlation_id: str = None) -> str:
        """
        히트 기록
        
        Args:
            correlation_id: 상관관계 ID (None이면 자동 생성)
            
        Returns:
            상관관계 ID
        """
        if correlation_id is None:
            correlation_id = self._generate_correlation_id("hit")
            
        self.hit_rate_data.append({
            "correlation_id": correlation_id,
            "timestamp": time.time(),
            "hit": True
        })
        
        self.total_requests += 1
        self.successful_requests += 1
        
        return correlation_id
        
    def record_miss(self, correlation_id: str = None) -> str:
        """
        미스 기록
        
        Args:
            correlation_id: 상관관계 ID (None이면 자동 생성)
            
        Returns:
            상관관계 ID
        """
        if correlation_id is None:
            correlation_id = self._generate_correlation_id("miss")
            
        self.hit_rate_data.append({
            "correlation_id": correlation_id,
            "timestamp": time.time(),
            "hit": False
        })
        
        self.total_requests += 1
        
        return correlation_id
        
    def record_latency(self, latency_ms: float, correlation_id: str = None) -> str:
        """
        지연시간 기록
        
        Args:
            latency_ms: 지연시간 (밀리초)
            correlation_id: 상관관계 ID (None이면 자동 생성)
            
        Returns:
            상관관계 ID
        """
        if correlation_id is None:
            correlation_id = self._generate_correlation_id("latency")
            
        self.latency_data.append({
            "correlation_id": correlation_id,
            "timestamp": time.time(),
            "latency_ms": latency_ms
        })
        
        return correlation_id
        
    def record_error(self, error_type: str, correlation_id: str = None) -> str:
        """
        오류 기록
        
        Args:
            error_type: 오류 유형
            correlation_id: 상관관계 ID (None이면 자동 생성)
            
        Returns:
            상관관계 ID
        """
        if correlation_id is None:
            correlation_id = self._generate_correlation_id("error")
            
        self.error_data.append({
            "correlation_id": correlation_id,
            "timestamp": time.time(),
            "error_type": error_type
        })
        
        self.total_requests += 1
        self.failed_requests += 1
        
        return correlation_id
        
    def record_drift(self, drift_level: int, file_path: str, correlation_id: str = None) -> str:
        """
        Drift 기록
        
        Args:
            drift_level: Drift 레벨 (0-3)
            file_path: 파일 경로
            correlation_id: 상관관계 ID (None이면 자동 생성)
            
        Returns:
            상관관계 ID
        """
        if correlation_id is None:
            correlation_id = self._generate_correlation_id("drift")
            
        self.drift_data.append({
            "correlation_id": correlation_id,
            "timestamp": time.time(),
            "drift_level": drift_level,
            "file_path": file_path
        })
        
        return correlation_id
        
    def calculate_hit_rate(self, time_window: int = 300) -> float:
        """
        히트율 계산
        
        Args:
            time_window: 시간 윈도우 (초)
            
        Returns:
            히트율 (0.0 ~ 1.0)
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        hits = 0
        total = 0
        
        for record in self.hit_rate_data:
            if record["timestamp"] >= cutoff_time:
                total += 1
                if record["hit"]:
                    hits += 1
                    
        return hits / total if total > 0 else 0.0
        
    def calculate_avg_latency(self, time_window: int = 300) -> float:
        """
        평균 지연시간 계산
        
        Args:
            time_window: 시간 윈도우 (초)
            
        Returns:
            평균 지연시간 (밀리초)
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        latencies = []
        for record in self.latency_data:
            if record["timestamp"] >= cutoff_time:
                latencies.append(record["latency_ms"])
                
        return statistics.mean(latencies) if latencies else 0.0
        
    def calculate_error_rate(self, time_window: int = 300) -> float:
        """
        오류율 계산
        
        Args:
            time_window: 시간 윈도우 (초)
            
        Returns:
            오류율 (0.0 ~ 1.0)
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        errors = 0
        total = 0
        
        for record in self.error_data:
            if record["timestamp"] >= cutoff_time:
                total += 1
                errors += 1
                
        return errors / total if total > 0 else 0.0
        
    def calculate_drift_levels(self, time_window: int = 300) -> Dict[str, int]:
        """
        Drift 레벨별 통계 계산
        
        Args:
            time_window: 시간 윈도우 (초)
            
        Returns:
            Drift 레벨별 카운트
        """
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        drift_counts = {"L1": 0, "L2": 0, "L3": 0}
        
        for record in self.drift_data:
            if record["timestamp"] >= cutoff_time:
                drift_level = record["drift_level"]
                if drift_level == 1:
                    drift_counts["L1"] += 1
                elif drift_level == 2:
                    drift_counts["L2"] += 1
                elif drift_level == 3:
                    drift_counts["L3"] += 1
                    
        return drift_counts
        
    def generate_rollup_metrics(self) -> Dict:
        """
        롤업 메트릭 생성
        
        Returns:
            롤업 메트릭 데이터
        """
        return {
            "timestamp": time.time(),
            "run_id": self.run_id,
            "hit_rate": self.calculate_hit_rate(),
            "avg_latency_ms": self.calculate_avg_latency(),
            "error_rate": self.calculate_error_rate(),
            "drift_levels": self.calculate_drift_levels(),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "active_correlations": len([c for c in self.correlation_ids.values() if c["status"] == "active"])
        }
        
    def save_rollup_metrics(self) -> str:
        """
        롤업 메트릭 저장
        
        Returns:
            저장된 파일 경로
        """
        rollup_data = self.generate_rollup_metrics()
        
        # JSONL 파일에 추가
        metrics_file = self.output_dir / "metrics.jsonl"
        
        with open(metrics_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rollup_data, ensure_ascii=False) + '\n')
            
        self.last_rollup_time = time.time()
        
        print(f"[StandardMetrics] Rollup metrics saved: {metrics_file}")
        return str(metrics_file)
        
    def should_rollup(self) -> bool:
        """
        롤업 필요 여부 확인
        
        Returns:
            롤업 필요 여부
        """
        return time.time() - self.last_rollup_time >= self.rollup_interval
        
    def get_correlation_info(self, correlation_id: str) -> Dict:
        """
        상관관계 ID 정보 조회
        
        Args:
            correlation_id: 상관관계 ID
            
        Returns:
            상관관계 정보
        """
        return self.correlation_ids.get(correlation_id, {})
        
    def complete_correlation(self, correlation_id: str, status: str = "completed") -> bool:
        """
        상관관계 ID 완료 처리
        
        Args:
            correlation_id: 상관관계 ID
            status: 완료 상태
            
        Returns:
            처리 성공 여부
        """
        if correlation_id in self.correlation_ids:
            self.correlation_ids[correlation_id]["status"] = status
            self.correlation_ids[correlation_id]["completed_at"] = time.time()
            return True
        return False
        
    def cleanup_old_correlations(self, max_age: int = 3600) -> int:
        """
        오래된 상관관계 ID 정리
        
        Args:
            max_age: 최대 보관 시간 (초)
            
        Returns:
            정리된 ID 수
        """
        current_time = time.time()
        cutoff_time = current_time - max_age
        
        to_remove = []
        for corr_id, info in self.correlation_ids.items():
            if info["created_at"] < cutoff_time:
                to_remove.append(corr_id)
                
        for corr_id in to_remove:
            del self.correlation_ids[corr_id]
            
        return len(to_remove)


if __name__ == "__main__":
    # 테스트 실행
    metrics = StandardMetrics()
    
    # 메트릭 기록
    metrics.record_hit()
    metrics.record_miss()
    metrics.record_latency(10.5)
    metrics.record_error("timeout")
    metrics.record_drift(2, "test_file.txt")
    
    # 롤업 메트릭 저장
    metrics.save_rollup_metrics()
    
    print("Standard metrics collection test completed")

