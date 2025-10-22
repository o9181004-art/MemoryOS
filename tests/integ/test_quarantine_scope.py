"""
Integration Test: Selective Restore + Minimize Write Block Scope

SelfHeal의 선별 복원 및 격리 범위 최소화 기능을 테스트합니다.
영향받은 경로만 복원하고 격리하는 기능을 검증합니다.
"""

import pytest
from pathlib import Path
import json
import time
from memoryos.guard.self_heal import SelfHeal
from memoryos.guard.drift_guard import DriftLevel


@pytest.fixture
def setup_self_heal_env(tmp_path):
    """테스트용 SelfHeal 환경 설정"""
    test_dir = tmp_path / "test_data"
    test_dir.mkdir()
    backup_dir = tmp_path / "test_backups"
    backup_dir.mkdir()
    quarantine_dir = tmp_path / "test_quarantine"
    quarantine_dir.mkdir()
    
    self_heal = SelfHeal(str(backup_dir), str(quarantine_dir))
    
    # 가상의 카탈로그 정보 생성
    catalog_info = {
        str(test_dir / "config.json"): {
            "producer_expected": "config_manager",
            "consumer_expected": ["module_A", "module_B"]
        },
        str(test_dir / "module_A_config.json"): {
            "producer_expected": "module_A",
            "consumer_expected": []
        },
        str(test_dir / "unaffected.json"): {
            "producer_expected": "unaffected_manager",
            "consumer_expected": []
        }
    }
    
    # 테스트 파일 생성
    (test_dir / "config.json").write_text('{"setting": "value"}', encoding='utf-8')
    (test_dir / "module_A_config.json").write_text('{"module_A_setting": "value_A"}', encoding='utf-8')
    (test_dir / "unaffected.json").write_text('{"unaffected_setting": "value_unaffected"}', encoding='utf-8')
    
    return self_heal, test_dir, catalog_info


def test_compute_affected_path_set(setup_self_heal_env):
    """영향 경로 집합 계산 테스트"""
    self_heal, test_dir, catalog_info = setup_self_heal_env
    
    config_file = str(test_dir / "config.json")
    affected = self_heal.compute_affected_path_set(config_file, catalog_info[config_file])
    
    expected_affected = {
        config_file,
        str(test_dir / "module_A_config.json"),
        str(test_dir / "module_B_config.json"),  # 가상의 파일
        str(test_dir / "backup.json")  # 디렉토리 기반 영향 경로
    }
    
    assert affected == expected_affected


