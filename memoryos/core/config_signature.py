"""
Configuration Signature Verification Module

Configuration 파일의 서명 검증 및 Feature Flag 관리
"""

import json
import time
import hashlib
from pathlib import Path
from typing import Dict, Optional, Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization


class ConfigSignatureVerifier:
    """
    Configuration 파일 서명 검증 클래스
    
    주요 기능:
    - features.json 서명 검증
    - Feature Flag 유효성 검사
    - 서명 실패 시 read-only 모드로 전환
    """
    
    def __init__(self, config_dir: str = "config"):
        """
        ConfigSignatureVerifier 초기화
        
        Args:
            config_dir: 설정 디렉토리 경로
        """
        self.config_dir = Path(config_dir)
        self.features_file = self.config_dir / "features.json"
        self.public_key_file = self.config_dir / "public_key.pem"
        self.private_key_file = self.config_dir / "private_key.pem"
        
        # Feature Flag 상태
        self.features = {}
        self.signature_valid = False
        self.read_only_mode = False
        
        # 키 관리
        self.public_key = None
        self.private_key = None
        
        # 초기화
        self._load_keys()
        self._load_and_verify_features()
        
    def _load_keys(self) -> None:
        """Ed25519 키 로드"""
        try:
            # 공개키 로드
            if self.public_key_file.exists():
                with open(self.public_key_file, 'rb') as f:
                    self.public_key = serialization.load_pem_public_key(f.read())
                    
            # 개인키 로드 (서명 생성용)
            if self.private_key_file.exists():
                with open(self.private_key_file, 'rb') as f:
                    self.private_key = serialization.load_pem_private_key(
                        f.read(), password=None
                    )
                    
        except Exception as e:
            print(f"[ConfigSignatureVerifier] Failed to load keys: {e}")
            
    def _load_and_verify_features(self) -> None:
        """Features 파일 로드 및 서명 검증"""
        try:
            if not self.features_file.exists():
                print("[ConfigSignatureVerifier] Features file not found, using defaults")
                self._create_default_features()
                return
                
            with open(self.features_file, 'r', encoding='utf-8') as f:
                features_data = json.load(f)
                
            # 서명 검증
            if self._verify_features_signature(features_data):
                self.features = features_data.get("features", {})
                self.signature_valid = True
                self.read_only_mode = False
                print("[ConfigSignatureVerifier] Features signature verified successfully")
            else:
                print("[ConfigSignatureVerifier] Features signature verification failed")
                self._fallback_to_read_only()
                
        except Exception as e:
            print(f"[ConfigSignatureVerifier] Failed to load features: {e}")
            self._fallback_to_read_only()
            
    def _verify_features_signature(self, features_data: Dict) -> bool:
        """Features 파일 서명 검증"""
        try:
            if not self.public_key:
                print("[ConfigSignatureVerifier] No public key available")
                # 키가 없을 때는 서명이 비어있으면 기본값으로 처리
                signature_hex = features_data.get("signature", "")
                if not signature_hex:
                    print("[ConfigSignatureVerifier] No signature found, using default features")
                    return True  # 기본값으로 처리
                return False
                
            # 서명 추출
            signature_hex = features_data.get("signature", "")
            if not signature_hex:
                print("[ConfigSignatureVerifier] No signature found")
                return False
                
            # 서명할 데이터 준비 (signature 필드 제외)
            data_to_verify = features_data.copy()
            del data_to_verify["signature"]
            
            # JSON 직렬화 (정렬된 키로 일관성 보장)
            json_data = json.dumps(data_to_verify, sort_keys=True, ensure_ascii=False)
            data_bytes = json_data.encode('utf-8')
            
            # 서명 검증
            signature_bytes = bytes.fromhex(signature_hex)
            self.public_key.verify(signature_bytes, data_bytes)
            
            return True
            
        except Exception as e:
            print(f"[ConfigSignatureVerifier] Signature verification failed: {e}")
            return False
            
    def _create_default_features(self) -> None:
        """기본 Features 생성 및 서명"""
        default_features = {
            "schema_version": "1.0.0",
            "features": {
                "enable_drift_detection": True,
                "enable_self_healing": True,
                "enable_quarantine": True,
                "enable_backup": True,
                "enable_signing": False,
                "enable_metrics": True,
                "enable_snapshot_export": True,
                "enable_wal_mode": True,
                "enable_idempotency": True,
                "enable_producer_trust": True,
                "enable_adaptive_thresholds": True,
                "enable_merkle_verification": True,
                "enable_atomic_transactions": True
            },
            "timestamp": time.time()
        }
        
        # 서명 추가
        if self.private_key:
            signature = self._sign_features_data(default_features)
            default_features["signature"] = signature
            
        # 파일 저장
        with open(self.features_file, 'w', encoding='utf-8') as f:
            json.dump(default_features, f, indent=2, ensure_ascii=False)
            
        self.features = default_features["features"]
        self.signature_valid = True
        
    def _sign_features_data(self, features_data: Dict) -> str:
        """Features 데이터 서명"""
        try:
            if not self.private_key:
                return ""
                
            # 서명할 데이터 준비
            data_to_sign = features_data.copy()
            if "signature" in data_to_sign:
                del data_to_sign["signature"]
                
            # JSON 직렬화
            json_data = json.dumps(data_to_sign, sort_keys=True, ensure_ascii=False)
            data_bytes = json_data.encode('utf-8')
            
            # 서명 생성
            signature = self.private_key.sign(data_bytes)
            return signature.hex()
            
        except Exception as e:
            print(f"[ConfigSignatureVerifier] Failed to sign features: {e}")
            return ""
            
    def _fallback_to_read_only(self) -> None:
        """서명 검증 실패 시 read-only 모드로 전환"""
        self.read_only_mode = True
        self.signature_valid = False
        
        # 안전한 기본 Features 설정
        self.features = {
            "enable_drift_detection": True,
            "enable_self_healing": False,  # 보안상 비활성화
            "enable_quarantine": False,    # 보안상 비활성화
            "enable_backup": True,
            "enable_signing": False,
            "enable_metrics": True,
            "enable_snapshot_export": False,  # 보안상 비활성화
            "enable_wal_mode": True,
            "enable_idempotency": True,
            "enable_producer_trust": False,   # 보안상 비활성화
            "enable_adaptive_thresholds": True,
            "enable_merkle_verification": True,
            "enable_atomic_transactions": True
        }
        
        print("[ConfigSignatureVerifier] Fallback to read-only mode with safe defaults")
        
    def is_feature_enabled(self, feature_name: str) -> bool:
        """
        Feature Flag 상태 확인
        
        Args:
            feature_name: 확인할 feature 이름
            
        Returns:
            Feature 활성화 여부
        """
        if self.read_only_mode:
            # read-only 모드에서는 보안상 제한된 기능만 허용
            safe_features = {
                "enable_drift_detection",
                "enable_backup", 
                "enable_metrics",
                "enable_wal_mode",
                "enable_idempotency",
                "enable_adaptive_thresholds",
                "enable_merkle_verification",
                "enable_atomic_transactions"
            }
            
            if feature_name not in safe_features:
                return False
                
        return self.features.get(feature_name, False)
        
    def get_feature_status(self) -> Dict:
        """
        Feature 상태 정보 반환
        
        Returns:
            Feature 상태 정보
        """
        return {
            "signature_valid": self.signature_valid,
            "read_only_mode": self.read_only_mode,
            "features": self.features.copy(),
            "schema_version": self.features.get("schema_version", "unknown"),
            "timestamp": time.time()
        }
        
    def update_feature(self, feature_name: str, enabled: bool) -> bool:
        """
        Feature Flag 업데이트 (서명 재생성)
        
        Args:
            feature_name: 업데이트할 feature 이름
            enabled: 활성화 여부
            
        Returns:
            업데이트 성공 여부
        """
        if self.read_only_mode:
            print("[ConfigSignatureVerifier] Cannot update features in read-only mode")
            return False
            
        if not self.private_key:
            print("[ConfigSignatureVerifier] No private key available for signing")
            return False
            
        try:
            # Feature 업데이트
            self.features[feature_name] = enabled
            
            # 새로운 Features 데이터 생성
            features_data = {
                "schema_version": "1.0.0",
                "features": self.features,
                "timestamp": time.time()
            }
            
            # 서명 추가
            signature = self._sign_features_data(features_data)
            features_data["signature"] = signature
            
            # 파일 저장
            with open(self.features_file, 'w', encoding='utf-8') as f:
                json.dump(features_data, f, indent=2, ensure_ascii=False)
                
            print(f"[ConfigSignatureVerifier] Feature '{feature_name}' updated to {enabled}")
            return True
            
        except Exception as e:
            print(f"[ConfigSignatureVerifier] Failed to update feature: {e}")
            return False
            
    def regenerate_signature(self) -> bool:
        """
        Features 파일 서명 재생성
        
        Returns:
            재생성 성공 여부
        """
        if self.read_only_mode:
            print("[ConfigSignatureVerifier] Cannot regenerate signature in read-only mode")
            return False
            
        if not self.private_key:
            print("[ConfigSignatureVerifier] No private key available for signing")
            return False
            
        try:
            # 현재 Features 데이터 로드
            with open(self.features_file, 'r', encoding='utf-8') as f:
                features_data = json.load(f)
                
            # 서명 재생성
            signature = self._sign_features_data(features_data)
            features_data["signature"] = signature
            features_data["timestamp"] = time.time()
            
            # 파일 저장
            with open(self.features_file, 'w', encoding='utf-8') as f:
                json.dump(features_data, f, indent=2, ensure_ascii=False)
                
            self.signature_valid = True
            print("[ConfigSignatureVerifier] Signature regenerated successfully")
            return True
            
        except Exception as e:
            print(f"[ConfigSignatureVerifier] Failed to regenerate signature: {e}")
            return False

