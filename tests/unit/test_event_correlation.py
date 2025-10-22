import pytest
import json
import time
from pathlib import Path
from memoryos.observe.event_log import EventLog
from memoryos.core.context_runtime import ContextRuntime

@pytest.fixture
def event_log(tmp_path):
    """EventLog 인스턴스 생성"""
    log_file = tmp_path / "test_event.log"
    return EventLog(str(log_file), enable_signing=False)

@pytest.fixture
def context_runtime_with_event_log(tmp_path):
    """ContextRuntime with EventLog 인스턴스 생성"""
    config_file = tmp_path / "default.toml"
    config_file.write_text("""
[system]
version = "1.0"

[paths]
watch_paths = ["data/"]
catalog_file = "data/catalog.json"
memory_index_file = "data/memory_index.json"
snapshot_dir = "snapshots"
log_file = "logs/event_log.jsonl"

[signing]
enable_signing = false
""")
    (tmp_path / "data").mkdir()
    (tmp_path / "snapshots").mkdir()
    (tmp_path / "logs").mkdir()
    return ContextRuntime(str(config_file))

def test_event_log_initialization(event_log):
    """EventLog 초기화 테스트"""
    el = event_log
    
    assert el.current_run_id is not None
    assert el.current_run_id.startswith("run_")
    assert len(el.correlation_context) == 0
    assert el.event_counter == 0

def test_generate_run_id(event_log):
    """run_id 생성 테스트"""
    el = event_log
    
    run_id1 = el._generate_run_id()
    run_id2 = el._generate_run_id()
    
    assert run_id1 != run_id2
    assert run_id1.startswith("run_")
    assert run_id2.startswith("run_")
    
    # 타임스탬프와 UUID 포함 확인
    parts1 = run_id1.split("_")
    assert len(parts1) == 3
    assert parts1[0] == "run"
    assert parts1[1].isdigit()  # 타임스탬프
    assert len(parts1[2]) == 8  # UUID 첫 8자리

def test_generate_correlation_id(event_log):
    """correlation_id 생성 테스트"""
    el = event_log
    
    # 최상위 correlation_id
    corr_id1 = el._generate_correlation_id()
    corr_id2 = el._generate_correlation_id()
    
    assert corr_id1 != corr_id2
    assert corr_id1.startswith("corr_")
    assert corr_id2.startswith("corr_")
    assert el.event_counter == 2
    
    # 부모 correlation_id가 있는 경우
    parent_corr_id = "parent_corr_123"
    child_corr_id = el._generate_correlation_id(parent_corr_id)
    
    assert child_corr_id.startswith(parent_corr_id)
    assert "." in child_corr_id
    assert el.event_counter == 3

def test_propagate_correlation_id(event_log):
    """correlation_id 전파 테스트"""
    el = event_log
    
    event_data = {"test": "data"}
    correlation_id = el.propagate_correlation_id(event_data)
    
    assert correlation_id is not None
    assert "correlation_id" in event_data
    assert "run_id" in event_data
    assert "event_sequence" in event_data
    
    assert event_data["correlation_id"] == correlation_id
    assert event_data["run_id"] == el.current_run_id
    assert event_data["event_sequence"] == 1

def test_propagate_correlation_id_with_parent(event_log):
    """부모 correlation_id가 있는 경우 전파 테스트"""
    el = event_log
    
    event_data = {"test": "data"}
    parent_corr_id = "parent_corr_123"
    correlation_id = el.propagate_correlation_id(event_data, parent_corr_id)
    
    assert correlation_id is not None
    assert "parent_correlation_id" in event_data
    assert event_data["parent_correlation_id"] == parent_corr_id
    assert correlation_id.startswith(parent_corr_id)

def test_set_get_correlation_context(event_log):
    """correlation 컨텍스트 설정 및 조회 테스트"""
    el = event_log
    
    correlation_id = "test_corr_123"
    context = {"user_id": "user123", "session_id": "session456"}
    
    el.set_correlation_context(correlation_id, context)
    
    retrieved_context = el.get_correlation_context(correlation_id)
    assert retrieved_context["context"] == context
    assert retrieved_context["run_id"] == el.current_run_id
    assert "created_at" in retrieved_context

def test_start_new_run(event_log):
    """새로운 run 시작 테스트"""
    el = event_log
    
    original_run_id = el.current_run_id
    original_counter = el.event_counter
    
    # 컨텍스트 설정
    el.set_correlation_context("test_corr", {"test": "data"})
    assert len(el.correlation_context) == 1
    
    # 새로운 run 시작
    new_run_id = el.start_new_run()
    
    assert new_run_id != original_run_id
    assert el.current_run_id == new_run_id
    assert el.event_counter == 0
    assert len(el.correlation_context) == 0