def test_selective_restore_and_quarantine_scope(setup_self_heal_env):
    """선별 복원 및 쓰기 차단 범위 최소화 테스트"""
    self_heal, test_dir, catalog_info = setup_self_heal_env
    
    config_file = test_dir / "config.json"
    module_a_file = test_dir / "module_A_config.json"
    unaffected_file = test_dir / "unaffected.json"
    
    # config.json에 drift 발생 시뮬레이션
    # (실제로는 memory_index와 hash_chain을 통해 이전 상태를 가져와야 함)
    # 여기서는 간단히 파일 내용을 변경하고 복원 시도
    original_config_content = config_file.read_text(encoding='utf-8')
    config_file.write_text('{"setting": "malicious_value"}', encoding='utf-8')
    
    # affected_paths 계산
    affected_paths = self_heal.compute_affected_path_set(str(config_file), catalog_info[str(config_file)])
    
    # L3 drift 시뮬레이션 (복원 및 격리)
    drift_result = {
        "file_path": str(config_file),
        "drift_level": DriftLevel.L3.value,
        "producer_actual": "malicious_actor",
        "producer_expected": "config_manager",
        "timestamp": time.time()
    }
    
    # _execute_l3_heal을 직접 호출하여 선별 복원 및 격리 테스트
    # 이 테스트를 위해 _execute_l3_heal 내부 로직을 수정해야 함
    # 현재 _execute_l3_heal은 file_path만 받으므로, affected_paths를 전달하도록 수정 필요
    
    # 임시로 _execute_l3_heal을 모의(mock)하거나, 테스트용 헬퍼 함수를 만들어 사용
    # 여기서는 SelfHeal 클래스에 직접 접근하여 테스트
    
    # 1. 백업 생성 (config.json)
    backup_path = self_heal._create_backup(str(config_file))
    assert backup_path.exists()
    
    # 2. 선별 복원 (affected_paths에 있는 파일만)
    # _restore_to_previous_state는 실제 이전 상태로 복원하는 로직이 필요
    # 여기서는 간단히 백업 파일이 존재하면 복원 성공으로 간주
    
    # _restore_to_previous_state를 모의하여 항상 성공하도록 설정
    def mock_restore_to_previous_state(path, _memory_index=None):
        if Path(backup_dir / Path(path).name).exists():
            shutil.copy(str(backup_dir / Path(path).name), path)
            return True
        return False
    
    original_restore_method = self_heal._restore_to_previous_state
    self_heal._restore_to_previous_state = mock_restore_to_previous_state
    
    restore_results = self_heal.selective_restore(str(config_file), affected_paths, None)
    
    # config.json은 복원되어야 함
    assert restore_results[str(config_file)]["success"]
    assert config_file.read_text(encoding='utf-8') == original_config_content
    
    # module_A_config.json도 affected_paths에 포함되어 있다면 복원 시도
    if str(module_a_file) in affected_paths:
        assert restore_results[str(module_a_file)]["success"]
        # 실제로는 module_A_config.json의 백업이 없으므로 실패할 수 있음
        # 이 테스트는 _restore_to_previous_state가 어떻게 동작하는지에 따라 달라짐
        
    # unaffected.json은 복원되지 않아야 함
    assert str(unaffected_file) not in restore_results
    
    # 3. 격리 범위 최소화 (affected_paths에 있는 파일만 격리)
    quarantine_results = self_heal.quarantine_scope_minimization(str(config_file), affected_paths)
    
    assert quarantine_results[str(config_file)]["quarantined"]
    assert str(config_file) in self_heal.quarantined_files
    
    # unaffected.json은 격리되지 않아야 함
    assert str(unaffected_file) not in self_heal.quarantined_files
    
    # _restore_to_previous_state 원본으로 복원
    self_heal._restore_to_previous_state = original_restore_method


def test_quarantine_release_auto_manual(setup_self_heal_env):
    """격리 해제 조건 자동/수동 경로 테스트"""
    self_heal, test_dir, _ = setup_self_heal_env
    config_file = str(test_dir / "config.json")
    
    # 파일 격리 시뮬레이션
    self_heal._enter_quarantine_mode(config_file)
    self_heal.quarantined_files.add(config_file)
    self_heal.setup_quarantine_release_conditions(config_file)
    
    # 1. 자동 해제 조건 테스트
    conditions = self_heal.quarantine_release_conditions[config_file]
    
    # 조건 미달
    assert not self_heal.check_quarantine_release_conditions(config_file)
    
    # 성공 이벤트 및 정상 Δt 카운트 증가
    self_heal.success_events[config_file] = conditions["success_events_required"]
    self_heal.normal_delta_count[config_file] = conditions["normal_delta_required"]
    
    # 시간 경과 시뮬레이션
    conditions["last_check"] = time.time() - conditions["monitoring_interval"] - 1
    
    assert self_heal.check_quarantine_release_conditions(config_file)
    
    # 자동 해제 후 quarantined_files에서 제거되어야 함 (실제 해제 로직은 execute_heal에서 호출)
    # 여기서는 check_quarantine_release_conditions만 테스트하므로, 실제 제거는 하지 않음
    
    # 2. 수동 해제 테스트
    # 다시 격리 시뮬레이션
    self_heal.quarantined_files.add(config_file)
    self_heal.setup_quarantine_release_conditions(config_file)  # 조건 재설정
    
    unlock_result = self_heal.unlock_quarantine([config_file], approver="admin")
    
    assert unlock_result[config_file]["success"]
    assert config_file not in self_heal.quarantined_files
    assert config_file not in self_heal.quarantine_release_conditions
    assert config_file not in self_heal.success_events
    assert config_file not in self_heal.normal_delta_count
    
    # 격리되지 않은 파일 해제 시도
    not_quarantined_file = str(test_dir / "not_quarantined.json")
    unlock_result_fail = self_heal.unlock_quarantine([not_quarantined_file])
    assert not unlock_result_fail[not_quarantined_file]["success"]
    assert unlock_result_fail[not_quarantined_file]["reason"] == "not_quarantined"


