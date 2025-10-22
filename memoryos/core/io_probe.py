"""
IoProbe - 파일 입출력 감시 및 Δ(delta) 추출

파일 시스템의 변경사항을 감지하고 delta 이벤트를 생성합니다.
Debounce/Batching을 포함합니다.
"""

import time
import hashlib
from typing import Dict, List, Optional, Callable
from pathlib import Path
# from collections import defaultdict  # Not used in current implementation
import threading
from dataclasses import dataclass


@dataclass
class DebounceConfig:
    """Debounce 설정"""
    debounce_delay: float = 0.1  # 100ms debounce per path
    batch_size: int = 10          # 최대 배치 크기
    max_wait_time: float = 1.0    # 최대 대기 시간 (초)


class IoProbe:
    """
    파일 입출력 감시 및 delta 추출 클래스
    
    주요 기능:
    - 파일 변경 감지 (write, delete, move)
    - delta 이벤트 생성
    - 파일 해시 계산
    - 변경사항 추적
    """
    
    def __init__(self, watch_paths: List[str], callback: Optional[Callable] = None, 
                 debounce_config: Optional[DebounceConfig] = None):
        """
        IoProbe 초기화
        
        Args:
            watch_paths: 감시할 경로 목록
            callback: 변경 감지 시 호출될 콜백 함수
            debounce_config: Debounce/Batching 설정
        """
        self.watch_paths = [Path(p) for p in watch_paths]
        self.callback = callback
        self.file_hashes = {}  # 파일 경로 -> 해시 매핑
        self.is_monitoring = False
        
        # Debounce/Batching 설정
        self.debounce_config = debounce_config or DebounceConfig()
        self.pending_changes: Dict[str, Dict] = {}  # path -> change_info
        self.batch_timers: Dict[str, threading.Timer] = {}  # path -> timer
        self.batch_lock = threading.Lock()
        self.batch_queue: List[Dict] = []  # 배치 처리 대기열
        
    def start_monitoring(self) -> None:
        """파일 시스템 모니터링 시작"""
        self.is_monitoring = True
        print(f"[IoProbe] Monitoring started for paths: {self.watch_paths}")
        
    def stop_monitoring(self) -> None:
        """파일 시스템 모니터링 중지"""
        self.is_monitoring = False
        print("[IoProbe] Monitoring stopped")
        
    def calculate_file_hash(self, file_path: Path) -> str:
        """
        파일의 SHA256 해시 계산
        
        Args:
            file_path: 해시를 계산할 파일 경로
            
        Returns:
            파일의 SHA256 해시값
        """
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                return hashlib.sha256(content).hexdigest()
        except (FileNotFoundError, PermissionError):
            return ""
            
    def detect_changes(self) -> List[Dict]:
        """
        현재 상태와 이전 상태를 비교하여 변경사항 감지
        
        Returns:
            감지된 delta 이벤트 목록
        """
        deltas = []
        current_time = time.time()
        
        for watch_path in self.watch_paths:
            if not watch_path.exists():
                continue
                
            if watch_path.is_file():
                # 단일 파일 감시
                current_hash = self.calculate_file_hash(watch_path)
                previous_hash = self.file_hashes.get(str(watch_path), "")
                
                if current_hash != previous_hash:
                    if previous_hash == "":
                        # 새 파일 생성
                        delta = {
                            "path": str(watch_path),
                            "op": "create",
                            "hash": current_hash,
                            "ts": current_time,
                            "producer_actual": "unknown"
                        }
                    else:
                        # 파일 수정
                        delta = {
                            "path": str(watch_path),
                            "op": "write",
                            "hash": current_hash,
                            "ts": current_time,
                            "producer_actual": "unknown"
                        }
                    deltas.append(delta)
                    
                self.file_hashes[str(watch_path)] = current_hash
                
            elif watch_path.is_dir():
                # 디렉토리 내 모든 파일 감시
                for file_path in watch_path.rglob("*"):
                    if file_path.is_file():
                        current_hash = self.calculate_file_hash(file_path)
                        previous_hash = self.file_hashes.get(str(file_path), "")
                        
                        if current_hash != previous_hash:
                            if previous_hash == "":
                                delta = {
                                    "path": str(file_path),
                                    "op": "create",
                                    "hash": current_hash,
                                    "ts": current_time,
                                    "producer_actual": "unknown"
                                }
                            else:
                                delta = {
                                    "path": str(file_path),
                                    "op": "write",
                                    "hash": current_hash,
                                    "ts": current_time,
                                    "producer_actual": "unknown"
                                }
                            deltas.append(delta)
                            
                        self.file_hashes[str(file_path)] = current_hash
                        
        return deltas
        
    def simulate_delta(self, path: str, operation: str = "write", producer: str = "module_A") -> Dict:
        """
        테스트용 delta 이벤트 시뮬레이션
        
        Args:
            path: 파일 경로
            operation: 작업 유형 (write, create, delete)
            producer: 변경을 발생시킨 모듈
            
        Returns:
            시뮬레이션된 delta 이벤트
        """
        file_path = Path(path)
        current_hash = self.calculate_file_hash(file_path) if file_path.exists() else ""
        
        delta = {
            "path": path,
            "op": operation,
            "hash": current_hash,
            "ts": time.time(),
            "producer_actual": producer
        }
        
        print(f"[IoProbe] Simulated delta: {delta}")
        return delta
    
    def _schedule_debounced_change(self, file_path: str, change_info: Dict) -> None:
        """
        Debounce된 변경사항 스케줄링
        
        Args:
            file_path: 파일 경로
            change_info: 변경 정보
        """
        with self.batch_lock:
            # 기존 타이머가 있으면 취소
            if file_path in self.batch_timers:
                self.batch_timers[file_path].cancel()
            
            # 변경사항 저장
            self.pending_changes[file_path] = change_info
            
            # 새 타이머 설정
            timer = threading.Timer(
                self.debounce_config.debounce_delay,
                self._process_debounced_change,
                args=(file_path,)
            )
            self.batch_timers[file_path] = timer
            timer.start()
    
    def _process_debounced_change(self, file_path: str) -> None:
        """
        Debounce된 변경사항 처리
        
        Args:
            file_path: 파일 경로
        """
        with self.batch_lock:
            if file_path in self.pending_changes:
                change_info = self.pending_changes.pop(file_path)
                
                # 배치 큐에 추가
                self.batch_queue.append({
                    "file_path": file_path,
                    "change_info": change_info,
                    "timestamp": time.time()
                })
                
                # 배치 크기나 시간 조건 확인
                if (len(self.batch_queue) >= self.debounce_config.batch_size or
                    self._should_flush_batch()):
                    self._flush_batch()
                
                # 타이머 정리
                if file_path in self.batch_timers:
                    del self.batch_timers[file_path]
    
    def _should_flush_batch(self) -> bool:
        """
        배치 플러시 조건 확인
        
        Returns:
            배치를 플러시해야 하는지 여부
        """
        if not self.batch_queue:
            return False
        
        oldest_timestamp = min(item["timestamp"] for item in self.batch_queue)
        return time.time() - oldest_timestamp >= self.debounce_config.max_wait_time
    
    def _flush_batch(self) -> None:
        """
        배치 큐 플러시 및 콜백 호출
        """
        if not self.batch_queue:
            return
        
        batch_items = self.batch_queue.copy()
        self.batch_queue.clear()
        
        print(f"[IoProbe] Flushing batch of {len(batch_items)} changes")
        
        # 배치 처리된 변경사항들을 콜백으로 전달
        if self.callback:
            try:
                self.callback(batch_items)
            except Exception as e:
                print(f"[IoProbe] Error in batch callback: {e}")
    
    def force_flush_batch(self) -> None:
        """
        강제로 배치 플러시
        """
        with self.batch_lock:
            # 모든 대기 중인 타이머 취소
            for timer in self.batch_timers.values():
                timer.cancel()
            self.batch_timers.clear()
            
            # 대기 중인 변경사항들을 즉시 처리
            for file_path, change_info in self.pending_changes.items():
                self.batch_queue.append({
                    "file_path": file_path,
                    "change_info": change_info,
                    "timestamp": time.time()
                })
            self.pending_changes.clear()
            
            # 배치 플러시
            self._flush_batch()
    
    def get_batch_status(self) -> Dict:
        """
        배치 상태 정보 반환
        
        Returns:
            배치 상태 정보
        """
        with self.batch_lock:
            return {
                "pending_changes": len(self.pending_changes),
                "batch_queue_size": len(self.batch_queue),
                "active_timers": len(self.batch_timers),
                "debounce_config": {
                    "debounce_delay": self.debounce_config.debounce_delay,
                    "batch_size": self.debounce_config.batch_size,
                    "max_wait_time": self.debounce_config.max_wait_time
                }
            }
