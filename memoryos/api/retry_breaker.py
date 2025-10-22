"""
Retry + Circuit Breaker Module

API 호출에 대한 재시도 및 서킷 브레이커 패턴 구현
Exponential backoff + Jitter와 half-open retry 기반 실패율 관리
"""

import time
import random
import threading
from typing import Callable, Any, Dict, Optional, List
from enum import Enum
from dataclasses import dataclass
from collections import deque


class CircuitState(Enum):
    """서킷 브레이커 상태"""
    CLOSED = "closed"      # 정상 상태
    OPEN = "open"          # 서킷 열림 (요청 차단)
    HALF_OPEN = "half_open"  # 반열림 상태 (제한적 요청 허용)


@dataclass
class RetryConfig:
    """재시도 설정"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_range: float = 0.1


@dataclass
class CircuitBreakerConfig:
    """서킷 브레이커 설정"""
    failure_threshold: int = 5          # 실패 임계값
    recovery_timeout: float = 60.0     # 복구 타임아웃 (초)
    success_threshold: int = 3         # 반열림 상태에서 성공 임계값
    monitoring_window: int = 100       # 모니터링 윈도우 크기


class RetryBreaker:
    """
    재시도 및 서킷 브레이커 클래스
    
    주요 기능:
    - Exponential backoff + Jitter를 사용한 재시도
    - 실패율 기반 서킷 브레이커
    - Half-open 상태에서의 제한적 재시도
    - 스레드 안전성 보장
    """
    
    def __init__(self, retry_config: RetryConfig = None, 
                 circuit_config: CircuitBreakerConfig = None):
        """
        RetryBreaker 초기화
        
        Args:
            retry_config: 재시도 설정
            circuit_config: 서킷 브레이커 설정
        """
        self.retry_config = retry_config or RetryConfig()
        self.circuit_config = circuit_config or CircuitBreakerConfig()
        
        # 서킷 브레이커 상태
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.last_success_time = 0
        
        # 모니터링 데이터
        self.request_history = deque(maxlen=self.circuit_config.monitoring_window)
        self.failure_history = deque(maxlen=self.circuit_config.monitoring_window)
        
        # 스레드 안전성을 위한 락
        self._lock = threading.RLock()
        
    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        Exponential backoff 지연 시간 계산
        
        Args:
            attempt: 현재 시도 횟수 (0부터 시작)
            
        Returns:
            지연 시간 (초)
        """
        if attempt == 0:
            return 0
            
        # Exponential backoff 계산
        delay = self.retry_config.base_delay * (
            self.retry_config.exponential_base ** (attempt - 1)
        )
        
        # 최대 지연 시간 제한
        delay = min(delay, self.retry_config.max_delay)
        
        # Jitter 추가
        if self.retry_config.jitter:
            jitter_range = delay * self.retry_config.jitter_range
            jitter = random.uniform(-jitter_range, jitter_range)
            delay += jitter
            
        return max(0, delay)
        
    def _record_request(self, success: bool, duration: float) -> None:
        """
        요청 결과 기록
        
        Args:
            success: 성공 여부
            duration: 요청 소요 시간
        """
        with self._lock:
            current_time = time.time()
            
            request_record = {
                "timestamp": current_time,
                "success": success,
                "duration": duration
            }
            
            self.request_history.append(request_record)
            
            if success:
                self.success_count += 1
                self.last_success_time = current_time
                
                # Half-open 상태에서 성공 임계값 달성 시 Closed로 전환
                if self.state == CircuitState.HALF_OPEN:
                    if self.success_count >= self.circuit_config.success_threshold:
                        self.state = CircuitState.CLOSED
                        self.failure_count = 0
                        self.success_count = 0
                        print("[RetryBreaker] Circuit breaker closed - service recovered")
            else:
                self.failure_count += 1
                self.last_failure_time = current_time
                self.failure_history.append(request_record)
                
                # 실패 임계값 달성 시 Open으로 전환
                if self.failure_count >= self.circuit_config.failure_threshold:
                    if self.state == CircuitState.CLOSED:
                        self.state = CircuitState.OPEN
                        print(f"[RetryBreaker] Circuit breaker opened - {self.failure_count} failures")
                        
    def _should_allow_request(self) -> bool:
        """
        요청 허용 여부 확인
        
        Returns:
            요청 허용 여부
        """
        with self._lock:
            current_time = time.time()
            
            if self.state == CircuitState.CLOSED:
                return True
                
            elif self.state == CircuitState.OPEN:
                # 복구 타임아웃 경과 시 Half-open으로 전환
                if current_time - self.last_failure_time >= self.circuit_config.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    print("[RetryBreaker] Circuit breaker half-open - testing service")
                    return True
                return False
                
            elif self.state == CircuitState.HALF_OPEN:
                # Half-open 상태에서는 제한적으로 허용
                return True
                
            return False
            
    def _get_failure_rate(self) -> float:
        """
        현재 실패율 계산
        
        Returns:
            실패율 (0.0 ~ 1.0)
        """
        with self._lock:
            if not self.request_history:
                return 0.0
                
            recent_requests = list(self.request_history)
            failures = sum(1 for req in recent_requests if not req["success"])
            total = len(recent_requests)
            
            return failures / total if total > 0 else 0.0
            
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        함수 실행 (재시도 및 서킷 브레이커 적용)
        
        Args:
            func: 실행할 함수
            *args: 함수 인자
            **kwargs: 함수 키워드 인자
            
        Returns:
            함수 실행 결과
            
        Raises:
            Exception: 모든 재시도 실패 시 마지막 예외
        """
        last_exception = None
        
        for attempt in range(self.retry_config.max_attempts):
            # 서킷 브레이커 확인
            if not self._should_allow_request():
                raise Exception(f"Circuit breaker is {self.state.value} - request blocked")
                
            start_time = time.time()
            
            try:
                # 함수 실행
                result = func(*args, **kwargs)
                
                # 성공 기록
                duration = time.time() - start_time
                self._record_request(True, duration)
                
                return result
                
            except Exception as e:
                # 실패 기록
                duration = time.time() - start_time
                self._record_request(False, duration)
                
                last_exception = e
                
                # 마지막 시도가 아니면 재시도
                if attempt < self.retry_config.max_attempts - 1:
                    delay = self._calculate_backoff_delay(attempt + 1)
                    if delay > 0:
                        print(f"[RetryBreaker] Attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}")
                        time.sleep(delay)
                else:
                    print(f"[RetryBreaker] All {self.retry_config.max_attempts} attempts failed")
                    
        # 모든 재시도 실패
        raise last_exception
        
    def execute_with_custom_retry(self, func: Callable, 
                                 custom_retry_config: RetryConfig,
                                 *args, **kwargs) -> Any:
        """
        커스텀 재시도 설정으로 함수 실행
        
        Args:
            func: 실행할 함수
            custom_retry_config: 커스텀 재시도 설정
            *args: 함수 인자
            **kwargs: 함수 키워드 인자
            
        Returns:
            함수 실행 결과
        """
        # 임시로 재시도 설정 변경
        original_config = self.retry_config
        self.retry_config = custom_retry_config
        
        try:
            return self.execute(func, *args, **kwargs)
        finally:
            # 원래 설정 복원
            self.retry_config = original_config
            
    def get_status(self) -> Dict:
        """
        현재 상태 정보 반환
        
        Returns:
            상태 정보 딕셔너리
        """
        with self._lock:
            return {
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "failure_rate": self._get_failure_rate(),
                "last_failure_time": self.last_failure_time,
                "last_success_time": self.last_success_time,
                "total_requests": len(self.request_history),
                "recent_failures": len(self.failure_history),
                "config": {
                    "retry": {
                        "max_attempts": self.retry_config.max_attempts,
                        "base_delay": self.retry_config.base_delay,
                        "max_delay": self.retry_config.max_delay,
                        "exponential_base": self.retry_config.exponential_base,
                        "jitter": self.retry_config.jitter
                    },
                    "circuit": {
                        "failure_threshold": self.circuit_config.failure_threshold,
                        "recovery_timeout": self.circuit_config.recovery_timeout,
                        "success_threshold": self.circuit_config.success_threshold,
                        "monitoring_window": self.circuit_config.monitoring_window
                    }
                }
            }
            
    def reset(self) -> None:
        """서킷 브레이커 상태 초기화"""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = 0
            self.last_success_time = 0
            self.request_history.clear()
            self.failure_history.clear()
            print("[RetryBreaker] Circuit breaker reset")
            
    def force_open(self) -> None:
        """서킷 브레이커 강제 열기"""
        with self._lock:
            self.state = CircuitState.OPEN
            self.last_failure_time = time.time()
            print("[RetryBreaker] Circuit breaker forced open")
            
    def force_close(self) -> None:
        """서킷 브레이커 강제 닫기"""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            print("[RetryBreaker] Circuit breaker forced closed")
            
    def get_recent_requests(self, count: int = 10) -> List[Dict]:
        """
        최근 요청 기록 조회
        
        Args:
            count: 조회할 요청 수
            
        Returns:
            최근 요청 기록 목록
        """
        with self._lock:
            return list(self.request_history)[-count:]
            
    def get_failure_pattern(self) -> Dict:
        """
        실패 패턴 분석
        
        Returns:
            실패 패턴 정보
        """
        with self._lock:
            if not self.failure_history:
                return {"pattern": "no_failures", "details": {}}
                
            failures = list(self.failure_history)
            total_failures = len(failures)
            
            # 연속 실패 구간 분석
            consecutive_failures = []
            current_consecutive = 0
            
            for req in self.request_history:
                if not req["success"]:
                    current_consecutive += 1
                else:
                    if current_consecutive > 0:
                        consecutive_failures.append(current_consecutive)
                        current_consecutive = 0
                        
            if current_consecutive > 0:
                consecutive_failures.append(current_consecutive)
                
            return {
                "pattern": "consecutive_failures" if consecutive_failures else "isolated_failures",
                "total_failures": total_failures,
                "consecutive_failure_groups": consecutive_failures,
                "max_consecutive_failures": max(consecutive_failures) if consecutive_failures else 0,
                "average_consecutive_failures": sum(consecutive_failures) / len(consecutive_failures) if consecutive_failures else 0
            }


# 편의 함수들
def with_retry(retry_config: RetryConfig = None, 
               circuit_config: CircuitBreakerConfig = None):
    """
    데코레이터로 사용할 수 있는 재시도 및 서킷 브레이커
    
    Args:
        retry_config: 재시도 설정
        circuit_config: 서킷 브레이커 설정
        
    Returns:
        데코레이터 함수
    """
    def decorator(func: Callable) -> Callable:
        breaker = RetryBreaker(retry_config, circuit_config)
        
        def wrapper(*args, **kwargs):
            return breaker.execute(func, *args, **kwargs)
            
        # 래퍼 함수에 breaker 인스턴스 추가
        wrapper.breaker = breaker
        return wrapper
        
    return decorator


def create_breaker(retry_config: RetryConfig = None, 
                  circuit_config: CircuitBreakerConfig = None) -> RetryBreaker:
    """
    RetryBreaker 인스턴스 생성 편의 함수
    
    Args:
        retry_config: 재시도 설정
        circuit_config: 서킷 브레이커 설정
        
    Returns:
        RetryBreaker 인스턴스
    """
    return RetryBreaker(retry_config, circuit_config)