# MemoryOS - Operational Memory Layer SDK

MemoryOS는 AI·LLM 시스템이 문맥(Context)을 지속·복원(Self-Healing)할 수 있도록 하는 운영 메모리 계층(Operational Memory Layer)을 구현하는 SDK입니다.

## 🎯 프로젝트 목적

MemoryOS는 특허 「운영 메모리 계층 기반의 문맥 지속 및 자동 복원 시스템」 (출원 중)을 기반으로 만들어진 SDK로, 다음과 같은 목표를 가집니다:

- **문맥 지속**: AI 시스템의 문맥을 영구적으로 보존
- **자동 복원**: Drift 감지 시 자동으로 이전 상태로 복원
- **무결성 검증**: Hash Chain과 Merkle Tree를 통한 데이터 무결성 보장
- **실시간 모니터링**: 시스템 상태를 실시간으로 추적 및 알림

## 🏗️ 아키텍처

```
memoryos/
├─ core/                    # 핵심 컴포넌트
│  ├─ io_probe.py          # 파일 입출력 감시 및 Δ(delta) 추출
│  ├─ data_catalog.py      # producer_expected / consumer_expected 관리
│  ├─ memory_sync.py       # delta + catalog 병합 → Temporal Hash Chain
│  ├─ hashchain.py         # Hash + Merkle 기반 무결성 검증
│  ├─ snapshot_generator.py # 구조화 스냅샷(JSON) 출력
│  └─ context_runtime.py   # 전체 파이프라인 조정 (entrypoint)
│
├─ guard/                   # 보호 및 복원 컴포넌트
│  ├─ drift_guard.py       # producer_actual vs expected 비교, L1~L3 결정
│  ├─ self_heal.py         # 복원·검증·격리 루틴
│  └─ policy.py            # 복구정책 레벨 및 임계값 관리
│
├─ store/                   # 저장소 컴포넌트
│  ├─ memory_index_store.py # memory_index 저장소(SQLite/File)
│  └─ log_store.py         # append-only event log
│
├─ observe/                 # 관찰 및 모니터링 컴포넌트
│  ├─ metrics.py           # 평균 Δt, drift율 등 계산
│  └─ event_log.py         # 불변 로그 기록기 (서명 옵션)
│
├─ examples/                # 사용 예제
│  ├─ demo_io_probe.py     # delta 감지 예제
│  └─ demo_self_heal.py    # drift → self-heal 시뮬레이션
│
├─ config/                  # 설정 파일
│  └─ default.toml         # 기본 설정
│
└─ README.md
```

## 🔄 실행 흐름

주요 실행 흐름은 다음과 같습니다:

```
io_probe → data_catalog → memory_sync → drift_guard → self_heal → snapshot_generator
```

### 1. IoProbe
- 파일 이벤트 감지 → Δ(delta) 생성
- 예: `{"path": "data/config.json", "op": "write", "hash": "abc123", "ts": 1729}`

### 2. DataCatalog
- producer_expected / consumer_expected 정보 유지
- 예: `{"path": "data/config.json", "producer_expected": "module_X", "interval": 30}`

### 3. MemorySync
- delta + catalog 병합 → memory_index 갱신
- Temporal Hash Chain(prev_hash, curr_hash, ts) 생성
- 충돌 시 정책(policy_id)에 따라 병합

### 4. DriftGuard
- expected vs actual 비교 → drift / staleness 판단
- Δt 기준으로 L1~L3 정책 등급 결정

### 5. SelfHeal
- **L1**: 로그 기록만
- **L2**: 자동 병합
- **L3**: 복원(prev_hash) + 쓰기 차단 + 격리 모드 진입

### 6. SnapshotGenerator
- AI-friendly JSON Schema로 현재 상태 export
- 필수 필드: `{state_summary, recent_deltas, provenance}`

## 🚀 빠른 시작

### 1. 기본 실행

