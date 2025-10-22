"""
상관관계 ID 테스트

전 구간에서 상관관계 ID가 일치하는지 테스트합니다.
"""

import pytest
import tempfile
import os
import time
from pathlib import Path
from memoryos.observe.standard_metrics import StandardMetrics


class TestCorrelationIds:
    """상관관계 ID 테스트 클래스"""
    
    def setup_method(self):
        """테스트 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.metrics_dir = os.path.join(self.temp_dir, "metrics")
        
    def teardown_method(self):
        """테스트 정리"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_correlation_id_generation(self):
        """상관관계 ID 생성 테스트"""
        metrics = StandardMetrics(self.metrics_dir)
        
        # 상관관계 ID 생성
        corr_id1 = metrics._generate_correlation_id("test_operation")
        corr_id2 = metrics._generate_correlation_id("test_operation")
        
        # ID가 다르고 형식이 올바른지 확인
        assert corr_id1 != corr_id2
        assert corr_id1.startswith(metrics.run_id)
        assert "test_operation" in corr_id1
        
        # 상관관계 ID가 저장되었는지 확인
        assert corr_id1 in metrics.correlation_ids
        assert corr_id2 in metrics.correlation_ids
        
    def test_correlation_id_info(self):
        """상관관계 ID 정보 테스트"""
        metrics = StandardMetrics(self.metrics_dir)
        
        # 상관관계 ID 생성
        corr_id = metrics._generate_correlation_id("test_operation")
        
        # 정보 조회
        info = metrics.get_correlation_info(corr_id)
        
        # 정보 확인
        assert info["operation"] == "test_operation"
        assert info["status"] == "active"
        assert "created_at" in info
        
    def test_correlation_id_completion(self):
        """상관관계 ID 완료 처리 테스트"""
        metrics = StandardMetrics(self.metrics_dir)
        
        # 상관관계 ID 생성
        corr_id = metrics._generate_correlation_id("test_operation")
        
        # 완료 처리
        success = metrics.complete_correlation(corr_id, "completed")
        
        # 완료 처리 확인
        assert success is True
        
        info = metrics.get_correlation_info(corr_id)
        assert info["status"] == "completed"
        assert "completed_at" in info
        
    def test_correlation_id_cleanup(self):
        """상관관계 ID 정리 테스트"""
        metrics = StandardMetrics(self.metrics_dir)
        
        # 여러 상관관계 ID 생성
        corr_ids = []
        for i in range(5):
            corr_id = metrics._generate_correlation_id(f"operation_{i}")
            corr_ids.append(corr_id)
            
        # 일부는 오래된 것으로 설정
        for i in range(3):
            metrics.correlation_ids[corr_ids[i]]["created_at"] = time.time() - 4000  # 4000초 전
            
        # 정리 수행
        cleaned_count = metrics.cleanup_old_correlations(max_age=3600)  # 1시간
        
        # 정리 결과 확인
        assert cleaned_count == 3
        
        # 남은 ID 확인
        remaining_ids = [corr_id for corr_id in corr_ids if corr_id in metrics.correlation_ids]
        assert len(remaining_ids) == 2
        
    def test_metrics_with_correlation_ids(self):
        """메트릭 기록 시 상관관계 ID 테스트"""
        metrics = StandardMetrics(self.metrics_dir)
        
        # 상관관계 ID로 메트릭 기록
        corr_id = metrics.record_hit()
        
        # 히트 데이터에 상관관계 ID가 포함되었는지 확인
        hit_record = metrics.hit_rate_data[-1]
        assert hit_record["correlation_id"] == corr_id
        assert hit_record["hit"] is True
        
        # 다른 메트릭도 테스트
        corr_id2 = metrics.record_latency(15.5)
        latency_record = metrics.latency_data[-1]
        assert latency_record["correlation_id"] == corr_id2
        assert latency_record["latency_ms"] == 15.5
        
    def test_rollup_metrics_with_correlation_ids(self):
        """롤업 메트릭에 상관관계 ID 포함 테스트"""
        metrics = StandardMetrics(self.metrics_dir)
        
        # 메트릭 기록
        metrics.record_hit()
        metrics.record_miss()
        metrics.record_latency(10.0)
        metrics.record_error("timeout")
        
        # 롤업 메트릭 생성
        rollup_data = metrics.generate_rollup_metrics()
        
        # 상관관계 ID 정보가 포함되었는지 확인
        assert "run_id" in rollup_data
        assert "active_correlations" in rollup_data
        assert rollup_data["run_id"] == metrics.run_id
        assert rollup_data["active_correlations"] > 0
        
    def test_correlation_id_persistence(self):
        """상관관계 ID 지속성 테스트"""
        metrics = StandardMetrics(self.metrics_dir)
        
        # 상관관계 ID 생성 및 메트릭 기록
        corr_id = metrics.record_hit()
        
        # 롤업 메트릭 저장
        metrics.save_rollup_metrics()
        
        # 저장된 파일 확인
        metrics_file = Path(self.metrics_dir) / "metrics.jsonl"
        assert metrics_file.exists()
        
        # 파일 내용 확인
        with open(metrics_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 롤업 데이터가 JSONL 형식으로 저장되었는지 확인
        assert "run_id" in content
        assert metrics.run_id in content
        
    def test_multiple_operations_correlation(self):
        """여러 작업의 상관관계 ID 테스트"""
        metrics = StandardMetrics(self.metrics_dir)
        
        # 동일한 상관관계 ID로 여러 작업 기록
        corr_id = metrics._generate_correlation_id("multi_operation")
        
        metrics.record_hit(corr_id)
        metrics.record_latency(20.0, corr_id)
        metrics.record_drift(1, "test_file.txt", corr_id)
        
        # 모든 기록에 동일한 상관관계 ID가 사용되었는지 확인
        hit_record = metrics.hit_rate_data[-1]
        latency_record = metrics.latency_data[-1]
        drift_record = metrics.drift_data[-1]
        
        assert hit_record["correlation_id"] == corr_id
        assert latency_record["correlation_id"] == corr_id
        assert drift_record["correlation_id"] == corr_id
        
    def test_correlation_id_across_time(self):
        """시간에 따른 상관관계 ID 테스트"""
        metrics = StandardMetrics(self.metrics_dir)
        
        # 시간 간격을 두고 메트릭 기록
        corr_id1 = metrics.record_hit()
        time.sleep(0.1)
        corr_id2 = metrics.record_hit()
        
        # 시간이 다르면 다른 ID가 생성되는지 확인
        assert corr_id1 != corr_id2
        
        # 두 ID 모두 유효한지 확인
        info1 = metrics.get_correlation_info(corr_id1)
        info2 = metrics.get_correlation_info(corr_id2)
        
        assert info1["operation"] == "hit"
        assert info2["operation"] == "hit"
        assert info1["created_at"] < info2["created_at"]


if __name__ == "__main__":
    pytest.main([__file__])

