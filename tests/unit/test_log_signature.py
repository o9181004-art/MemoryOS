"""
Unit Test: Append-only Log + Ed25519 Signature

EventLog의 Ed25519 서명 기능을 테스트합니다.
각 이벤트 레코드의 서명 생성 및 검증을 검증합니다.
"""

import pytest
import json
import time
from pathlib import Path
from memoryos.observe.event_log import EventLog


@pytest.fixture
def event_log_with_keys(tmp_path):
    """테스트용 EventLog with Ed25519 keys"""
    log_file = tmp_path / "test_event.log"
    private_key_file = tmp_path / "private_key.pem"
    public_key_file = tmp_path / "public_key.pem"
    
    # EventLog 초기화 시 키 생성 및 저장
    el = EventLog(str(log_file), enable_signing=True, private_key_file=str(private_key_file))
    
    # 공개키 파일도 생성되었는지 확인
    assert public_key_file.exists()
    
    yield el
    
    # Clean up
    if log_file.exists():
        log_file.unlink()
    if private_key_file.exists():
        private_key_file.unlink()
    if public_key_file.exists():
        public_key_file.unlink()


@pytest.fixture
def event_log_without_signing(tmp_path):
    """테스트용 EventLog without signing"""
    log_file = tmp_path / "test_event_no_sig.log"
    el = EventLog(str(log_file), enable_signing=False)
    
    yield el
    
    # Clean up
    if log_file.exists():
        log_file.unlink()


def test_sign_and_verify_line_success(event_log_with_keys):
    """Ed25519 서명 및 검증 성공 테스트"""
    el = event_log_with_keys
    
    event_data = {"message": "test event", "level": "INFO"}
    line_bytes = json.dumps(event_data, ensure_ascii=False).encode('utf-8')
    
    signature = el.sign_line_ed25519(line_bytes)
    assert signature != b""
    
    # 동일한 공개키로 검증
    assert el.verify_line_ed25519(line_bytes, signature, el.public_key)


def test_verify_line_tampered_data(event_log_with_keys):
    """데이터 위변조 시 서명 검증 실패 테스트"""
    el = event_log_with_keys
    
    original_event_data = {"message": "original event", "level": "INFO"}
    original_line_bytes = json.dumps(original_event_data, ensure_ascii=False).encode('utf-8')
    signature = el.sign_line_ed25519(original_line_bytes)
    
    tampered_event_data = {"message": "tampered event", "level": "INFO"}
    tampered_line_bytes = json.dumps(tampered_event_data, ensure_ascii=False).encode('utf-8')
    
    assert not el.verify_line_ed25519(tampered_line_bytes, signature, el.public_key)


def test_verify_line_tampered_signature(event_log_with_keys):
    """서명 위변조 시 서명 검증 실패 테스트"""
    el = event_log_with_keys
    
    event_data = {"message": "test event", "level": "INFO"}
    line_bytes = json.dumps(event_data, ensure_ascii=False).encode('utf-8')
    
    original_signature = el.sign_line_ed25519(line_bytes)
    tampered_signature = b"a" * len(original_signature)  # 잘못된 서명
    
    assert not el.verify_line_ed25519(line_bytes, tampered_signature, el.public_key)