```bash
# 기본 시뮬레이션 실행
python run_memoryos.py

# 데모 모드 실행
python run_memoryos.py --mode demo

# 모니터링 모드 실행
python run_memoryos.py --mode monitor --verbose

# 읽기 전용 모드 실행
python run_memoryos.py --readonly

# 리플레이 모드 실행
python run_memoryos.py --mode replay --input events.jsonl

# 사용자 정의 설정 파일 사용
python run_memoryos.py --config my_config.toml

# 드라이 런 (실제 실행 없이 테스트)
python run_memoryos.py --dry-run --mode simulate

# 타임아웃과 최대 이벤트 수 설정
python run_memoryos.py --mode monitor --timeout 60 --max-events 100

# 버전 정보 확인
python run_memoryos.py --version
```

### 2. 프로그래밍 방식 사용

```python
from memoryos.core.context_runtime import ContextRuntime

# ContextRuntime 초기화
ctx = ContextRuntime(config_path="memoryos/config/default.toml")

# Step 1: 감시된 변경 이벤트 시뮬레이션
delta = {"path":"data/example.txt","op":"write","ts":1730,"producer_actual":"module_A"}
ctx.handle_delta(delta)

# Step 2: drift 감지 및 복원 수행
ctx.check_drift_and_heal(delta)

# Step 3: 스냅샷 출력
ctx.export_snapshot()
```

### 3. 예제 실행

```bash
# IoProbe 데모
python -m memoryos.examples.demo_io_probe

# SelfHeal 데모
python -m memoryos.examples.demo_self_heal

# A/B 테스트 실행 (정책 비교)
python -m memoryos.examples.ab_runner
```

## 📊 실행 결과 예시

```
[Δ] Detected change in data/example.txt
[SYNC] Updated memory_index (ver_07 -> ver_08)
[DRIFT] Level=L2 detected, merge attempted
[SELF-HEAL] success=True, quarantine=False
[SNAPSHOT] exported: snapshots/snap_20251022.json
```

## ⚙️ 설정

설정 파일 (`memoryos/config/default.toml`)에서 다음 항목들을 조정할 수 있습니다:

- **drift_thresholds**: L1~L3 레벨별 임계값
- **paths**: 감시할 경로 및 저장소 위치
- **policy**: 복구 정책 및 시도 횟수
- **signing**: Ed25519 서명 활성화 여부
- **storage**: SQLite 또는 JSON 저장소 선택

## 🔧 주요 기능

### 고급 Drift 감지 및 복원
- **L1 Drift**: 경미한 drift - 로그 기록만
- **L2 Drift**: 중간 drift - 자동 병합 시도
- **L3 Drift**: 심각한 drift - 복원 + 격리 모드
- **Self-Adaptive Thresholds**: EMA + Percentile 하이브리드 임계값 계산
- **Producer Trust Scoring**: 실행 파일 해시, 서명, 경로 기반 신뢰도 점수

### 무결성 검증 및 보안
- **Temporal Hash Chain**: 시간순 해시 체인으로 무결성 보장
- **Merkle Tree**: 효율적인 무결성 검증 및 부분 검증 지원
- **Ed25519 서명**: 로그 무결성 보장 및 설정 파일 서명 검증
- **Atomic Transactions**: SQLite 트랜잭션을 통한 원자성 보장

### 고급 복원 및 격리
- **Selective Restore**: 영향받은 경로만 선별 복원
- **Quarantine Scope Minimization**: 최소 범위 격리로 성능 최적화
- **Automatic/Manual Release**: 자동 및 수동 격리 해제 조건
- **Idempotency Guarantee**: 중복 처리 방지 메커니즘

### 성능 및 안정성
- **SQLite WAL Mode**: Write-Ahead Logging으로 성능 향상
- **Retry + Circuit Breaker**: 지수 백오프 및 서킷 브레이커 패턴
- **File Monitoring Debounce**: 100ms 디바운스로 배치 처리
- **Standard Metrics**: Hit rate, latency, error rate, drift levels 수집

### 관찰 및 모니터링
- **Event Correlation ID**: 자동 생성된 run_id와 correlation_id 추적
- **1-minute Rollup**: 메트릭 데이터의 1분 롤업 JSONL 저장
- **Configuration Signature Verification**: 설정 파일 무결성 검증
- **JSON Schema Validation**: 스냅샷 데이터의 엄격한 검증

## 📝 로깅 정책

모든 이벤트는 append-only 구조로 `logs/event_log.jsonl`에 기록됩니다:

