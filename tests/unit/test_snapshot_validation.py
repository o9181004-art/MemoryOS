import pytest
import json
import time
from pathlib import Path
from memoryos.core.snapshot_generator import SnapshotGenerator

@pytest.fixture
def snapshot_generator(tmp_path):
    """SnapshotGenerator 인스턴스 생성"""
    snapshot_dir = tmp_path / "snapshots"
    return SnapshotGenerator(str(snapshot_dir))

@pytest.fixture
def sample_memory_index():
    """샘플 메모리 인덱스 데이터"""
    return {
        "files": {
            "data/file1.txt": {
                "hash": "a" * 64,
                "producer_actual": "module_A",
                "producer_expected": "module_A",
                "last_updated": time.time(),
                "update_interval": 300,
                "metadata": {"version": 1}
            },
            "data/file2.txt": {
                "hash": "b" * 64,
                "producer_actual": "module_B",
                "producer_expected": "module_B",
                "last_updated": time.time() - 3600,  # 1시간 전
                "update_interval": 600,
                "metadata": {"version": 2}
            }
        },
        "catalog": {
            "data/file1.txt": {
                "producer_expected": "module_A",
                "consumer_expected": ["consumer_A"],
                "update_interval": 300
            }
        }
    }

@pytest.fixture
def sample_hash_chain():
    """샘플 Hash Chain 데이터"""
    return [
        {
            "index": 0,
            "timestamp": time.time() - 1000,
            "data": {"file": "file1.txt"},
            "prev_hash": None,
            "hash": "c" * 64,
            "merkle_root": "d" * 64
        },
        {
            "index": 1,
            "timestamp": time.time() - 500,
            "data": {"file": "file2.txt"},
            "prev_hash": "c" * 64,
            "hash": "e" * 64,
            "merkle_root": "f" * 64
        }
    ]

def test_snapshot_generator_initialization(snapshot_generator):
    """SnapshotGenerator 초기화 테스트"""
    sg = snapshot_generator
    
    assert sg.snapshot_dir.exists()
    assert sg.schema_version == "1.0.0"
    assert sg.schema is not None

def test_generate_snapshot_with_strict_validation(snapshot_generator, sample_memory_index, sample_hash_chain):
    """Strict Validation을 포함한 스냅샷 생성 테스트"""
    sg = snapshot_generator
    
    snapshot = sg.generate_snapshot(sample_memory_index, sample_hash_chain)
    
    # 필수 필드 존재 확인
    required_fields = [
        "schema_version", "snapshot_id", "timestamp", "memory_index",
        "drift_status", "hash_chain", "quarantine_status", 
        "performance_metrics", "system_info"
    ]
    
    for field in required_fields:
        assert field in snapshot, f"Missing required field: {field}"
        assert snapshot[field] is not None, f"Required field '{field}' is null"
    
    # 스키마 버전 확인
    assert snapshot["schema_version"] == "1.0.0"
    
    # 스냅샷 ID 형식 확인
    assert snapshot["snapshot_id"].startswith("snap_")
    
    # 타임스탬프 확인
    assert isinstance(snapshot["timestamp"], (int, float))
    assert snapshot["timestamp"] > 0

def test_validate_snapshot_success(snapshot_generator, sample_memory_index, sample_hash_chain):
    """스냅샷 검증 성공 테스트"""
    sg = snapshot_generator
    
    snapshot = sg.generate_snapshot(sample_memory_index, sample_hash_chain)
    validation_result = sg.validate_snapshot(snapshot)
    
    assert validation_result["is_valid"] == True
    assert len(validation_result["errors"]) == 0

