"""
Unit Test: Self-Adaptive Threshold (EMA+Percentile Hybrid)

DriftGuard의 자기적응 임계값 계산 로직을 테스트합니다.
EMA와 백분위수 하이브리드 방식을 검증합니다.
"""

import pytest
import time
from memoryos.guard.drift_guard import DriftGuard, DriftLevel


@pytest.fixture
def drift_guard_instance():
    """테스트용 DriftGuard 인스턴스"""
    return DriftGuard(thresholds={"l1_threshold": 10, "l2_threshold": 60, "l3_threshold": 300})


def test_record_delta_time_and_ema(drift_guard_instance):
    """Delta 시간 기록 및 EMA 업데이트 테스트"""
    dg = drift_guard_instance
    
    # 첫 번째 값
    dg.record_delta_time(10.0)
    assert dg.ema_delta_t == 10.0
    assert len(dg.delta_times) == 1
    
    # 두 번째 값 (EMA 계산)
    dg.record_delta_time(20.0)
    # EMA = 0.1 * 20 + 0.9 * 10 = 2 + 9 = 11
    assert dg.ema_delta_t == pytest.approx(11.0)
    assert len(dg.delta_times) == 2


def test_calculate_adaptive_threshold_warmup(drift_guard_instance):
    """워밍업 구간에서의 자기적응 임계값 테스트"""
    dg = drift_guard_instance
    
    # 워밍업 샘플 수 미달
    for i in range(dg.warmup_samples - 1):
        dg.record_delta_time(10.0 + i)
    
    # 워밍업 중에는 l1_threshold 반환
    assert dg.calculate_adaptive_threshold() == dg.thresholds["l1_threshold"]
    assert not dg.is_warmed_up
    
    # 워밍업 완료
    dg.record_delta_time(10.0 + dg.warmup_samples - 1)
    assert dg.is_warmed_up
    # 이제 실제 계산된 임계값이 반환되어야 함 (정확한 값은 데이터에 따라 다름)
    assert dg.calculate_adaptive_threshold() != dg.thresholds["l1_threshold"]


def test_calculate_adaptive_threshold_dynamic_change(drift_guard_instance):
    """분포 변화에 따른 임계값 동적 이동 테스트"""
    dg = drift_guard_instance
    
    # 초기 워밍업 (낮은 Δt)
    for _ in range(dg.warmup_samples + 10):
        dg.record_delta_time(5.0)
    
    initial_threshold = dg.calculate_adaptive_threshold()
    assert initial_threshold < dg.thresholds["l2_threshold"]
    
    # 높은 Δt 값 주입
    for _ in range(20):
        dg.record_delta_time(100.0)
    
    # 임계값이 증가해야 함
    new_threshold = dg.calculate_adaptive_threshold()
    assert new_threshold > initial_threshold
    assert new_threshold > dg.thresholds["l1_threshold"]


def test_calculate_producer_trust_score(drift_guard_instance):
    """Producer 신뢰도 점수 계산 테스트"""
    dg = drift_guard_instance
    producer = "test_producer"
    
    # 초기 점수
    score = dg.calculate_producer_trust_score(producer)
    assert score == 0.5  # 기본값
    
    # 성공 업데이트
    dg.update_producer_trust(producer, True)
    score = dg.calculate_producer_trust_score(producer)
    assert score > 0.5  # 성공 시 점수 증가
    
    # 실패 업데이트
    dg.update_producer_trust(producer, False)
    score = dg.calculate_producer_trust_score(producer)
    assert score < 0.5  # 실패 시 점수 감소
    
    # 시간 감쇠 테스트 (간단하게 시뮬레이션)
    dg.producer_trust_scores[producer]["last_seen"] = time.time() - 7200  # 2시간 전
    score_decayed = dg.calculate_producer_trust_score(producer)
    assert score_decayed < score  # 시간이 지나면 점수 감소


