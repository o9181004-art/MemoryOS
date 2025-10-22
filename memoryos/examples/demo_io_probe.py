"""
Demo IoProbe - Delta 감지 예제

IoProbe를 사용한 파일 변경 감지 및 delta 이벤트 생성 예제입니다.
"""

import time
from pathlib import Path
from memoryos.core.io_probe import IoProbe


def demo_io_probe():
    """IoProbe 데모 실행"""
    print("=== MemoryOS IoProbe Demo ===")
    
    # 테스트 디렉토리 생성
    test_dir = Path("test_data")
    test_dir.mkdir(exist_ok=True)
    
    # IoProbe 초기화
    io_probe = IoProbe(
        watch_paths=[str(test_dir)],
        callback=lambda delta: print(f"[Callback] Delta detected: {delta}")
    )
    
    print(f"Monitoring directory: {test_dir}")
    
    # 테스트 파일 생성 및 수정
    test_file = test_dir / "example.txt"
    
    print("\n1. Creating test file...")
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("Initial content")
    
    # 변경사항 감지
    print("\n2. Detecting changes...")
    deltas = io_probe.detect_changes()
    for delta in deltas:
        print(f"   Detected: {delta}")
    
    time.sleep(1)
    
    print("\n3. Modifying test file...")
    with open(test_file, 'a', encoding='utf-8') as f:
        f.write("\nModified content")
    
    # 변경사항 감지
    deltas = io_probe.detect_changes()
    for delta in deltas:
        print(f"   Detected: {delta}")
    
    time.sleep(1)
    
    print("\n4. Simulating delta event...")
    io_probe.simulate_delta(
        path=str(test_file),
        operation="write",
        producer="demo_module"
    )
    
    print("\n5. File hash calculation demo...")
    file_hash = io_probe.calculate_file_hash(test_file)
    print(f"   File hash: {file_hash}")
    
    # 정리
    print("\n6. Cleaning up...")
    test_file.unlink()
    test_dir.rmdir()
    
    print("=== Demo completed ===")


if __name__ == "__main__":
    demo_io_probe()
