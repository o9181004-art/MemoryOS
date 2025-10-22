"""
Unit Test: Producer Actual Trust Scoring

DataCatalog의 Producer 신뢰도 스코어링 기능을 테스트합니다.
실행 가능한 해시, 서명, 경로 기반 가중 점수를 검증합니다.
"""

import pytest
import hashlib
import time
from pathlib import Path
from memoryos.core.data_catalog import DataCatalog


@pytest.fixture
def data_catalog_instance(tmp_path):
    """테스트용 DataCatalog 인스턴스"""
    catalog_file = tmp_path / "test_catalog.json"
    return DataCatalog(str(catalog_file))


def test_calculate_producer_trust_score_basic(data_catalog_instance):
    """기본 Producer 신뢰도 점수 계산 테스트"""
    dc = data_catalog_instance
    producer = "test_producer"
    
    # 초기 점수
    score = dc.calculate_producer_trust_score(producer)
    assert score == 0.5  # 기본값
    
    # 성공 업데이트
    dc.update_producer_trust(producer, True)
    score = dc.calculate_producer_trust_score(producer)
    assert score > 0.5  # 성공 시 점수 증가
    
    # 실패 업데이트
    dc.update_producer_trust(producer, False)
    score = dc.calculate_producer_trust_score(producer)
    assert score < 0.5  # 실패 시 점수 감소


def test_register_producer_executable_hash(data_catalog_instance, tmp_path):
    """Producer 실행 가능한 해시 등록 테스트"""
    dc = data_catalog_instance
    producer = "test_producer"
    
    # 테스트용 실행 파일 생성
    test_file = tmp_path / "test_executable.py"
    test_file.write_text("print('Hello World')", encoding='utf-8')
    
    # 해시 등록
    dc.register_producer_executable_hash(producer, str(test_file))
    
    # 신뢰도 점수 확인
    score = dc.calculate_producer_trust_score(producer)
    assert score > 0.5  # 해시 등록으로 인한 점수 증가
    
    # 신뢰도 정보 확인
    trust_info = dc.get_producer_trust_info(producer)
    assert trust_info["executable_hash"] is not None
    assert len(trust_info["executable_hash"]) == 64  # SHA256 해시 길이


def test_verify_producer_signature(data_catalog_instance):
    """Producer 서명 검증 테스트"""
    dc = data_catalog_instance
    producer = "test_producer"
    data = "test_data"
    
    # 올바른 서명 생성
    correct_signature = hashlib.sha256(data.encode()).hexdigest()
    
    # 서명 검증 성공
    is_valid = dc.verify_producer_signature(producer, correct_signature, data)
    assert is_valid
    
    # 신뢰도 점수 확인
    score = dc.calculate_producer_trust_score(producer)
    assert score > 0.5  # 서명 검증으로 인한 점수 증가
    
    # 잘못된 서명 검증
    wrong_signature = "wrong_signature"
    is_invalid = dc.verify_producer_signature(producer, wrong_signature, data)
    assert not is_invalid


def test_register_trusted_path(data_catalog_instance):
    """Producer 신뢰할 수 있는 경로 등록 테스트"""
    dc = data_catalog_instance
    producer = "test_producer"
    trusted_path = "/trusted/path"
    
    # 신뢰할 수 있는 경로 등록
    dc.register_trusted_path(producer, trusted_path)
    
    # 신뢰도 점수 확인
    score = dc.calculate_producer_trust_score(producer)
    assert score > 0.5  # 신뢰할 수 있는 경로로 인한 점수 증가
    
    # 신뢰도 정보 확인
    trust_info = dc.get_producer_trust_info(producer)
    assert trust_info["path_trusted"] is True
    assert dc.producer_paths[producer] == trusted_path


