"""
Unit Test: Idempotency Guarantee

ContextRuntime과 LogStore의 Idempotency 보장 기능을 테스트합니다.
(conversation_id, turn_id) 기반 중복 처리 방지를 검증합니다.
"""

import pytest
import time
from memoryos.core.context_runtime import ContextRuntime
from memoryos.store.log_store import LogStore


@pytest.fixture
def context_runtime_instance(tmp_path):
    """테스트용 ContextRuntime 인스턴스"""
    config_file = tmp_path / "test_config.toml"
    config_file.write_text("""
[watch_paths]
paths = ["data/"]

catalog_file = "data/catalog.json"
memory_index_file = "data/memory_index.json"
snapshot_dir = "snapshots"
""", encoding='utf-8')
    
    return ContextRuntime(str(config_file))


@pytest.fixture
def log_store_instance(tmp_path):
    """테스트용 LogStore 인스턴스"""
    log_file = tmp_path / "test_log.jsonl"
    return LogStore(str(log_file))


def test_context_runtime_idempotency(context_runtime_instance):
    """ContextRuntime의 Idempotency 보장 테스트"""
    cr = context_runtime_instance
    
    # 동일한 이벤트 데이터
    delta = {
        "path": "test_file.txt",
        "operation": "write",
        "producer_actual": "test_producer",
        "ts": time.time(),
        "conversation_id": "conv_123",
        "turn_id": "turn_456"
    }
    
    # 첫 번째 처리
    result1 = cr.handle_delta(delta)
    assert result1["success"] is True
    assert result1["idempotency_key"] == ("conv_123", "turn_456")
    
    # 두 번째 처리 (동일한 이벤트)
    result2 = cr.handle_delta(delta)
    assert result2["success"] is False
    assert result2["error"] == "Event already processed"
    assert result2["idempotency_key"] == ("conv_123", "turn_456")
    
    # 처리된 이벤트 수 확인
    assert len(cr.processed_events) == 1
    assert ("conv_123", "turn_456") in cr.processed_events


def test_context_runtime_different_conversations(context_runtime_instance):
    """다른 대화 ID의 이벤트 처리 테스트"""
    cr = context_runtime_instance
    
    # 첫 번째 대화
    delta1 = {
        "path": "test_file1.txt",
        "operation": "write",
        "producer_actual": "test_producer",
        "ts": time.time(),
        "conversation_id": "conv_123",
        "turn_id": "turn_456"
    }
    
    # 두 번째 대화
    delta2 = {
        "path": "test_file2.txt",
        "operation": "write",
        "producer_actual": "test_producer",
        "ts": time.time(),
        "conversation_id": "conv_789",
        "turn_id": "turn_456"
    }
    
    # 두 이벤트 모두 처리되어야 함
    result1 = cr.handle_delta(delta1)
    result2 = cr.handle_delta(delta2)
    
    assert result1["success"] is True
    assert result2["success"] is True
    assert result1["idempotency_key"] != result2["idempotency_key"]
    
    # 처리된 이벤트 수 확인
    assert len(cr.processed_events) == 2


def test_context_runtime_different_turns(context_runtime_instance):
    """같은 대화의 다른 턴 처리 테스트"""
    cr = context_runtime_instance
    
    # 첫 번째 턴
    delta1 = {
        "path": "test_file.txt",
        "operation": "write",
        "producer_actual": "test_producer",
        "ts": time.time(),
        "conversation_id": "conv_123",
        "turn_id": "turn_456"
    }
    
    # 두 번째 턴
    delta2 = {
        "path": "test_file.txt",
        "operation": "write",
        "producer_actual": "test_producer",
        "ts": time.time(),
        "conversation_id": "conv_123",
        "turn_id": "turn_789"
    }
    
    # 두 이벤트 모두 처리되어야 함
    result1 = cr.handle_delta(delta1)
    result2 = cr.handle_delta(delta2)
    
    assert result1["success"] is True
    assert result2["success"] is True
    assert result1["idempotency_key"] != result2["idempotency_key"]
    
    # 처리된 이벤트 수 확인
    assert len(cr.processed_events) == 2


def test_context_runtime_default_idempotency_key(context_runtime_instance):
    """기본 Idempotency 키 생성 테스트"""
    cr = context_runtime_instance
    
    # conversation_id와 turn_id가 없는 이벤트
    delta = {
        "path": "test_file.txt",
        "operation": "write",
        "producer_actual": "test_producer",
        "ts": time.time()
    }
    
    result = cr.handle_delta(delta)
    assert result["success"] is True
    assert result["idempotency_key"] == ("default", delta["ts"])
    
    # 동일한 이벤트 재처리
    result2 = cr.handle_delta(delta)
    assert result2["success"] is False
    assert result2["error"] == "Event already processed"


def test_log_store_idempotency(log_store_instance):
    """LogStore의 Idempotency 보장 테스트"""
    ls = log_store_instance
    
    # 동일한 이벤트 데이터
    event = {
        "message": "test event",
        "level": "INFO",
        "conversation_id": "conv_123",
        "turn_id": "turn_456"
    }
    
    # 첫 번째 추가
    result1 = ls.append_log(event)
    assert result1 is True
    
    # 두 번째 추가 (동일한 이벤트)
    result2 = ls.append_log(event)
    assert result2 is True  # LogStore는 중복을 허용하지만 결과를 캐시에서 반환
    
    # Idempotency 확인
    assert ls.check_idempotency("conv_123", "turn_456") is True
    
    # 이벤트 결과 조회
    event_result = ls.get_event_result("conv_123", "turn_456")
    assert event_result["processed"] is True
    assert event_result["result"] is True