def test_validate_snapshot_missing_required_fields(snapshot_generator):
    """필수 필드 누락 시 검증 실패 테스트"""
    sg = snapshot_generator
    
    # 필수 필드가 누락된 스냅샷
    incomplete_snapshot = {
        "schema_version": "1.0.0",
        "snapshot_id": "test_snap",
        # "timestamp" 누락
        "memory_index": {"files": {}},
        # "drift_status" 누락
        "hash_chain": {"chain_length": 0},
        "quarantine_status": {"quarantined_files": []},
        "performance_metrics": {"hit_rate": 1.0},
        "system_info": {"version": "1.0.0"}
    }
    
    validation_result = sg.validate_snapshot(incomplete_snapshot)
    
    assert validation_result["is_valid"] == False
    assert len(validation_result["errors"]) > 0
    assert any("Missing required field: timestamp" in error for error in validation_result["errors"])
    assert any("Missing required field: drift_status" in error for error in validation_result["errors"])

def test_validate_snapshot_null_required_fields(snapshot_generator):
    """필수 필드가 null인 경우 검증 실패 테스트"""
    sg = snapshot_generator
    
    # 필수 필드가 null인 스냅샷
    null_snapshot = {
        "schema_version": "1.0.0",
        "snapshot_id": "test_snap",
        "timestamp": None,  # null 값
        "memory_index": {"files": {}},
        "drift_status": {"total_files": 0},
        "hash_chain": {"chain_length": 0},
        "quarantine_status": {"quarantined_files": []},
        "performance_metrics": {"hit_rate": 1.0},
        "system_info": {"version": "1.0.0"}
    }
    
    validation_result = sg.validate_snapshot(null_snapshot)
    
    assert validation_result["is_valid"] == False
    assert any("Required field 'timestamp' is null" in error for error in validation_result["errors"])

def test_validate_nested_required_fields(snapshot_generator):
    """중첩 객체의 필수 필드 검증 테스트"""
    sg = snapshot_generator
    
    # 중첩 필드가 누락된 스냅샷
    nested_incomplete_snapshot = {
        "schema_version": "1.0.0",
        "snapshot_id": "test_snap",
        "timestamp": time.time(),
        "memory_index": {
            "files": {
                "data/test.txt": {
                    "hash": "a" * 64,
                    # "producer_actual" 누락
                    "producer_expected": "module_A",
                    "last_updated": time.time()
                }
            }
        },
        "drift_status": {
            "total_files": 1,
            "active_files": 1,
            "stale_files": 0,
            "error_files": 0,
            "drift_counts": {"0": 1, "1": 0, "2": 0, "3": 0}
        },
        "hash_chain": {
            "chain_length": 0,
            "latest_hash": "0" * 64,
            "merkle_root": "0" * 64,
            "integrity_verified": True
        },
        "quarantine_status": {
            "quarantined_files": [],
            "quarantine_count": 0,
            "auto_release_candidates": []
        },
        "performance_metrics": {
            "hit_rate": 1.0,
            "avg_latency_ms": 0.0,
            "error_rate": 0.0,
            "drift_levels": {"L1": 0, "L2": 0, "L3": 0}
        },
        "system_info": {
            "version": "1.0.0",
            "uptime_seconds": time.time(),
            "config_hash": "0" * 64
        }
    }
    
    validation_result = sg.validate_snapshot(nested_incomplete_snapshot)
    
    assert validation_result["is_valid"] == False
    assert any("Missing required field 'producer_actual' in file" in error for error in validation_result["errors"])

def test_prepare_memory_index(snapshot_generator, sample_memory_index):
    """메모리 인덱스 데이터 준비 테스트"""
    sg = snapshot_generator
    
    prepared = sg._prepare_memory_index(sample_memory_index)
    
    assert "files" in prepared
    assert "catalog" in prepared
    
    # 파일 데이터 검증
    files = prepared["files"]
    assert len(files) == 2
    
    for file_path, file_info in files.items():
        required_fields = ["hash", "producer_actual", "producer_expected", "last_updated", "update_interval", "metadata"]
        for field in required_fields:
            assert field in file_info, f"Missing field '{field}' in file {file_path}"
            assert file_info[field] is not None, f"Field '{field}' is null in file {file_path}"

