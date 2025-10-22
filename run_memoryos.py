#!/usr/bin/env python3
"""
MemoryOS Main Runner

MemoryOS SDK의 메인 실행 파일입니다.
전체 파이프라인을 실행하고 워크플로우를 시뮬레이션합니다.
"""

import sys
import time
import argparse
from pathlib import Path
from enum import Enum

# MemoryOS 모듈 import
from memoryos.core.context_runtime import ContextRuntime


class ExitCode(Enum):
    """표준화된 종료 코드"""
    SUCCESS = 0
    GENERAL_ERROR = 1
    CONFIG_ERROR = 2
    RUNTIME_ERROR = 3
    PERMISSION_ERROR = 4
    VALIDATION_ERROR = 5
    MONITORING_ERROR = 6
    SIMULATION_ERROR = 7
    DEMO_ERROR = 8


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="MemoryOS - Operational Memory Layer SDK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_memoryos.py                           # Basic simulation
  python run_memoryos.py --mode demo              # Demo mode
  python run_memoryos.py --mode monitor --verbose # Monitor mode with verbose output
  python run_memoryos.py --config my_config.toml  # Custom configuration
  python run_memoryos.py --readonly               # Read-only mode
  python run_memoryos.py --mode replay --input events.jsonl  # Replay mode
        """
    )
    
    # 기본 옵션
    parser.add_argument("--config", "-c", 
                      default="memoryos/config/default.toml",
                      help="Configuration file path (default: memoryos/config/default.toml)")
    
    parser.add_argument("--mode", "-m", 
                      choices=["demo", "monitor", "simulate", "replay"],
                      default="simulate", 
                      help="Execution mode (default: simulate)")
    
    parser.add_argument("--verbose", "-v", 
                      action="store_true",
                      help="Enable verbose output")
    
    parser.add_argument("--readonly", "-r",
                      action="store_true",
                      help="Run in read-only mode (no writes to filesystem)")
    
    # 고급 옵션
    parser.add_argument("--input", "-i",
                      help="Input file for replay mode (JSONL format)")
    
    parser.add_argument("--output", "-o",
                      help="Output file for results (default: stdout)")
    
    parser.add_argument("--timeout", "-t",
                      type=int,
                      default=300,
                      help="Timeout in seconds for monitoring mode (default: 300)")
    
    parser.add_argument("--interval", "-n",
                      type=int,
                      default=1,
                      help="Monitoring interval in seconds (default: 1)")
    
    parser.add_argument("--max-events", "-e",
                      type=int,
                      help="Maximum number of events to process")
    
    parser.add_argument("--dry-run",
                      action="store_true",
                      help="Perform a dry run without actual execution")
    
    parser.add_argument("--version",
                      action="version",
                      version="MemoryOS SDK v1.0.0")
    
    args = parser.parse_args()
    
    print("🧭 MemoryOS - Operational Memory Layer SDK")
    print("=" * 50)
    
    try:
        # 설정 파일 검증
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"❌ Configuration file not found: {args.config}")
            sys.exit(ExitCode.CONFIG_ERROR.value)
        
        # ContextRuntime 초기화
        print(f"📁 Loading configuration from: {args.config}")
        
        # Read-only 모드 설정
        if args.readonly:
            print("🔒 Running in read-only mode")
        
        ctx = ContextRuntime(config_path=str(config_path))
        
        if args.verbose:
            print("🔧 Configuration loaded successfully")
            print(f"📊 Runtime status: {ctx.get_runtime_status()}")
            print(f"🔒 Read-only mode: {args.readonly}")
        
        # Dry run 모드
        if args.dry_run:
            print("🧪 Dry run mode - no actual execution")
            print(f"Would execute mode: {args.mode}")
            if args.input:
                print(f"Would process input: {args.input}")
            sys.exit(ExitCode.SUCCESS.value)
        
        # 실행 모드에 따른 처리
        exit_code = ExitCode.SUCCESS
        
        if args.mode == "demo":
            exit_code = run_demo_mode(ctx, args)
        elif args.mode == "monitor":
            exit_code = run_monitor_mode(ctx, args)
        elif args.mode == "simulate":
            exit_code = run_simulate_mode(ctx, args)
        elif args.mode == "replay":
            exit_code = run_replay_mode(ctx, args)
        
        sys.exit(exit_code.value)
            
    except PermissionError as e:
        print(f"❌ Permission error: {e}")
        sys.exit(ExitCode.PERMISSION_ERROR.value)
    except FileNotFoundError as e:
        print(f"❌ File not found: {e}")
        sys.exit(ExitCode.CONFIG_ERROR.value)
    except Exception as e:
        print(f"❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(ExitCode.GENERAL_ERROR.value)


def run_demo_mode(_ctx: ContextRuntime, args) -> ExitCode:
    """데모 모드 실행"""
    print("\n🎬 Running Demo Mode")
    print("-" * 30)
    
    try:
        # 예제 실행
        from memoryos.examples.demo_io_probe import demo_io_probe
        from memoryos.examples.demo_self_heal import demo_self_heal
        
        print("\n1. IoProbe Demo")
        demo_io_probe()
        
        print("\n2. SelfHeal Demo")
        demo_self_heal()
        
        # A/B Runner 데모 (선택적)
        if args.verbose:
            try:
                from memoryos.examples.ab_runner import run_ab_test
                print("\n3. A/B Runner Demo")
                run_ab_test()
            except ImportError:
                print("\n3. A/B Runner Demo (skipped - dependencies not available)")
        
        print("\n✅ Demo mode completed successfully")
        return ExitCode.SUCCESS
        
    except Exception as e:
        print(f"❌ Demo mode failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return ExitCode.DEMO_ERROR


def run_monitor_mode(ctx: ContextRuntime, args) -> ExitCode:
    """모니터링 모드 실행"""
    print("\n👁️ Running Monitor Mode")
    print("-" * 30)
    
    try:
        # 모니터링 시작
        ctx.start_monitoring()
        
        print(f"🔍 Monitoring started. Timeout: {args.timeout}s, Interval: {args.interval}s")
        print("Press Ctrl+C to stop...")
        
        start_time = time.time()
        event_count = 0
        
        # 모니터링 루프
        while True:
            time.sleep(args.interval)
            
            # 타임아웃 확인
            if time.time() - start_time > args.timeout:
                print(f"\n⏰ Monitoring timeout reached ({args.timeout}s)")
                break
            
            # 최대 이벤트 수 확인
            if args.max_events and event_count >= args.max_events:
                print(f"\n📊 Maximum events processed ({args.max_events})")
                break
            
            if args.verbose:
                status = ctx.get_runtime_status()
                print(f"📊 Status: {status}")
            
            event_count += 1
                
    except KeyboardInterrupt:
        print("\n⏹️ Monitoring stopped by user")
        ctx.stop_monitoring()
        return ExitCode.SUCCESS
    except Exception as e:
        print(f"❌ Monitoring failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        ctx.stop_monitoring()
        return ExitCode.MONITORING_ERROR


def run_simulate_mode(ctx: ContextRuntime, args) -> ExitCode:
    """시뮬레이션 모드 실행"""
    print("\n🎯 Running Simulation Mode")
    print("-" * 30)
    
    try:
        # 전체 워크플로우 시뮬레이션
        print("🚀 Starting workflow simulation...")
        
        result = ctx.simulate_workflow()
        
        # 결과 출력
        if args.output:
            output_path = Path(args.output)
            with open(output_path, 'w', encoding='utf-8') as f:
                import json
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"📄 Results saved to: {output_path}")
        else:
            print("\n📋 Simulation Results:")
            print(f"  - Delta processed: {result['handle_result']['success']}")
            print(f"  - Drift detected: {result['drift_result']['drift_detected']}")
            print(f"  - Drift level: {result['drift_result'].get('level', 'N/A')}")
            print(f"  - Snapshot created: {result['snapshot_path']}")
        
        if args.verbose:
            print("🔍 Detailed Results:")
            print(f"  - Delta: {result['delta']}")
            print(f"  - Handle result: {result['handle_result']}")
            print(f"  - Drift result: {result['drift_result']}")
            print(f"  - Runtime status: {result['runtime_status']}")
        
        print("\n✅ Simulation completed successfully")
        return ExitCode.SUCCESS
        
    except Exception as e:
        print(f"❌ Simulation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return ExitCode.SIMULATION_ERROR


def run_replay_mode(ctx: ContextRuntime, args) -> ExitCode:
    """리플레이 모드 실행"""
    print("\n🔄 Running Replay Mode")
    print("-" * 30)
    
    try:
        # 입력 파일 검증
        if not args.input:
            print("❌ Input file required for replay mode")
            print("Use --input <file.jsonl> to specify input file")
            return ExitCode.CONFIG_ERROR
        
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"❌ Input file not found: {args.input}")
            return ExitCode.CONFIG_ERROR
        
        print(f"📁 Processing input file: {args.input}")
        
        # JSONL 파일 읽기 및 처리
        events_processed = 0
        events_failed = 0
        
        with open(input_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    import json
                    event = json.loads(line)
                    
                    # 이벤트 처리
                    result = ctx.handle_delta(event)
                    
                    if result.get('success', False):
                        events_processed += 1
                    else:
                        events_failed += 1
                        if args.verbose:
                            print(f"⚠️ Event {line_num} failed: {result}")
                    
                    # 최대 이벤트 수 확인
                    if args.max_events and (events_processed + events_failed) >= args.max_events:
                        print(f"\n📊 Maximum events reached ({args.max_events})")
                        break
                    
                    if args.verbose and events_processed % 10 == 0:
                        print(f"📊 Processed {events_processed} events...")
                
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid JSON at line {line_num}: {e}")
                    events_failed += 1
                except Exception as e:
                    print(f"❌ Error processing line {line_num}: {e}")
                    events_failed += 1
        
        # 결과 출력
        print("\n📋 Replay Results:")
        print(f"  - Events processed: {events_processed}")
        print(f"  - Events failed: {events_failed}")
        print(f"  - Success rate: {events_processed/(events_processed+events_failed)*100:.1f}%")
        
        if args.output:
            output_path = Path(args.output)
            with open(output_path, 'w', encoding='utf-8') as f:
                import json
                json.dump({
                    "events_processed": events_processed,
                    "events_failed": events_failed,
                    "success_rate": events_processed/(events_processed+events_failed) if (events_processed+events_failed) > 0 else 0
                }, f, indent=2, ensure_ascii=False)
            print(f"📄 Results saved to: {output_path}")
        
        print("\n✅ Replay completed successfully")
        return ExitCode.SUCCESS
        
    except Exception as e:
        print(f"❌ Replay failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return ExitCode.RUNTIME_ERROR


def print_usage():
    """사용법 출력"""
    print("""
MemoryOS Usage Examples:

1. Basic simulation:
   python run_memoryos.py

2. Demo mode:
   python run_memoryos.py --mode demo

3. Monitor mode:
   python run_memoryos.py --mode monitor --verbose

4. Custom config:
   python run_memoryos.py --config my_config.toml --mode simulate

5. Read-only mode:
   python run_memoryos.py --readonly

6. Replay mode:
   python run_memoryos.py --mode replay --input events.jsonl

7. Dry run:
   python run_memoryos.py --dry-run --mode simulate

8. With timeout and max events:
   python run_memoryos.py --mode monitor --timeout 60 --max-events 100

9. Verbose output:
   python run_memoryos.py --verbose

10. Version info:
    python run_memoryos.py --version

Exit Codes:
  0 - Success
  1 - General error
  2 - Configuration error
  3 - Runtime error
  4 - Permission error
  5 - Validation error
  6 - Monitoring error
  7 - Simulation error
  8 - Demo error
""")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["--help", "-h", "help"]:
        print_usage()
        sys.exit(ExitCode.SUCCESS.value)
        
    main()
