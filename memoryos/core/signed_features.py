"""
설정 파일 서명 검증

features.json 파일의 서명을 검증하고 기능 토글 유효성을 체크합니다.
"""

import json
import time
from typing import Dict, Optional
from pathlib import Path
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.backends import default_backend


class SignedFeaturesValidator:
    """
    서명된 기능 설정 검증 클래스
    
    주요 기능:
    - features.json 서명 검증
    - 기능 토글 유효성 체크
    - 서명 불일치 시 read-only 강등
    """
    
    def __init__(self, features_file: str = "config/features.json", 
                 public_key_file: str = "config/features.pub"):
        """
        SignedFeaturesValidator 초기화
        
        Args:
            features_file: 기능 설정 파일 경로
            public_key_file: 공개키 파일 경로
        """
        self.features_file = Path(features_file)
        self.public_key_file = Path(public_key_file)
        self.public_key = None
        self.features_data = None
        self.is_valid = False
        
        # 공개키 로드
        self._load_public_key()
        
    def _load_public_key(self) -> bool:
        """
        공개키 로드
        
        Returns:
            로드 성공 여부
        """
        try:
            if self.public_key_file.exists():
                with open(self.public_key_file, 'rb') as f:
                    public_key_data = f.read()
                    self.public_key = serialization.load_pem_public_key(
                        public_key_data, backend=default_backend()
                    )
                return True
            else:
                print(f"[SignedFeaturesValidator] Public key file not found: {self.public_key_file}")
                return False
        except Exception as e:
            print(f"[SignedFeaturesValidator] Failed to load public key: {e}")
            return False
            
    def verify_features_signature(self) -> bool:
        """
        기능 설정 파일 서명 검증
        
        Returns:
            검증 성공 여부
        """
        try:
            if not self.features_file.exists():
                print(f"[SignedFeaturesValidator] Features file not found: {self.features_file}")
                return False
                
            if not self.public_key:
                print("[SignedFeaturesValidator] No public key available")
                return False
                
            # 기능 설정 파일 로드
            with open(self.features_file, 'r', encoding='utf-8') as f:
                features_content = f.read()
                
            # JSON 파싱
            features_data = json.loads(features_content)
            
            # 서명 검증
            if "signature" not in features_data:
                print("[SignedFeaturesValidator] No signature found in features file")
                return False
                
            signature = bytes.fromhex(features_data["signature"])
            
            # 서명할 데이터 (서명 제외)
            data_to_sign = {k: v for k, v in features_data.items() if k != "signature"}
            data_bytes = json.dumps(data_to_sign, sort_keys=True).encode('utf-8')
            
            # 서명 검증
            try:
                self.public_key.verify(signature, data_bytes)
                self.features_data = features_data
                self.is_valid = True
                print("[SignedFeaturesValidator] Features signature verified successfully")
                return True
            except Exception as e:
                print(f"[SignedFeaturesValidator] Signature verification failed: {e}")
                self.is_valid = False
                return False
                
        except Exception as e:
            print(f"[SignedFeaturesValidator] Failed to verify features: {e}")
            self.is_valid = False
            return False
            
    def get_feature_toggle(self, feature_name: str) -> bool:
        """
        기능 토글 값 조회
        
        Args:
            feature_name: 기능 이름
            
        Returns:
            기능 활성화 여부
        """
        if not self.is_valid or not self.features_data:
            print("[SignedFeaturesValidator] Features not validated or loaded")
            return False
            
        features = self.features_data.get("features", {})
        return features.get(feature_name, False)
        
    def get_all_features(self) -> Dict:
        """
        모든 기능 토글 조회
        
        Returns:
            기능 토글 딕셔너리
        """
        if not self.is_valid or not self.features_data:
            return {}
            
        return self.features_data.get("features", {})
        
    def check_feature_validity(self, feature_name: str) -> Dict:
        """
        기능 유효성 체크
        
        Args:
            feature_name: 기능 이름
            
        Returns:
            유효성 체크 결과
        """
        result = {
            "feature_name": feature_name,
            "is_valid": False,
            "is_enabled": False,
            "error": None,
            "timestamp": time.time()
        }
        
        try:
            if not self.is_valid:
                result["error"] = "Features not validated"
                return result
                
            if not self.features_data:
                result["error"] = "Features data not loaded"
                return result
                
            features = self.features_data.get("features", {})
            
            if feature_name not in features:
                result["error"] = f"Feature '{feature_name}' not found"
                return result
                
            result["is_valid"] = True
            result["is_enabled"] = features[feature_name]
            
        except Exception as e:
            result["error"] = str(e)
            
        return result
        
    def enforce_read_only_mode(self) -> bool:
        """
        read-only 모드 강제 적용
        
        Returns:
            적용 성공 여부
        """
        try:
            print("[SignedFeaturesValidator] Enforcing read-only mode due to signature failure")
            
            # 모든 기능 비활성화
            if self.features_data:
                self.features_data["features"] = {
                    k: False for k in self.features_data.get("features", {}).keys()
                }
                
            # read-only 모드 플래그 설정
            if self.features_data:
                self.features_data["read_only_mode"] = True
                self.features_data["read_only_reason"] = "signature_verification_failed"
                self.features_data["read_only_timestamp"] = time.time()
                
            return True
            
        except Exception as e:
            print(f"[SignedFeaturesValidator] Failed to enforce read-only mode: {e}")
            return False
            
    def get_validation_status(self) -> Dict:
        """
        검증 상태 조회
        
        Returns:
            검증 상태 정보
        """
        return {
            "is_valid": self.is_valid,
            "features_file": str(self.features_file),
            "public_key_file": str(self.public_key_file),
            "public_key_loaded": self.public_key is not None,
            "features_loaded": self.features_data is not None,
            "timestamp": time.time()
        }
        
    def create_sample_features_file(self, output_path: str = None) -> bool:
        """
        샘플 기능 설정 파일 생성 (테스트용)
        
        Args:
            output_path: 출력 파일 경로
            
        Returns:
            생성 성공 여부
        """
        try:
            if output_path is None:
                output_path = "config/features_sample.json"
                
            sample_features = {
                "features": {
                    "enable_auto_merge": True,
                    "enable_quarantine": True,
                    "enable_signatures": True,
                    "enable_adaptive_thresholds": True,
                    "enable_selective_restore": True,
                    "enable_wal_mode": True,
                    "enable_idempotency": True
                },
                "metadata": {
                    "version": "1.0.0",
                    "created_at": time.time(),
                    "description": "Sample features configuration"
                },
                "signature": "sample_signature_hex"  # 실제로는 서명이어야 함
            }
            
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path_obj, 'w', encoding='utf-8') as f:
                json.dump(sample_features, f, indent=2, ensure_ascii=False)
                
            print(f"[SignedFeaturesValidator] Sample features file created: {output_path}")
            return True
            
        except Exception as e:
            print(f"[SignedFeaturesValidator] Failed to create sample features file: {e}")
            return False


if __name__ == "__main__":
    # 테스트 실행
    validator = SignedFeaturesValidator()
    
    # 샘플 파일 생성
    validator.create_sample_features_file()
    
    # 검증 상태 출력
    status = validator.get_validation_status()
    print(f"Validation status: {status}")

