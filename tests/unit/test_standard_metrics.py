import pytest
import json
import time
from pathlib import Path
from memoryos.observe.metrics import StandardMetricsCollector

@pytest.fixture
def metrics_collector():
    """StandardMetricsCollector 인스턴스 생성"""
    return StandardMetricsCollector(window_size=100, rollup_interval=1)  # 짧은 간격으로 테스트

@pytest.fixture
def temp_rollup_file(tmp_path):
    """임시 롤업 파일 경로"""
    return tmp_path / "test_metrics.jsonl"

def test_metrics_collector_initialization(metrics_collector):
    """StandardMetricsCollector 초기화 테스트"""
    mc = metrics_collector
    
    assert mc.window_size == 100
    assert mc.rollup_interval == 1
    assert len(mc.delta_times) == 0
    assert len(mc.drift_events) == 0
    assert len(mc.operation_times) == 0
    assert len(mc.cache_hits) == 0
    assert len(mc.error_events) == 0
    assert len(mc.rollup_data) == 0
    
    # 초기 메트릭 확인
    assert mc.current_metrics["hit_rate"] == 0.0
    assert mc.current_metrics["token_saving"] == 0.0
    assert mc.current_metrics["avg_latency_ms"] == 0.0
    assert mc.current_metrics["error_rate"] == 0.0
    assert mc.current_metrics["drift_levels"] == {"L1": 0, "L2": 0, "L3": 0}

def test_record_cache_hit_miss(metrics_collector):
    """캐시 히트/미스 기록 테스트"""
    mc = metrics_collector
    
    # 캐시 히트 기록
    mc.record_cache_hit("memory")
    mc.record_cache_hit("disk")
    
    # 캐시 미스 기록
    mc.record_cache_miss("memory")
    
    assert len(mc.cache_hits) == 3
    
    # 히트율 계산
    hit_rate = mc.calculate_hit_rate()
    assert hit_rate == 2/3  # 2 hits out of 3 total

def test_record_error(metrics_collector):
    """오류 이벤트 기록 테스트"""
    mc = metrics_collector
    
    mc.record_error("IO_ERROR", "File not found")
    mc.record_error("VALIDATION_ERROR", "Invalid data format")
    
    assert len(mc.error_events) == 2
    
    # 오류율 계산
    error_rate = mc.calculate_error_rate()
    assert error_rate == 1.0  # 2 errors out of 2 total operations (no successful operations)

def test_calculate_hit_rate(metrics_collector):
    """캐시 히트율 계산 테스트"""
    mc = metrics_collector
    
    # 초기 히트율
    assert mc.calculate_hit_rate() == 0.0
    
    # 히트/미스 기록
    for _ in range(5):
        mc.record_cache_hit("memory")
    for _ in range(3):
        mc.record_cache_miss("memory")
    
    hit_rate = mc.calculate_hit_rate()
    assert hit_rate == 5/8  # 5 hits out of 8 total

def test_calculate_token_saving(metrics_collector):
    """토큰 절약량 계산 테스트 (Placeholder)"""
    mc = metrics_collector
    
    # 히트율에 따른 토큰 절약량 계산
    mc.record_cache_hit("memory")
    mc.record_cache_hit("memory")
    mc.record_cache_miss("memory")
    
    token_saving = mc.calculate_token_saving()
    hit_rate = mc.calculate_hit_rate()
    expected_saving = hit_rate * 1000  # Placeholder 계산식
    
    assert token_saving == expected_saving

def test_calculate_avg_latency_ms(metrics_collector):
    """평균 지연시간 계산 테스트"""
    mc = metrics_collector
    
    # 초기 지연시간
    assert mc.calculate_avg_latency_ms() == 0.0
    
    # 작업 시간 기록
    mc.record_operation_time("file_read", 0.1)  # 100ms
    mc.record_operation_time("file_write", 0.2)  # 200ms
    mc.record_operation_time("cache_lookup", 0.05)  # 50ms
    
    avg_latency = mc.calculate_avg_latency_ms()
    expected_avg = ((0.1 + 0.2 + 0.05) / 3) * 1000  # 평균을 밀리초로 변환
    
    assert avg_latency == pytest.approx(expected_avg, rel=1e-6)

