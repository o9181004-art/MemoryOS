"""
EventLog - 불변 로그 기록기 (서명 옵션)

시스템 이벤트를 불변 로그로 기록하고 서명 옵션을 제공합니다.
"""

import json
import time
import hashlib
import uuid
from typing import Dict, List, Tuple
from pathlib import Path
from collections import defaultdict
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.backends import default_backend


class EventLog:
    """
    불변 이벤트 로그 클래스 (Event Correlation ID 포함)
    
    주요 기능:
    - 불변 이벤트 로그 기록
    - Ed25519 서명 옵션
    - 로그 무결성 검증
    - 체인 기반 로그 연결
    - run_id 및 correlation_id 자동 생성 및 전파
    """
    
    def __init__(self, log_file: str = "logs/event_log.jsonl", 
                 enable_signing: bool = False, 
                 private_key_file: str = None):
        """
        EventLog 초기화
        
        Args:
            log_file: 로그 파일 경로
            enable_signing: 서명 활성화 여부
            private_key_file: 개인키 파일 경로
        """
        self.log_file = Path(log_file)
        self.enable_signing = enable_signing
        self.private_key = None
        self.public_key = None
        
        # 로그 디렉토리 생성
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 서명 설정
        if enable_signing:
            # 키 파일 경로가 제공되지 않으면 기본 경로 사용
            if private_key_file is None:
                private_key_file = str(self.log_file.parent / "private_key.pem")
            self._setup_signing(private_key_file)
            
        # 로그 체인 관리
        self.log_chain = []
        self.last_log_hash = None
        
        # Event Correlation ID 관리
        self.current_run_id = self._generate_run_id()
        self.correlation_context = {}  # correlation_id -> context 정보
        self.event_counter = 0  # 이벤트 카운터
        
    def _generate_run_id(self) -> str:
        """
        새로운 run_id 생성
        
        Returns:
            고유한 run_id
        """
        timestamp = int(time.time() * 1000)  # 밀리초 단위 타임스탬프
        unique_id = str(uuid.uuid4())[:8]  # UUID의 첫 8자리
        return f"run_{timestamp}_{unique_id}"
        
    def _generate_correlation_id(self, parent_correlation_id: str = None) -> str:
        """
        새로운 correlation_id 생성
        
        Args:
            parent_correlation_id: 부모 correlation_id (선택사항)
            
        Returns:
            고유한 correlation_id
        """
        self.event_counter += 1
        timestamp = int(time.time() * 1000)
        
        if parent_correlation_id:
            # 부모 correlation_id가 있으면 계층 구조 생성
            return f"{parent_correlation_id}.{self.event_counter}_{timestamp}"
        else:
            # 최상위 correlation_id 생성
            return f"corr_{timestamp}_{self.event_counter}"
            
    def set_correlation_context(self, correlation_id: str, context: Dict) -> None:
        """
        correlation_id에 대한 컨텍스트 정보 설정
        
        Args:
            correlation_id: correlation ID
            context: 컨텍스트 정보
        """
        self.correlation_context[correlation_id] = {
            "context": context,
            "created_at": time.time(),
            "run_id": self.current_run_id
        }
        
    def get_correlation_context(self, correlation_id: str) -> Dict:
        """
        correlation_id에 대한 컨텍스트 정보 조회
        
        Args:
            correlation_id: correlation ID
            
        Returns:
            컨텍스트 정보
        """
        return self.correlation_context.get(correlation_id, {})
        
    def propagate_correlation_id(self, event_data: Dict, 
                                parent_correlation_id: str = None) -> str:
        """
        이벤트에 correlation_id 전파
        
        Args:
            event_data: 이벤트 데이터
            parent_correlation_id: 부모 correlation_id
            
        Returns:
            생성된 correlation_id
        """
        correlation_id = self._generate_correlation_id(parent_correlation_id)
        
        # 이벤트 데이터에 correlation 정보 추가
        event_data["correlation_id"] = correlation_id
        event_data["run_id"] = self.current_run_id
        event_data["event_sequence"] = self.event_counter
        
        # 부모 correlation_id가 있으면 추가
        if parent_correlation_id:
            event_data["parent_correlation_id"] = parent_correlation_id
            
        return correlation_id
        
    def start_new_run(self) -> str:
        """
        새로운 run 시작
        
        Returns:
            새로운 run_id
        """
        self.current_run_id = self._generate_run_id()
        self.event_counter = 0
        self.correlation_context.clear()
        
        print(f"[EventLog] Started new run: {self.current_run_id}")
        return self.current_run_id
        
    def get_current_run_id(self) -> str:
        """
        현재 run_id 조회
        
        Returns:
            현재 run_id
        """
        return self.current_run_id
        
    def _setup_signing(self, private_key_file: str = None) -> None:
        """서명 설정"""
        try:
            if private_key_file and Path(private_key_file).exists():
                # 기존 키 로드
                with open(private_key_file, 'rb') as f:
                    private_key_data = f.read()
                    self.private_key = serialization.load_pem_private_key(
                        private_key_data, password=None, backend=default_backend()
                    )
            else:
                # 새 키 생성
                self.private_key = ed25519.Ed25519PrivateKey.generate()
                
                # 키 저장
                if private_key_file:
                    key_path = Path(private_key_file)
                    key_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(key_path, 'wb') as f:
                        f.write(self.private_key.private_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PrivateFormat.PKCS8,
                            encryption_algorithm=serialization.NoEncryption()
                        ))
                        
            # 공개키 추출
            self.public_key = self.private_key.public_key()
            
            # 공개키도 저장
            if private_key_file:
                public_key_file = private_key_file.replace("private_key.pem", "public_key.pem")
                with open(public_key_file, 'wb') as f:
                    f.write(self.public_key.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo
                    ))
            
            print("[EventLog] Signing enabled with Ed25519")
            
        except Exception as e:
            print(f"[EventLog] Failed to setup signing: {e}")
            self.enable_signing = False
            
    def sign_line_ed25519(self, line_bytes: bytes, private_key=None) -> bytes:
        """
        Ed25519 서명 생성
        
        Args:
            line_bytes: 서명할 라인 바이트
            private_key: Ed25519 개인키 (None이면 기본 키 사용)
            
        Returns:
            서명 바이트
        """
        try:
            if private_key is None:
                private_key = self.private_key
                
            if private_key is None:
                print("[EventLog] No private key available for signing")
                return b""
                
            signature = private_key.sign(line_bytes)
            return signature
        except Exception as e:
            print(f"[EventLog] Failed to sign line: {e}")
            return b""
            
    def verify_line_ed25519(self, line_bytes: bytes, signature: bytes, public_key=None) -> bool:
        """
        Ed25519 서명 검증
        
        Args:
            line_bytes: 검증할 라인 바이트
            signature: 서명 바이트
            public_key: Ed25519 공개키 (None이면 기본 키 사용)
            
        Returns:
            검증 성공 여부
        """
        try:
            if public_key is None:
                public_key = self.public_key
                
            if public_key is None:
                print("[EventLog] No public key available for verification")
                return False
                
            public_key.verify(signature, line_bytes)
            return True
        except Exception as e:
            print(f"[EventLog] Signature verification failed: {e}")
            return False
            
    def log_event(self, event_type: str, event_data: Dict, 
                  metadata: Dict = None, correlation_id: str = None, 
                  parent_correlation_id: str = None) -> bool:
        """
        이벤트 로그 기록 (Correlation ID 자동 생성 및 전파)
        
        Args:
            event_type: 이벤트 타입
            event_data: 이벤트 데이터
            metadata: 추가 메타데이터
            correlation_id: 기존 correlation_id (선택사항)
            parent_correlation_id: 부모 correlation_id (선택사항)
            
        Returns:
            로그 기록 성공 여부
        """
        try:
            # Correlation ID 처리
            if correlation_id:
                # 기존 correlation_id 사용
                final_correlation_id = correlation_id
            else:
                # 새로운 correlation_id 생성 및 전파
                final_correlation_id = self.propagate_correlation_id(event_data, parent_correlation_id)
            
            # 로그 엔트리 구성
            log_entry = {
                "timestamp": time.time(),
                "event_type": event_type,
                "event_data": event_data,
                "metadata": metadata or {},
                "log_id": self._generate_log_id(),
                "prev_hash": self.last_log_hash,
                # Correlation ID 정보 추가
                "correlation_id": final_correlation_id,
                "run_id": self.current_run_id,
                "event_sequence": self.event_counter
            }
            
            # 부모 correlation_id가 있으면 추가
            if parent_correlation_id:
                log_entry["parent_correlation_id"] = parent_correlation_id
            
            # 해시 계산
            log_entry["hash"] = self._calculate_log_hash(log_entry)
            
            # 서명 생성 (enable_signing이 True일 때만)
            if self.enable_signing and self.private_key:
                log_entry["signature"] = self._sign_log_entry(log_entry)
                
            # 로그 체인에 추가
            self.log_chain.append(log_entry)
            self.last_log_hash = log_entry["hash"]
            
            # 파일에 기록
            self._write_log_entry(log_entry)
            
            print(f"[EventLog] Event logged: {event_type} (correlation_id: {final_correlation_id})")
            return True
            
        except Exception as e:
            print(f"[EventLog] Failed to log event: {e}")
            return False
            
    def _generate_log_id(self) -> str:
        """로그 ID 생성"""
        import uuid
        return str(uuid.uuid4())
        
    def _calculate_log_hash(self, log_entry: Dict) -> str:
        """로그 엔트리 해시 계산"""
        # 서명을 제외한 데이터로 해시 계산
        hash_data = {k: v for k, v in log_entry.items() if k != "signature"}
        hash_string = json.dumps(hash_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(hash_string.encode()).hexdigest()
        
    def _sign_log_entry(self, log_entry: Dict) -> str:
        """로그 엔트리 서명"""
        try:
            # 서명할 데이터 준비 (signature 필드 제외)
            sign_data = log_entry.copy()
            sign_data.pop("signature", None)
            
            # JSON 문자열로 변환하여 서명
            json_string = json.dumps(sign_data, sort_keys=True, ensure_ascii=False)
            signature = self.private_key.sign(json_string.encode('utf-8'))
            return signature.hex()
            
        except Exception as e:
            print(f"[EventLog] Failed to sign log entry: {e}")
            return ""
            
    def _write_log_entry(self, log_entry: Dict) -> None:
        """로그 엔트리를 파일에 기록"""
        log_line = json.dumps(log_entry, ensure_ascii=False) + "\n"
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_line)
            
    def verify_log_integrity(self) -> Tuple[bool, List[str]]:
        """
        로그 무결성 검증
        
        Returns:
            (검증 성공 여부, 오류 메시지 목록)
        """
        errors = []
        
        try:
            # 파일에서 로그 읽기
            file_logs = self._read_logs_from_file()
            
            if len(file_logs) != len(self.log_chain):
                errors.append("Log chain length mismatch")
                
            # 각 로그 엔트리 검증
            prev_hash = None
            for i, log_entry in enumerate(file_logs):
                # 이전 해시 검증
                if log_entry["prev_hash"] != prev_hash:
                    errors.append(f"Previous hash mismatch at entry {i}")
                    
                # 서명 검증
                if self.enable_signing and log_entry.get("signature"):
                    if not self._verify_log_signature(log_entry):
                        errors.append(f"Signature verification failed at entry {i}")
                        
                prev_hash = log_entry["hash"]
                
        except Exception as e:
            errors.append(f"Integrity check failed: {str(e)}")
            
        return len(errors) == 0, errors
        
    def _read_logs_from_file(self) -> List[Dict]:
        """파일에서 로그 읽기"""
        logs = []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    log_entry = json.loads(line.strip())
                    logs.append(log_entry)
        except FileNotFoundError:
            pass
            
        return logs
        
    def _verify_log_signature(self, log_entry: Dict) -> bool:
        """로그 서명 검증"""
        try:
            if not self.public_key or not log_entry.get("signature"):
                return False
                
            signature_bytes = bytes.fromhex(log_entry["signature"])
            
            # 서명할 데이터 준비 (signature 필드 제외)
            sign_data = log_entry.copy()
            sign_data.pop("signature", None)
            
            # JSON 문자열로 변환하여 검증
            json_string = json.dumps(sign_data, sort_keys=True, ensure_ascii=False)
            
            self.public_key.verify(signature_bytes, json_string.encode('utf-8'))
            return True
            
        except Exception:
            return False
            
    def get_log_entries(self, event_type: str = None, 
                       start_time: float = None, 
                       end_time: float = None,
                       limit: int = None) -> List[Dict]:
        """
        로그 엔트리 조회
        
        Args:
            event_type: 이벤트 타입 필터
            start_time: 시작 시간
            end_time: 종료 시간
            limit: 조회할 엔트리 수 제한
            
        Returns:
            필터링된 로그 엔트리 목록
        """
        filtered_logs = []
        
        for log_entry in self.log_chain:
            # 이벤트 타입 필터
            if event_type and log_entry["event_type"] != event_type:
                continue
                
            # 시간 필터
            if start_time and log_entry["timestamp"] < start_time:
                continue
            if end_time and log_entry["timestamp"] > end_time:
                continue
                
            filtered_logs.append(log_entry)
            
            # 제한 확인
            if limit and len(filtered_logs) >= limit:
                break
                
        return filtered_logs
        
    def get_log_statistics(self) -> Dict:
        """로그 통계 정보 조회"""
        event_types = defaultdict(int)
        total_events = len(self.log_chain)
        
        for log_entry in self.log_chain:
            event_types[log_entry["event_type"]] += 1
            
        return {
            "total_events": total_events,
            "event_type_counts": dict(event_types),
            "signing_enabled": self.enable_signing,
            "log_file": str(self.log_file),
            "chain_length": len(self.log_chain),
            "last_log_hash": self.last_log_hash
        }
        
    def export_logs(self, output_file: str, event_type: str = None,
                   start_time: float = None, end_time: float = None) -> bool:
        """
        로그 내보내기
        
        Args:
            output_file: 출력 파일 경로
            event_type: 이벤트 타입 필터
            start_time: 시작 시간
            end_time: 종료 시간
            
        Returns:
            내보내기 성공 여부
        """
        try:
            logs = self.get_log_entries(event_type, start_time, end_time)
            
            export_data = {
                "exported_at": time.time(),
                "total_logs": len(logs),
                "filters": {
                    "event_type": event_type,
                    "start_time": start_time,
                    "end_time": end_time
                },
                "logs": logs
            }
            
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
                
            print(f"[EventLog] Exported {len(logs)} logs to {output_file}")
            return True
            
        except Exception as e:
            print(f"[EventLog] Failed to export logs: {e}")
            return False
            
    def get_public_key_pem(self) -> str:
        """공개키 PEM 형식 반환"""
        if not self.public_key:
            return ""
            
        try:
            public_key_pem = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            return public_key_pem.decode()
        except Exception:
            return ""
            
    def verify_external_log(self, log_entry: Dict, public_key_pem: str) -> bool:
        """
        외부 로그 엔트리 검증
        
        Args:
            log_entry: 검증할 로그 엔트리
            public_key_pem: 공개키 PEM 문자열
            
        Returns:
            검증 성공 여부
        """
        try:
            # 공개키 로드
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode(), backend=default_backend()
            )
            
            # 서명 검증
            if not log_entry.get("signature"):
                return False
                
            signature_bytes = bytes.fromhex(log_entry["signature"])
            
            # 서명할 데이터 준비 (signature 필드 제외)
            sign_data = log_entry.copy()
            sign_data.pop("signature", None)
            
            # JSON 문자열로 변환하여 검증
            json_string = json.dumps(sign_data, sort_keys=True, ensure_ascii=False)
            
            public_key.verify(signature_bytes, json_string.encode('utf-8'))
            return True
            
        except Exception:
            return False
            
    def clear_logs(self) -> bool:
        """로그 초기화"""
        try:
            if self.log_file.exists():
                self.log_file.unlink()
                
            self.log_chain.clear()
            self.last_log_hash = None
            
            print("[EventLog] Logs cleared")
            return True
            
        except Exception as e:
            print(f"[EventLog] Failed to clear logs: {e}")
            return False
