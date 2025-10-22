"""
DataCatalog - producer_expected / consumer_expected 관리

파일과 모듈 간의 예상 관계를 관리하고 추적합니다.
Producer 신뢰도 스코어링을 포함합니다.
"""

from typing import Dict, List, Optional
from pathlib import Path
import json
import hashlib
import time


class DataCatalog:
    """
    데이터 카탈로그 관리 클래스
    
    주요 기능:
    - producer_expected / consumer_expected 관계 관리
    - 파일별 예상 업데이트 주기 관리
    - 모듈 간 의존성 추적
    """
    
    def __init__(self, catalog_file: Optional[str] = None):
        """
        DataCatalog 초기화
        
        Args:
            catalog_file: 카탈로그 데이터를 저장할 파일 경로
        """
        self.catalog_file = catalog_file or "data/catalog.json"
        self.catalog_data = self._load_catalog()
        
        # Producer 신뢰도 스코어링을 위한 데이터
        self.producer_trust_scores = {}
        self.producer_signatures = {}  # producer별 서명 정보
        self.producer_paths = {}  # producer별 경로 정보
        
    def _load_catalog(self) -> Dict:
        """카탈로그 데이터 로드"""
        try:
            catalog_path = Path(self.catalog_file)
            if catalog_path.exists():
                with open(catalog_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
            
        # 기본 카탈로그 구조
        return {
            "files": {},
            "modules": {},
            "relationships": {},
            "version": "1.0"
        }
        
    def _save_catalog(self) -> None:
        """카탈로그 데이터 저장"""
        try:
            catalog_path = Path(self.catalog_file)
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(catalog_path, 'w', encoding='utf-8') as f:
                json.dump(self.catalog_data, f, indent=2, ensure_ascii=False)
        except (OSError, ValueError) as e:
            print(f"[DataCatalog] Failed to save catalog: {e}")
            
    def register_file(self, file_path: str, producer_expected: str, 
                     consumer_expected: List[str] = None, 
                     update_interval: int = 30) -> None:
        """
        파일을 카탈로그에 등록
        
        Args:
            file_path: 등록할 파일 경로
            producer_expected: 예상 생산자 모듈
            consumer_expected: 예상 소비자 모듈 목록
            update_interval: 예상 업데이트 주기 (초)
        """
        if consumer_expected is None:
            consumer_expected = []
            
        self.catalog_data["files"][file_path] = {
            "producer_expected": producer_expected,
            "consumer_expected": consumer_expected,
            "update_interval": update_interval,
            "last_updated": None,
            "status": "active"
        }
        
        self._save_catalog()
        print(f"[DataCatalog] Registered file: {file_path}")
        
    def register_module(self, module_name: str, module_type: str = "unknown") -> None:
        """
        모듈을 카탈로그에 등록
        
        Args:
            module_name: 모듈 이름
            module_type: 모듈 유형
        """
        self.catalog_data["modules"][module_name] = {
            "type": module_type,
            "status": "active",
            "registered_at": None
        }
        
        self._save_catalog()
        print(f"[DataCatalog] Registered module: {module_name}")
        
    def get_expected_producer(self, file_path: str) -> Optional[str]:
        """
        파일의 예상 생산자 조회
        
        Args:
            file_path: 파일 경로
            
        Returns:
            예상 생산자 모듈명 또는 None
        """
        file_info = self.catalog_data["files"].get(file_path)
        return file_info.get("producer_expected") if file_info else None
        
    def get_expected_consumers(self, file_path: str) -> List[str]:
        """
        파일의 예상 소비자 목록 조회
        
        Args:
            file_path: 파일 경로
            
        Returns:
            예상 소비자 모듈 목록
        """
        file_info = self.catalog_data["files"].get(file_path)
        return file_info.get("consumer_expected", []) if file_info else []
        
    def get_update_interval(self, file_path: str) -> int:
        """
        파일의 예상 업데이트 주기 조회
        
        Args:
            file_path: 파일 경로
            
        Returns:
            예상 업데이트 주기 (초)
        """
        file_info = self.catalog_data["files"].get(file_path)
        return file_info.get("update_interval", 30) if file_info else 30
        
    def update_file_status(self, file_path: str, producer_actual: str, 
                          timestamp: float) -> None:
        """
        파일 상태 업데이트
        
        Args:
            file_path: 파일 경로
            producer_actual: 실제 생산자 모듈
            timestamp: 업데이트 시간
        """
        if file_path in self.catalog_data["files"]:
            self.catalog_data["files"][file_path]["last_updated"] = timestamp
            self.catalog_data["files"][file_path]["producer_actual"] = producer_actual
            
        self._save_catalog()
        
    def check_drift(self, file_path: str, producer_actual: str, 
                   timestamp: float) -> Dict:
        """
        드리프트 검사
        
        Args:
            file_path: 파일 경로
            producer_actual: 실제 생산자 모듈
            timestamp: 현재 시간
            
        Returns:
            드리프트 검사 결과
        """
        file_info = self.catalog_data["files"].get(file_path)
        if not file_info:
            return {
                "drift_detected": False,
                "reason": "file_not_registered",
                "level": 0
            }
            
        producer_expected = file_info.get("producer_expected")
        last_updated = file_info.get("last_updated")
        update_interval = file_info.get("update_interval", 30)
        
        # 생산자 불일치 검사
        producer_mismatch = producer_expected != producer_actual
        
        # 시간 기반 staleness 검사
        time_drift = False
        if last_updated:
            time_since_update = timestamp - last_updated
            time_drift = time_since_update > update_interval * 2
            
        # 드리프트 레벨 결정
        if producer_mismatch and time_drift:
            level = 3  # L3: 심각한 드리프트
        elif producer_mismatch or time_drift:
            level = 2  # L2: 중간 드리프트
        elif producer_expected != producer_actual:
            level = 1  # L1: 경미한 드리프트
        else:
            level = 0  # 드리프트 없음
            
        return {
            "drift_detected": level > 0,
            "producer_mismatch": producer_mismatch,
            "time_drift": time_drift,
            "level": level,
            "producer_expected": producer_expected,
            "producer_actual": producer_actual
        }
        
    def calculate_producer_trust_score(self, producer_actual: str, 
                                      file_path: str = None) -> float:
        """
        Producer 신뢰도 점수 계산 (실행 가능한 해시, 서명, 경로 기반)
        
        Args:
            producer_actual: 실제 producer
            file_path: 파일 경로 (선택사항)
            
        Returns:
            신뢰도 점수 (0.0 ~ 1.0)
        """
        if producer_actual not in self.producer_trust_scores:
            # 새로운 producer는 기본 신뢰도
            self.producer_trust_scores[producer_actual] = {
                "score": 0.5,
                "success_count": 0,
                "failure_count": 0,
                "last_seen": time.time(),
                "executable_hash": None,
                "signature_valid": False,
                "path_trusted": False
            }
            
        trust_data = self.producer_trust_scores[producer_actual]
        
        # 기본 신뢰도 계산 (성공률 기반)
        total_attempts = trust_data["success_count"] + trust_data["failure_count"]
        if total_attempts > 0:
            success_rate = trust_data["success_count"] / total_attempts
        else:
            success_rate = 0.5  # 기본값
            
        # 실행 가능한 해시 기반 신뢰도
        hash_trust = 0.5  # 기본값
        if trust_data["executable_hash"]:
            # 해시가 등록되어 있으면 신뢰도 증가
            hash_trust = 0.8
            
        # 서명 기반 신뢰도
        signature_trust = 0.5  # 기본값
        if trust_data["signature_valid"]:
            signature_trust = 0.9
            
        # 경로 기반 신뢰도
        path_trust = 0.5  # 기본값
        if trust_data["path_trusted"]:
            path_trust = 0.7
            
        # 시간 기반 감쇠
        time_since_last_seen = time.time() - trust_data["last_seen"]
        time_decay = max(0.1, 1.0 - (time_since_last_seen / 3600))  # 1시간 기준
        
        # 가중 평균으로 최종 신뢰도 계산
        weights = {
            "success_rate": 0.4,
            "hash_trust": 0.2,
            "signature_trust": 0.2,
            "path_trust": 0.2
        }
        
        weighted_score = (
            success_rate * weights["success_rate"] +
            hash_trust * weights["hash_trust"] +
            signature_trust * weights["signature_trust"] +
            path_trust * weights["path_trust"]
        )
        
        # 시간 감쇠 적용
        final_score = weighted_score * time_decay
        
        # 신뢰도 업데이트
        trust_data["score"] = final_score
        trust_data["last_seen"] = time.time()
        
        return final_score
        
    def register_producer_executable_hash(self, producer_actual: str, 
                                        executable_path: str) -> None:
        """
        Producer의 실행 가능한 해시 등록
        
        Args:
            producer_actual: Producer 이름
            file_path: 실행 가능한 파일 경로
        """
        try:
            with open(executable_path, 'rb') as f:
                content = f.read()
                executable_hash = hashlib.sha256(content).hexdigest()
                
            if producer_actual not in self.producer_trust_scores:
                self.producer_trust_scores[producer_actual] = {
                    "score": 0.5,
                    "success_count": 0,
                    "failure_count": 0,
                    "last_seen": time.time(),
                    "executable_hash": None,
                    "signature_valid": False,
                    "path_trusted": False
                }
                
            self.producer_trust_scores[producer_actual]["executable_hash"] = executable_hash
            print(f"[DataCatalog] Registered executable hash for {producer_actual}")
            
        except Exception as e:
            print(f"[DataCatalog] Failed to register executable hash for {producer_actual}: {e}")
            
    def verify_producer_signature(self, producer_actual: str, 
                                signature: str, data: str) -> bool:
        """
        Producer 서명 검증
        
        Args:
            producer_actual: Producer 이름
            signature: 서명 문자열
            data: 서명할 데이터
            
        Returns:
            서명 검증 성공 여부
        """
        try:
            # 간단한 서명 검증 (실제로는 더 복잡한 검증 로직 필요)
            expected_signature = hashlib.sha256(data.encode()).hexdigest()
            is_valid = signature == expected_signature
            
            if producer_actual not in self.producer_trust_scores:
                self.producer_trust_scores[producer_actual] = {
                    "score": 0.5,
                    "success_count": 0,
                    "failure_count": 0,
                    "last_seen": time.time(),
                    "executable_hash": None,
                    "signature_valid": False,
                    "path_trusted": False
                }
                
            self.producer_trust_scores[producer_actual]["signature_valid"] = is_valid
            
            if is_valid:
                print(f"[DataCatalog] Signature verified for {producer_actual}")
            else:
                print(f"[DataCatalog] Signature verification failed for {producer_actual}")
                
            return is_valid
            
        except Exception as e:
            print(f"[DataCatalog] Signature verification error for {producer_actual}: {e}")
            return False
            
    def register_trusted_path(self, producer_actual: str, trusted_path: str) -> None:
        """
        Producer의 신뢰할 수 있는 경로 등록
        
        Args:
            producer_actual: Producer 이름
            trusted_path: 신뢰할 수 있는 경로
        """
        if producer_actual not in self.producer_trust_scores:
            self.producer_trust_scores[producer_actual] = {
                "score": 0.5,
                "success_count": 0,
                "failure_count": 0,
                "last_seen": time.time(),
                "executable_hash": None,
                "signature_valid": False,
                "path_trusted": False
            }
            
        self.producer_trust_scores[producer_actual]["path_trusted"] = True
        self.producer_paths[producer_actual] = trusted_path
        print(f"[DataCatalog] Registered trusted path for {producer_actual}: {trusted_path}")
        
    def update_producer_trust(self, producer_actual: str, success: bool) -> None:
        """
        Producer 신뢰도 업데이트
        
        Args:
            producer_actual: Producer 이름
            success: 성공 여부
        """
        if producer_actual not in self.producer_trust_scores:
            self.producer_trust_scores[producer_actual] = {
                "score": 0.5,
                "success_count": 0,
                "failure_count": 0,
                "last_seen": time.time(),
                "executable_hash": None,
                "signature_valid": False,
                "path_trusted": False
            }
            
        trust_data = self.producer_trust_scores[producer_actual]
        
        if success:
            trust_data["success_count"] += 1
        else:
            trust_data["failure_count"] += 1
            
        # 신뢰도 점수 재계산
        self.calculate_producer_trust_score(producer_actual)
        
    def get_producer_trust_info(self, producer_actual: str) -> Dict:
        """
        Producer 신뢰도 정보 조회
        
        Args:
            producer_actual: Producer 이름
            
        Returns:
            신뢰도 정보 딕셔너리
        """
        if producer_actual not in self.producer_trust_scores:
            return {
                "score": 0.5,
                "success_count": 0,
                "failure_count": 0,
                "last_seen": time.time(),
                "executable_hash": None,
                "signature_valid": False,
                "path_trusted": False
            }
            
        return self.producer_trust_scores[producer_actual].copy()
        
    def get_catalog_summary(self) -> Dict:
        """카탈로그 요약 정보 반환"""
        return {
            "total_files": len(self.catalog_data["files"]),
            "total_modules": len(self.catalog_data["modules"]),
            "active_files": len([f for f in self.catalog_data["files"].values() 
                               if f.get("status") == "active"]),
            "version": self.catalog_data.get("version", "1.0"),
            "producer_trust_summary": {
                "total_producers": len(self.producer_trust_scores),
                "trusted_producers": len([p for p in self.producer_trust_scores.values() 
                                        if p["score"] > 0.7]),
                "untrusted_producers": len([p for p in self.producer_trust_scores.values() 
                                          if p["score"] < 0.3])
            }
        }