def test_calculate_error_rate(metrics_collector):
    """오류율 계산 테스트"""
    mc = metrics_collector
    
    # 초기 오류율
    assert mc.calculate_error_rate() == 0.0
    
    # 성공 작업 기록
    mc.record_operation_time("success_op", 0.1)
    mc.record_operation_time("success_op", 0.2)
    
    # 오류 작업 기록
    mc.record_error("ERROR", "Test error")
    
    error_rate = mc.calculate_error_rate()
    assert error_rate == 1/3  # 1 error out of 3 total operations

def test_calculate_drift_levels(metrics_collector):
    """Drift 레벨별 통계 계산 테스트"""
    mc = metrics_collector
    
    # 초기 drift 레벨
    drift_levels = mc.calculate_drift_levels()
    assert drift_levels == {"L1": 0, "L2": 0, "L3": 0}
    
    # Drift 이벤트 기록
    mc.record_drift_event(1, "file1.txt")  # L1
    mc.record_drift_event(1, "file2.txt")  # L1
    mc.record_drift_event(2, "file3.txt")  # L2
    mc.record_drift_event(3, "file4.txt")  # L3
    
    drift_levels = mc.calculate_drift_levels()
    assert drift_levels == {"L1": 2, "L2": 1, "L3": 1}

def test_update_metrics(metrics_collector):
    """표준 메트릭 업데이트 테스트"""
    mc = metrics_collector
    
    # 데이터 기록
    mc.record_cache_hit("memory")
    mc.record_cache_miss("memory")
    mc.record_operation_time("test_op", 0.1)
    mc.record_drift_event(1, "test.txt")
    
    # 메트릭 업데이트
    metrics = mc.update_metrics()
    
    # 표준 메트릭 확인
    assert "hit_rate" in metrics
    assert "token_saving" in metrics
    assert "avg_latency_ms" in metrics
    assert "error_rate" in metrics
    assert "drift_levels" in metrics
    assert "timestamp" in metrics
    
    assert metrics["hit_rate"] == 0.5  # 1 hit out of 2 total
    assert metrics["avg_latency_ms"] == 100.0  # 0.1초 = 100ms
    assert metrics["drift_levels"]["L1"] == 1

