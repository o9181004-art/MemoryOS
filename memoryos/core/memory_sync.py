"""
MemorySync - delta + catalog 병합 → Temporal Hash Chain

delta 이벤트와 카탈로그 정보를 병합하여 메모리 인덱스를 갱신합니다.
"""

import time
import json
from typing import Dict, List
from pathlib import Path


class MemorySync:
    """
    메모리 동기화 클래스
    
    주요 기능:
    - delta 이벤트와 카탈로그 정보 병합
    - Temporal Hash Chain 생성 및 관리
    - 메모리 인덱스 갱신
    - 충돌 해결 및 병합 정책 적용
    """
    
    def __init__(self, memory_index_file: str = "data/memory_index.json", data_catalog=None):
        """
        MemorySync 초기화
        
        Args:
            memory_index_file: 메모리 인덱스 저장 파일 경로
            data_catalog: DataCatalog 인스턴스 (선택사항)
        """
        self.memory_index_file = memory_index_file
        self.data_catalog = data_catalog
        self.memory_index = self._load_memory_index()
        self.hash_chain = []  # Temporal Hash Chain
        
    def _load_memory_index(self) -> Dict:
        """메모리 인덱스 로드"""
        try:
            index_path = Path(self.memory_index_file)
            if index_path.exists():
                with open(index_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
            
        # 기본 메모리 인덱스 구조
        return {
            "version": "1.0",
            "files": {},
            "metadata": {
                "created_at": time.time(),
                "last_updated": time.time(),
                "total_operations": 0
            }
        }
        
    def _save_memory_index(self) -> None:
        """메모리 인덱스 저장"""
        try:
            index_path = Path(self.memory_index_file)
            index_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.memory_index["metadata"]["last_updated"] = time.time()
            
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(self.memory_index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[MemorySync] Failed to save memory index: {e}")
            
    def _calculate_hash(self, data: Dict) -> str:
        """
        데이터의 해시 계산
        
        Args:
            data: 해시를 계산할 데이터
            
        Returns:
            SHA256 해시값
        """
        import hashlib
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()
        
    def _add_to_hash_chain(self, delta: Dict, prev_hash: str = None) -> str:
        """
        Temporal Hash Chain에 항목 추가
        
        Args:
            delta: 추가할 delta 이벤트
            prev_hash: 이전 해시값
            
        Returns:
            현재 해시값
        """
        chain_entry = {
            "timestamp": delta.get("ts", time.time()),
            "delta": delta,
            "prev_hash": prev_hash,
            "curr_hash": None
        }
        
        # 현재 해시 계산
        chain_entry["curr_hash"] = self._calculate_hash(chain_entry)
        
        # 체인에 추가
        self.hash_chain.append(chain_entry)
        
        return chain_entry["curr_hash"]
        
    def sync_delta(self, delta: Dict, catalog_info: Dict = None) -> Dict:
        """
        delta 이벤트를 메모리 인덱스에 동기화
        
        Args:
            delta: 동기화할 delta 이벤트
            catalog_info: 카탈로그 정보
            
        Returns:
            동기화 결과
        """
        file_path = delta.get("path")
        if not file_path:
            return {"success": False, "error": "No file path in delta"}
            
        # 이전 해시 가져오기
        prev_hash = None
        if self.hash_chain:
            prev_hash = self.hash_chain[-1]["curr_hash"]
            
        # Hash Chain에 추가
        curr_hash = self._add_to_hash_chain(delta, prev_hash)
        
        # 메모리 인덱스 업데이트
        if file_path not in self.memory_index["files"]:
            self.memory_index["files"][file_path] = {
                "operations": [],
                "current_hash": "",
                "last_updated": None,
                "version": 0
            }
            
        file_entry = self.memory_index["files"][file_path]
        
        # 충돌 검사
        conflict_detected = False
        if file_entry["current_hash"] and file_entry["current_hash"] != delta.get("hash", ""):
            conflict_detected = True
            
        # 충돌 해결 정책 적용
        if conflict_detected:
            resolution_result = self._resolve_conflict(file_path, delta, catalog_info)
            if not resolution_result["success"]:
                return resolution_result
                
        # 파일 엔트리 업데이트
        file_entry["operations"].append({
            "operation": delta.get("op"),
            "timestamp": delta.get("ts"),
            "producer": delta.get("producer_actual"),
            "hash": delta.get("hash"),
            "chain_hash": curr_hash
        })
        
        file_entry["current_hash"] = delta.get("hash", "")
        file_entry["last_updated"] = delta.get("ts", time.time())
        file_entry["version"] += 1
        
        # 메타데이터 업데이트
        self.memory_index["metadata"]["total_operations"] += 1
        
        # 저장
        self._save_memory_index()
        
        result = {
            "success": True,
            "file_path": file_path,
            "version": file_entry["version"],
            "chain_hash": curr_hash,
            "conflict_resolved": conflict_detected
        }
        
        print(f"[MemorySync] Synced delta for {file_path} (ver_{file_entry['version']:02d})")
        return result
        
    def _resolve_conflict(self, _file_path: str, _delta: Dict, 
                         catalog_info: Dict = None) -> Dict:
        """
        충돌 해결
        
        Args:
            file_path: 충돌이 발생한 파일 경로
            delta: 새로운 delta 이벤트
            catalog_info: 카탈로그 정보
            
        Returns:
            충돌 해결 결과
        """
        # 기본 정책: 새로운 변경사항 우선 (Last Write Wins)
        policy_id = catalog_info.get("policy_id", "lww") if catalog_info else "lww"
        
        if policy_id == "lww":
            # Last Write Wins - 새로운 변경사항 적용
            return {"success": True, "policy": "lww", "action": "overwrite"}
        elif policy_id == "merge":
            # 병합 정책 - 두 변경사항을 병합
            return {"success": True, "policy": "merge", "action": "merge"}
        elif policy_id == "reject":
            # 거부 정책 - 새로운 변경사항 거부
            return {"success": False, "policy": "reject", "action": "reject"}
        else:
            # 기본값: Last Write Wins
            return {"success": True, "policy": "lww", "action": "overwrite"}
            
    def get_file_history(self, file_path: str) -> List[Dict]:
        """
        파일의 변경 이력 조회
        
        Args:
            file_path: 파일 경로
            
        Returns:
            파일 변경 이력 목록
        """
        file_entry = self.memory_index["files"].get(file_path)
        if not file_entry:
            return []
            
        return file_entry.get("operations", [])
        
    def get_memory_summary(self) -> Dict:
        """메모리 인덱스 요약 정보 반환"""
        return {
            "total_files": len(self.memory_index["files"]),
            "total_operations": self.memory_index["metadata"]["total_operations"],
            "chain_length": len(self.hash_chain),
            "last_updated": self.memory_index["metadata"]["last_updated"],
            "version": self.memory_index["version"]
        }
        
    def get_hash_chain(self, limit: int = 10) -> List[Dict]:
        """
        Hash Chain 조회
        
        Args:
            limit: 반환할 항목 수 제한
            
        Returns:
            Hash Chain 항목 목록
        """
        return self.hash_chain[-limit:] if limit > 0 else self.hash_chain