def test_check_drift_with_adaptive_threshold_and_trust(drift_guard_instance):
    """자기적응 임계값 및 신뢰도를 반영한 drift 검사"""
    dg = drift_guard_instance
    file_path = "test_file.txt"
    producer_expected = "trusted_module"
    
    # 워밍업 (낮은 Δt)
    for _ in range(dg.warmup_samples + 10):
        dg.record_delta_time(5.0)
    
    # 신뢰도 높은 producer
    dg.update_producer_trust(producer_expected, True)
    dg.update_producer_trust(producer_expected, True)
    
    # L1 임계값보다 약간 높은 Δt, 신뢰도 높은 producer
    result = dg.check_drift(file_path, producer_expected, producer_expected, time.time() - 15)
    assert result["drift_level"] == DriftLevel.L1.value  # L1으로 감지
    assert result["trust_score"] > 0.5
    
    # 신뢰도 낮은 producer
    untrusted_producer = "untrusted_module"
    dg.update_producer_trust(untrusted_producer, False)
    dg.update_producer_trust(untrusted_producer, False)
    
    # 동일한 Δt라도 신뢰도 낮은 producer는 더 높은 레벨로 감지될 수 있음
    result_untrusted = dg.check_drift(file_path, untrusted_producer, producer_expected, time.time() - 15)
    assert result_untrusted["drift_level"] >= DriftLevel.L1.value  # L1 이상으로 감지될 수 있음
    assert result_untrusted["trust_score"] < 0.5
    assert result_untrusted["trust_adjusted_threshold"] < result["trust_adjusted_threshold"]  # 임계값이 더 엄격해짐


def test_adaptive_threshold_boundaries(drift_guard_instance):
    """자기적응 임계값의 경계값 테스트"""
    dg = drift_guard_instance
    
    # 워밍업 완료
    for _ in range(dg.warmup_samples + 10):
        dg.record_delta_time(50.0)
    
    # 매우 낮은 Δt 값들
    for _ in range(20):
        dg.record_delta_time(1.0)
    
    threshold_low = dg.calculate_adaptive_threshold()
    assert threshold_low >= dg.thresholds["l1_threshold"]  # 최소값 보장
    
    # 매우 높은 Δt 값들
    for _ in range(20):
        dg.record_delta_time(1000.0)
    
    threshold_high = dg.calculate_adaptive_threshold()
    assert threshold_high <= dg.thresholds["l3_threshold"]  # 최대값 보장


def test_producer_trust_score_edge_cases(drift_guard_instance):
    """Producer 신뢰도 점수의 엣지 케이스 테스트"""
    dg = drift_guard_instance
    
    # 존재하지 않는 producer
    score = dg.calculate_producer_trust_score("nonexistent")
    assert score == 0.5  # 기본값
    
    # 매우 오래된 producer
    old_producer = "old_producer"
    dg.producer_trust_scores[old_producer] = {
        "score": 0.8,
        "success_count": 10,
        "failure_count": 2,
        "last_seen": time.time() - 86400  # 24시간 전
    }
    
    score_old = dg.calculate_producer_trust_score(old_producer)
    assert score_old < 0.8  # 시간 감쇠로 인해 점수 감소
    assert score_old >= 0.1  # 최소값 보장


def test_drift_level_determination_with_trust(drift_guard_instance):
    """신뢰도를 반영한 drift 레벨 결정 테스트"""
    dg = drift_guard_instance
    
    # 워밍업 완료
    for _ in range(dg.warmup_samples + 10):
        dg.record_delta_time(30.0)
    
    file_path = "test_file.txt"
    producer_expected = "expected_producer"
    
    # 신뢰도 높은 producer
    dg.update_producer_trust(producer_expected, True)
    dg.update_producer_trust(producer_expected, True)
    dg.update_producer_trust(producer_expected, True)
    
    # 신뢰도 낮은 producer
    untrusted_producer = "untrusted_producer"
    dg.update_producer_trust(untrusted_producer, False)
    dg.update_producer_trust(untrusted_producer, False)
    
    # 동일한 조건에서 신뢰도에 따른 차이 확인
    result_trusted = dg.check_drift(file_path, producer_expected, producer_expected, time.time() - 100)
    result_untrusted = dg.check_drift(file_path, untrusted_producer, producer_expected, time.time() - 100)
    
    # 신뢰도가 낮은 producer는 더 높은 레벨로 감지될 가능성이 높음
    assert result_untrusted["drift_level"] >= result_trusted["drift_level"]
    assert result_untrusted["trust_adjusted_threshold"] < result_trusted["trust_adjusted_threshold"]


def test_adaptive_threshold_stability(drift_guard_instance):
    """자기적응 임계값의 안정성 테스트"""
    dg = drift_guard_instance
    
    # 워밍업 완료
    for _ in range(dg.warmup_samples + 10):
        dg.record_delta_time(30.0)
    
    # 연속적인 계산에서 임계값이 안정적인지 확인
    thresholds = []
    for _ in range(10):
        threshold = dg.calculate_adaptive_threshold()
        thresholds.append(threshold)
        dg.record_delta_time(30.0)  # 동일한 값 추가
    
    # 임계값이 크게 변하지 않아야 함 (안정성)
    threshold_variance = max(thresholds) - min(thresholds)
    assert threshold_variance < 10.0  # 임계값 변화가 10초 이내여야 함


if __name__ == "__main__":
    pytest.main([__file__])