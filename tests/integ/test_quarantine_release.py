"""
Integration tests for SelfHeal automatic/manual quarantine release conditions
"""

import unittest
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from memoryos.guard.self_heal import SelfHeal


class TestQuarantineReleaseConditions(unittest.TestCase):
    """SelfHeal 격리 해제 조건 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.backup_dir = Path(self.temp_dir) / "backups"
        self.quarantine_dir = Path(self.temp_dir) / "quarantine"
        
        self.self_heal = SelfHeal(
            backup_dir=str(self.backup_dir),
            quarantine_dir=str(self.quarantine_dir)
        )
        
        # 테스트용 파일 생성
        self.test_file = Path(self.temp_dir) / "test_file.txt"
        self.test_file.write_text("test content")
    
    def tearDown(self):
        """테스트 정리"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_setup_quarantine_release_conditions(self):
        """격리 해제 조건 설정 테스트"""
        file_path = str(self.test_file)
        
        # 격리 해제 조건 설정
        self.self_heal.setup_quarantine_release_conditions(file_path)
        
        # 조건이 설정되었는지 확인
        self.assertIn(file_path, self.self_heal.quarantine_release_conditions)
        conditions = self.self_heal.quarantine_release_conditions[file_path]
        
        self.assertEqual(conditions["success_events_required"], 1)
        self.assertEqual(conditions["normal_delta_required"], 3)
        self.assertEqual(conditions["monitoring_interval"], 30)
        self.assertIn("last_check", conditions)
        
        # 카운터 초기화 확인
        self.assertEqual(self.self_heal.success_events[file_path], 0)
        self.assertEqual(self.self_heal.normal_delta_count[file_path], 0)
    
    def test_check_quarantine_release_conditions_not_set(self):
        """격리 해제 조건이 설정되지 않은 경우 테스트"""
        file_path = "nonexistent_file.txt"
        
        # 조건이 설정되지 않은 경우 False 반환
        result = self.self_heal.check_quarantine_release_conditions(file_path)
        self.assertFalse(result)
    
    def test_check_quarantine_release_conditions_monitoring_interval(self):
        """모니터링 주기 내 조건 확인 테스트"""
        file_path = str(self.test_file)
        
        # 격리 해제 조건 설정
        self.self_heal.setup_quarantine_release_conditions(file_path)
        
        # 즉시 조건 확인 (모니터링 주기 내)
        result = self.self_heal.check_quarantine_release_conditions(file_path)
        self.assertFalse(result)
    
    def test_check_quarantine_release_conditions_success_events_insufficient(self):
        """성공 이벤트 부족 테스트"""
        file_path = str(self.test_file)
        
        # 격리 해제 조건 설정
        self.self_heal.setup_quarantine_release_conditions(file_path)
        
        # 모니터링 주기 지나도록 시간 조작
        conditions = self.self_heal.quarantine_release_conditions[file_path]
        conditions["last_check"] = time.time() - 35  # 35초 전
        
        # 성공 이벤트 부족 (0개)
        result = self.self_heal.check_quarantine_release_conditions(file_path)
        self.assertFalse(result)
    
    def test_check_quarantine_release_conditions_normal_delta_insufficient(self):
        """정상 Δt 부족 테스트"""
        file_path = str(self.test_file)
        
        # 격리 해제 조건 설정
        self.self_heal.setup_quarantine_release_conditions(file_path)
        
        # 모니터링 주기 지나도록 시간 조작
        conditions = self.self_heal.quarantine_release_conditions[file_path]
        conditions["last_check"] = time.time() - 35  # 35초 전
        
        # 성공 이벤트 충족 (1개)
        self.self_heal.success_events[file_path] = 1
        
        # 정상 Δt 부족 (0개)
        result = self.self_heal.check_quarantine_release_conditions(file_path)
        self.assertFalse(result)
    
    def test_check_quarantine_release_conditions_all_conditions_met(self):
        """모든 조건 만족 테스트"""
        file_path = str(self.test_file)
        
        # 격리 해제 조건 설정
        self.self_heal.setup_quarantine_release_conditions(file_path)
        
        # 모니터링 주기 지나도록 시간 조작
        conditions = self.self_heal.quarantine_release_conditions[file_path]
        conditions["last_check"] = time.time() - 35  # 35초 전
        
        # 모든 조건 충족
        self.self_heal.success_events[file_path] = 1  # 성공 이벤트 1개
        self.self_heal.normal_delta_count[file_path] = 3  # 정상 Δt 3개
        
        result = self.self_heal.check_quarantine_release_conditions(file_path)
        self.assertTrue(result)
        
        # last_check가 업데이트되었는지 확인
        self.assertGreater(conditions["last_check"], time.time() - 5)
    
    def test_unlock_quarantine_success(self):
        """수동 격리 해제 성공 테스트"""
        file_path = str(self.test_file)
        
        # 파일을 격리 상태로 설정
        self.self_heal.quarantined_files.add(file_path)
        
        # 격리 디렉토리에 파일 복사
        quarantine_path = self.quarantine_dir / self.test_file.name
        shutil.copy2(self.test_file, quarantine_path)
        
        # 수동 격리 해제
        result = self.self_heal.unlock_quarantine([file_path], approver="test_user")
        
        # 해제 결과 확인
        self.assertIn(file_path, result)
        self.assertTrue(result[file_path]["success"])
        self.assertEqual(result[file_path]["approver"], "test_user")
        self.assertIn("timestamp", result[file_path])
        
        # 격리 상태에서 제거되었는지 확인
        self.assertNotIn(file_path, self.self_heal.quarantined_files)
        
        # 격리 해제 조건이 정리되었는지 확인
        self.assertNotIn(file_path, self.self_heal.quarantine_release_conditions)
        self.assertNotIn(file_path, self.self_heal.success_events)
        self.assertNotIn(file_path, self.self_heal.normal_delta_count)
    
    def test_unlock_quarantine_not_quarantined(self):
        """격리되지 않은 파일 해제 테스트"""
        file_path = "nonexistent_file.txt"
        
        # 수동 격리 해제 시도
        result = self.self_heal.unlock_quarantine([file_path])
        
        # 해제 실패 확인
        self.assertIn(file_path, result)
        self.assertFalse(result[file_path]["success"])
        self.assertEqual(result[file_path]["reason"], "not_quarantined")
    
    def test_unlock_quarantine_multiple_files(self):
        """여러 파일 동시 격리 해제 테스트"""
        # 여러 테스트 파일 생성
        test_files = []
        for i in range(3):
            test_file = Path(self.temp_dir) / f"test_file_{i}.txt"
            test_file.write_text(f"test content {i}")
            test_files.append(str(test_file))
            
            # 격리 상태로 설정
            self.self_heal.quarantined_files.add(str(test_file))
            
            # 격리 디렉토리에 파일 복사
            quarantine_path = self.quarantine_dir / test_file.name
            shutil.copy2(test_file, quarantine_path)
        
        # 여러 파일 동시 격리 해제
        result = self.self_heal.unlock_quarantine(test_files, approver="batch_user")
        
        # 모든 파일 해제 성공 확인
        for file_path in test_files:
            self.assertIn(file_path, result)
            self.assertTrue(result[file_path]["success"])
            self.assertEqual(result[file_path]["approver"], "batch_user")
        
        # 모든 파일이 격리 상태에서 제거되었는지 확인
        self.assertEqual(len(self.self_heal.quarantined_files), 0)
    
    def test_unlock_quarantine_error_handling(self):
        """격리 해제 에러 처리 테스트"""
        file_path = str(self.test_file)
        
        # 파일을 격리 상태로 설정하지만 실제 파일은 존재하지 않음
        self.self_heal.quarantined_files.add(file_path)
        
        # 수동 격리 해제 시도
        result = self.self_heal.unlock_quarantine([file_path])
        
        # 에러 처리 확인
        self.assertIn(file_path, result)
        self.assertFalse(result[file_path]["success"])
        self.assertIn("error", result[file_path])
    
    def test_automatic_quarantine_release_workflow(self):
        """자동 격리 해제 워크플로우 테스트"""
        file_path = str(self.test_file)
        
        # 파일을 격리 상태로 설정
        self.self_heal.quarantined_files.add(file_path)
        
        # 격리 해제 조건 설정
        self.self_heal.setup_quarantine_release_conditions(file_path)
        
        # 성공 이벤트 및 정상 Δt 카운트 증가
        self.self_heal.success_events[file_path] = 1
        self.self_heal.normal_delta_count[file_path] = 3
        
        # 모니터링 주기 지나도록 시간 조작
        conditions = self.self_heal.quarantine_release_conditions[file_path]
        conditions["last_check"] = time.time() - 35  # 35초 전
        
        # 자동 해제 조건 확인
        release_ready = self.self_heal.check_quarantine_release_conditions(file_path)
        self.assertTrue(release_ready)
        
        # 실제 해제는 별도 프로세스에서 수행
        # 여기서는 조건 확인만 테스트
    
    def test_quarantine_release_conditions_persistence(self):
        """격리 해제 조건 지속성 테스트"""
        file_path = str(self.test_file)
        
        # 격리 해제 조건 설정
        self.self_heal.setup_quarantine_release_conditions(file_path)
        
        # 조건 정보 수정
        self.self_heal.success_events[file_path] = 2
        self.self_heal.normal_delta_count[file_path] = 5
        
        # 조건 정보가 유지되는지 확인
        self.assertEqual(self.self_heal.success_events[file_path], 2)
        self.assertEqual(self.self_heal.normal_delta_count[file_path], 5)
        
        # 조건 확인 후에도 정보가 유지되는지 확인
        conditions = self.self_heal.quarantine_release_conditions[file_path]
        conditions["last_check"] = time.time() - 35
        self.self_heal.check_quarantine_release_conditions(file_path)
        
        self.assertEqual(self.self_heal.success_events[file_path], 2)
        self.assertEqual(self.self_heal.normal_delta_count[file_path], 5)
    
    def test_quarantine_release_conditions_custom_values(self):
        """사용자 정의 격리 해제 조건 테스트"""
        file_path = str(self.test_file)
        
        # 격리 해제 조건 설정
        self.self_heal.setup_quarantine_release_conditions(file_path)
        
        # 사용자 정의 조건으로 수정
        conditions = self.self_heal.quarantine_release_conditions[file_path]
        conditions["success_events_required"] = 2
        conditions["normal_delta_required"] = 5
        conditions["monitoring_interval"] = 60  # 60초
        
        # 조건 확인
        conditions["last_check"] = time.time() - 65  # 65초 전
        
        # 조건 부족 상태
        self.self_heal.success_events[file_path] = 1  # 2개 필요
        self.self_heal.normal_delta_count[file_path] = 3  # 5개 필요
        
        result = self.self_heal.check_quarantine_release_conditions(file_path)
        self.assertFalse(result)
        
        # 조건 충족 상태
        self.self_heal.success_events[file_path] = 2
        self.self_heal.normal_delta_count[file_path] = 5
        
        result = self.self_heal.check_quarantine_release_conditions(file_path)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()

