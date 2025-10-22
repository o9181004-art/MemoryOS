"""
Unit tests for IoProbe debounce/batching functionality
"""

import unittest
import time
import threading
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
import os

from memoryos.core.io_probe import IoProbe, DebounceConfig


class TestIoProbeDebounce(unittest.TestCase):
    """IoProbe debounce/batching 기능 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.watch_paths = [self.temp_dir]
        self.callback = Mock()
        
        # 빠른 테스트를 위한 짧은 debounce 설정
        self.debounce_config = DebounceConfig(
            debounce_delay=0.01,  # 10ms
            batch_size=3,
            max_wait_time=0.05  # 50ms
        )
        
        self.probe = IoProbe(
            watch_paths=self.watch_paths,
            callback=self.callback,
            debounce_config=self.debounce_config
        )
    
    def tearDown(self):
        """테스트 정리"""
        # 임시 파일 정리
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_debounce_config_initialization(self):
        """DebounceConfig 초기화 테스트"""
        config = DebounceConfig()
        self.assertEqual(config.debounce_delay, 0.1)
        self.assertEqual(config.batch_size, 10)
        self.assertEqual(config.max_wait_time, 1.0)
        
        custom_config = DebounceConfig(
            debounce_delay=0.05,
            batch_size=5,
            max_wait_time=0.5
        )
        self.assertEqual(custom_config.debounce_delay, 0.05)
        self.assertEqual(custom_config.batch_size, 5)
        self.assertEqual(custom_config.max_wait_time, 0.5)
    
    def test_io_probe_debounce_initialization(self):
        """IoProbe debounce 초기화 테스트"""
        self.assertEqual(self.probe.debounce_config.debounce_delay, 0.01)
        self.assertEqual(self.probe.debounce_config.batch_size, 3)
        self.assertEqual(self.probe.debounce_config.max_wait_time, 0.05)
        self.assertEqual(len(self.probe.pending_changes), 0)
        self.assertEqual(len(self.probe.batch_timers), 0)
        self.assertEqual(len(self.probe.batch_queue), 0)
    
    def test_schedule_debounced_change(self):
        """Debounce된 변경사항 스케줄링 테스트"""
        file_path = "test_file.txt"
        change_info = {
            "op": "write",
            "hash": "abc123",
            "ts": time.time()
        }
        
        # 변경사항 스케줄링
        self.probe._schedule_debounced_change(file_path, change_info)
        
        # pending_changes에 추가되었는지 확인
        self.assertIn(file_path, self.probe.pending_changes)
        self.assertEqual(self.probe.pending_changes[file_path], change_info)
        
        # 타이머가 설정되었는지 확인
        self.assertIn(file_path, self.probe.batch_timers)
        self.assertTrue(self.probe.batch_timers[file_path].is_alive())
    
    def test_debounce_multiple_changes_same_file(self):
        """같은 파일에 대한 여러 변경사항 debounce 테스트"""
        file_path = "test_file.txt"
        
        # 첫 번째 변경사항
        change1 = {"op": "write", "hash": "hash1", "ts": time.time()}
        self.probe._schedule_debounced_change(file_path, change1)
        
        # 두 번째 변경사항 (첫 번째 타이머 취소되어야 함)
        change2 = {"op": "write", "hash": "hash2", "ts": time.time()}
        self.probe._schedule_debounced_change(file_path, change2)
        
        # pending_changes에는 마지막 변경사항만 있어야 함
        self.assertEqual(len(self.probe.pending_changes), 1)
        self.assertEqual(self.probe.pending_changes[file_path], change2)
        
        # 타이머는 하나만 있어야 함
        self.assertEqual(len(self.probe.batch_timers), 1)
    
    def test_process_debounced_change(self):
        """Debounce된 변경사항 처리 테스트"""
        file_path = "test_file.txt"
        change_info = {
            "op": "write",
            "hash": "abc123",
            "ts": time.time()
        }
        
        # 변경사항 스케줄링
        self.probe._schedule_debounced_change(file_path, change_info)
        
        # 즉시 처리 (타이머 대기 없이)
        self.probe._process_debounced_change(file_path)
        
        # pending_changes에서 제거되었는지 확인
        self.assertNotIn(file_path, self.probe.pending_changes)
        
        # batch_queue에 추가되었는지 확인
        self.assertEqual(len(self.probe.batch_queue), 1)
        self.assertEqual(self.probe.batch_queue[0]["file_path"], file_path)
        self.assertEqual(self.probe.batch_queue[0]["change_info"], change_info)
    
    def test_batch_size_flush(self):
        """배치 크기 조건으로 플러시 테스트"""
        # 배치 크기만큼 변경사항 추가
        for i in range(3):
            file_path = f"test_file_{i}.txt"
            change_info = {
                "op": "write",
                "hash": f"hash_{i}",
                "ts": time.time()
            }
            self.probe._schedule_debounced_change(file_path, change_info)
            self.probe._process_debounced_change(file_path)
        
        # 배치 크기에 도달했으므로 콜백이 호출되어야 함
        self.callback.assert_called_once()
        call_args = self.callback.call_args[0][0]
        self.assertEqual(len(call_args), 3)
        
        # batch_queue가 비워졌는지 확인
        self.assertEqual(len(self.probe.batch_queue), 0)
    
    def test_max_wait_time_flush(self):
        """최대 대기 시간 조건으로 플러시 테스트"""
        file_path = "test_file.txt"
        change_info = {
            "op": "write",
            "hash": "abc123",
            "ts": time.time()
        }
        
        # 변경사항 추가
        self.probe._schedule_debounced_change(file_path, change_info)
        self.probe._process_debounced_change(file_path)
        
        # 최대 대기 시간이 지났는지 확인
        self.assertTrue(self.probe._should_flush_batch())
        
        # 플러시 실행
        self.probe._flush_batch()
        
        # 콜백이 호출되었는지 확인
        self.callback.assert_called_once()
        
        # batch_queue가 비워졌는지 확인
        self.assertEqual(len(self.probe.batch_queue), 0)
    
    def test_force_flush_batch(self):
        """강제 배치 플러시 테스트"""
        # 여러 변경사항 추가
        for i in range(2):
            file_path = f"test_file_{i}.txt"
            change_info = {
                "op": "write",
                "hash": f"hash_{i}",
                "ts": time.time()
            }
            self.probe._schedule_debounced_change(file_path, change_info)
        
        # 강제 플러시
        self.probe.force_flush_batch()
        
        # 모든 타이머가 취소되었는지 확인
        self.assertEqual(len(self.probe.batch_timers), 0)
        
        # pending_changes가 비워졌는지 확인
        self.assertEqual(len(self.probe.pending_changes), 0)
        
        # 콜백이 호출되었는지 확인
        self.callback.assert_called_once()
        
        # batch_queue가 비워졌는지 확인
        self.assertEqual(len(self.probe.batch_queue), 0)
    
    def test_get_batch_status(self):
        """배치 상태 정보 반환 테스트"""
        # 초기 상태
        status = self.probe.get_batch_status()
        self.assertEqual(status["pending_changes"], 0)
        self.assertEqual(status["batch_queue_size"], 0)
        self.assertEqual(status["active_timers"], 0)
        self.assertEqual(status["debounce_config"]["debounce_delay"], 0.01)
        self.assertEqual(status["debounce_config"]["batch_size"], 3)
        self.assertEqual(status["debounce_config"]["max_wait_time"], 0.05)
        
        # 변경사항 추가 후 상태
        file_path = "test_file.txt"
        change_info = {"op": "write", "hash": "abc123", "ts": time.time()}
        self.probe._schedule_debounced_change(file_path, change_info)
        
        status = self.probe.get_batch_status()
        self.assertEqual(status["pending_changes"], 1)
        self.assertEqual(status["active_timers"], 1)
    
    def test_callback_error_handling(self):
        """콜백 에러 처리 테스트"""
        # 에러를 발생시키는 콜백 설정
        error_callback = Mock(side_effect=Exception("Test error"))
        self.probe.callback = error_callback
        
        # 변경사항 추가 및 플러시
        file_path = "test_file.txt"
        change_info = {"op": "write", "hash": "abc123", "ts": time.time()}
        self.probe._schedule_debounced_change(file_path, change_info)
        self.probe._process_debounced_change(file_path)
        self.probe._flush_batch()
        
        # 에러가 발생해도 batch_queue는 정리되어야 함
        self.assertEqual(len(self.probe.batch_queue), 0)
        
        # 콜백이 호출되었는지 확인
        error_callback.assert_called_once()
    
    def test_concurrent_debounce_operations(self):
        """동시 debounce 작업 테스트"""
        def add_change(file_path: str):
            change_info = {
                "op": "write",
                "hash": f"hash_{file_path}",
                "ts": time.time()
            }
            self.probe._schedule_debounced_change(file_path, change_info)
            self.probe._process_debounced_change(file_path)
        
        # 여러 스레드에서 동시에 변경사항 추가
        threads = []
        for i in range(5):
            thread = threading.Thread(target=add_change, args=(f"file_{i}.txt",))
            threads.append(thread)
            thread.start()
        
        # 모든 스레드 완료 대기
        for thread in threads:
            thread.join()
        
        # 배치 상태 확인
        status = self.probe.get_batch_status()
        self.assertEqual(status["batch_queue_size"], 5)
        
        # 강제 플러시
        self.probe.force_flush_batch()
        
        # 콜백이 호출되었는지 확인
        self.callback.assert_called_once()
        call_args = self.callback.call_args[0][0]
        self.assertEqual(len(call_args), 5)


if __name__ == "__main__":
    unittest.main()

