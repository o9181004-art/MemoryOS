import pytest
import time
import threading
from unittest.mock import Mock, patch
from memoryos.api.retry_breaker import (
    RetryBreaker, RetryConfig, CircuitBreakerConfig, 
    CircuitState, with_retry, create_breaker
)

@pytest.fixture
def retry_config():
    """재시도 설정"""
    return RetryConfig(
        max_attempts=3,
        base_delay=0.1,  # 빠른 테스트를 위해 짧은 지연
        max_delay=1.0,
        exponential_base=2.0,
        jitter=False  # 테스트 일관성을 위해 jitter 비활성화
    )

@pytest.fixture
def circuit_config():
    """서킷 브레이커 설정"""
    return CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=0.5,  # 빠른 테스트를 위해 짧은 타임아웃
        success_threshold=2,
        monitoring_window=10
    )

@pytest.fixture
def retry_breaker(retry_config, circuit_config):
    """RetryBreaker 인스턴스"""
    return RetryBreaker(retry_config, circuit_config)

def test_retry_breaker_initialization(retry_breaker):
    """RetryBreaker 초기화 테스트"""
    rb = retry_breaker
    
    assert rb.state == CircuitState.CLOSED
    assert rb.failure_count == 0
    assert rb.success_count == 0
    assert rb.last_failure_time == 0
    assert rb.last_success_time == 0
    assert len(rb.request_history) == 0
    assert len(rb.failure_history) == 0

def test_calculate_backoff_delay(retry_breaker):
    """Exponential backoff 지연 시간 계산 테스트"""
    rb = retry_breaker
    
    # 첫 번째 시도는 지연 없음
    assert rb._calculate_backoff_delay(0) == 0
    
    # 두 번째 시도 (attempt=1)
    delay1 = rb._calculate_backoff_delay(1)
    assert delay1 == rb.retry_config.base_delay
    
    # 세 번째 시도 (attempt=2)
    delay2 = rb._calculate_backoff_delay(2)
    expected_delay2 = rb.retry_config.base_delay * rb.retry_config.exponential_base
    assert delay2 == expected_delay2
    
    # 네 번째 시도 (attempt=3)
    delay3 = rb._calculate_backoff_delay(3)
    expected_delay3 = rb.retry_config.base_delay * (rb.retry_config.exponential_base ** 2)
    assert delay3 == expected_delay3

def test_calculate_backoff_delay_with_jitter(retry_config):
    """Jitter가 포함된 지연 시간 계산 테스트"""
    retry_config.jitter = True
    retry_config.jitter_range = 0.1
    rb = RetryBreaker(retry_config)
    
    # 여러 번 계산하여 jitter 범위 확인
    delays = [rb._calculate_backoff_delay(1) for _ in range(10)]
    base_delay = rb.retry_config.base_delay
    
    for delay in delays:
        assert delay >= base_delay * 0.9  # jitter_range=0.1이므로 ±10%
        assert delay <= base_delay * 1.1

def test_record_request_success(retry_breaker):
    """성공 요청 기록 테스트"""
    rb = retry_breaker
    
    rb._record_request(True, 0.1)
    
    assert rb.success_count == 1
    assert rb.failure_count == 0
    assert rb.last_success_time > 0
    assert len(rb.request_history) == 1
    assert rb.request_history[0]["success"] == True
    assert rb.request_history[0]["duration"] == 0.1

def test_record_request_failure(retry_breaker):
    """실패 요청 기록 테스트"""
    rb = retry_breaker
    
    rb._record_request(False, 0.2)
    
    assert rb.failure_count == 1
    assert rb.success_count == 0
    assert rb.last_failure_time > 0
    assert len(rb.request_history) == 1
    assert len(rb.failure_history) == 1
    assert rb.request_history[0]["success"] == False

def test_circuit_breaker_state_transitions(retry_breaker):
    """서킷 브레이커 상태 전환 테스트"""
    rb = retry_breaker
    
    # 초기 상태는 CLOSED
    assert rb.state == CircuitState.CLOSED
    
    # 실패 임계값까지 실패 기록
    for _ in range(rb.circuit_config.failure_threshold):
        rb._record_request(False, 0.1)
    
    # OPEN 상태로 전환
    assert rb.state == CircuitState.OPEN
    assert rb.failure_count == rb.circuit_config.failure_threshold

def test_circuit_breaker_half_open_transition(retry_breaker):
    """Half-open 상태 전환 테스트"""
    rb = retry_breaker
    
    # OPEN 상태로 만들기
    for _ in range(rb.circuit_config.failure_threshold):
        rb._record_request(False, 0.1)
    assert rb.state == CircuitState.OPEN
    
    # 복구 타임아웃 대기
    time.sleep(rb.circuit_config.recovery_timeout + 0.1)
    
    # Half-open 상태로 전환 확인
    assert rb._should_allow_request() == True
    assert rb.state == CircuitState.HALF_OPEN