def test_log_store_different_events(log_store_instance):
    """다른 이벤트의 처리 테스트"""
    ls = log_store_instance
    
    # 첫 번째 이벤트
    event1 = {
        "message": "test event 1",
        "level": "INFO",
        "conversation_id": "conv_123",
        "turn_id": "turn_456"
    }
    
    # 두 번째 이벤트
    event2 = {
        "message": "test event 2",
        "level": "ERROR",
        "conversation_id": "conv_123",
        "turn_id": "turn_789"
    }
    
    # 두 이벤트 모두 추가되어야 함
    result1 = ls.append_log(event1)
    result2 = ls.append_log(event2)
    
    assert result1 is True
    assert result2 is True
    
    # Idempotency 확인
    assert ls.check_idempotency("conv_123", "turn_456") is True
    assert ls.check_idempotency("conv_123", "turn_789") is True
    
    # 처리되지 않은 이벤트 확인
    assert ls.check_idempotency("conv_123", "turn_999") is False


def test_log_store_idempotency_statistics(log_store_instance):
    """LogStore의 Idempotency 통계 테스트"""
    ls = log_store_instance
    
    # 초기 통계
    stats = ls.get_idempotency_statistics()
    assert stats["processed_events_count"] == 0
    assert stats["cached_results_count"] == 0
    
    # 이벤트 추가
    event = {
        "message": "test event",
        "level": "INFO",
        "conversation_id": "conv_123",
        "turn_id": "turn_456"
    }
    ls.append_log(event)
    
    # 통계 확인
    stats = ls.get_idempotency_statistics()
    assert stats["processed_events_count"] == 1
    assert stats["cached_results_count"] == 1
    assert stats["cache_size_bytes"] > 0


def test_log_store_clear_idempotency_cache(log_store_instance):
    """LogStore의 Idempotency 캐시 초기화 테스트"""
    ls = log_store_instance
    
    # 이벤트 추가
    event = {
        "message": "test event",
        "level": "INFO",
        "conversation_id": "conv_123",
        "turn_id": "turn_456"
    }
    ls.append_log(event)
    
    # 캐시 확인
    assert ls.check_idempotency("conv_123", "turn_456") is True
    
    # 캐시 초기화
    ls.clear_idempotency_cache()
    
    # 캐시 확인
    assert ls.check_idempotency("conv_123", "turn_456") is False
    
    # 통계 확인
    stats = ls.get_idempotency_statistics()
    assert stats["processed_events_count"] == 0
    assert stats["cached_results_count"] == 0


def test_context_runtime_event_store_cache(context_runtime_instance):
    """ContextRuntime의 이벤트 저장소 캐시 테스트"""
    cr = context_runtime_instance
    
    # 이벤트 처리
    delta = {
        "path": "test_file.txt",
        "operation": "write",
        "producer_actual": "test_producer",
        "ts": time.time(),
        "conversation_id": "conv_123",
        "turn_id": "turn_456"
    }
    
    result1 = cr.handle_delta(delta)
    assert result1["success"] is True
    
    # 이벤트 저장소에서 결과 조회
    idempotency_key = ("conv_123", "turn_456")
    assert idempotency_key in cr.event_store
    assert cr.event_store[idempotency_key]["success"] is True
    
    # 동일한 이벤트 재처리 시 캐시된 결과 반환
    result2 = cr.handle_delta(delta)
    assert result2["success"] is False
    assert result2["error"] == "Event already processed"


def test_idempotency_key_generation_edge_cases(context_runtime_instance):
    """Idempotency 키 생성의 엣지 케이스 테스트"""
    cr = context_runtime_instance
    
    # conversation_id만 있는 경우
    delta1 = {
        "path": "test_file1.txt",
        "operation": "write",
        "producer_actual": "test_producer",
        "ts": time.time(),
        "conversation_id": "conv_123"
    }
    
    # turn_id만 있는 경우
    delta2 = {
        "path": "test_file2.txt",
        "operation": "write",
        "producer_actual": "test_producer",
        "ts": time.time(),
        "turn_id": "turn_456"
    }
    
    # 둘 다 없는 경우
    delta3 = {
        "path": "test_file3.txt",
        "operation": "write",
        "producer_actual": "test_producer",
        "ts": time.time()
    }
    
    # 모든 이벤트 처리
    result1 = cr.handle_delta(delta1)
    result2 = cr.handle_delta(delta2)
    result3 = cr.handle_delta(delta3)
    
    assert result1["success"] is True
    assert result2["success"] is True
    assert result3["success"] is True
    
    # Idempotency 키 확인
    assert result1["idempotency_key"] == ("conv_123", delta1["ts"])
    assert result2["idempotency_key"] == ("default", "turn_456")
    assert result3["idempotency_key"] == ("default", delta3["ts"])
    
    # 처리된 이벤트 수 확인
    assert len(cr.processed_events) == 3


if __name__ == "__main__":
    pytest.main([__file__])

