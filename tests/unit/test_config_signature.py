import pytest
import json
import time
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from memoryos.core.config_signature import ConfigSignatureVerifier
from memoryos.core.context_runtime import ContextRuntime

@pytest.fixture
def config_dir_with_keys(tmp_path):
    """Ed25519 키가 있는 설정 디렉토리 생성"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    # Ed25519 키 쌍 생성
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # 키 파일 저장
    private_key_file = config_dir / "private_key.pem"
    public_key_file = config_dir / "public_key.pem"
    
    with open(private_key_file, 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    with open(public_key_file, 'wb') as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    
    return config_dir, private_key, public_key

@pytest.fixture
def config_verifier(config_dir_with_keys):
    """ConfigSignatureVerifier 인스턴스 생성"""
    config_dir, _, _ = config_dir_with_keys
    return ConfigSignatureVerifier(str(config_dir))

def test_config_verifier_initialization(config_dir_with_keys):
    """ConfigSignatureVerifier 초기화 테스트"""
    config_dir, _, _ = config_dir_with_keys
    verifier = ConfigSignatureVerifier(str(config_dir))
    
    assert verifier.config_dir == config_dir
    assert verifier.features_file == config_dir / "features.json"
    assert verifier.public_key is not None
    assert verifier.private_key is not None

def test_create_default_features(config_verifier):
    """기본 Features 생성 및 서명 테스트"""
    verifier = config_verifier
    
    # features.json 파일이 없으면 기본 생성
    if not verifier.features_file.exists():
        verifier._create_default_features()
    
    assert verifier.features_file.exists()
    
    with open(verifier.features_file, 'r', encoding='utf-8') as f:
        features_data = json.load(f)
    
    assert "schema_version" in features_data
    assert "features" in features_data
    assert "signature" in features_data
    assert "timestamp" in features_data
    
    # 서명 검증
    assert verifier._verify_features_signature(features_data)

def test_verify_features_signature_success(config_verifier):
    """Features 서명 검증 성공 테스트"""
    verifier = config_verifier
    
    # 유효한 Features 데이터 생성
    features_data = {
        "schema_version": "1.0.0",
        "features": {
            "enable_drift_detection": True,
            "enable_self_healing": False
        },
        "timestamp": time.time()
    }
    
    # 서명 추가
    signature = verifier._sign_features_data(features_data)
    features_data["signature"] = signature
    
    # 서명 검증
    assert verifier._verify_features_signature(features_data)

def test_verify_features_signature_failure(config_verifier):
    """Features 서명 검증 실패 테스트"""
    verifier = config_verifier
    
    # 유효한 Features 데이터 생성
    features_data = {
        "schema_version": "1.0.0",
        "features": {
            "enable_drift_detection": True,
            "enable_self_healing": False
        },
        "timestamp": time.time()
    }
    
    # 서명 추가
    signature = verifier._sign_features_data(features_data)
    features_data["signature"] = signature
    
    # 데이터 변조
    features_data["features"]["enable_drift_detection"] = False
    
    # 서명 검증 실패
    assert not verifier._verify_features_signature(features_data)

def test_verify_features_signature_tampered_signature(config_verifier):
    """서명 위변조 시 검증 실패 테스트"""
    verifier = config_verifier
    
    # 유효한 Features 데이터 생성
    features_data = {
        "schema_version": "1.0.0",
        "features": {
            "enable_drift_detection": True,
            "enable_self_healing": False
        },
        "timestamp": time.time()
    }
    
    # 서명 추가
    signature = verifier._sign_features_data(features_data)
    features_data["signature"] = signature
    
    # 서명 위변조
    features_data["signature"] = "a" * len(signature)
    
    # 서명 검증 실패
    assert not verifier._verify_features_signature(features_data)

def test_fallback_to_read_only_mode(config_verifier):
    """서명 검증 실패 시 read-only 모드 전환 테스트"""
    verifier = config_verifier
    
    # 잘못된 Features 데이터 생성
    invalid_features = {
        "schema_version": "1.0.0",
        "features": {
            "enable_drift_detection": True,
            "enable_self_healing": True
        },
        "signature": "invalid_signature",
        "timestamp": time.time()
    }
    
    # 파일에 저장
    with open(verifier.features_file, 'w', encoding='utf-8') as f:
        json.dump(invalid_features, f, indent=2, ensure_ascii=False)
    
    # 다시 로드하여 검증 실패 시뮬레이션
    verifier._load_and_verify_features()
    
    assert verifier.read_only_mode
    assert not verifier.signature_valid
    assert not verifier.features.get("enable_self_healing", False)  # 보안상 비활성화

def test_is_feature_enabled(config_verifier):
    """Feature Flag 상태 확인 테스트"""
    verifier = config_verifier
    
    # 기본 Features 생성
    verifier._create_default_features()
    
    # 활성화된 Feature 확인
    assert verifier.is_feature_enabled("enable_drift_detection")
    assert verifier.is_feature_enabled("enable_backup")
    
    # 비활성화된 Feature 확인
    assert not verifier.is_feature_enabled("enable_self_healing")

def test_is_feature_enabled_read_only_mode(config_verifier):
    """read-only 모드에서 Feature Flag 확인 테스트"""
    verifier = config_verifier
    
    # read-only 모드로 전환
    verifier._fallback_to_read_only()
    
    # 안전한 Feature만 허용
    assert verifier.is_feature_enabled("enable_drift_detection")
    assert verifier.is_feature_enabled("enable_backup")
    assert verifier.is_feature_enabled("enable_metrics")
    
    # 위험한 Feature는 비활성화
    assert not verifier.is_feature_enabled("enable_self_healing")
    assert not verifier.is_feature_enabled("enable_quarantine")
    assert not verifier.is_feature_enabled("enable_snapshot_export")

def test_update_feature_success(config_verifier):
    """Feature Flag 업데이트 성공 테스트"""
    verifier = config_verifier
    
    # 기본 Features 생성
    verifier._create_default_features()
    
    # Feature 업데이트
    success = verifier.update_feature("enable_self_healing", True)
    assert success
    
    # 업데이트 확인
    assert verifier.is_feature_enabled("enable_self_healing")
    
    # 파일에서도 확인
    with open(verifier.features_file, 'r', encoding='utf-8') as f:
        features_data = json.load(f)
    
    assert features_data["features"]["enable_self_healing"] == True
    assert "signature" in features_data

def test_update_feature_read_only_mode(config_verifier):
    """read-only 모드에서 Feature Flag 업데이트 실패 테스트"""
    verifier = config_verifier
    
    # read-only 모드로 전환
    verifier._fallback_to_read_only()
    
    # Feature 업데이트 시도
    success = verifier.update_feature("enable_self_healing", True)
    assert not success

def test_update_feature_no_private_key(config_verifier):
    """개인키 없이 Feature Flag 업데이트 실패 테스트"""
    verifier = config_verifier
    
    # 개인키 제거
    verifier.private_key = None
    
    # Feature 업데이트 시도
    success = verifier.update_feature("enable_self_healing", True)
    assert not success

def test_regenerate_signature(config_verifier):
    """Features 파일 서명 재생성 테스트"""
    verifier = config_verifier
    
    # 기본 Features 생성
    verifier._create_default_features()
    
    # 서명 재생성
    success = verifier.regenerate_signature()
    assert success
    
    # 서명 유효성 확인
    with open(verifier.features_file, 'r', encoding='utf-8') as f:
        features_data = json.load(f)
    
    assert verifier._verify_features_signature(features_data)

def test_context_runtime_integration(config_dir_with_keys):
    """ContextRuntime과의 통합 테스트"""
    config_dir, _, _ = config_dir_with_keys
    
    # config 파일 생성
    config_file = config_dir / "default.toml"
    config_file.write_text("""
