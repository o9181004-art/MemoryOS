"""
SnapshotGenerator - 구조화 스냅샷(JSON) 출력

AI-friendly JSON Schema로 현재 상태를 export합니다.
JSON Schema 검증을 포함합니다.
"""

import json
import time
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
import jsonschema


class SnapshotGenerator:
    """
    스냅샷 생성 클래스
    
    주요 기능:
    - 현재 시스템 상태의 구조화된 스냅샷 생성
    - AI-friendly JSON Schema 출력
    - 상태 요약 및 최근 변경사항 포함
    - Provenance 정보 제공
    """
    
    def __init__(self, snapshot_dir: str = "snapshots"):
        """
        SnapshotGenerator 초기화
        
        Args:
            snapshot_dir: 스냅샷 저장 디렉토리
        """
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON 스키마 로드
        schema_file = Path(__file__).parent / "snapshot_schema.json"
        self.schema = self._load_schema(schema_file)
        self.schema_version = "1.0.0"
        
    def _load_schema(self, schema_file: str) -> Dict:
        """
        JSON 스키마 로드
        
        Args:
            schema_file: 스키마 파일 경로
            
        Returns:
            로드된 스키마
        """
        try:
            schema_path = Path(schema_file)
            if schema_path.exists():
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema = json.load(f)
                print(f"[SnapshotGenerator] Schema loaded from {schema_file}")
                return schema
            else:
                print(f"[SnapshotGenerator] Schema file not found: {schema_file}")
                return {}
        except Exception as e:
            print(f"[SnapshotGenerator] Failed to load schema: {e}")
            return {}
            
    def validate_snapshot(self, snapshot_data: Dict) -> Dict:
        """
        스냅샷 데이터 검증 (Strict Validation 포함)
        
        Args:
            snapshot_data: 검증할 스냅샷 데이터
            
        Returns:
            검증 결과
        """
        result = {
            "is_valid": False,
            "errors": [],
            "warnings": [],
            "timestamp": time.time()
        }
        
        try:
            if not self.schema:
                result["errors"].append("Schema not loaded")
                return result
                
            # 1. 필수 필드 존재 여부 검증
            required_fields = self.schema.get("required", [])
            missing_fields = self._check_required_fields(snapshot_data, required_fields)
            result["errors"].extend(missing_fields)
            
            # 2. JSON Schema 검증
            if not missing_fields:  # 필수 필드가 모두 있으면 스키마 검증 수행
                jsonschema.validate(snapshot_data, self.schema)
            
            # 3. 추가 검증 로직
            additional_errors = self._validate_additional_rules(snapshot_data)
            result["errors"].extend(additional_errors)
            
            # 4. 중첩 객체 필수 필드 검증
            nested_errors = self._validate_nested_required_fields(snapshot_data)
            result["errors"].extend(nested_errors)
            
            if not result["errors"]:
                result["is_valid"] = True
                print("[SnapshotGenerator] Snapshot validation passed")
            else:
                print(f"[SnapshotGenerator] Snapshot validation failed: {result['errors']}")
                
        except jsonschema.ValidationError as e:
            result["errors"].append(f"Schema validation error: {e.message}")
            print(f"[SnapshotGenerator] Schema validation error: {e.message}")
        except Exception as e:
            result["errors"].append(f"Validation error: {str(e)}")
            print(f"[SnapshotGenerator] Validation error: {str(e)}")
            
        return result
        
    def _check_required_fields(self, data: Dict, required_fields: List[str]) -> List[str]:
        """
        필수 필드 존재 여부 검증
        
        Args:
            data: 검증할 데이터
            required_fields: 필수 필드 목록
            
        Returns:
            누락된 필드 목록
        """
        missing_fields = []
        
        for field in required_fields:
            if field not in data:
                missing_fields.append(f"Missing required field: {field}")
            elif data[field] is None:
                missing_fields.append(f"Required field '{field}' is null")
                
        return missing_fields
        
    def _validate_nested_required_fields(self, snapshot_data: Dict) -> List[str]:
        """
        중첩 객체의 필수 필드 검증
        
        Args:
            snapshot_data: 검증할 스냅샷 데이터
            
        Returns:
            오류 목록
        """
        errors = []
        
        try:
            # memory_index.files 검증
            memory_index = snapshot_data.get("memory_index", {})
            files = memory_index.get("files", {})
            
            for file_path, file_info in files.items():
                required_file_fields = ["hash", "producer_actual", "producer_expected", "last_updated"]
                for field in required_file_fields:
                    if field not in file_info:
                        errors.append(f"Missing required field '{field}' in file {file_path}")
                    elif file_info[field] is None:
                        errors.append(f"Required field '{field}' is null in file {file_path}")
                        
            # drift_status 검증
            drift_status = snapshot_data.get("drift_status", {})
            required_drift_fields = ["total_files", "active_files", "stale_files", "error_files", "drift_counts"]
            for field in required_drift_fields:
                if field not in drift_status:
                    errors.append(f"Missing required field '{field}' in drift_status")
                    
            # hash_chain 검증
            hash_chain = snapshot_data.get("hash_chain", {})
            required_chain_fields = ["chain_length", "latest_hash", "merkle_root", "integrity_verified"]
            for field in required_chain_fields:
                if field not in hash_chain:
                    errors.append(f"Missing required field '{field}' in hash_chain")
                    
            # quarantine_status 검증
            quarantine_status = snapshot_data.get("quarantine_status", {})
            required_quarantine_fields = ["quarantined_files", "quarantine_count", "auto_release_candidates"]
            for field in required_quarantine_fields:
                if field not in quarantine_status:
                    errors.append(f"Missing required field '{field}' in quarantine_status")
                    
            # performance_metrics 검증
            performance_metrics = snapshot_data.get("performance_metrics", {})
            required_metrics_fields = ["hit_rate", "avg_latency_ms", "error_rate", "drift_levels"]
            for field in required_metrics_fields:
                if field not in performance_metrics:
                    errors.append(f"Missing required field '{field}' in performance_metrics")
                    
            # system_info 검증
            system_info = snapshot_data.get("system_info", {})
            required_system_fields = ["version", "uptime_seconds", "config_hash"]
            for field in required_system_fields:
                if field not in system_info:
                    errors.append(f"Missing required field '{field}' in system_info")
                    
        except Exception as e:
            errors.append(f"Nested validation error: {str(e)}")
            
        return errors
        
    def _validate_additional_rules(self, snapshot_data: Dict) -> List[str]:
        """
        추가 검증 규칙
        
        Args:
            snapshot_data: 검증할 스냅샷 데이터
            
        Returns:
            오류 목록
        """
        errors = []
        
        try:
            # 스키마 버전 검증
            schema_version = snapshot_data.get("schema_version")
            if schema_version != self.schema_version:
                errors.append(f"Schema version mismatch: expected {self.schema_version}, got {schema_version}")
                
            # 메모리 인덱스 검증
            memory_index = snapshot_data.get("memory_index", {})
            files = memory_index.get("files", {})
            
            for file_path, file_info in files.items():
                # 파일 해시 형식 검증
                file_hash = file_info.get("hash", "")
                if len(file_hash) != 64 or not all(c in "0123456789abcdef" for c in file_hash):
                    errors.append(f"Invalid hash format for file {file_path}: {file_hash}")
                    
                # 시간 검증
                last_updated = file_info.get("last_updated", 0)
                if last_updated <= 0:
                    errors.append(f"Invalid last_updated time for file {file_path}: {last_updated}")
                    
            # Drift 상태 검증
            drift_status = snapshot_data.get("drift_status", {})
            total_files = drift_status.get("total_files", 0)
            active_files = drift_status.get("active_files", 0)
            stale_files = drift_status.get("stale_files", 0)
            error_files = drift_status.get("error_files", 0)
            
            if total_files != active_files + stale_files + error_files:
                errors.append(f"Drift status mismatch: total={total_files}, sum={active_files + stale_files + error_files}")
                
            # Hash Chain 검증
            hash_chain = snapshot_data.get("hash_chain", {})
            chain_length = hash_chain.get("chain_length", 0)
            if chain_length < 0:
                errors.append(f"Invalid chain length: {chain_length}")
                
        except Exception as e:
            errors.append(f"Additional validation error: {str(e)}")
            
        return errors
        
    def generate_snapshot(self, memory_index: Dict, hash_chain: List[Dict], 
                         recent_deltas: List[Dict] = None, 
                         catalog_summary: Dict = None) -> Dict:
        """
        전체 시스템 스냅샷 생성 (Strict Validation 포함)
        
        Args:
            memory_index: 메모리 인덱스 데이터
            hash_chain: Hash Chain 데이터
            recent_deltas: 최근 delta 이벤트 목록
            catalog_summary: 카탈로그 요약 정보
            
        Returns:
            생성된 스냅샷 데이터
        """
        current_time = time.time()
        
        # 기본 스냅샷 구조 (Strict Schema 준수)
        snapshot = {
            "schema_version": self.schema_version,
            "snapshot_id": f"snap_{int(current_time)}",
            "timestamp": current_time,
            "memory_index": self._prepare_memory_index(memory_index),
            "drift_status": self._generate_drift_status(memory_index),
            "hash_chain": self._prepare_hash_chain(hash_chain),
            "quarantine_status": self._generate_quarantine_status(),
            "performance_metrics": self._generate_performance_metrics(memory_index),
            "system_info": self._generate_system_info()
        }
        
        # Strict Validation 수행
        validation_result = self.validate_snapshot(snapshot)
        if not validation_result["is_valid"]:
            print(f"[SnapshotGenerator] Snapshot validation failed: {validation_result['errors']}")
            # 검증 실패 시 기본값으로 대체
            snapshot = self._create_fallback_snapshot(current_time)
            
        return snapshot
        
    def _prepare_memory_index(self, memory_index: Dict) -> Dict:
        """
        메모리 인덱스 데이터를 스키마에 맞게 준비
        
        Args:
            memory_index: 원본 메모리 인덱스 데이터
            
        Returns:
            스키마 준수 메모리 인덱스 데이터
        """
        files = memory_index.get("files", {})
        prepared_files = {}
        
        for file_path, file_info in files.items():
            # file_info가 딕셔너리가 아닌 경우 기본값으로 처리
            if not isinstance(file_info, dict):
                file_info = {}
                
            # 필수 필드 검증 및 기본값 설정
            prepared_files[file_path] = {
                "hash": file_info.get("hash", "0" * 64),  # 기본 해시
                "producer_actual": file_info.get("producer_actual", "unknown"),
                "producer_expected": file_info.get("producer_expected", "unknown"),
                "last_updated": file_info.get("last_updated", 0),
                "update_interval": file_info.get("update_interval", 300),
                "metadata": file_info.get("metadata", {})
            }
            
        return {
            "files": prepared_files,
            "catalog": memory_index.get("catalog", {})
        }
        
    def _prepare_hash_chain(self, hash_chain: List[Dict]) -> Dict:
        """
        Hash Chain 데이터를 스키마에 맞게 준비
        
        Args:
            hash_chain: 원본 Hash Chain 데이터
            
        Returns:
            스키마 준수 Hash Chain 데이터
        """
        if not hash_chain:
            return {
                "chain_length": 0,
                "latest_hash": "0" * 64,
                "merkle_root": "0" * 64,
                "integrity_verified": True
            }
            
        # 체인 무결성 검증
        chain_valid = True
        for i in range(1, len(hash_chain)):
            if hash_chain[i].get("prev_hash") != hash_chain[i-1].get("hash"):
                chain_valid = False
                break
                
        return {
            "chain_length": len(hash_chain),
            "latest_hash": hash_chain[-1].get("hash", "0" * 64),
            "merkle_root": hash_chain[-1].get("merkle_root", "0" * 64),
            "integrity_verified": chain_valid
        }
        
    def _generate_drift_status(self, memory_index: Dict) -> Dict:
        """
        Drift 상태 정보 생성
        
        Args:
            memory_index: 메모리 인덱스 데이터
            
        Returns:
            Drift 상태 정보
        """
        files = memory_index.get("files", {})
        current_time = time.time()
        
        active_files = 0
        stale_files = 0
        error_files = 0
        
        for file_path, file_info in files.items():
            last_updated = file_info.get("last_updated", 0)
            if last_updated == 0:
                error_files += 1
            elif current_time - last_updated > 3600:  # 1시간 이상 미업데이트
                stale_files += 1
            else:
                active_files += 1
                
        return {
            "total_files": len(files),
            "active_files": active_files,
            "stale_files": stale_files,
            "error_files": error_files,
            "drift_counts": {
                "0": active_files,
                "1": stale_files,
                "2": error_files,
                "3": 0
            }
        }
        
    def _generate_quarantine_status(self) -> Dict:
        """
        격리 상태 정보 생성
        
        Returns:
            격리 상태 정보
        """
        return {
            "quarantined_files": [],
            "quarantine_count": 0,
            "auto_release_candidates": []
        }
        
    def _generate_performance_metrics(self, memory_index: Dict) -> Dict:
        """
        성능 메트릭 생성
        
        Args:
            memory_index: 메모리 인덱스 데이터
            
        Returns:
            성능 메트릭 정보
        """
        files = memory_index.get("files", {})
        total_files = len(files)
        
        if total_files == 0:
            hit_rate = 1.0
            error_rate = 0.0
        else:
            active_files = sum(1 for f in files.values() if f.get("last_updated", 0) > 0)
            hit_rate = active_files / total_files
            error_rate = 1.0 - hit_rate
            
        return {
            "hit_rate": hit_rate,
            "avg_latency_ms": 0.0,  # Placeholder
            "error_rate": error_rate,
            "drift_levels": {
                "L1": 0,
                "L2": 0,
                "L3": 0
            }
        }
        
    def _generate_system_info(self) -> Dict:
        """
        시스템 정보 생성
        
        Returns:
            시스템 정보
        """
        return {
            "version": "1.0.0",
            "uptime_seconds": time.time(),
            "config_hash": "0" * 64  # Placeholder
        }
        
    def _create_fallback_snapshot(self, timestamp: float) -> Dict:
        """
        검증 실패 시 기본 스냅샷 생성
        
        Args:
            timestamp: 타임스탬프
            
        Returns:
            기본 스냅샷 데이터
        """
        return {
            "schema_version": self.schema_version,
            "snapshot_id": f"fallback_{int(timestamp)}",
            "timestamp": timestamp,
            "memory_index": {
                "files": {},
                "catalog": {}
            },
            "drift_status": {
                "total_files": 0,
                "active_files": 0,
                "stale_files": 0,
                "error_files": 0,
                "drift_counts": {
                    "0": 0,
                    "1": 0,
                    "2": 0,
                    "3": 0
                }
            },
            "hash_chain": {
                "chain_length": 0,
                "latest_hash": "0" * 64,
                "merkle_root": "0" * 64,
                "integrity_verified": True
            },
            "quarantine_status": {
                "quarantined_files": [],
                "quarantine_count": 0,
                "auto_release_candidates": []
            },
            "performance_metrics": {
                "hit_rate": 1.0,
                "avg_latency_ms": 0.0,
                "error_rate": 0.0,
                "drift_levels": {
                    "L1": 0,
                    "L2": 0,
                    "L3": 0
                }
            },
            "system_info": {
                "version": "1.0.0",
                "uptime_seconds": timestamp,
                "config_hash": "0" * 64
            }
        }
        
    def _generate_state_summary(self, memory_index: Dict, 
                               catalog_summary: Dict = None) -> Dict:
        """
        시스템 상태 요약 생성
        
        Args:
            memory_index: 메모리 인덱스 데이터
            catalog_summary: 카탈로그 요약 정보
            
        Returns:
            상태 요약 정보
        """
        files = memory_index.get("files", {})
        
        # 파일별 상태 분석
        active_files = 0
        stale_files = 0
        error_files = 0
        
        current_time = time.time()
        
        for _file_path, file_info in files.items():
            last_updated = file_info.get("last_updated", 0)
            if last_updated == 0:
                error_files += 1
            elif current_time - last_updated > 3600:  # 1시간 이상 미업데이트
                stale_files += 1
            else:
                active_files += 1
                
        return {
            "total_files": len(files),
            "active_files": active_files,
            "stale_files": stale_files,
            "error_files": error_files,
            "total_operations": memory_index.get("metadata", {}).get("total_operations", 0) if isinstance(memory_index.get("metadata"), dict) else 0,
            "catalog_info": catalog_summary or {},
            "last_system_update": memory_index.get("metadata", {}).get("last_updated", 0) if isinstance(memory_index.get("metadata"), dict) else 0
        }
        
    def _generate_provenance(self, hash_chain: List[Dict]) -> Dict:
        """
        Provenance 정보 생성
        
        Args:
            hash_chain: Hash Chain 데이터
            
        Returns:
            Provenance 정보
        """
        if not hash_chain:
            return {
                "chain_length": 0,
                "merkle_root": "",
                "chain_integrity": True,
                "last_block_hash": ""
            }
            
        # 체인 무결성 검증
        chain_valid = True
        for i in range(1, len(hash_chain)):
            if hash_chain[i].get("prev_hash") != hash_chain[i-1].get("hash"):
                chain_valid = False
                break
                
        return {
            "chain_length": len(hash_chain),
            "merkle_root": hash_chain[-1].get("hash", "") if hash_chain else "",
            "chain_integrity": chain_valid,
            "last_block_hash": hash_chain[-1].get("hash", "") if hash_chain else "",
            "first_block_timestamp": hash_chain[0].get("timestamp", 0) if hash_chain else 0,
            "last_block_timestamp": hash_chain[-1].get("timestamp", 0) if hash_chain else 0
        }
        
    def _assess_system_health(self, memory_index: Dict, 
                            hash_chain: List[Dict]) -> Dict:
        """
        시스템 건강도 평가
        
        Args:
            memory_index: 메모리 인덱스 데이터
            hash_chain: Hash Chain 데이터
            
        Returns:
            시스템 건강도 정보
        """
        health_score = 100
        issues = []
        
        # 파일 상태 검사
        files = memory_index.get("files", {})
        current_time = time.time()
        
        for file_path, file_info in files.items():
            last_updated = file_info.get("last_updated", 0)
            if last_updated == 0:
                health_score -= 10
                issues.append(f"File {file_path} has no update timestamp")
            elif current_time - last_updated > 3600:
                health_score -= 5
                issues.append(f"File {file_path} is stale")
                
        # 체인 무결성 검사
        if not hash_chain:
            health_score -= 20
            issues.append("Hash chain is empty")
        else:
            # 체인 연속성 검사
            for i in range(1, len(hash_chain)):
                if hash_chain[i].get("prev_hash") != hash_chain[i-1].get("hash"):
                    health_score -= 30
                    issues.append(f"Hash chain integrity broken at block {i}")
                    break
                    
        # 건강도 등급 결정
        if health_score >= 90:
            health_status = "excellent"
        elif health_score >= 70:
            health_status = "good"
        elif health_score >= 50:
            health_status = "fair"
        else:
            health_status = "poor"
            
        return {
            "health_score": max(0, health_score),
            "health_status": health_status,
            "issues": issues,
            "recommendations": self._generate_recommendations(issues)
        }
        
    def _generate_recommendations(self, issues: List[str]) -> List[str]:
        """
        문제점에 대한 권장사항 생성
        
        Args:
            issues: 발견된 문제점 목록
            
        Returns:
            권장사항 목록
        """
        recommendations = []
        
        for issue in issues:
            if "no update timestamp" in issue:
                recommendations.append("Check file monitoring configuration")
            elif "is stale" in issue:
                recommendations.append("Investigate file update frequency")
            elif "Hash chain integrity" in issue:
                recommendations.append("Perform chain repair or reset")
            elif "Hash chain is empty" in issue:
                recommendations.append("Initialize hash chain with seed data")
                
        return recommendations
        
    def _generate_file_status(self, memory_index: Dict) -> Dict:
        """
        파일별 상세 상태 생성
        
        Args:
            memory_index: 메모리 인덱스 데이터
            
        Returns:
            파일 상태 정보
        """
        files = memory_index.get("files", {})
        file_status = {}
        
        current_time = time.time()
        
        for file_path, file_info in files.items():
            operations = file_info.get("operations", [])
            last_updated = file_info.get("last_updated", 0)
            
            # 상태 결정
            if last_updated == 0:
                status = "error"
            elif current_time - last_updated > 3600:
                status = "stale"
            elif current_time - last_updated > 1800:
                status = "warning"
            else:
                status = "active"
                
            file_status[file_path] = {
                "status": status,
                "version": file_info.get("version", 0),
                "last_updated": last_updated,
                "operation_count": len(operations),
                "current_hash": file_info.get("current_hash", ""),
                "last_operation": operations[-1] if operations else None
            }
            
        return file_status
        
    def save_snapshot(self, snapshot: Dict, filename: str = None) -> str:
        """
        스냅샷을 파일로 저장
        
        Args:
            snapshot: 저장할 스냅샷 데이터
            filename: 저장할 파일명 (None이면 자동 생성)
            
        Returns:
            저장된 파일 경로
        """
        if filename is None:
            timestamp = int(snapshot.get("metadata", {}).get("generated_at", time.time()))
            filename = f"snap_{timestamp}.json"
            
        file_path = self.snapshot_dir / filename
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
            
        print(f"[SnapshotGenerator] Snapshot saved: {file_path}")
        return str(file_path)
        
    def load_snapshot(self, filename: str) -> Optional[Dict]:
        """
        스냅샷 파일 로드
        
        Args:
            filename: 로드할 파일명
            
        Returns:
            스냅샷 데이터 또는 None
        """
        file_path = self.snapshot_dir / filename
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[SnapshotGenerator] Failed to load snapshot: {e}")
            return None
            
    def get_snapshot_list(self) -> List[Dict]:
        """저장된 스냅샷 목록 조회"""
        snapshots = []
        
        for file_path in self.snapshot_dir.glob("snap_*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    snapshot = json.load(f)
                    snapshots.append({
                        "filename": file_path.name,
                        "generated_at": snapshot.get("metadata", {}).get("generated_at", 0),
                        "snapshot_id": snapshot.get("metadata", {}).get("snapshot_id", ""),
                        "file_size": file_path.stat().st_size
                    })
            except Exception:
                continue
                
        # 생성 시간순 정렬
        snapshots.sort(key=lambda x: x["generated_at"], reverse=True)
        return snapshots