def test_prepare_hash_chain(snapshot_generator, sample_hash_chain):
    """Hash Chain 데이터 준비 테스트"""
    sg = snapshot_generator
    
    prepared = sg._prepare_hash_chain(sample_hash_chain)
    
    required_fields = ["chain_length", "latest_hash", "merkle_root", "integrity_verified"]
    for field in required_fields:
        assert field in prepared, f"Missing field '{field}' in hash_chain"
        assert prepared[field] is not None, f"Field '{field}' is null in hash_chain"
    
    assert prepared["chain_length"] == 2
    assert prepared["integrity_verified"] == True

def test_prepare_hash_chain_empty(snapshot_generator):
    """빈 Hash Chain 데이터 준비 테스트"""
    sg = snapshot_generator
    
    prepared = sg._prepare_hash_chain([])
    
    assert prepared["chain_length"] == 0
    assert prepared["latest_hash"] == "0" * 64
    assert prepared["merkle_root"] == "0" * 64
    assert prepared["integrity_verified"] == True

def test_generate_drift_status(snapshot_generator, sample_memory_index):
    """Drift 상태 생성 테스트"""
    sg = snapshot_generator
    
    drift_status = sg._generate_drift_status(sample_memory_index)
    
    required_fields = ["total_files", "active_files", "stale_files", "error_files", "drift_counts"]
    for field in required_fields:
        assert field in drift_status, f"Missing field '{field}' in drift_status"
        assert drift_status[field] is not None, f"Field '{field}' is null in drift_status"
    
    assert drift_status["total_files"] == 2
    assert drift_status["active_files"] == 1  # file1.txt는 최신
    assert drift_status["stale_files"] == 1   # file2.txt는 1시간 전
    assert drift_status["error_files"] == 0

def test_create_fallback_snapshot(snapshot_generator):
    """Fallback 스냅샷 생성 테스트"""
    sg = snapshot_generator
    timestamp = time.time()
    
    fallback = sg._create_fallback_snapshot(timestamp)
    
    # 모든 필수 필드가 존재하는지 확인
    required_fields = [
        "schema_version", "snapshot_id", "timestamp", "memory_index",
        "drift_status", "hash_chain", "quarantine_status", 
        "performance_metrics", "system_info"
    ]
    
    for field in required_fields:
        assert field in fallback, f"Missing required field: {field}"
        assert fallback[field] is not None, f"Required field '{field}' is null"
    
    # Fallback 스냅샷 검증
    validation_result = sg.validate_snapshot(fallback)
    assert validation_result["is_valid"] == True

def test_save_and_load_snapshot(snapshot_generator, sample_memory_index, sample_hash_chain):
    """스냅샷 저장 및 로드 테스트"""
    sg = snapshot_generator
    
    snapshot = sg.generate_snapshot(sample_memory_index, sample_hash_chain)
    saved_path = sg.save_snapshot(snapshot)
    
    assert Path(saved_path).exists()
    
    # 로드 테스트
    loaded_snapshot = sg.load_snapshot(Path(saved_path).name)
    assert loaded_snapshot is not None
    assert loaded_snapshot["snapshot_id"] == snapshot["snapshot_id"]
    
    # 로드된 스냅샷 검증
    validation_result = sg.validate_snapshot(loaded_snapshot)
    assert validation_result["is_valid"] == True

def test_schema_versioning(snapshot_generator):
    """스키마 버전 관리 테스트"""
    sg = snapshot_generator
    
    # 스키마 버전 확인
    assert sg.schema_version == "1.0.0"
    
    # 생성된 스냅샷의 스키마 버전 확인
    snapshot = sg.generate_snapshot({}, [])
    assert snapshot["schema_version"] == "1.0.0"
    
    # 스키마 버전 변경 테스트
    sg.schema_version = "1.1.0"
    snapshot_v2 = sg.generate_snapshot({}, [])
    assert snapshot_v2["schema_version"] == "1.1.0"