[system]
version = "1.0"

[paths]
watch_paths = ["data/"]
catalog_file = "data/catalog.json"
memory_index_file = "data/memory_index.json"
snapshot_dir = "snapshots"
""")
    
    # ContextRuntime 초기화
    runtime = ContextRuntime(str(config_file))
    
    # Configuration Signature Verification 확인
    assert hasattr(runtime, 'config_verifier')
    assert runtime.config_verifier is not None
    
    # Feature Flag 확인
    assert runtime.is_feature_enabled("enable_drift_detection")
    
    # Configuration 상태 확인
    status = runtime.get_configuration_status()
    assert "signature_valid" in status
    assert "read_only_mode" in status
    assert "features" in status

def test_context_runtime_feature_flag_integration(config_dir_with_keys):
    """ContextRuntime의 Feature Flag 통합 테스트"""
    config_dir, _, _ = config_dir_with_keys
    
    # config 파일 생성
    config_file = config_dir / "default.toml"
    config_file.write_text("""
[system]
version = "1.0"

[paths]
watch_paths = ["data/"]
catalog_file = "data/catalog.json"
memory_index_file = "data/memory_index.json"
snapshot_dir = "snapshots"
""")
    
    # ContextRuntime 초기화
    runtime = ContextRuntime(str(config_file))
    
    # Feature Flag 업데이트
    success = runtime.update_feature_flag("enable_drift_detection", False)
    assert success
    
    # Delta 처리 시 Feature Flag 검사
    delta = {
        "path": "data/test.txt",
        "operation": "write",
        "producer_actual": "test_module",
        "ts": time.time(),
        "conversation_id": "test_conv",
        "turn_id": "test_turn"
    }
    
    result = runtime.handle_delta(delta)
    assert not result["success"]
    assert "Drift detection disabled by feature flag" in result["error"]
    assert result["read_only_mode"] == runtime.config_verifier.read_only_mode