def test_log_event_with_correlation_id(event_log):
    """correlation_id가 포함된 이벤트 로그 기록 테스트"""
    el = event_log
    
    event_type = "TEST_EVENT"
    event_data = {"message": "test message"}
    
    success = el.log_event(event_type, event_data)
    assert success
    
    # 로그 파일 확인
    assert el.log_file.exists()
    
    with open(el.log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        assert len(lines) == 1
        
        log_entry = json.loads(lines[0])
        assert log_entry["event_type"] == event_type
        assert log_entry["event_data"] == event_data
        assert "correlation_id" in log_entry
        assert "run_id" in log_entry
        assert "event_sequence" in log_entry
        assert log_entry["run_id"] == el.current_run_id

def test_log_event_with_existing_correlation_id(event_log):
    """기존 correlation_id를 사용한 이벤트 로그 기록 테스트"""
    el = event_log
    
    event_type = "TEST_EVENT"
    event_data = {"message": "test message"}
    existing_corr_id = "existing_corr_123"
    
    success = el.log_event(event_type, event_data, correlation_id=existing_corr_id)
    assert success
    
    with open(el.log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        log_entry = json.loads(lines[0])
        assert log_entry["correlation_id"] == existing_corr_id

def test_log_event_with_parent_correlation_id(event_log):
    """부모 correlation_id가 있는 이벤트 로그 기록 테스트"""
    el = event_log
    
    event_type = "CHILD_EVENT"
    event_data = {"message": "child message"}
    parent_corr_id = "parent_corr_123"
    
    success = el.log_event(event_type, event_data, parent_correlation_id=parent_corr_id)
    assert success
    
    with open(el.log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        log_entry = json.loads(lines[0])
        assert "parent_correlation_id" in log_entry
        assert log_entry["parent_correlation_id"] == parent_corr_id
        assert log_entry["correlation_id"].startswith(parent_corr_id)

def test_context_runtime_correlation_integration(context_runtime_with_event_log):
    """ContextRuntime과 EventLog의 correlation ID 통합 테스트"""
    cr = context_runtime_with_event_log
    
    # EventLog 인스턴스 확인
    assert hasattr(cr, 'event_log')
    assert cr.event_log is not None
    
    # 현재 run_id 확인
    run_id = cr.event_log.get_current_run_id()
    assert run_id is not None
    assert run_id.startswith("run_")

def test_context_runtime_delta_processing_with_correlation(context_runtime_with_event_log):
    """ContextRuntime의 delta 처리 시 correlation ID 전파 테스트"""
    cr = context_runtime_with_event_log
    
    # Delta 이벤트 생성
    delta = {
        "path": "data/test.txt",
        "operation": "write",
        "producer_actual": "test_module",
        "ts": time.time(),
        "conversation_id": "test_conv",
        "turn_id": "test_turn"
    }
    
    # Delta 처리
    result = cr.handle_delta(delta)
    
    # 결과에 correlation ID 포함 확인
    assert "correlation_id" in result
    assert "run_id" in result
    assert result["run_id"] == cr.event_log.get_current_run_id()
    
    # 이벤트 로그 파일 확인
    log_file = Path(cr.event_log.log_file)
    assert log_file.exists()
    
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        assert len(lines) >= 2  # DELTA_PROCESSING + DELTA_SUCCESS 또는 SYNC_FAILURE
        
        # 첫 번째 로그 엔트리 확인 (DELTA_PROCESSING)
        first_entry = json.loads(lines[0])
        assert first_entry["event_type"] == "DELTA_PROCESSING"
        assert first_entry["correlation_id"] == result["correlation_id"]
        assert first_entry["run_id"] == result["run_id"]

def test_correlation_id_hierarchy(event_log):
    """correlation ID 계층 구조 테스트"""
    el = event_log
    
    # 최상위 이벤트
    root_event = {"type": "root"}
    root_corr_id = el.propagate_correlation_id(root_event)
    
    # 자식 이벤트 1
    child1_event = {"type": "child1"}
    child1_corr_id = el.propagate_correlation_id(child1_event, root_corr_id)
    
    # 자식 이벤트 2
    child2_event = {"type": "child2"}
    child2_corr_id = el.propagate_correlation_id(child2_event, root_corr_id)
    
    # 손자 이벤트
    grandchild_event = {"type": "grandchild"}
    grandchild_corr_id = el.propagate_correlation_id(grandchild_event, child1_corr_id)
    
    # 계층 구조 확인
    assert root_corr_id.startswith("corr_")
    assert child1_corr_id.startswith(root_corr_id)
    assert child2_corr_id.startswith(root_corr_id)
    assert grandchild_corr_id.startswith(child1_corr_id)
    
    # 각 이벤트의 시퀀스 번호 확인
    assert root_event["event_sequence"] == 1
    assert child1_event["event_sequence"] == 2
    assert child2_event["event_sequence"] == 3
    assert grandchild_event["event_sequence"] == 4

def test_correlation_context_persistence(event_log):
    """correlation 컨텍스트 지속성 테스트"""
    el = event_log
    
    correlation_id = "persistent_corr_123"
    context = {"user_id": "user123", "session_id": "session456", "data": {"key": "value"}}
    
    # 컨텍스트 설정
    el.set_correlation_context(correlation_id, context)
    
    # 컨텍스트 조회
    retrieved = el.get_correlation_context(correlation_id)
    assert retrieved["context"] == context
    assert retrieved["run_id"] == el.current_run_id
    
    # 존재하지 않는 correlation_id 조회
    non_existent = el.get_correlation_context("non_existent_corr")
    assert non_existent == {}

def test_event_counter_increment(event_log):
    """이벤트 카운터 증가 테스트"""
    el = event_log
    
    initial_counter = el.event_counter
    
    # 여러 이벤트 생성
    for i in range(5):
        event_data = {"index": i}
        el.propagate_correlation_id(event_data)
    
    assert el.event_counter == initial_counter + 5
    
    # 새로운 run 시작 후 카운터 초기화 확인
    el.start_new_run()
    assert el.event_counter == 0