def test_rollup_functionality(metrics_collector, temp_rollup_file):
    """1분 롤업 기능 테스트"""
    mc = metrics_collector
    mc.rollup_file = temp_rollup_file
    
    # 데이터 기록
    mc.record_cache_hit("memory")
    mc.record_operation_time("test_op", 0.1)
    
    # 메트릭 업데이트 (롤업 트리거)
    mc.update_metrics()
    
    # 롤업 파일 존재 확인
    assert temp_rollup_file.exists()
    
    # 롤업 데이터 확인
    with open(temp_rollup_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        assert len(lines) > 0
        
        # 첫 번째 롤업 엔트리 파싱
        rollup_entry = json.loads(lines[0])
        assert "timestamp" in rollup_entry
        assert "iso_timestamp" in rollup_entry
        assert "metrics" in rollup_entry
        assert "summary" in rollup_entry
        
        # 메트릭 확인
        metrics = rollup_entry["metrics"]
        assert "hit_rate" in metrics
        assert "token_saving" in metrics
        assert "avg_latency_ms" in metrics
        assert "error_rate" in metrics
        assert "drift_levels" in metrics

def test_load_rollup_from_file(metrics_collector, temp_rollup_file):
    """롤업 파일에서 데이터 로드 테스트"""
    mc = metrics_collector
    mc.rollup_file = temp_rollup_file
    
    # 테스트 롤업 데이터 생성
    test_rollup_entry = {
        "timestamp": time.time(),
        "iso_timestamp": "2024-01-01T00:00:00",
        "metrics": {
            "hit_rate": 0.8,
            "token_saving": 800.0,
            "avg_latency_ms": 150.0,
            "error_rate": 0.1,
            "drift_levels": {"L1": 2, "L2": 1, "L3": 0}
        },
        "summary": {
            "total_cache_events": 10,
            "total_drift_events": 3,
            "total_operations": 5,
            "total_errors": 1,
            "window_size": 100
        }
    }
    
    # 롤업 파일에 데이터 쓰기
    with open(temp_rollup_file, 'w', encoding='utf-8') as f:
        f.write(json.dumps(test_rollup_entry, ensure_ascii=False) + '\n')
    
    # 롤업 데이터 로드
    mc.load_rollup_from_file()
    
    assert len(mc.rollup_data) == 1
    assert mc.rollup_data[0]["metrics"]["hit_rate"] == 0.8

def test_get_rollup_data(metrics_collector):
    """롤업 데이터 조회 테스트"""
    mc = metrics_collector
    
    # 테스트 롤업 데이터 추가
    current_time = time.time()
    mc.rollup_data = [
        {
            "timestamp": current_time - 7200,  # 2시간 전
            "metrics": {"hit_rate": 0.5}
        },
        {
            "timestamp": current_time - 1800,  # 30분 전
            "metrics": {"hit_rate": 0.7}
        },
        {
            "timestamp": current_time - 300,    # 5분 전
            "metrics": {"hit_rate": 0.9}
        }
    ]
    
    # 1시간 윈도우로 조회
    recent_rollup = mc.get_rollup_data(time_window=3600)
    assert len(recent_rollup) == 2  # 30분 전, 5분 전 데이터만
    
    # 10분 윈도우로 조회
    very_recent_rollup = mc.get_rollup_data(time_window=600)
    assert len(very_recent_rollup) == 1  # 5분 전 데이터만

def test_export_rollup_data(metrics_collector, tmp_path):
    """롤업 데이터 내보내기 테스트"""
    mc = metrics_collector
    
    # 테스트 롤업 데이터 추가
    mc.rollup_data = [
        {
            "timestamp": time.time(),
            "metrics": {"hit_rate": 0.8},
            "summary": {"total_cache_events": 10}
        }
    ]
    
    # 내보내기
    export_file = tmp_path / "exported_rollup.json"
    success = mc.export_rollup_data(str(export_file))
    
    assert success
    assert export_file.exists()
    
    # 내보낸 데이터 확인
    with open(export_file, 'r', encoding='utf-8') as f:
        export_data = json.load(f)
        
    assert "exported_at" in export_data
    assert "rollup_entries" in export_data
    assert "total_entries" in export_data
    assert export_data["total_entries"] == 1

def test_get_metrics_summary(metrics_collector):
    """메트릭 요약 정보 조회 테스트"""
    mc = metrics_collector
    
    # 데이터 기록
    mc.record_cache_hit("memory")
    mc.record_drift_event(1, "test.txt")
    mc.record_operation_time("test_op", 0.1)
    mc.record_error("ERROR", "Test error")
    
    summary = mc.get_metrics_summary()
    
    assert "current_metrics" in summary
    assert "total_cache_events" in summary
    assert "total_drift_events" in summary
    assert "total_operations" in summary
    assert "total_errors" in summary
    assert "rollup_entries_count" in summary
    assert "last_calculation" in summary
    assert "last_rollup" in summary
    
    assert summary["total_cache_events"] == 1
    assert summary["total_drift_events"] == 1
    assert summary["total_operations"] == 1
    assert summary["total_errors"] == 1

def test_reset_metrics(metrics_collector):
    """메트릭 데이터 초기화 테스트"""
    mc = metrics_collector
    
    # 데이터 기록
    mc.record_cache_hit("memory")
    mc.record_drift_event(1, "test.txt")
    mc.record_operation_time("test_op", 0.1)
    mc.record_error("ERROR", "Test error")
    
    # 초기화 전 확인
    assert len(mc.cache_hits) == 1
    assert len(mc.drift_events) == 1
    assert len(mc.operation_times) == 1
    assert len(mc.error_events) == 1
    
    # 초기화
    mc.reset_metrics()
    
    # 초기화 후 확인
    assert len(mc.cache_hits) == 0
    assert len(mc.drift_events) == 0
    assert len(mc.operation_times) == 0
    assert len(mc.error_events) == 0
    assert len(mc.rollup_data) == 0
    
    # 메트릭 초기값 확인
    assert mc.current_metrics["hit_rate"] == 0.0
    assert mc.current_metrics["token_saving"] == 0.0
    assert mc.current_metrics["avg_latency_ms"] == 0.0
    assert mc.current_metrics["error_rate"] == 0.0
    assert mc.current_metrics["drift_levels"] == {"L1": 0, "L2": 0, "L3": 0}

