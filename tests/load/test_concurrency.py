"""
Load Test: SQLite WAL Mode Concurrency

SQLite WAL 모드에서 동시 읽기/쓰기 작업의 성능을 테스트합니다.
50개 읽기 세션과 1개 쓰기 세션의 동시 실행을 검증합니다.
"""

import pytest
import sqlite3
import threading
import time
from pathlib import Path
from memoryos.store.memory_index_store import MemoryIndexStore


@pytest.fixture
def wal_db_path(tmp_path):
    """테스트용 WAL 데이터베이스 경로"""
    db_file = tmp_path / "test_wal.db"
    yield str(db_file)
    # Clean up WAL files
    if db_file.exists():
        try:
            db_file.unlink()
        except PermissionError:
            # Windows에서 파일이 사용 중일 때 무시
            pass
    if Path(str(db_file) + "-wal").exists():
        Path(str(db_file) + "-wal").unlink()
    if Path(str(db_file) + "-shm").exists():
        Path(str(db_file) + "-shm").unlink()


@pytest.fixture
def wal_store(wal_db_path):
    """테스트용 WAL 저장소"""
    store = MemoryIndexStore(wal_db_path, storage_type="sqlite")
    # 초기 데이터 삽입
    store.save_file_index("initial.txt", {"current_hash": "abc", "last_updated": time.time(), "version": 1})
    yield store
    store.close()


def reader_task(db_path, results, stop_event):
    """읽기 작업 스레드"""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")  # Reader도 WAL 모드로 연결
        read_count = 0
        
        while not stop_event.is_set():
            try:
                cursor = conn.execute("SELECT * FROM file_index")
                rows = cursor.fetchall()
                assert len(rows) >= 1  # 최소한 초기 데이터는 있어야 함
                read_count += 1
                time.sleep(0.01)  # 짧은 대기
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    results.append(f"Reader locked: {e}")
                    time.sleep(0.05)  # 잠금 시 더 오래 대기
                else:
                    raise
                    
        results.append(f"Reader finished, reads: {read_count}")
    except Exception as e:
        results.append(f"Reader error: {e}")
    finally:
        if conn:
            conn.close()


def writer_task(store: MemoryIndexStore, results, stop_event):
    """쓰기 작업 스레드"""
    write_count = 0
    try:
        while not stop_event.is_set():
            file_name = f"file_{write_count}.txt"
            file_data = {
                "current_hash": f"hash_{write_count}",
                "last_updated": time.time(),
                "version": write_count + 1
            }
            store.save_file_index(file_name, file_data)
            write_count += 1
            time.sleep(0.05)  # Reader보다 쓰기 빈도를 낮춤
            
        results.append(f"Writer finished, writes: {write_count}")
    except Exception as e:
        results.append(f"Writer error: {e}")


def test_concurrency_wal_mode(wal_db_path):
    """
    SQLite WAL 모드에서 동시 50세션 read + 1 write 충돌 없음 테스트
    """
    num_readers = 50
    duration = 5  # 초
    
    # Writer 설정
    writer_store = MemoryIndexStore(wal_db_path, storage_type="sqlite")
    writer_results = []
    writer_stop_event = threading.Event()
    writer_thread = threading.Thread(target=writer_task, args=(writer_store, writer_results, writer_stop_event))
    
    # Reader 설정
    reader_results = [[] for _ in range(num_readers)]
    reader_stop_event = threading.Event()
    reader_threads = []
    
    for i in range(num_readers):
        thread = threading.Thread(target=reader_task, args=(wal_db_path, reader_results[i], reader_stop_event))
        reader_threads.append(thread)
    
    # 스레드 시작
    writer_thread.start()
    for thread in reader_threads:
        thread.start()
    
    # 지정된 시간 동안 실행
    time.sleep(duration)
    
    # 스레드 종료 신호
    writer_stop_event.set()
    reader_stop_event.set()
    
    # 스레드 종료 대기
    writer_thread.join()
    for thread in reader_threads:
        thread.join()
    
    writer_store.close()
    
    # 결과 검증
    print("\n--- Concurrency Test Results ---")
    for res in writer_results:
        print(res)
    for i, res_list in enumerate(reader_results):
        for res in res_list:
            print(f"Reader {i}: {res}")
            assert "locked" not in res  # "database is locked" 오류가 발생하지 않아야 함
    
    # 모든 스레드가 성공적으로 실행되었는지 확인
    assert any("Writer finished" in res for res in writer_results)
    assert all(any("Reader finished" in res for res in res_list) for res_list in reader_results)
    
    # 최소한의 읽기/쓰기 작업이 수행되었는지 확인
    total_reads = sum(int(res.split(': ')[1]) for res_list in reader_results for res in res_list if "reads" in res)
    total_writes = sum(int(res.split(': ')[1]) for res in writer_results if "writes" in res)
    
    print(f"Total reads: {total_reads}")
    print(f"Total writes: {total_writes}")
    
    assert total_reads > 0
    assert total_writes > 0


