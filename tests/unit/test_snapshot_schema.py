"""
스냅샷 스키마 검증 테스트

JSON Schema 검증 및 추가 검증 규칙을 테스트합니다.
"""

import pytest
import tempfile
import os
import json
import time
from pathlib import Path
from memoryos.core.snapshot_generator import SnapshotGenerator


class TestSnapshotSchema:
    """스냅샷 스키마 검증 테스트 클래스"""
    
    def setup_method(self):
        """테스트 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.snapshot_dir = os.path.join(self.temp_dir, "snapshots")
        
    def teardown_method(self):
        """테스트 정리"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_valid_snapshot_validation(self):
        """유효한 스냅샷 검증 테스트"""
        generator = SnapshotGenerator(self.snapshot_dir)
        
        # 유효한 스냅샷 데이터
        valid_snapshot = {
            "schema_version": "1.0.0",
            "snapshot_id": "test_snapshot_001",
            "timestamp": time.time(),
            "memory_index": {
                "files": {
                    "test_file.txt": {
                        "hash": "a" * 64,  # 64자리 hex
                        "producer_actual": "test_producer",
                        "producer_expected": "test_producer",
                        "last_updated": time.time(),
                        "update_interval": 30,
                        "metadata": {}
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
                "chain_length": 1,
                "latest_hash": "b" * 64,
                "merkle_root": "c" * 64,
                "integrity_verified": True
            },
            "quarantine_status": {
                "quarantined_files": [],
                "quarantine_count": 0,
                "auto_release_candidates": []
            },
            "performance_metrics": {
                "hit_rate": 0.95,
                "avg_latency_ms": 10.5,
                "error_rate": 0.01,
                "drift_levels": {"L1": 0, "L2": 0, "L3": 0}
            },
            "system_info": {
                "version": "1.0.0",
                "uptime_seconds": 3600,
                "config_hash": "d" * 64
            }
        }
        
        # 검증 수행
        result = generator.validate_snapshot(valid_snapshot)
        
        # 결과 확인
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0
        
    def test_invalid_schema_version(self):
        """잘못된 스키마 버전 테스트"""
        generator = SnapshotGenerator(self.snapshot_dir)
        
        # 잘못된 스키마 버전
        invalid_snapshot = {
            "schema_version": "2.0.0",  # 잘못된 버전
            "snapshot_id": "test_snapshot_002",
            "timestamp": time.time(),
            "memory_index": {"files": {}},
            "drift_status": {
                "total_files": 0, "active_files": 0, "stale_files": 0, "error_files": 0,
                "drift_counts": {"0": 0, "1": 0, "2": 0, "3": 0}
            },
            "hash_chain": {
                "chain_length": 0, "latest_hash": "a" * 64, "merkle_root": "b" * 64,
                "integrity_verified": True
            },
            "quarantine_status": {
                "quarantined_files": [], "quarantine_count": 0, "auto_release_candidates": []
            },
            "performance_metrics": {
                "hit_rate": 0.0, "avg_latency_ms": 0.0, "error_rate": 0.0,
                "drift_levels": {"L1": 0, "L2": 0, "L3": 0}
            },
            "system_info": {
                "version": "1.0.0", "uptime_seconds": 0, "config_hash": "c" * 64
            }
        }
        
        # 검증 수행
        result = generator.validate_snapshot(invalid_snapshot)
        
        # 결과 확인
        assert result["is_valid"] is False
        assert any("Schema version mismatch" in error for error in result["errors"])
        
    def test_invalid_hash_format(self):
        """잘못된 해시 형식 테스트"""
        generator = SnapshotGenerator(self.snapshot_dir)
        
        # 잘못된 해시 형식
        invalid_snapshot = {
            "schema_version": "1.0.0",
            "snapshot_id": "test_snapshot_003",
            "timestamp": time.time(),
            "memory_index": {
                "files": {
                    "test_file.txt": {
                        "hash": "invalid_hash",  # 잘못된 해시 형식
                        "producer_actual": "test_producer",
                        "producer_expected": "test_producer",
                        "last_updated": time.time()
                    }
                }
            },
            "drift_status": {
                "total_files": 1, "active_files": 1, "stale_files": 0, "error_files": 0,
                "drift_counts": {"0": 1, "1": 0, "2": 0, "3": 0}
            },
            "hash_chain": {
                "chain_length": 1, "latest_hash": "a" * 64, "merkle_root": "b" * 64,
                "integrity_verified": True
            },
            "quarantine_status": {
                "quarantined_files": [], "quarantine_count": 0, "auto_release_candidates": []
            },
            "performance_metrics": {
                "hit_rate": 0.0, "avg_latency_ms": 0.0, "error_rate": 0.0,
                "drift_levels": {"L1": 0, "L2": 0, "L3": 0}
            },
            "system_info": {
                "version": "1.0.0", "uptime_seconds": 0, "config_hash": "c" * 64
            }
        }
        
        # 검증 수행
        result = generator.validate_snapshot(invalid_snapshot)
        
        # 결과 확인
        assert result["is_valid"] is False
        assert any("Invalid hash format" in error for error in result["errors"])
        
    def test_drift_status_mismatch(self):
        """Drift 상태 불일치 테스트"""
        generator = SnapshotGenerator(self.snapshot_dir)
        
        # Drift 상태 불일치
        invalid_snapshot = {
            "schema_version": "1.0.0",
            "snapshot_id": "test_snapshot_004",
            "timestamp": time.time(),
            "memory_index": {"files": {}},
            "drift_status": {
                "total_files": 10,  # 총 10개
                "active_files": 5,  # 활성 5개
                "stale_files": 3,   # 오래된 3개
                "error_files": 1,   # 오류 1개 (합계 9개, 불일치)
                "drift_counts": {"0": 5, "1": 3, "2": 1, "3": 1}
            },
            "hash_chain": {
                "chain_length": 0, "latest_hash": "a" * 64, "merkle_root": "b" * 64,
                "integrity_verified": True
            },
            "quarantine_status": {
                "quarantined_files": [], "quarantine_count": 0, "auto_release_candidates": []
            },
            "performance_metrics": {
                "hit_rate": 0.0, "avg_latency_ms": 0.0, "error_rate": 0.0,
                "drift_levels": {"L1": 0, "L2": 0, "L3": 0}
            },
            "system_info": {
                "version": "1.0.0", "uptime_seconds": 0, "config_hash": "c" * 64
            }
        }
        
        # 검증 수행
        result = generator.validate_snapshot(invalid_snapshot)
        
        # 결과 확인
        assert result["is_valid"] is False
        assert any("Drift status mismatch" in error for error in result["errors"])
        
    def test_missing_required_fields(self):
        """필수 필드 누락 테스트"""
        generator = SnapshotGenerator(self.snapshot_dir)
        
        # 필수 필드 누락
        invalid_snapshot = {
            "schema_version": "1.0.0",
            "snapshot_id": "test_snapshot_005",
            "timestamp": time.time(),
            # memory_index 누락
            "drift_status": {
                "total_files": 0, "active_files": 0, "stale_files": 0, "error_files": 0,
                "drift_counts": {"0": 0, "1": 0, "2": 0, "3": 0}
            },
            "hash_chain": {
                "chain_length": 0, "latest_hash": "a" * 64, "merkle_root": "b" * 64,
                "integrity_verified": True
            },
            "quarantine_status": {
                "quarantined_files": [], "quarantine_count": 0, "auto_release_candidates": []
            },
            "performance_metrics": {
                "hit_rate": 0.0, "avg_latency_ms": 0.0, "error_rate": 0.0,
                "drift_levels": {"L1": 0, "L2": 0, "L3": 0}
            },
            "system_info": {
                "version": "1.0.0", "uptime_seconds": 0, "config_hash": "c" * 64
            }
        }
        
        # 검증 수행
        result = generator.validate_snapshot(invalid_snapshot)
        
        # 결과 확인
        assert result["is_valid"] is False
        assert any("'memory_index' is a required property" in error for error in result["errors"])
        
    def test_invalid_chain_length(self):
        """잘못된 체인 길이 테스트"""
        generator = SnapshotGenerator(self.snapshot_dir)
        
        # 잘못된 체인 길이
        invalid_snapshot = {
            "schema_version": "1.0.0",
            "snapshot_id": "test_snapshot_006",
            "timestamp": time.time(),
            "memory_index": {"files": {}},
            "drift_status": {
                "total_files": 0, "active_files": 0, "stale_files": 0, "error_files": 0,
                "drift_counts": {"0": 0, "1": 0, "2": 0, "3": 0}
            },
            "hash_chain": {
                "chain_length": -1,  # 잘못된 체인 길이
                "latest_hash": "a" * 64,
                "merkle_root": "b" * 64,
                "integrity_verified": True
            },
            "quarantine_status": {
                "quarantined_files": [], "quarantine_count": 0, "auto_release_candidates": []
            },
            "performance_metrics": {
                "hit_rate": 0.0, "avg_latency_ms": 0.0, "error_rate": 0.0,
                "drift_levels": {"L1": 0, "L2": 0, "L3": 0}
            },
            "system_info": {
                "version": "1.0.0", "uptime_seconds": 0, "config_hash": "c" * 64
            }
        }
        
        # 검증 수행
        result = generator.validate_snapshot(invalid_snapshot)
        
        # 결과 확인
        assert result["is_valid"] is False
        assert any("Invalid chain length" in error for error in result["errors"])
        
    def test_schema_loading(self):
        """스키마 로딩 테스트"""
        generator = SnapshotGenerator(self.snapshot_dir)
        
        # 스키마가 로드되었는지 확인
        assert generator.schema is not None
        assert generator.schema_version == "1.0.0"
        
        # 스키마 구조 확인
        assert "properties" in generator.schema
        assert "required" in generator.schema
        
    def test_additional_validation_rules(self):
        """추가 검증 규칙 테스트"""
        generator = SnapshotGenerator(self.snapshot_dir)
        
        # 추가 검증 규칙 테스트
        test_data = {
            "schema_version": "1.0.0",
            "memory_index": {
                "files": {
                    "test.txt": {
                        "hash": "a" * 64,
                        "last_updated": 0  # 잘못된 시간
                    }
                }
            },
            "drift_status": {
                "total_files": 1, "active_files": 1, "stale_files": 0, "error_files": 0,
                "drift_counts": {"0": 1, "1": 0, "2": 0, "3": 0}
            }
        }
        
        errors = generator._validate_additional_rules(test_data)
        
        # 잘못된 시간에 대한 오류 확인
        assert any("Invalid last_updated time" in error for error in errors)


if __name__ == "__main__":
    pytest.main([__file__])

