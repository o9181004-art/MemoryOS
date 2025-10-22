"""
MemoryIndexStore - 메모리 인덱스 저장소 (WAL 최적화)

메모리 인덱스 데이터를 영구 저장하고 관리합니다.
SQLite WAL 모드 및 성능 최적화를 포함합니다.
"""

import json
import sqlite3
import time
from typing import Dict, List, Optional
from pathlib import Path


class MemoryIndexStore:
    """
    메모리 인덱스 저장소 클래스 (WAL 최적화)
    
    주요 기능:
    - 메모리 인덱스 데이터 영구 저장
    - SQLite WAL 모드 및 성능 최적화
    - 다중 리더·단일 라이터 안전성
    - Idempotency 보장
    - 백업 및 복원
    """
    
    def __init__(self, db_path: str = "data/memory_index.db"):
        """
        MemoryIndexStore 초기화
        
        Args:
            db_path: SQLite 데이터베이스 경로
        """
        self.db_path = db_path
        self.db_dir = Path(db_path).parent
        self.db_dir.mkdir(parents=True, exist_ok=True)
        
        # Idempotency를 위한 중복 처리 방지 키
        self.processed_keys = set()
        
        # 데이터베이스 초기화
        self._init_database()
        
    def _init_database(self) -> None:
        """데이터베이스 초기화 및 WAL 모드 설정"""
        with sqlite3.connect(self.db_path) as conn:
            # WAL 모드 및 성능 최적화 설정
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA mmap_size=268435456")  # 256MB
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA locking_mode=EXCLUSIVE")
            
            # 테이블 생성 (Idempotency 지원)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    producer_actual TEXT,
                    producer_expected TEXT,
                    last_updated REAL NOT NULL,
                    update_interval INTEGER DEFAULT 30,
                    metadata TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    UNIQUE(conversation_id, turn_id, file_path)
                )
            """)
            
            # 인덱스 생성
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_turn 
                ON memory_index(conversation_id, turn_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_file_path 
                ON memory_index(file_path)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_updated 
                ON memory_index(last_updated)
            """)
            
            conn.commit()
            
    def _check_idempotency(self, conversation_id: str, turn_id: str, file_path: str) -> bool:
        """
        Idempotency 확인
        
        Args:
            conversation_id: 대화 ID
            turn_id: 턴 ID
            file_path: 파일 경로
            
        Returns:
            이미 처리된 요청인지 여부
        """
        key = f"{conversation_id}:{turn_id}:{file_path}"
        return key in self.processed_keys
        
    def _mark_processed(self, conversation_id: str, turn_id: str, file_path: str) -> None:
        """
        처리 완료 마킹
        
        Args:
            conversation_id: 대화 ID
            turn_id: 턴 ID
            file_path: 파일 경로
        """
        key = f"{conversation_id}:{turn_id}:{file_path}"
        self.processed_keys.add(key)
        
        # 메모리 사용량 제한 (최근 10000개만 유지)
        if len(self.processed_keys) > 10000:
            # 오래된 키 제거 (간단한 FIFO 방식)
            keys_to_remove = list(self.processed_keys)[:1000]
            for key_to_remove in keys_to_remove:
                self.processed_keys.remove(key_to_remove)
                
    def save_memory_index(self, memory_index: Dict, conversation_id: str = "default", 
                         turn_id: str = None) -> bool:
        """
        메모리 인덱스 저장 (Idempotency 보장)
        
        Args:
            memory_index: 저장할 메모리 인덱스 데이터
            conversation_id: 대화 ID
            turn_id: 턴 ID
            
        Returns:
            저장 성공 여부
        """
        if turn_id is None:
            turn_id = str(int(time.time()))
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")  # WAL 모드 확인
                
                files = memory_index.get("files", {})
                
                for file_path, file_info in files.items():
                    # Idempotency 확인
                    if self._check_idempotency(conversation_id, turn_id, file_path):
                        continue  # 이미 처리된 요청
                    
                    # 데이터베이스에 저장
                    conn.execute("""
                        INSERT OR REPLACE INTO memory_index 
                        (conversation_id, turn_id, file_path, file_hash, producer_actual, 
                         producer_expected, last_updated, update_interval, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        conversation_id,
                        turn_id,
                        file_path,
                        file_info.get("hash", ""),
                        file_info.get("producer_actual", ""),
                        file_info.get("producer_expected", ""),
                        file_info.get("last_updated", time.time()),
                        file_info.get("update_interval", 30),
                        json.dumps(file_info.get("metadata", {}))
                    ))
                    
                    # 처리 완료 마킹
                    self._mark_processed(conversation_id, turn_id, file_path)
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to save memory index: {e}")
            return False
            
    def load_memory_index(self, conversation_id: str = "default", 
                         turn_id: str = None) -> Dict:
        """
        메모리 인덱스 로드
        
        Args:
            conversation_id: 대화 ID
            turn_id: 턴 ID
            
        Returns:
            메모리 인덱스 데이터
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")  # WAL 모드 확인
                
                if turn_id:
                    # 특정 턴의 데이터 로드
                    cursor = conn.execute("""
                        SELECT file_path, file_hash, producer_actual, producer_expected,
                               last_updated, update_interval, metadata
                        FROM memory_index
                        WHERE conversation_id = ? AND turn_id = ?
                        ORDER BY file_path
                    """, (conversation_id, turn_id))
                else:
                    # 최신 턴의 데이터 로드
                    cursor = conn.execute("""
                        SELECT file_path, file_hash, producer_actual, producer_expected,
                               last_updated, update_interval, metadata
                        FROM memory_index
                        WHERE conversation_id = ?
                        AND turn_id = (
                            SELECT MAX(turn_id) FROM memory_index 
                            WHERE conversation_id = ?
                        )
                        ORDER BY file_path
                    """, (conversation_id, conversation_id))
                
                files = {}
                for row in cursor.fetchall():
                    file_path = row[0]
                    files[file_path] = {
                        "hash": row[1],
                        "producer_actual": row[2],
                        "producer_expected": row[3],
                        "last_updated": row[4],
                        "update_interval": row[5],
                        "metadata": json.loads(row[6]) if row[6] else {}
                    }
                
                return {
                    "files": files,
                    "conversation_id": conversation_id,
                    "turn_id": turn_id,
                    "loaded_at": time.time()
                }
                
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to load memory index: {e}")
            return {"files": {}, "error": str(e)}
            
    def get_file_history(self, file_path: str, limit: int = 100) -> List[Dict]:
        """
        파일 히스토리 조회
        
        Args:
            file_path: 파일 경로
            limit: 조회할 최대 개수
            
        Returns:
            파일 히스토리 목록
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                
                cursor = conn.execute("""
                    SELECT conversation_id, turn_id, file_hash, producer_actual,
                           producer_expected, last_updated, metadata
                    FROM memory_index
                    WHERE file_path = ?
                    ORDER BY last_updated DESC
                    LIMIT ?
                """, (file_path, limit))
                
                history = []
                for row in cursor.fetchall():
                    history.append({
                        "conversation_id": row[0],
                        "turn_id": row[1],
                        "file_hash": row[2],
                        "producer_actual": row[3],
                        "producer_expected": row[4],
                        "last_updated": row[5],
                        "metadata": json.loads(row[6]) if row[6] else {}
                    })
                
                return history
                
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to get file history: {e}")
            return []
            
    def cleanup_old_data(self, days_to_keep: int = 30) -> int:
        """
        오래된 데이터 정리
        
        Args:
            days_to_keep: 보관할 일수
            
        Returns:
            삭제된 레코드 수
        """
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 3600)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                
                cursor = conn.execute("""
                    DELETE FROM memory_index 
                    WHERE last_updated < ?
                """, (cutoff_time,))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                return deleted_count
                
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to cleanup old data: {e}")
            return 0
            
    def get_statistics(self) -> Dict:
        """저장소 통계 정보 반환"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                
                # 전체 레코드 수
                cursor = conn.execute("SELECT COUNT(*) FROM memory_index")
                total_records = cursor.fetchone()[0]
                
                # 고유 파일 수
                cursor = conn.execute("SELECT COUNT(DISTINCT file_path) FROM memory_index")
                unique_files = cursor.fetchone()[0]
                
                # 고유 대화 수
                cursor = conn.execute("SELECT COUNT(DISTINCT conversation_id) FROM memory_index")
                unique_conversations = cursor.fetchone()[0]
                
                # 최신 업데이트 시간
                cursor = conn.execute("SELECT MAX(last_updated) FROM memory_index")
                latest_update = cursor.fetchone()[0]
                
                return {
                    "total_records": total_records,
                    "unique_files": unique_files,
                    "unique_conversations": unique_conversations,
                    "latest_update": latest_update,
                    "processed_keys_count": len(self.processed_keys),
                    "database_path": self.db_path
                }
                
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to get statistics: {e}")
            return {"error": str(e)}
            
    def backup_database(self, backup_path: str = None) -> bool:
        """
        데이터베이스 백업
        
        Args:
            backup_path: 백업 파일 경로
            
        Returns:
            백업 성공 여부
        """
        try:
            if backup_path is None:
                backup_path = f"{self.db_path}.backup.{int(time.time())}"
                
            with sqlite3.connect(self.db_path) as source:
                with sqlite3.connect(backup_path) as backup:
                    source.backup(backup)
                    
            return True
            
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to backup database: {e}")
            return False
            
    def restore_database(self, backup_path: str) -> bool:
        """
        데이터베이스 복원
        
        Args:
            backup_path: 백업 파일 경로
            
        Returns:
            복원 성공 여부
        """
        try:
            with sqlite3.connect(backup_path) as source:
                with sqlite3.connect(self.db_path) as restore:
                    source.backup(restore)
                    
            return True
            
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to restore database: {e}")
            return False