def test_execute_heal_with_selective_restore(setup_self_heal_env):
    """선별 복원을 적용한 execute_heal 테스트"""
    self_heal, test_dir, catalog_info = setup_self_heal_env
    
    config_file = str(test_dir / "config.json")
    
    # L3 drift 시뮬레이션
    drift_result = {
        "file_path": config_file,
        "drift_level": DriftLevel.L3.value,
        "producer_actual": "malicious_actor",
        "producer_expected": "config_manager",
        "timestamp": time.time()
    }
    
    # execute_heal 호출
    heal_result = self_heal.execute_heal(drift_result, None)
    
    # 결과 검증
    assert heal_result["success"] is True
    assert heal_result["action"] == "restore_and_quarantine"
    assert heal_result["file_path"] == config_file
    assert heal_result["drift_level"] == DriftLevel.L3.value
    
    # 격리된 파일 확인
    assert config_file in self_heal.quarantined_files
    assert self_heal.quarantine_count > 0


def test_quarantine_scope_minimization_edge_cases(setup_self_heal_env):
    """격리 범위 최소화의 엣지 케이스 테스트"""
    self_heal, test_dir, _ = setup_self_heal_env
    
    # 빈 영향 경로 집합
    empty_affected = set()
    quarantine_results = self_heal.quarantine_scope_minimization("nonexistent.txt", empty_affected)
    assert quarantine_results == {}
    
    # 존재하지 않는 파일
    nonexistent_paths = {"nonexistent1.txt", "nonexistent2.txt"}
    quarantine_results = self_heal.quarantine_scope_minimization("nonexistent.txt", nonexistent_paths)
    
    # 모든 경로에 대해 격리 시도 (실패할 수 있음)
    for path in nonexistent_paths:
        assert path in quarantine_results
        # 격리 실패는 정상적인 동작일 수 있음


def test_selective_restore_reason_codes(setup_self_heal_env):
    """선별 복원의 reason_code 테스트"""
    self_heal, test_dir, _ = setup_self_heal_env
    
    # 정상적인 복원
    normal_paths = {str(test_dir / "config.json")}
    restore_results = self_heal.selective_restore(str(test_dir / "config.json"), normal_paths, None)
    
    for path, result in restore_results.items():
        assert "reason_code" in result
        assert result["reason_code"] in ["MERGE_OK", "HASH_MISMATCH", "IO_DENIED", "UNKNOWN_ERROR"]


def test_quarantine_release_conditions_setup(setup_self_heal_env):
    """격리 해제 조건 설정 테스트"""
    self_heal, test_dir, _ = setup_self_heal_env
    config_file = str(test_dir / "config.json")
    
    # 격리 해제 조건 설정
    self_heal.setup_quarantine_release_conditions(config_file)
    
    # 조건 확인
    assert config_file in self_heal.quarantine_release_conditions
    assert config_file in self_heal.success_events
    assert config_file in self_heal.normal_delta_count
    
    conditions = self_heal.quarantine_release_conditions[config_file]
    assert conditions["success_events_required"] == 1
    assert conditions["normal_delta_required"] == 3
    assert conditions["monitoring_interval"] == 30


if __name__ == "__main__":
    pytest.main([__file__])