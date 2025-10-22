"""
Integration Test: HashChain Atomicity Guarantee

Temporal Hash Chain의 원자성 보장을 검증합니다.
SQLite 트랜잭션을 통한 체인 업데이트의 일관성을 테스트합니다.
"""

import pytest
import sqlite3
from memoryos.core.hashchain import HashChain
from pathlib import Path


@pytest.fixture
def hash_chain_db(tmp_path):
    """테스트용 HashChain 데이터베이스"""
    db_path = tmp_path / "test_hashchain.db"
    hc = HashChain(str(db_path))
    yield hc
    # Clean up
    try:
        if db_path.exists():
            db_path.unlink()
    except PermissionError:
        # Windows에서 파일이 사용 중일 때 무시
        pass


def test_add_block_atomic_success(hash_chain_db):
    """원자적 블록 추가 성공 시 체인 무결성 검증"""
    initial_data = {"file": "a.txt", "content": "hello"}
    first_hash = hash_chain_db.add_block_atomic(initial_data)
    
    assert first_hash is not None
    assert len(hash_chain_db.chain) == 1
    assert hash_chain_db.chain[0]["hash"] == first_hash
    
    # 데이터베이스에서 확인
    with sqlite3.connect(hash_chain_db.db_path) as conn:
        cursor = conn.execute("SELECT version_id, prev_hash, content_hash, data FROM hash_chain")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 1  # version_id
        assert row[1] is None  # prev_hash (첫 블록)
        assert row[2] == first_hash  # content_hash
        assert row[3] == '{"file": "a.txt", "content": "hello"}'  # data
    
    # 두 번째 블록 추가
    second_data = {"file": "b.txt", "content": "world"}
    second_hash = hash_chain_db.add_block_atomic(second_data, first_hash)
    
    assert second_hash is not None
    assert len(hash_chain_db.chain) == 2
    assert hash_chain_db.chain[1]["hash"] == second_hash
    assert hash_chain_db.chain[1]["prev_hash"] == first_hash
    
    # 데이터베이스에서 두 번째 블록 확인
    with sqlite3.connect(hash_chain_db.db_path) as conn:
        cursor = conn.execute("SELECT version_id, prev_hash, content_hash FROM hash_chain WHERE version_id = 2")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 2  # version_id
        assert row[1] == first_hash  # prev_hash
        assert row[2] == second_hash  # content_hash


def test_add_block_atomic_failure_no_chain_break(hash_chain_db):
    """원자적 블록 추가 중 강제 예외 발생 시 체인 끊김이 없어야 함"""
    initial_data = {"file": "a.txt", "content": "hello"}
    first_hash = hash_chain_db.add_block_atomic(initial_data)
    
    assert len(hash_chain_db.chain) == 1
    with sqlite3.connect(hash_chain_db.db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM hash_chain")
        assert cursor.fetchone()[0] == 1
    
    # 강제 예외를 발생시키는 더미 데이터
    class BadData(dict):
        def __str__(self):
            raise ValueError("Simulated error during serialization")
    
    bad_data = BadData({"file": "c.txt", "content": "error"})
    
    with pytest.raises(ValueError):
        hash_chain_db.add_block_atomic(bad_data, first_hash)
    
    # 예외 발생 후에도 기존 체인은 그대로 유지되어야 함
    assert len(hash_chain_db.chain) == 1
    with sqlite3.connect(hash_chain_db.db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM hash_chain")
        assert cursor.fetchone()[0] == 1  # 새로운 블록은 추가되지 않아야 함
    
    # 기존 블록의 prev_hash는 단절되지 않아야 함
    with sqlite3.connect(hash_chain_db.db_path) as conn:
        cursor = conn.execute("SELECT prev_hash FROM hash_chain WHERE version_id = 1")
        assert cursor.fetchone()[0] is None  # 첫 블록이므로 prev_hash는 None


def test_merkle_root_update_atomic(hash_chain_db):
    """원자적 블록 추가 시 Merkle 루트가 올바르게 업데이트되는지 확인"""
    data1 = {"file": "f1.txt", "content": "data1"}
    hash_chain_db.add_block_atomic(data1)
    
    with sqlite3.connect(hash_chain_db.db_path) as conn:
        cursor = conn.execute("SELECT merkle_root FROM hash_chain WHERE version_id = 1")
        merkle_root1 = cursor.fetchone()[0]
        assert merkle_root1 != ""
    
    data2 = {"file": "f2.txt", "content": "data2"}
    hash_chain_db.add_block_atomic(data2)
    
    with sqlite3.connect(hash_chain_db.db_path) as conn:
        cursor = conn.execute("SELECT merkle_root FROM hash_chain WHERE version_id = 2")
        merkle_root2 = cursor.fetchone()[0]
        assert merkle_root2 != ""
        assert merkle_root1 != merkle_root2  # 루트 해시가 변경되어야 함


def test_concurrent_atomic_operations(hash_chain_db):
    """동시 원자적 작업 시 데이터 일관성 검증"""
    import threading
    import time
    
    results = []
    errors = []
    
    def add_block_worker(worker_id, data_prefix):
        try:
            for i in range(5):
                data = {"worker": worker_id, "index": i, "content": f"{data_prefix}_{i}"}
                hash_val = hash_chain_db.add_block_atomic(data)
                results.append((worker_id, i, hash_val))
                time.sleep(0.01)  # 짧은 대기
        except Exception as e:
            errors.append(f"Worker {worker_id}: {e}")
    
    # 두 개의 워커 스레드 시작
    thread1 = threading.Thread(target=add_block_worker, args=(1, "worker1"))
    thread2 = threading.Thread(target=add_block_worker, args=(2, "worker2"))
    
    thread1.start()
    thread2.start()
    
    thread1.join()
    thread2.join()
    
    # 에러가 없어야 함
    assert len(errors) == 0, f"Concurrent operations failed: {errors}"
    
    # 모든 작업이 성공적으로 완료되었는지 확인
    assert len(results) == 10  # 2 workers * 5 operations each
    
    # 체인 무결성 검증
    is_valid, errors = hash_chain_db.verify_chain()
    assert is_valid, f"Chain verification failed: {errors}"
    
    # 데이터베이스와 메모리 체인이 일치하는지 확인
    with sqlite3.connect(hash_chain_db.db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM hash_chain")
        db_count = cursor.fetchone()[0]
        assert db_count == len(hash_chain_db.chain)


def test_transaction_rollback_on_error(hash_chain_db):
    """트랜잭션 롤백 시 데이터베이스 상태 검증"""
    initial_data = {"file": "initial.txt", "content": "initial"}
    initial_hash = hash_chain_db.add_block_atomic(initial_data)
    
    initial_count = len(hash_chain_db.chain)
    
    # 데이터베이스 직접 조작으로 트랜잭션 실패 시뮬레이션
    with sqlite3.connect(hash_chain_db.db_path) as conn:
        # 잘못된 데이터로 인한 제약 조건 위반 시도
        try:
            conn.execute("""
                INSERT INTO hash_chain (version_id, prev_hash, content_hash, timestamp, data, merkle_root)
                VALUES (NULL, ?, ?, ?, ?, ?)
            """, (initial_hash, "invalid_hash", time.time(), "{}", ""))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
    
    # 체인 상태가 변경되지 않았는지 확인
    assert len(hash_chain_db.chain) == initial_count
    
    with sqlite3.connect(hash_chain_db.db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM hash_chain")
        db_count = cursor.fetchone()[0]
        assert db_count == initial_count


if __name__ == "__main__":
    pytest.main([__file__])