def test_log_event_with_signature(event_log_with_keys):
    """log_event 메서드가 서명을 포함하여 기록하는지 테스트"""
    el = event_log_with_keys
    el.enable_signing = True  # 서명 활성화
    
    event_type = "FILE_CHANGE"
    event_data = {"path": "/app/data.txt", "op": "write"}
    
    success = el.log_event(event_type, event_data)
    assert success
    
    # 로그 파일에서 마지막 라인 읽기
    with open(el.log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        last_line = lines[-1].strip()
    
    logged_entry = json.loads(last_line)
    assert "signature" in logged_entry
    assert logged_entry["event_type"] == event_type
    assert logged_entry["event_data"] == event_data
    
    # 기록된 서명 검증
    logged_signature = bytes.fromhex(logged_entry["signature"])
    # 서명된 데이터는 'signature' 필드를 제외한 나머지 부분
    temp_entry = logged_entry.copy()
    del temp_entry["signature"]
    signed_content_bytes = json.dumps(temp_entry, sort_keys=True, ensure_ascii=False).encode('utf-8')
    
    assert el.verify_line_ed25519(signed_content_bytes, logged_signature, el.public_key)


def test_log_event_without_signing(event_log_without_signing):
    """서명 비활성화 시 서명이 포함되지 않는지 테스트"""
    el = event_log_without_signing
    el.enable_signing = False  # 서명 비활성화
    
    event_type = "SYSTEM_START"
    event_data = {"status": "online"}
    
    success = el.log_event(event_type, event_data)
    assert success
    
    with open(el.log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        last_line = lines[-1].strip()
    
    logged_entry = json.loads(last_line)
    assert "signature" not in logged_entry


def test_log_integrity_verification(event_log_with_keys):
    """로그 무결성 검증 테스트"""
    el = event_log_with_keys
    
    # 여러 이벤트 로그
    events = [
        ("FILE_CHANGE", {"path": "/app/file1.txt", "op": "write"}),
        ("SYSTEM_START", {"status": "online"}),
        ("DRIFT_DETECTED", {"level": "L2", "file": "/app/config.json"})
    ]
    
    for event_type, event_data in events:
        el.log_event(event_type, event_data)
    
    # 무결성 검증
    is_valid, errors = el.verify_log_integrity()
    assert is_valid
    assert len(errors) == 0


def test_log_integrity_tampering_detection(event_log_with_keys):
    """로그 위변조 감지 테스트"""
    el = event_log_with_keys
    
    # 이벤트 로그
    el.log_event("FILE_CHANGE", {"path": "/app/file1.txt", "op": "write"})
    
    # 로그 파일 직접 수정 (위변조 시뮬레이션)
    with open(el.log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 첫 번째 라인 수정
    tampered_entry = json.loads(lines[0].strip())
    tampered_entry["event_data"]["path"] = "/app/tampered.txt"
    
    # 수정된 내용으로 파일 덮어쓰기
    with open(el.log_file, 'w', encoding='utf-8') as f:
        f.write(json.dumps(tampered_entry, ensure_ascii=False) + "\n")
    
    # 무결성 검증 (실패해야 함)
    is_valid, errors = el.verify_log_integrity()
    assert not is_valid
    assert len(errors) > 0
    # 서명 검증 실패를 확인 (데이터가 변조되었으므로 서명이 맞지 않음)
    assert any("Signature verification failed" in str(error) for error in errors)


def test_external_log_verification(event_log_with_keys):
    """외부 로그 검증 테스트"""
    el = event_log_with_keys
    
    # 이벤트 로그
    el.log_event("EXTERNAL_EVENT", {"source": "external_system", "data": "test"})
    
    # 공개키 PEM 형식으로 가져오기
    public_key_pem = el.get_public_key_pem()
    assert public_key_pem != ""
    
    # 로그 엔트리 가져오기
    log_entries = el.get_log_entries("EXTERNAL_EVENT")
    assert len(log_entries) == 1
    
    log_entry = log_entries[0]
    
    # 외부 검증
    is_valid = el.verify_external_log(log_entry, public_key_pem)
    assert is_valid


def test_external_log_verification_failure(event_log_with_keys):
    """외부 로그 검증 실패 테스트"""
    el = event_log_with_keys
    
    # 이벤트 로그
    el.log_event("EXTERNAL_EVENT", {"source": "external_system", "data": "test"})
    
    # 로그 엔트리 가져오기
    log_entries = el.get_log_entries("EXTERNAL_EVENT")
    log_entry = log_entries[0]
    
    # 서명 제거 (위변조 시뮬레이션)
    log_entry["signature"] = ""
    
    # 외부 검증 (실패해야 함)
    is_valid = el.verify_external_log(log_entry, el.get_public_key_pem())
    assert not is_valid


def test_log_chain_continuity(event_log_with_keys):
    """로그 체인 연속성 테스트"""
    el = event_log_with_keys
    
    # 여러 이벤트 로그
    events = [
        ("EVENT_1", {"data": "first"}),
        ("EVENT_2", {"data": "second"}),
        ("EVENT_3", {"data": "third"})
    ]
    
    for event_type, event_data in events:
        el.log_event(event_type, event_data)
    
    # 체인 연속성 확인
    assert len(el.log_chain) == 3
    
    # 이전 해시 연결 확인
    for i in range(1, len(el.log_chain)):
        current_entry = el.log_chain[i]
        previous_entry = el.log_chain[i-1]
        assert current_entry["prev_hash"] == previous_entry["hash"]


def test_log_statistics_with_signing(event_log_with_keys):
    """서명 활성화 상태에서의 로그 통계 테스트"""
    el = event_log_with_keys
    
    # 이벤트 로그
    el.log_event("EVENT_1", {"data": "test1"})
    el.log_event("EVENT_2", {"data": "test2"})
    el.log_event("EVENT_1", {"data": "test3"})
    
    # 통계 확인
    stats = el.get_log_statistics()
    
    assert stats["total_events"] == 3
    assert stats["signing_enabled"] is True
    assert stats["chain_length"] == 3
    assert stats["last_log_hash"] is not None
    assert stats["event_type_counts"]["EVENT_1"] == 2
    assert stats["event_type_counts"]["EVENT_2"] == 1


def test_log_statistics_without_signing(event_log_without_signing):
    """서명 비활성화 상태에서의 로그 통계 테스트"""
    el = event_log_without_signing
    
    # 이벤트 로그
    el.log_event("EVENT_1", {"data": "test1"})
    el.log_event("EVENT_2", {"data": "test2"})
    
    # 통계 확인
    stats = el.get_log_statistics()
    
    assert stats["total_events"] == 2
    assert stats["signing_enabled"] is False
    assert stats["chain_length"] == 2
    assert stats["last_log_hash"] is not None


def test_log_export_with_signing(event_log_with_keys, tmp_path):
    """서명이 포함된 로그 내보내기 테스트"""
    el = event_log_with_keys
    
    # 이벤트 로그
    el.log_event("EXPORT_TEST", {"data": "export_me"})
    
    # 로그 내보내기
    export_file = tmp_path / "exported_logs.json"
    success = el.export_logs(str(export_file), event_type="EXPORT_TEST")
    
    assert success
    assert export_file.exists()
    
    # 내보내기된 로그 확인
    with open(export_file, 'r', encoding='utf-8') as f:
        exported_data = json.load(f)
    
    assert exported_data["total_logs"] == 1
    assert exported_data["filters"]["event_type"] == "EXPORT_TEST"
    assert len(exported_data["logs"]) == 1
    
    log_entry = exported_data["logs"][0]
    assert log_entry["event_type"] == "EXPORT_TEST"
    assert "signature" in log_entry
    assert log_entry["signature"] != ""


def test_log_clear_with_signing(event_log_with_keys):
    """서명이 포함된 로그 초기화 테스트"""
    el = event_log_with_keys
    
    # 이벤트 로그
    el.log_event("CLEAR_TEST", {"data": "clear_me"})
    
    # 로그 초기화
    success = el.clear_logs()
    
    assert success
    assert len(el.log_chain) == 0
    assert el.last_log_hash is None
    assert not el.log_file.exists()


if __name__ == "__main__":
    pytest.main([__file__])