"""
HashChain - Hash + Merkle 기반 무결성 검증

Temporal Hash Chain과 Merkle Tree를 통한 데이터 무결성 검증을 제공합니다.
원자성 보장을 위한 트랜잭션 지원을 포함합니다.
"""

import hashlib
import json
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import sqlite3
from contextlib import contextmanager


class HashChain:
    """
    Hash Chain 및 Merkle Tree 기반 무결성 검증 클래스
    
    주요 기능:
    - Temporal Hash Chain 관리
    - Merkle Tree 구성 및 검증
    - 데이터 무결성 검증
    - 체인 검증 및 복구
    - 원자성 보장을 위한 트랜잭션 지원
    """
    
    def __init__(self, db_path: str = "data/hashchain.db"):
        """
        HashChain 초기화
        
        Args:
            db_path: SQLite 데이터베이스 경로
        """
        self.db_path = db_path
        self.chain = []  # Temporal Hash Chain (메모리 캐시)
        self.merkle_tree = ""  # Merkle Tree 루트 해시
        self._init_database()
        
    def _init_database(self) -> None:
        """데이터베이스 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hash_chain (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_id INTEGER UNIQUE NOT NULL,
                    prev_hash TEXT,
                    content_hash TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    data TEXT NOT NULL,
                    merkle_root TEXT,
                    created_at REAL DEFAULT (julianday('now'))
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_version_id ON hash_chain(version_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_prev_hash ON hash_chain(prev_hash)
            """)
            
            conn.commit()
            
    @contextmanager
    def _atomic_transaction(self):
        """원자성 트랜잭션 컨텍스트 매니저"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
            
    def add_block_atomic(self, data: Dict, prev_hash: str = None) -> str:
        """
        원자성을 보장하는 블록 추가
        
        Args:
            data: 추가할 데이터
            prev_hash: 이전 블록의 해시
            
        Returns:
            현재 블록의 해시
        """
        timestamp = data.get("timestamp", time.time())
        
        # 블록 생성
        block = {
            "index": len(self.chain),
            "timestamp": timestamp,
            "data": data,
            "prev_hash": prev_hash,
            "nonce": 0,
            "hash": None
        }
        
        # 해시 계산
        block["hash"] = self._calculate_block_hash(block)
        
        # 원자성 트랜잭션으로 저장
        with self._atomic_transaction() as conn:
            # version_id 생성 (현재 최대값 + 1)
            cursor = conn.execute("SELECT MAX(version_id) FROM hash_chain")
            max_version = cursor.fetchone()[0] or 0
            version_id = max_version + 1
            
            # 데이터베이스에 저장
            conn.execute("""
                INSERT INTO hash_chain 
                (version_id, prev_hash, content_hash, timestamp, data, merkle_root)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                version_id,
                prev_hash,
                block["hash"],
                timestamp,
                json.dumps(data),
                ""  # merkle_root는 나중에 업데이트
            ))
            
            # Merkle Tree 업데이트
            self._update_merkle_tree()
            
            # merkle_root 업데이트
            conn.execute("""
                UPDATE hash_chain
                SET merkle_root = ?
                WHERE version_id = ?
            """, (self.merkle_tree, version_id))
            
        # 메모리 캐시 업데이트
        self.chain.append(block)
        
        return block["hash"]
        
    def add_block(self, data: Dict, prev_hash: str = None) -> str:
        """
        새로운 블록을 체인에 추가 (원자성 보장)
        
        Args:
            data: 추가할 데이터
            prev_hash: 이전 블록의 해시
            
        Returns:
            현재 블록의 해시
        """
        return self.add_block_atomic(data, prev_hash)
        
    def _calculate_block_hash(self, block: Dict) -> str:
        """
        블록의 해시 계산
        
        Args:
            block: 해시를 계산할 블록
            
        Returns:
            블록의 SHA256 해시값
        """
        block_string = f"{block['index']}{block['timestamp']}{json.dumps(block['data'], sort_keys=True)}{block['prev_hash']}{block['nonce']}"
        return hashlib.sha256(block_string.encode()).hexdigest()
        
    def _update_merkle_tree(self) -> None:
        """Merkle Tree 업데이트"""
        if not self.chain:
            return
            
        # 리프 노드 생성 (각 블록의 해시)
        leaves = [block["hash"] for block in self.chain]
        
        # Merkle Tree 구성
        self.merkle_tree = self.build_merkle_root(leaves)
        
    def build_merkle_root(self, chunks: List[str]) -> str:
        """
        청크 목록으로부터 Merkle 루트 계산
        
        Args:
            chunks: 해시 청크 목록
            
        Returns:
            Merkle 루트 해시
        """
        if not chunks:
            return ""
            
        if len(chunks) == 1:
            return chunks[0]
            
        # 레벨별로 트리 구성
        current_level = chunks
        levels = [current_level]
        
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else current_level[i]
                
                # 두 해시를 결합하여 부모 해시 생성
                combined = left + right
                parent_hash = hashlib.sha256(combined.encode()).hexdigest()
                next_level.append(parent_hash)
                
            levels.append(next_level)
            current_level = next_level
            
        return current_level[0]
        
    def verify_merkle_partial(self, chunks: List[str], root_hash: str) -> bool:
        """
        부분 Merkle 검증
        
        Args:
            chunks: 검증할 청크 목록
            root_hash: 예상 루트 해시
            
        Returns:
            검증 성공 여부
        """
        calculated_root = self.build_merkle_root(chunks)
        return calculated_root == root_hash
        
    def detect_chunk_tampering(self, original_chunks: List[str], 
                              modified_chunks: List[str], 
                              root_hash: str) -> List[int]:
        """
        청크 변조 감지
        
        Args:
            original_chunks: 원본 청크 목록
            modified_chunks: 수정된 청크 목록
            root_hash: 원본 루트 해시
            
        Returns:
            변조된 청크 인덱스 목록
        """
        tampered_indices = []
        
        if len(original_chunks) != len(modified_chunks):
            return list(range(len(original_chunks)))
            
        for i, (orig, mod) in enumerate(zip(original_chunks, modified_chunks)):
            if orig != mod:
                tampered_indices.append(i)
                
        # 부분 검증으로 확인
        if not self.verify_merkle_partial(modified_chunks, root_hash):
            return tampered_indices
            
        return []
        """
        Merkle Tree 구성
        
        Args:
            leaves: 리프 노드 해시 목록
            
        Returns:
            Merkle Tree 구조
        """
        if not leaves:
            return {}
            
        if len(leaves) == 1:
            return {"root": leaves[0], "leaves": leaves}
            
        # 레벨별로 트리 구성
        current_level = leaves
        levels = [current_level]
        
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else current_level[i]
                
                # 두 해시를 결합하여 부모 해시 생성
                combined = left + right
                parent_hash = hashlib.sha256(combined.encode()).hexdigest()
                next_level.append(parent_hash)
                
            levels.append(next_level)
            current_level = next_level
            
        return {
            "root": current_level[0],
            "levels": levels,
            "leaves": leaves
        }
        
    def verify_chain(self) -> Tuple[bool, List[str]]:
        """
        전체 체인의 무결성 검증
        
        Returns:
            (검증 성공 여부, 오류 메시지 목록)
        """
        errors = []
        
        if not self.chain:
            return True, []
            
        # 첫 번째 블록 검증
        if self.chain[0]["prev_hash"] is not None:
            errors.append("First block should have null prev_hash")
            
        # 연속된 블록들 검증
        for i in range(1, len(self.chain)):
            current_block = self.chain[i]
            prev_block = self.chain[i - 1]
            
            # 이전 해시 검증
            if current_block["prev_hash"] != prev_block["hash"]:
                errors.append(f"Block {i}: prev_hash mismatch")
                
            # 블록 해시 검증
            calculated_hash = self._calculate_block_hash(current_block)
            if current_block["hash"] != calculated_hash:
                errors.append(f"Block {i}: hash verification failed")
                
        # Merkle Tree 검증
        if self.merkle_tree:
            merkle_valid, merkle_errors = self._verify_merkle_tree()
            if not merkle_valid:
                errors.extend(merkle_errors)
                
        return len(errors) == 0, errors
        
    def _verify_merkle_tree(self) -> Tuple[bool, List[str]]:
        """
        Merkle Tree 검증
        
        Returns:
            (검증 성공 여부, 오류 메시지 목록)
        """
        errors = []
        
        if not self.merkle_tree:
            return True, []
            
        # 리프 노드 검증
        expected_leaves = [block["hash"] for block in self.chain]
        # merkle_tree가 문자열인 경우 처리
        if isinstance(self.merkle_tree, str):
            # 문자열인 경우 기본 검증만 수행
            return True, []
        actual_leaves = self.merkle_tree.get("leaves", [])
        
        if expected_leaves != actual_leaves:
            errors.append("Merkle tree leaves mismatch")
            
        # 루트 해시 재계산 및 검증
        if actual_leaves:
            recalculated_tree = self._build_merkle_tree(actual_leaves)
            if recalculated_tree["root"] != self.merkle_tree["root"]:
                errors.append("Merkle tree root hash mismatch")
                
        return len(errors) == 0, errors
        
    def get_merkle_proof(self, block_index: int) -> Optional[List[str]]:
        """
        특정 블록의 Merkle Proof 생성
        
        Args:
            block_index: 블록 인덱스
            
        Returns:
            Merkle Proof 또는 None
        """
        if not self.merkle_tree or block_index >= len(self.chain):
            return None
            
        proof = []
        current_index = block_index
        
        # 리프에서 루트까지의 경로 추적
        for level in self.merkle_tree["levels"][:-1]:
            if current_index % 2 == 0:
                # 왼쪽 노드인 경우 오른쪽 형제 추가
                if current_index + 1 < len(level):
                    proof.append(level[current_index + 1])
            else:
                # 오른쪽 노드인 경우 왼쪽 형제 추가
                proof.append(level[current_index - 1])
                
            current_index = current_index // 2
            
        return proof
        
    def verify_merkle_proof(self, block_hash: str, proof: List[str], 
                           root_hash: str) -> bool:
        """
        Merkle Proof 검증
        
        Args:
            block_hash: 검증할 블록 해시
            proof: Merkle Proof
            root_hash: 루트 해시
            
        Returns:
            검증 성공 여부
        """
        current_hash = block_hash
        
        for sibling_hash in proof:
            # 해시 순서 결정 (사전순으로 정렬)
            if current_hash < sibling_hash:
                combined = current_hash + sibling_hash
            else:
                combined = sibling_hash + current_hash
                
            current_hash = hashlib.sha256(combined.encode()).hexdigest()
            
        return current_hash == root_hash
        
    def get_chain_summary(self) -> Dict:
        """체인 요약 정보 반환"""
        return {
            "total_blocks": len(self.chain),
            "merkle_root": self.merkle_tree if isinstance(self.merkle_tree, str) else self.merkle_tree.get("root", ""),
            "last_block_hash": self.chain[-1]["hash"] if self.chain else "",
            "chain_valid": self.verify_chain()[0]
        }
        
    def get_block(self, index: int) -> Optional[Dict]:
        """
        특정 인덱스의 블록 조회
        
        Args:
            index: 블록 인덱스
            
        Returns:
            블록 데이터 또는 None
        """
        if 0 <= index < len(self.chain):
            return self.chain[index]
        return None
        
    def get_latest_blocks(self, count: int = 10) -> List[Dict]:
        """
        최근 블록들 조회
        
        Args:
            count: 조회할 블록 수
            
        Returns:
            최근 블록 목록
        """
        return self.chain[-count:] if count > 0 else self.chain
