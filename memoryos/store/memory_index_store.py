"""
MemoryIndexStore - memory_index 저장소(SQLite/File)

메모리 인덱스 데이터를 영구 저장하고 관리합니다.
SQLite WAL 모드 및 성능 최적화를 포함합니다.
"""

import json
import sqlite3
import time
import threading
from typing import Dict, List, Optional
from pathlib import Path


class MemoryIndexStore:
    """
    메모리 인덱스 저장소 클래스
    
    주요 기능:
    - 메모리 인덱스 데이터 영구 저장
    - SQLite 및 JSON 파일 지원
    - 버전 관리 및 히스토리 추적
    - 쿼리 및 검색 기능
    """
    
    def __init__(self, store_path: str = "data/memory_index.db", 
                 storage_type: str = "sqlite"):
        """
        MemoryIndexStore 초기화
        
        Args:
            store_path: 저장소 파일 경로
            storage_type: 저장소 유형 ("sqlite" 또는 "json")
        """
        self.store_path = Path(store_path)
        self.storage_type = storage_type
        self.connection = None
        
        # 스레드 로컬 연결을 위한 로컬 스토리지
        self._local = threading.local()
        
        # 저장소 초기화
        self._initialize_store()
        
    def _get_connection(self):
        """스레드 로컬 SQLite 연결 가져오기"""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(str(self.store_path), check_same_thread=False)
            self._initialize_sqlite_connection(self._local.connection)
        return self._local.connection
    
    def _initialize_store(self) -> None:
        """저장소 초기화"""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        
        if self.storage_type == "sqlite":
            # 스레드 로컬 연결 초기화
            self._get_connection()
        elif self.storage_type == "json":
            self._initialize_json()
        else:
            raise ValueError(f"Unsupported storage type: {self.storage_type}")
            
    def _initialize_sqlite_connection(self, connection) -> None:
        """SQLite 연결 초기화 (WAL 모드 및 PRAGMA 튜닝)"""
        connection.row_factory = sqlite3.Row
        
        # WAL 모드 활성화 및 PRAGMA 튜닝
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=NORMAL;")
        connection.execute("PRAGMA mmap_size=268435456;")  # 256MB
        connection.execute("PRAGMA cache_size=-16384;")  # 16MB
        connection.execute("PRAGMA temp_store=MEMORY;")
        connection.execute("PRAGMA locking_mode=EXCLUSIVE;")
        
        # 테이블 생성
        cursor = connection.cursor()
        
        # 파일 인덱스 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                current_hash TEXT,
                last_updated REAL,
                version INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now'))
            )
        """)
        
        # 파일 작업 히스토리 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                operation TEXT NOT NULL,
                timestamp REAL NOT NULL,
                producer TEXT,
                hash TEXT,
                chain_hash TEXT,
                version INTEGER,
                metadata TEXT,
                created_at REAL DEFAULT (julianday('now'))
            )
        """)
        
        # 메타데이터 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL DEFAULT (julianday('now'))
            )
        """)
        
        connection.commit()
        
    def _initialize_json(self) -> None:
        """JSON 저장소 초기화"""
        if not self.store_path.exists():
            initial_data = {
                "version": "1.0",
                "files": {},
                "metadata": {
                    "created_at": time.time(),
                    "last_updated": time.time(),
                    "total_operations": 0
                }
            }
            self._save_json_data(initial_data)
            
    def _save_json_data(self, data: Dict) -> None:
        """JSON 데이터 저장"""
        with open(self.store_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
    def _load_json_data(self) -> Dict:
        """JSON 데이터 로드"""
        try:
            with open(self.store_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
            
    def save_file_index(self, file_path: str, file_data: Dict) -> bool:
        """
        파일 인덱스 저장
        
        Args:
            file_path: 파일 경로
            file_data: 파일 데이터
            
        Returns:
            저장 성공 여부
        """
        try:
            if self.storage_type == "sqlite":
                return self._save_file_index_sqlite(file_path, file_data)
            elif self.storage_type == "json":
                return self._save_file_index_json(file_path, file_data)
            return False
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to save file index: {e}")
            return False
            
    def _save_file_index_sqlite(self, file_path: str, file_data: Dict) -> bool:
        """SQLite에 파일 인덱스 저장"""
        cursor = self._get_connection().cursor()
        
        # 파일 인덱스 업데이트 또는 삽입
        cursor.execute("""
            INSERT OR REPLACE INTO file_index 
            (file_path, current_hash, last_updated, version, status, updated_at)
            VALUES (?, ?, ?, ?, ?, julianday('now'))
        """, (
            file_path,
            file_data.get("current_hash", ""),
            file_data.get("last_updated", time.time()),
            file_data.get("version", 0),
            file_data.get("status", "active")
        ))
        
        self._get_connection().commit()
        return True
        
    def _save_file_index_json(self, file_path: str, file_data: Dict) -> bool:
        """JSON에 파일 인덱스 저장"""
        data = self._load_json_data()
        data["files"][file_path] = file_data
        data["metadata"]["last_updated"] = time.time()
        
        self._save_json_data(data)
        return True
        
    def save_file_operation(self, file_path: str, operation: Dict) -> bool:
        """
        파일 작업 저장
        
        Args:
            file_path: 파일 경로
            operation: 작업 데이터
            
        Returns:
            저장 성공 여부
        """
        try:
            if self.storage_type == "sqlite":
                return self._save_file_operation_sqlite(file_path, operation)
            elif self.storage_type == "json":
                return self._save_file_operation_json(file_path, operation)
            return False
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to save file operation: {e}")
            return False
            
    def _save_file_operation_sqlite(self, file_path: str, operation: Dict) -> bool:
        """SQLite에 파일 작업 저장"""
        cursor = self._get_connection().cursor()
        
        cursor.execute("""
            INSERT INTO file_operations 
            (file_path, operation, timestamp, producer, hash, chain_hash, version, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_path,
            operation.get("operation", ""),
            operation.get("timestamp", time.time()),
            operation.get("producer", ""),
            operation.get("hash", ""),
            operation.get("chain_hash", ""),
            operation.get("version", 0),
            json.dumps(operation.get("metadata", {}))
        ))
        
        self._get_connection().commit()
        return True
        
    def _save_file_operation_json(self, file_path: str, operation: Dict) -> bool:
        """JSON에 파일 작업 저장"""
        data = self._load_json_data()
        
        if file_path not in data["files"]:
            data["files"][file_path] = {"operations": []}
            
        data["files"][file_path]["operations"].append(operation)
        data["metadata"]["total_operations"] += 1
        data["metadata"]["last_updated"] = time.time()
        
        self._save_json_data(data)
        return True
        
    def get_file_index(self, file_path: str) -> Optional[Dict]:
        """
        파일 인덱스 조회
        
        Args:
            file_path: 파일 경로
            
        Returns:
            파일 인덱스 데이터 또는 None
        """
        try:
            if self.storage_type == "sqlite":
                return self._get_file_index_sqlite(file_path)
            elif self.storage_type == "json":
                return self._get_file_index_json(file_path)
            return None
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to get file index: {e}")
            return None
            
    def _get_file_index_sqlite(self, file_path: str) -> Optional[Dict]:
        """SQLite에서 파일 인덱스 조회"""
        cursor = self._get_connection().cursor()
        cursor.execute("SELECT * FROM file_index WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        
        if row:
            return {
                "file_path": row["file_path"],
                "current_hash": row["current_hash"],
                "last_updated": row["last_updated"],
                "version": row["version"],
                "status": row["status"]
            }
        return None
        
    def _get_file_index_json(self, file_path: str) -> Optional[Dict]:
        """JSON에서 파일 인덱스 조회"""
        data = self._load_json_data()
        return data.get("files", {}).get(file_path)
        
    def get_file_operations(self, file_path: str, limit: int = 100) -> List[Dict]:
        """
        파일 작업 히스토리 조회
        
        Args:
            file_path: 파일 경로
            limit: 조회할 작업 수 제한
            
        Returns:
            작업 히스토리 목록
        """
        try:
            if self.storage_type == "sqlite":
                return self._get_file_operations_sqlite(file_path, limit)
            elif self.storage_type == "json":
                return self._get_file_operations_json(file_path, limit)
            return []
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to get file operations: {e}")
            return []
            
    def _get_file_operations_sqlite(self, file_path: str, limit: int) -> List[Dict]:
        """SQLite에서 파일 작업 히스토리 조회"""
        cursor = self._get_connection().cursor()
        cursor.execute("""
            SELECT * FROM file_operations 
            WHERE file_path = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (file_path, limit))
        
        operations = []
        for row in cursor.fetchall():
            operations.append({
                "operation": row["operation"],
                "timestamp": row["timestamp"],
                "producer": row["producer"],
                "hash": row["hash"],
                "chain_hash": row["chain_hash"],
                "version": row["version"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
            })
            
        return operations
        
    def _get_file_operations_json(self, file_path: str, limit: int) -> List[Dict]:
        """JSON에서 파일 작업 히스토리 조회"""
        data = self._load_json_data()
        file_data = data.get("files", {}).get(file_path, {})
        operations = file_data.get("operations", [])
        
        # 최신 순으로 정렬하고 제한
        operations.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return operations[:limit]
        
    def get_all_files(self) -> List[str]:
        """모든 파일 경로 목록 조회"""
        try:
            if self.storage_type == "sqlite":
                cursor = self._get_connection().cursor()
                cursor.execute("SELECT file_path FROM file_index WHERE status = 'active'")
                return [row["file_path"] for row in cursor.fetchall()]
            elif self.storage_type == "json":
                data = self._load_json_data()
                return list(data.get("files", {}).keys())
            return []
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to get all files: {e}")
            return []
            
    def get_wal_status(self) -> Dict:
        """
        WAL 모드 상태 확인
        
        Returns:
            WAL 모드 상태 정보
        """
        if self.storage_type != "sqlite":
            return {"wal_mode": False, "reason": "not_sqlite"}
            
        try:
            cursor = self._get_connection().cursor()
            
            # WAL 모드 확인
            cursor.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]
            
            # WAL 파일 존재 확인
            wal_file = Path(str(self.store_path) + "-wal")
            wal_exists = wal_file.exists()
            
            # WAL 파일 크기 확인
            wal_size = wal_file.stat().st_size if wal_exists else 0
            
            # WAL 체크포인트 정보
            cursor.execute("PRAGMA wal_checkpoint(PASSIVE);")
            checkpoint_info = cursor.fetchone()
            
            return {
                "wal_mode": journal_mode == "wal",
                "journal_mode": journal_mode,
                "wal_file_exists": wal_exists,
                "wal_file_size": wal_size,
                "checkpoint_info": {
                    "busy": checkpoint_info[0],
                    "log": checkpoint_info[1],
                    "checkpointed": checkpoint_info[2]
                }
            }
            
        except Exception as e:
            return {"wal_mode": False, "error": str(e)}
            
    def optimize_sqlite_performance(self) -> Dict:
        """
        SQLite 성능 최적화
        
        Returns:
            최적화 결과
        """
        if self.storage_type != "sqlite":
            return {"optimized": False, "reason": "not_sqlite"}
            
        try:
            cursor = self._get_connection().cursor()
            
            # 인덱스 재구성
            cursor.execute("REINDEX;")
            
            # 통계 업데이트
            cursor.execute("ANALYZE;")
            
            # WAL 체크포인트
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            checkpoint_result = cursor.fetchone()
            
            # VACUUM (선택적)
            # cursor.execute("VACUUM;")  # 주석 처리 - 성능에 영향
            
            self._get_connection().commit()
            
            return {
                "optimized": True,
                "reindex_completed": True,
                "analyze_completed": True,
                "checkpoint_result": {
                    "busy": checkpoint_result[0],
                    "log": checkpoint_result[1],
                    "checkpointed": checkpoint_result[2]
                }
            }
            
        except Exception as e:
            return {"optimized": False, "error": str(e)}
            
    def get_store_statistics(self) -> Dict:
        """저장소 통계 정보 조회"""
        try:
            if self.storage_type == "sqlite":
                cursor = self._get_connection().cursor()
                
                # 파일 수 통계
                cursor.execute("SELECT COUNT(*) as total FROM file_index")
                total_files = cursor.fetchone()["total"]
                
                cursor.execute("SELECT COUNT(*) as active FROM file_index WHERE status = 'active'")
                active_files = cursor.fetchone()["active"]
                
                # 작업 수 통계
                cursor.execute("SELECT COUNT(*) as total FROM file_operations")
                total_operations = cursor.fetchone()["total"]
                
                # WAL 상태 정보 추가
                wal_status = self.get_wal_status()
                
                return {
                    "total_files": total_files,
                    "active_files": active_files,
                    "total_operations": total_operations,
                    "storage_type": self.storage_type,
                    "store_path": str(self.store_path),
                    "wal_status": wal_status
                }
                
            elif self.storage_type == "json":
                data = self._load_json_data()
                files = data.get("files", {})
                
                return {
                    "total_files": len(files),
                    "active_files": len(files),
                    "total_operations": data.get("metadata", {}).get("total_operations", 0),
                    "storage_type": self.storage_type,
                    "store_path": str(self.store_path),
                    "wal_status": {"wal_mode": False, "reason": "not_sqlite"}
                }
                
        except Exception as e:
            print(f"[MemoryIndexStore] Failed to get statistics: {e}")
            return {}
            
    def close(self) -> None:
        """저장소 연결 종료"""
        # 스레드 로컬 연결들 닫기
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')
        
        # 기존 연결도 닫기 (호환성을 위해)
        if hasattr(self, 'connection') and self.connection:
            self.connection.close()
            self.connection = None
            
    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()