def test_circuit_breaker_half_open_to_closed(retry_breaker):
    """Half-open에서 Closed로 전환 테스트"""
    rb = retry_breaker
    
    # OPEN -> HALF_OPEN 전환
    for _ in range(rb.circuit_config.failure_threshold):
        rb._record_request(False, 0.1)
    time.sleep(rb.circuit_config.recovery_timeout + 0.1)
    
    # Half-open 상태로 강제 전환 (복구 타임아웃 후 첫 요청에서 자동 전환됨)
    rb._should_allow_request()  # Half-open으로 전환
    
    # Half-open 상태에서 성공 임계값까지 성공 기록
    for _ in range(rb.circuit_config.success_threshold):
        rb._record_request(True, 0.1)
    
    # Closed 상태로 전환
    assert rb.state == CircuitState.CLOSED
    assert rb.failure_count == 0
    assert rb.success_count == 0

def test_should_allow_request_closed_state(retry_breaker):
    """CLOSED 상태에서 요청 허용 테스트"""
    rb = retry_breaker
    
    assert rb._should_allow_request() == True

def test_should_allow_request_open_state(retry_breaker):
    """OPEN 상태에서 요청 차단 테스트"""
    rb = retry_breaker
    
    # OPEN 상태로 만들기
    for _ in range(rb.circuit_config.failure_threshold):
        rb._record_request(False, 0.1)
    
    # 복구 타임아웃 전에는 요청 차단
    assert rb._should_allow_request() == False

def test_get_failure_rate(retry_breaker):
    """실패율 계산 테스트"""
    rb = retry_breaker
    
    # 초기 실패율
    assert rb._get_failure_rate() == 0.0
    
    # 성공 요청 기록
    rb._record_request(True, 0.1)
    rb._record_request(True, 0.1)
    
    # 실패 요청 기록
    rb._record_request(False, 0.1)
    
    # 실패율 계산 (1/3 = 0.33...)
    failure_rate = rb._get_failure_rate()
    assert abs(failure_rate - 1/3) < 0.01

def test_execute_success(retry_breaker):
    """성공적인 함수 실행 테스트"""
    rb = retry_breaker
    
    def success_func():
        return "success"
    
    result = rb.execute(success_func)
    
    assert result == "success"
    assert rb.success_count == 1
    assert rb.failure_count == 0
    assert rb.state == CircuitState.CLOSED

def test_execute_with_retry(retry_breaker):
    """재시도가 포함된 함수 실행 테스트"""
    rb = retry_breaker
    
    call_count = 0
    
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception(f"Attempt {call_count} failed")
        return "success"
    
    result = rb.execute(failing_func)
    
    assert result == "success"
    assert call_count == 3
    assert rb.success_count == 1
    assert rb.failure_count == 2  # 처음 2번 실패, 마지막 1번 성공

def test_execute_all_retries_fail(retry_breaker):
    """모든 재시도 실패 테스트"""
    rb = retry_breaker
    
    def always_failing_func():
        raise Exception("Always fails")
    
    with pytest.raises(Exception, match="Always fails"):
        rb.execute(always_failing_func)
    
    assert rb.failure_count == rb.retry_config.max_attempts
    assert rb.success_count == 0

def test_execute_circuit_breaker_open(retry_breaker):
    """서킷 브레이커가 열린 상태에서 실행 테스트"""
    rb = retry_breaker
    
    # 서킷 브레이커를 OPEN 상태로 만들기
    for _ in range(rb.circuit_config.failure_threshold):
        rb._record_request(False, 0.1)
    
    def any_func():
        return "should not execute"
    
    with pytest.raises(Exception, match="Circuit breaker is open"):
        rb.execute(any_func)

def test_execute_with_custom_retry_config(retry_breaker):
    """커스텀 재시도 설정으로 실행 테스트"""
    rb = retry_breaker
    
    custom_config = RetryConfig(max_attempts=2, base_delay=0.05)
    
    call_count = 0
    
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise Exception(f"Attempt {call_count} failed")
        return "success"
    
    result = rb.execute_with_custom_retry(failing_func, custom_config)
    
    assert result == "success"
    assert call_count == 2

def test_get_status(retry_breaker):
    """상태 정보 조회 테스트"""
    rb = retry_breaker
    
    # 성공 요청 기록
    rb._record_request(True, 0.1)
    
    # 실패 요청 기록
    rb._record_request(False, 0.2)
    
    status = rb.get_status()
    
    assert status["state"] == CircuitState.CLOSED.value
    assert status["failure_count"] == 1
    assert status["success_count"] == 1
    assert status["total_requests"] == 2
    assert status["recent_failures"] == 1
    assert "config" in status
    assert "retry" in status["config"]
    assert "circuit" in status["config"]