def test_weighted_trust_score_calculation(data_catalog_instance, tmp_path):
    """가중 신뢰도 점수 계산 테스트"""
    dc = data_catalog_instance
    producer = "test_producer"
    
    # 모든 신뢰도 요소 설정
    # 1. 성공률 높이기
    for _ in range(5):
        dc.update_producer_trust(producer, True)
    dc.update_producer_trust(producer, False)
    
    # 2. 실행 가능한 해시 등록
    test_file = tmp_path / "test_executable.py"
    test_file.write_text("print('Hello World')", encoding='utf-8')
    dc.register_producer_executable_hash(producer, str(test_file))
    
    # 3. 서명 검증
    data = "test_data"
    correct_signature = hashlib.sha256(data.encode()).hexdigest()
    dc.verify_producer_signature(producer, correct_signature, data)
    
    # 4. 신뢰할 수 있는 경로 등록
    dc.register_trusted_path(producer, "/trusted/path")
    
    # 최종 신뢰도 점수 계산
    final_score = dc.calculate_producer_trust_score(producer)
    
    # 모든 요소가 설정되었으므로 높은 점수여야 함
    assert final_score > 0.8
    
    # 신뢰도 정보 확인
    trust_info = dc.get_producer_trust_info(producer)
    assert trust_info["success_count"] == 5
    assert trust_info["failure_count"] == 1
    assert trust_info["executable_hash"] is not None
    assert trust_info["signature_valid"] is True
    assert trust_info["path_trusted"] is True


def test_time_decay_effect(data_catalog_instance):
    """시간 감쇠 효과 테스트"""
    dc = data_catalog_instance
    producer = "test_producer"
    
    # 초기 신뢰도 설정
    dc.update_producer_trust(producer, True)
    dc.update_producer_trust(producer, True)
    
    initial_score = dc.calculate_producer_trust_score(producer)
    
    # 시간 감쇠 시뮬레이션 (1시간 전으로 설정)
    dc.producer_trust_scores[producer]["last_seen"] = time.time() - 3600
    
    decayed_score = dc.calculate_producer_trust_score(producer)
    
    # 시간이 지나면 점수 감소
    assert decayed_score < initial_score
    assert decayed_score >= 0.1  # 최소값 보장


def test_producer_trust_info_edge_cases(data_catalog_instance):
    """Producer 신뢰도 정보의 엣지 케이스 테스트"""
    dc = data_catalog_instance
    
    # 존재하지 않는 producer
    trust_info = dc.get_producer_trust_info("nonexistent")
    assert trust_info["score"] == 0.5
    assert trust_info["success_count"] == 0
    assert trust_info["failure_count"] == 0
    assert trust_info["executable_hash"] is None
    assert trust_info["signature_valid"] is False
    assert trust_info["path_trusted"] is False


def test_catalog_summary_with_trust_info(data_catalog_instance, tmp_path):
    """신뢰도 정보를 포함한 카탈로그 요약 테스트"""
    dc = data_catalog_instance
    
    # 여러 producer 등록
    producers = ["producer1", "producer2", "producer3"]
    
    for producer in producers:
        dc.update_producer_trust(producer, True)
        dc.update_producer_trust(producer, True)
        
        # 신뢰할 수 있는 경로 등록
        dc.register_trusted_path(producer, f"/trusted/{producer}")
    
    # 신뢰도가 낮은 producer 추가
    untrusted_producer = "untrusted_producer"
    dc.update_producer_trust(untrusted_producer, False)
    dc.update_producer_trust(untrusted_producer, False)
    
    # 카탈로그 요약 확인
    summary = dc.get_catalog_summary()
    
    assert summary["producer_trust_summary"]["total_producers"] == 4
    assert summary["producer_trust_summary"]["trusted_producers"] >= 3
    assert summary["producer_trust_summary"]["untrusted_producers"] >= 1


def test_producer_trust_score_boundaries(data_catalog_instance):
    """Producer 신뢰도 점수의 경계값 테스트"""
    dc = data_catalog_instance
    producer = "test_producer"
    
    # 매우 높은 성공률
    for _ in range(100):
        dc.update_producer_trust(producer, True)
    
    high_score = dc.calculate_producer_trust_score(producer)
    assert high_score <= 1.0  # 최대값 보장
    
    # 매우 낮은 성공률
    producer2 = "test_producer2"
    for _ in range(100):
        dc.update_producer_trust(producer2, False)
    
    low_score = dc.calculate_producer_trust_score(producer2)
    assert low_score >= 0.0  # 최소값 보장


def test_producer_trust_score_consistency(data_catalog_instance):
    """Producer 신뢰도 점수의 일관성 테스트"""
    dc = data_catalog_instance
    producer = "test_producer"
    
    # 동일한 조건에서 여러 번 계산
    scores = []
    for _ in range(10):
        dc.update_producer_trust(producer, True)
        score = dc.calculate_producer_trust_score(producer)
        scores.append(score)
    
    # 점수가 일관되게 증가해야 함
    for i in range(1, len(scores)):
        assert scores[i] >= scores[i-1]  # 점수가 감소하지 않아야 함


if __name__ == "__main__":
    pytest.main([__file__])