- 복원, 병합, 격리 이벤트는 JSON 한 줄당 1건 기록
- 무결성 검증은 SHA256 서명 또는 Ed25519 서명 옵션으로 확장 가능
- 로그 로테이션 및 압축 지원

## 🛡️ 구현 규칙

- **Overwrite 금지**: 모든 업데이트는 Upsert + prev_hash 방식
- **데이터 구조**: JSON 중심 (DB 필요 시 SQLite 사용)
- **실패 시 처리**: read-only fallback 자동 전환
- **서킷브레이커**: 재시도 정책은 추후 추가 예정

## 📚 API 문서

### ContextRuntime
메인 런타임 클래스로 전체 파이프라인을 조정합니다.

```python
ctx = ContextRuntime(config_path="config/default.toml")
ctx.handle_delta(delta)                    # Delta 이벤트 처리
ctx.check_drift_and_heal(delta)            # Drift 감지 및 복원
ctx.export_snapshot()                       # 스냅샷 생성
ctx.start_monitoring()                     # 모니터링 시작
ctx.stop_monitoring()                      # 모니터링 중지
```

### IoProbe
파일 시스템 변경사항을 감지하고 delta 이벤트를 생성합니다.

```python
probe = IoProbe(watch_paths=["data/"])
probe.start_monitoring()                    # 모니터링 시작
deltas = probe.detect_changes()             # 변경사항 감지
delta = probe.simulate_delta("file.txt")    # Delta 시뮬레이션
```

### DriftGuard
Drift를 감지하고 레벨을 결정합니다.

```python
guard = DriftGuard()
result = guard.check_drift(file_path, producer_actual, producer_expected, last_updated)
stats = guard.get_drift_statistics()        # Drift 통계 조회
```

### SelfHeal
Drift가 감지되었을 때 자동으로 복원을 수행합니다.

```python
heal = SelfHeal()
result = heal.execute_heal(drift_result)   # 복원 실행
stats = heal.get_heal_statistics()         # 복원 통계 조회
```

### RetryBreaker
재시도 및 서킷 브레이커 패턴을 구현합니다.

```python
from memoryos.api.retry_breaker import RetryBreaker

breaker = RetryBreaker()
result = breaker.execute(lambda: risky_operation())  # 재시도 실행
status = breaker.get_status()                        # 상태 조회
```

### StandardMetricsCollector
표준 메트릭을 수집하고 롤업합니다.

```python
from memoryos.observe.metrics import StandardMetricsCollector

metrics = StandardMetricsCollector()
metrics.record_cache_hit()                           # 캐시 히트 기록
metrics.record_error()                               # 에러 기록
summary = metrics.get_metrics_summary()              # 메트릭 요약
```

### A/B Runner
정책 비교를 위한 A/B 테스트 프레임워크입니다.

```python
from memoryos.examples.ab_runner import ABRunner, ABTestConfig

config = ABTestConfig(test_name="Policy Comparison", iterations=10)
runner = ABRunner(config)
results = runner.run_ab_test()                       # A/B 테스트 실행
summary = runner.generate_summary_report()           # 요약 보고서 생성
```

## 📋 종료 코드

MemoryOS는 표준화된 종료 코드를 사용합니다:

- **0**: 성공
- **1**: 일반 오류
- **2**: 설정 오류
- **3**: 런타임 오류
- **4**: 권한 오류
- **5**: 검증 오류
- **6**: 모니터링 오류
- **7**: 시뮬레이션 오류
- **8**: 데모 오류

## 🔮 향후 계획

- **대시보드**: Streamlit 기반 웹 대시보드 (PoC 이후)
- **분산 지원**: 다중 노드 환경에서의 동기화
- **ML 기반 예측**: Drift 패턴 학습 및 예측
- **클라우드 연동**: AWS/Azure/GCP 연동 지원

## 📄 라이선스

이 프로젝트는 특허 출원 중인 기술을 기반으로 하며, 상업적 사용 시 별도 라이선스가 필요할 수 있습니다.

## 🤝 기여

현재는 개발 초기 단계로 외부 기여는 제한적입니다. 버그 리포트나 기능 제안은 이슈로 등록해 주세요.

## 📞 지원

기술적 문의나 지원이 필요한 경우, 프로젝트 이슈를 통해 연락해 주세요.

---

**MemoryOS** - Operational Memory Layer for AI Systems
