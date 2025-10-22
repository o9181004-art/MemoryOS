"""
Unit tests for enhanced CLI functionality in run_memoryos.py
"""

import unittest
import tempfile
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import argparse

# CLI 모듈 import를 위한 경로 설정
sys.path.insert(0, str(Path(__file__).parent.parent))

from run_memoryos import ExitCode, main, run_demo_mode, run_monitor_mode, run_simulate_mode, run_replay_mode


class TestCLIEnhancements(unittest.TestCase):
    """CLI 향상 기능 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_config = Path(self.temp_dir) / "test_config.toml"
        self.temp_config.write_text("[test]\nvalue = 1")
    
    def tearDown(self):
        """테스트 정리"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_exit_code_enum(self):
        """ExitCode 열거형 테스트"""
        self.assertEqual(ExitCode.SUCCESS.value, 0)
        self.assertEqual(ExitCode.GENERAL_ERROR.value, 1)
        self.assertEqual(ExitCode.CONFIG_ERROR.value, 2)
        self.assertEqual(ExitCode.RUNTIME_ERROR.value, 3)
        self.assertEqual(ExitCode.PERMISSION_ERROR.value, 4)
        self.assertEqual(ExitCode.VALIDATION_ERROR.value, 5)
        self.assertEqual(ExitCode.MONITORING_ERROR.value, 6)
        self.assertEqual(ExitCode.SIMULATION_ERROR.value, 7)
        self.assertEqual(ExitCode.DEMO_ERROR.value, 8)
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_demo_mode_success(self, mock_context_runtime):
        """데모 모드 성공 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_context_runtime.return_value = mock_ctx
        
        # Mock 데모 함수들
        with patch('run_memoryos.demo_io_probe') as mock_io_probe, \
             patch('run_memoryos.demo_self_heal') as mock_self_heal:
            
            # 테스트 인수 생성
            args = Mock()
            args.verbose = False
            
            # 데모 모드 실행
            result = run_demo_mode(mock_ctx, args)
            
            # 결과 확인
            self.assertEqual(result, ExitCode.SUCCESS)
            mock_io_probe.assert_called_once()
            mock_self_heal.assert_called_once()
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_demo_mode_with_ab_runner(self, mock_context_runtime):
        """A/B Runner 포함 데모 모드 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_context_runtime.return_value = mock_ctx
        
        # Mock 데모 함수들
        with patch('run_memoryos.demo_io_probe') as mock_io_probe, \
             patch('run_memoryos.demo_self_heal') as mock_self_heal, \
             patch('run_memoryos.run_ab_test') as mock_ab_test:
            
            # 테스트 인수 생성
            args = Mock()
            args.verbose = True
            
            # 데모 모드 실행
            result = run_demo_mode(mock_ctx, args)
            
            # 결과 확인
            self.assertEqual(result, ExitCode.SUCCESS)
            mock_io_probe.assert_called_once()
            mock_self_heal.assert_called_once()
            mock_ab_test.assert_called_once()
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_demo_mode_error(self, mock_context_runtime):
        """데모 모드 에러 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_context_runtime.return_value = mock_ctx
        
        # Mock에서 예외 발생
        with patch('run_memoryos.demo_io_probe', side_effect=Exception("Demo error")):
            # 테스트 인수 생성
            args = Mock()
            args.verbose = False
            
            # 데모 모드 실행
            result = run_demo_mode(mock_ctx, args)
            
            # 결과 확인
            self.assertEqual(result, ExitCode.DEMO_ERROR)
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_monitor_mode_success(self, mock_context_runtime):
        """모니터링 모드 성공 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 인수 생성
        args = Mock()
        args.timeout = 1  # 빠른 테스트를 위해 1초
        args.interval = 0.1  # 빠른 테스트를 위해 0.1초
        args.max_events = 5
        args.verbose = False
        
        # 모니터링 모드 실행
        result = run_monitor_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.SUCCESS)
        mock_ctx.start_monitoring.assert_called_once()
        mock_ctx.stop_monitoring.assert_called_once()
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_monitor_mode_timeout(self, mock_context_runtime):
        """모니터링 모드 타임아웃 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 인수 생성
        args = Mock()
        args.timeout = 0.1  # 매우 짧은 타임아웃
        args.interval = 0.05
        args.max_events = None
        args.verbose = False
        
        # 모니터링 모드 실행
        result = run_monitor_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.SUCCESS)
        mock_ctx.start_monitoring.assert_called_once()
        mock_ctx.stop_monitoring.assert_called_once()
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_monitor_mode_error(self, mock_context_runtime):
        """모니터링 모드 에러 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_ctx.start_monitoring.side_effect = Exception("Monitoring error")
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 인수 생성
        args = Mock()
        args.timeout = 300
        args.interval = 1
        args.max_events = None
        args.verbose = False
        
        # 모니터링 모드 실행
        result = run_monitor_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.MONITORING_ERROR)
        mock_ctx.stop_monitoring.assert_called_once()
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_simulate_mode_success(self, mock_context_runtime):
        """시뮬레이션 모드 성공 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_ctx.simulate_workflow.return_value = {
            'handle_result': {'success': True},
            'drift_result': {'drift_detected': False, 'level': 0},
            'snapshot_path': '/tmp/snapshot.json',
            'delta': {'test': 'data'},
            'runtime_status': {'status': 'ok'}
        }
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 인수 생성
        args = Mock()
        args.output = None
        args.verbose = False
        
        # 시뮬레이션 모드 실행
        result = run_simulate_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.SUCCESS)
        mock_ctx.simulate_workflow.assert_called_once()
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_simulate_mode_with_output(self, mock_context_runtime):
        """출력 파일이 있는 시뮬레이션 모드 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_ctx.simulate_workflow.return_value = {
            'handle_result': {'success': True},
            'drift_result': {'drift_detected': False, 'level': 0},
            'snapshot_path': '/tmp/snapshot.json',
            'delta': {'test': 'data'},
            'runtime_status': {'status': 'ok'}
        }
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 인수 생성
        args = Mock()
        args.output = str(self.temp_dir / "output.json")
        args.verbose = False
        
        # 시뮬레이션 모드 실행
        result = run_simulate_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.SUCCESS)
        mock_ctx.simulate_workflow.assert_called_once()
        
        # 출력 파일 생성 확인
        output_file = Path(args.output)
        self.assertTrue(output_file.exists())
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_simulate_mode_error(self, mock_context_runtime):
        """시뮬레이션 모드 에러 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_ctx.simulate_workflow.side_effect = Exception("Simulation error")
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 인수 생성
        args = Mock()
        args.output = None
        args.verbose = False
        
        # 시뮬레이션 모드 실행
        result = run_simulate_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.SIMULATION_ERROR)
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_replay_mode_success(self, mock_context_runtime):
        """리플레이 모드 성공 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_ctx.handle_delta.return_value = {'success': True}
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 입력 파일 생성
        input_file = self.temp_dir / "events.jsonl"
        with open(input_file, 'w') as f:
            f.write('{"event": "test1"}\n')
            f.write('{"event": "test2"}\n')
        
        # 테스트 인수 생성
        args = Mock()
        args.input = str(input_file)
        args.output = None
        args.max_events = None
        args.verbose = False
        
        # 리플레이 모드 실행
        result = run_replay_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.SUCCESS)
        self.assertEqual(mock_ctx.handle_delta.call_count, 2)
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_replay_mode_no_input(self, mock_context_runtime):
        """입력 파일이 없는 리플레이 모드 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 인수 생성
        args = Mock()
        args.input = None
        args.output = None
        args.max_events = None
        args.verbose = False
        
        # 리플레이 모드 실행
        result = run_replay_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.CONFIG_ERROR)
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_replay_mode_file_not_found(self, mock_context_runtime):
        """존재하지 않는 입력 파일 리플레이 모드 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 인수 생성
        args = Mock()
        args.input = "nonexistent.jsonl"
        args.output = None
        args.max_events = None
        args.verbose = False
        
        # 리플레이 모드 실행
        result = run_replay_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.CONFIG_ERROR)
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_replay_mode_with_max_events(self, mock_context_runtime):
        """최대 이벤트 수 제한 리플레이 모드 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_ctx.handle_delta.return_value = {'success': True}
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 입력 파일 생성
        input_file = self.temp_dir / "events.jsonl"
        with open(input_file, 'w') as f:
            for i in range(10):
                f.write(f'{{"event": "test{i}"}}\n')
        
        # 테스트 인수 생성
        args = Mock()
        args.input = str(input_file)
        args.output = None
        args.max_events = 5
        args.verbose = False
        
        # 리플레이 모드 실행
        result = run_replay_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.SUCCESS)
        self.assertEqual(mock_ctx.handle_delta.call_count, 5)
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_replay_mode_invalid_json(self, mock_context_runtime):
        """잘못된 JSON 리플레이 모드 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 입력 파일 생성 (잘못된 JSON)
        input_file = self.temp_dir / "events.jsonl"
        with open(input_file, 'w') as f:
            f.write('{"event": "test1"}\n')
            f.write('invalid json\n')
            f.write('{"event": "test2"}\n')
        
        # 테스트 인수 생성
        args = Mock()
        args.input = str(input_file)
        args.output = None
        args.max_events = None
        args.verbose = False
        
        # 리플레이 모드 실행
        result = run_replay_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.SUCCESS)
        self.assertEqual(mock_ctx.handle_delta.call_count, 2)  # 유효한 JSON만 처리
    
    @patch('run_memoryos.ContextRuntime')
    def test_run_replay_mode_with_output(self, mock_context_runtime):
        """출력 파일이 있는 리플레이 모드 테스트"""
        # Mock 설정
        mock_ctx = Mock()
        mock_ctx.handle_delta.return_value = {'success': True}
        mock_context_runtime.return_value = mock_ctx
        
        # 테스트 입력 파일 생성
        input_file = self.temp_dir / "events.jsonl"
        with open(input_file, 'w') as f:
            f.write('{"event": "test1"}\n')
            f.write('{"event": "test2"}\n')
        
        # 테스트 인수 생성
        args = Mock()
        args.input = str(input_file)
        args.output = str(self.temp_dir / "replay_output.json")
        args.max_events = None
        args.verbose = False
        
        # 리플레이 모드 실행
        result = run_replay_mode(mock_ctx, args)
        
        # 결과 확인
        self.assertEqual(result, ExitCode.SUCCESS)
        
        # 출력 파일 생성 확인
        output_file = Path(args.output)
        self.assertTrue(output_file.exists())
        
        # 출력 파일 내용 확인
        import json
        with open(output_file, 'r') as f:
            output_data = json.load(f)
            self.assertEqual(output_data['events_processed'], 2)
            self.assertEqual(output_data['events_failed'], 0)
            self.assertEqual(output_data['success_rate'], 100.0)


if __name__ == "__main__":
    unittest.main()

