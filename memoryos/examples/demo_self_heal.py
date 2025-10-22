"""
Demo SelfHeal - Drift → Self-Heal 시뮬레이션

Drift 감지부터 자동 복원까지의 전체 워크플로우를 시뮬레이션합니다.
"""

import time
from pathlib import Path
from memoryos.guard.drift_guard import DriftGuard
from memoryos.guard.self_heal import SelfHeal
from memoryos.guard.policy import Policy


def demo_self_heal():
    """SelfHeal 데모 실행"""
    print("=== MemoryOS SelfHeal Demo ===")
    
    # 테스트 디렉토리 생성
    test_dir = Path("test_data")
    test_dir.mkdir(exist_ok=True)
    
    # 컴포넌트 초기화
    drift_guard = DriftGuard()
    self_heal = SelfHeal(
        backup_dir="test_backups",
        quarantine_dir="test_quarantine"
    )
    policy = Policy()
    
    print("Components initialized:")
    print(f"  - DriftGuard: {drift_guard}")
    print(f"  - SelfHeal: {self_heal}")
    print(f"  - Policy: {policy}")
    
    # 테스트 파일 생성
    test_file = test_dir / "config.json"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write('{"setting": "value"}')
    
    print(f"\nCreated test file: {test_file}")
    
    # 시나리오 1: L1 Drift (경미한 drift)
    print("\n=== Scenario 1: L1 Drift (Log Only) ===")
    
    drift_result_l1 = drift_guard.check_drift(
        file_path=str(test_file),
        producer_actual="unknown_module",
        producer_expected="config_manager",
        last_updated=time.time() - 60,  # 1분 전 업데이트
        update_interval=30
    )
    
    print(f"Drift check result: {drift_result_l1}")
    
    if drift_result_l1["drift_detected"]:
        heal_result = self_heal.execute_heal(drift_result_l1)
        print(f"Heal result: {heal_result}")
    
    time.sleep(1)
    
    # 시나리오 2: L2 Drift (중간 drift)
    print("\n=== Scenario 2: L2 Drift (Auto Merge) ===")
    
    drift_result_l2 = drift_guard.check_drift(
        file_path=str(test_file),
        producer_actual="wrong_module",
        producer_expected="config_manager",
        last_updated=time.time() - 400,  # 6분 전 업데이트
        update_interval=30
    )
    
    print(f"Drift check result: {drift_result_l2}")
    
    if drift_result_l2["drift_detected"]:
        heal_result = self_heal.execute_heal(drift_result_l2)
        print(f"Heal result: {heal_result}")
    
    time.sleep(1)
    
    # 시나리오 3: L3 Drift (심각한 drift)
    print("\n=== Scenario 3: L3 Drift (Restore & Quarantine) ===")
    
    drift_result_l3 = drift_guard.check_drift(
        file_path=str(test_file),
        producer_actual="malicious_module",
        producer_expected="config_manager",
        last_updated=time.time() - 2000,  # 33분 전 업데이트
        update_interval=30
    )
    
    print(f"Drift check result: {drift_result_l3}")
    
    if drift_result_l3["drift_detected"]:
        heal_result = self_heal.execute_heal(drift_result_l3)
        print(f"Heal result: {heal_result}")
    
    # 통계 정보 출력
    print("\n=== Statistics ===")
    
    drift_stats = drift_guard.get_drift_statistics()
    print(f"Drift statistics: {drift_stats}")
    
    heal_stats = self_heal.get_heal_statistics()
    print(f"Heal statistics: {heal_stats}")
    
    policy_stats = policy.get_execution_statistics()
    print(f"Policy statistics: {policy_stats}")
    
    # 격리된 파일 확인
    quarantined_files = self_heal.get_quarantined_files()
    print(f"Quarantined files: {quarantined_files}")
    
    # 정리
    print("\n=== Cleaning up ===")
    
    # 격리에서 파일 해제 (테스트용)
    for file_path in quarantined_files:
        self_heal.release_from_quarantine(file_path)
    
    # 테스트 파일 정리
    if test_file.exists():
        test_file.unlink()
    test_dir.rmdir()
    
    # 백업 및 격리 디렉토리 정리
    import shutil
    if Path("test_backups").exists():
        shutil.rmtree("test_backups")
    if Path("test_quarantine").exists():
        shutil.rmtree("test_quarantine")
    
    print("=== Demo completed ===")


if __name__ == "__main__":
    demo_self_heal()