def test_wal_mode_status(wal_store):
    """WAL 모드 상태 확인 테스트"""
    wal_status = wal_store.get_wal_status()
    
    assert wal_status["wal_mode"] is True
    assert wal_status["journal_mode"] == "wal"
    assert wal_status["wal_file_exists"] is True
    assert wal_status["wal_file_size"] >= 0
    
    # 체크포인트 정보 확인
    checkpoint_info = wal_status["checkpoint_info"]
    assert "busy" in checkpoint_info
    assert "log" in checkpoint_info
    assert "checkpointed" in checkpoint_info


def test_wal_performance_optimization(wal_store):
    """WAL 성능 최적화 테스트"""
    # 초기 데이터 추가
    for i in range(100):
        wal_store.save_file_index(f"test_file_{i}.txt", {
            "current_hash": f"hash_{i}",
            "last_updated": time.time(),
            "version": i
        })
    
    # 성능 최적화 실행
    optimization_result = wal_store.optimize_sqlite_performance()
    
    assert optimization_result["optimized"] is True
    assert optimization_result["reindex_completed"] is True
    assert optimization_result["analyze_completed"] is True
    
    # 체크포인트 결과 확인
    checkpoint_result = optimization_result["checkpoint_result"]
    assert "busy" in checkpoint_result
    assert "log" in checkpoint_result
    assert "checkpointed" in checkpoint_result


def test_wal_concurrent_readers(wal_db_path):
    """WAL 모드에서 동시 읽기 작업 테스트"""
    num_readers = 20
    duration = 3  # 초
    
    # 초기 데이터 설정
    store = MemoryIndexStore(wal_db_path, storage_type="sqlite")
    for i in range(50):
        store.save_file_index(f"data_{i}.txt", {
            "current_hash": f"hash_{i}",
            "last_updated": time.time(),
            "version": i
        })
    store.close()
    
    # 읽기 스레드들
    reader_results = [[] for _ in range(num_readers)]
    reader_stop_event = threading.Event()
    reader_threads = []
    
    for i in range(num_readers):
        thread = threading.Thread(target=reader_task, args=(wal_db_path, reader_results[i], reader_stop_event))
        reader_threads.append(thread)
    
    # 스레드 시작
    for thread in reader_threads:
        thread.start()
    
    # 지정된 시간 동안 실행
    time.sleep(duration)
    
    # 스레드 종료
    reader_stop_event.set()
    for thread in reader_threads:
        thread.join()
    
    # 결과 검증
    total_reads = sum(int(res.split(': ')[1]) for res_list in reader_results for res in res_list if "reads" in res)
    print(f"Total concurrent reads: {total_reads}")
    
    assert total_reads > 0
    # 모든 읽기 스레드가 성공적으로 실행되었는지 확인
    assert all(any("Reader finished" in res for res in res_list) for res_list in reader_results)


def test_wal_checkpoint_behavior(wal_store):
    """WAL 체크포인트 동작 테스트"""
    # WAL 상태 확인
    initial_status = wal_store.get_wal_status()
    initial_checkpointed = initial_status["checkpoint_info"]["checkpointed"]
    
    # 많은 쓰기 작업 수행
    for i in range(1000):
        wal_store.save_file_index(f"checkpoint_test_{i}.txt", {
            "current_hash": f"hash_{i}",
            "last_updated": time.time(),
            "version": i
        })
    
    # 체크포인트 실행
    optimization_result = wal_store.optimize_sqlite_performance()
    
    # 체크포인트 후 상태 확인
    final_status = wal_store.get_wal_status()
    final_checkpointed = final_status["checkpoint_info"]["checkpointed"]
    
    # 체크포인트가 진행되었는지 확인
    assert final_checkpointed >= initial_checkpointed
    
    # WAL 파일 크기 확인
    assert final_status["wal_file_size"] >= 0


def test_wal_mode_vs_delete_mode(wal_db_path):
    """WAL 모드와 DELETE 모드 성능 비교 테스트"""
    # WAL 모드 테스트
    wal_store = MemoryIndexStore(wal_db_path, storage_type="sqlite")
    wal_start_time = time.time()
    
    for i in range(100):
        wal_store.save_file_index(f"wal_test_{i}.txt", {
            "current_hash": f"hash_{i}",
            "last_updated": time.time(),
            "version": i
        })
    
    wal_end_time = time.time()
    wal_duration = wal_end_time - wal_start_time
    wal_store.close()
    
    # DELETE 모드로 변경
    conn = sqlite3.connect(wal_db_path)
    conn.execute("PRAGMA journal_mode=DELETE;")
    conn.close()
    
    delete_store = MemoryIndexStore(wal_db_path, storage_type="sqlite")
    delete_start_time = time.time()
    
    for i in range(100):
        delete_store.save_file_index(f"delete_test_{i}.txt", {
            "current_hash": f"hash_{i}",
            "last_updated": time.time(),
            "version": i
        })
    
    delete_end_time = time.time()
    delete_duration = delete_end_time - delete_start_time
    delete_store.close()
    
    print(f"WAL mode duration: {wal_duration:.3f}s")
    print(f"DELETE mode duration: {delete_duration:.3f}s")
    
    # WAL 모드가 더 빠르거나 비슷해야 함
    assert wal_duration <= delete_duration * 1.5  # 50% 이내 차이 허용


if __name__ == "__main__":
    pytest.main([__file__])