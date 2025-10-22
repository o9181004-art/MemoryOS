"""
파일 감시 Debounce/Batching 테스트

중복 이벤트 축소 및 배치 처리를 테스트합니다.
"""

import pytest
import tempfile
import os
import time
import threading
from pathlib import Path
from memoryos.core.io_probe import IoProbe


class TestProbeDebounce:
    """파일 감시 Debounce 테스트 클래스"""
    
    def setup_method(self):
        """테스트 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test_file.txt")
        
    def teardown_method(self):
        """테스트 정리"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_debounce_single_file(self):
        """단일 파일 Debounce 테스트"""
        # Debounce 시간을 짧게 설정
        io_probe = IoProbe([self.temp_dir], debounce_ms=50)
        
        # 파일 생성
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("initial content")
            
        # 여러 번 빠르게 수정
        for i in range(5):
            with open(self.test_file, 'w', encoding='utf-8') as f:
                f.write(f"content {i}")
            time.sleep(0.01)  # 10ms 간격
            
        # Debounce 시간 대기
        time.sleep(0.1)
        
        # 마지막 변경사항만 처리되었는지 확인
        assert len(io_probe.delta_events) == 1
        
    def test_debounce_multiple_files(self):
        """여러 파일 Debounce 테스트"""
        io_probe = IoProbe([self.temp_dir], debounce_ms=50)
        
        # 여러 파일 생성 및 수정
        files = []
        for i in range(3):
            file_path = os.path.join(self.temp_dir, f"file_{i}.txt")
            files.append(file_path)
            
            # 각 파일을 여러 번 빠르게 수정
            for j in range(3):
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"content {i}_{j}")
                time.sleep(0.01)
                
        # Debounce 시간 대기
        time.sleep(0.1)
        
        # 각 파일당 하나의 이벤트만 생성되었는지 확인
        assert len(io_probe.delta_events) == 3
        
    def test_debounce_callback(self):
        """Debounce 콜백 테스트"""
        callback_events = []
        
        def callback(event):
            callback_events.append(event)
            
        io_probe = IoProbe([self.temp_dir], debounce_ms=50)
        io_probe.change_callback = callback
        
        # 파일 생성 및 여러 번 수정
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("initial content")
            
        for i in range(3):
            with open(self.test_file, 'w', encoding='utf-8') as f:
                f.write(f"content {i}")
            time.sleep(0.01)
            
        # Debounce 시간 대기
        time.sleep(0.1)
        
        # 콜백이 한 번만 호출되었는지 확인
        assert len(callback_events) == 1
        assert callback_events[0]["path"] == self.test_file
        
    def test_debounce_timer_cancellation(self):
        """Debounce 타이머 취소 테스트"""
        io_probe = IoProbe([self.temp_dir], debounce_ms=100)
        
        # 파일 생성
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("initial content")
            
        # 첫 번째 수정
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("first modification")
            
        # 짧은 시간 후 두 번째 수정 (타이머 취소됨)
        time.sleep(0.05)
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("second modification")
            
        # Debounce 시간 대기
        time.sleep(0.15)
        
        # 마지막 수정만 처리되었는지 확인
        assert len(io_probe.delta_events) == 1
        
    def test_batch_processing(self):
        """배치 처리 테스트"""
        io_probe = IoProbe([self.temp_dir], debounce_ms=50)
        
        # 여러 파일을 빠르게 생성
        for i in range(5):
            file_path = os.path.join(self.temp_dir, f"batch_file_{i}.txt")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"batch content {i}")
                
        # Debounce 시간 대기
        time.sleep(0.1)
        
        # 모든 파일이 처리되었는지 확인
        assert len(io_probe.delta_events) == 5
        
        # 각 파일이 한 번씩만 처리되었는지 확인
        processed_files = set()
        for event in io_probe.delta_events:
            assert event["path"] not in processed_files
            processed_files.add(event["path"])
            
    def test_debounce_with_threading(self):
        """스레딩과 함께 Debounce 테스트"""
        io_probe = IoProbe([self.temp_dir], debounce_ms=50)
        
        def modify_file(file_path, content):
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
        # 여러 스레드에서 동시에 파일 수정
        threads = []
        for i in range(3):
            thread = threading.Thread(target=modify_file, 
                                     args=(self.test_file, f"thread_{i}"))
            threads.append(thread)
            thread.start()
            
        # 모든 스레드 완료 대기
        for thread in threads:
            thread.join()
            
        # Debounce 시간 대기
        time.sleep(0.1)
        
        # 마지막 수정만 처리되었는지 확인
        assert len(io_probe.delta_events) == 1
        
    def test_debounce_configuration(self):
        """Debounce 설정 테스트"""
        # 짧은 Debounce 시간
        io_probe_short = IoProbe([self.temp_dir], debounce_ms=10)
        
        # 긴 Debounce 시간
        io_probe_long = IoProbe([self.temp_dir], debounce_ms=200)
        
        # 파일 생성
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("initial content")
            
        # 짧은 Debounce 시간으로 테스트
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("short debounce")
            
        time.sleep(0.05)  # 50ms 대기
        
        # 짧은 Debounce는 이미 처리됨
        assert len(io_probe_short.delta_events) == 1
        
        # 긴 Debounce 시간으로 테스트
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("long debounce")
            
        time.sleep(0.1)  # 100ms 대기 (아직 처리되지 않음)
        
        # 긴 Debounce는 아직 처리되지 않음
        assert len(io_probe_long.delta_events) == 0
        
        time.sleep(0.15)  # 추가 대기
        
        # 이제 처리됨
        assert len(io_probe_long.delta_events) == 1
        
    def test_debounce_edge_cases(self):
        """Debounce 엣지 케이스 테스트"""
        io_probe = IoProbe([self.temp_dir], debounce_ms=50)
        
        # 존재하지 않는 파일에 대한 변경
        non_existent_file = os.path.join(self.temp_dir, "non_existent.txt")
        io_probe._debounce_file_change(non_existent_file, "write")
        
        # Debounce 시간 대기
        time.sleep(0.1)
        
        # 존재하지 않는 파일은 이벤트가 생성되지 않음
        assert len(io_probe.delta_events) == 0
        
    def test_debounce_cleanup(self):
        """Debounce 정리 테스트"""
        io_probe = IoProbe([self.temp_dir], debounce_ms=50)
        
        # 파일 생성 및 수정
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("initial content")
            
        # Debounce 처리
        io_probe._debounce_file_change(self.test_file, "write")
        
        # Debounce 시간 대기
        time.sleep(0.1)
        
        # 정리 확인
        assert self.test_file not in io_probe.pending_changes
        assert self.test_file not in io_probe.debounce_timers


if __name__ == "__main__":
    pytest.main([__file__])