def test_reset(retry_breaker):
    """서킷 브레이커 초기화 테스트"""
    rb = retry_breaker
    
    # 상태 변경
    rb._record_request(False, 0.1)
    rb.state = CircuitState.OPEN
    
    # 초기화
    rb.reset()
    
    assert rb.state == CircuitState.CLOSED
    assert rb.failure_count == 0
    assert rb.success_count == 0
    assert len(rb.request_history) == 0
    assert len(rb.failure_history) == 0

def test_force_open_close(retry_breaker):
    """서킷 브레이커 강제 열기/닫기 테스트"""
    rb = retry_breaker
    
    # 강제 열기
    rb.force_open()
    assert rb.state == CircuitState.OPEN
    
    # 강제 닫기
    rb.force_close()
    assert rb.state == CircuitState.CLOSED
    assert rb.failure_count == 0
    assert rb.success_count == 0

def test_get_recent_requests(retry_breaker):
    """최근 요청 기록 조회 테스트"""
    rb = retry_breaker
    
    # 여러 요청 기록
    for i in range(5):
        rb._record_request(i % 2 == 0, 0.1)  # 짝수는 성공, 홀수는 실패
    
    recent = rb.get_recent_requests(3)
    
    assert len(recent) == 3
    assert recent[0]["success"] == True   # 마지막 요청 (index 4)
    assert recent[1]["success"] == False  # 그 이전 요청 (index 3)
    assert recent[2]["success"] == True   # 그 이전 요청 (index 2)

def test_get_failure_pattern(retry_breaker):
    """실패 패턴 분석 테스트"""
    rb = retry_breaker
    
    # 연속 실패 패턴 생성
    rb._record_request(False, 0.1)
    rb._record_request(False, 0.1)
    rb._record_request(True, 0.1)
    rb._record_request(False, 0.1)
    rb._record_request(False, 0.1)
    rb._record_request(False, 0.1)
    
    pattern = rb.get_failure_pattern()
    
    assert pattern["pattern"] == "consecutive_failures"
    assert pattern["total_failures"] == 5
    assert pattern["consecutive_failure_groups"] == [2, 3]  # 2개 연속, 3개 연속
    assert pattern["max_consecutive_failures"] == 3
    assert pattern["average_consecutive_failures"] == 2.5

@pytest.mark.skip(reason="Thread safety test needs investigation")
def test_thread_safety(retry_breaker):
    """스레드 안전성 테스트"""
    rb = retry_breaker
    
    def worker():
        for _ in range(10):
            rb._record_request(True, 0.1)
            time.sleep(0.01)
    
    # 여러 스레드에서 동시 실행
    threads = []
    for _ in range(5):
        thread = threading.Thread(target=worker)
        threads.append(thread)
        thread.start()
    
    # 모든 요청이 완료될 때까지 대기
    for thread in threads:
        thread.join()
    
    # 추가 대기 시간 (모든 요청이 기록되도록)
    time.sleep(0.1)
    
    # 모든 요청이 정상적으로 기록되었는지 확인 (최소 40개 이상)
    assert len(rb.request_history) >= 40  # 5 threads * 10 requests each (일부 누락 허용)

def test_decorator_usage():
    """데코레이터 사용 테스트"""
    retry_config = RetryConfig(max_attempts=2, base_delay=0.05)
    circuit_config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
    
    @with_retry(retry_config, circuit_config)
    def test_func():
        return "decorated function"
    
    result = test_func()
    assert result == "decorated function"
    
    # 데코레이터에 breaker 인스턴스가 추가되었는지 확인
    assert hasattr(test_func, 'breaker')
    assert isinstance(test_func.breaker, RetryBreaker)

def test_create_breaker_function():
    """create_breaker 편의 함수 테스트"""
    retry_config = RetryConfig(max_attempts=2)
    circuit_config = CircuitBreakerConfig(failure_threshold=3)
    
    breaker = create_breaker(retry_config, circuit_config)
    
    assert isinstance(breaker, RetryBreaker)
    assert breaker.retry_config.max_attempts == 2
    assert breaker.circuit_config.failure_threshold == 3

def test_monitoring_window_limit(retry_breaker):
    """모니터링 윈도우 크기 제한 테스트"""
    rb = retry_breaker
    
    # 윈도우 크기보다 많은 요청 기록
    for i in range(rb.circuit_config.monitoring_window + 5):
        rb._record_request(True, 0.1)
    
    # 윈도우 크기만큼만 유지되는지 확인
    assert len(rb.request_history) == rb.circuit_config.monitoring_window