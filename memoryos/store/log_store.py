"""
LogStore - append-only event log

불변 이벤트 로그를 관리합니다.
"""

import json
import time
from typing import Dict, List, Optional, Iterator
from pathlib import Path


class LogStore:
    """
    Append-only 이벤트 로그 저장소 클래스
    
    주요 기능:
    - 불변 이벤트 로그 관리
    - JSONL 형식으로 저장
    - 로그 검색 및 필터링
    - 로그 무결성 검증
    """
    
    def __init__(self, log_file: str = "logs/event_log.jsonl", 
                 max_file_size: int = 100 * 1024 * 1024):  # 100MB
        """
        LogStore 초기화
        
        Args:
            log_file: 로그 파일 경로
            max_file_size: 최대 파일 크기 (바이트)
        """
        self.log_file = Path(log_file)
        self.max_file_size = max_file_size
        self.current_file_size = 0
        
        # 로그 디렉토리 생성
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 현재 파일 크기 확인
        if self.log_file.exists():
            self.current_file_size = self.log_file.stat().st_size
            
        # Idempotency 보장을 위한 처리된 이벤트 추적
        self.processed_events = set()  # (conversation_id, turn_id) 튜플 저장
        self.event_results = {}  # 이벤트 결과 캐시
            
    def append_log(self, event: Dict) -> bool:
        """
        이벤트 로그 추가 (Idempotency 보장)
        
        Args:
            event: 추가할 이벤트 데이터
            
        Returns:
            추가 성공 여부
        """
        try:
            # Idempotency 키 생성
            conversation_id = event.get("conversation_id", "default")
            turn_id = event.get("turn_id", event.get("ts", time.time()))
            idempotency_key = (conversation_id, turn_id)
            
            # 이미 처리된 이벤트인지 확인
            if idempotency_key in self.processed_events:
                print(f"[LogStore] Duplicate event detected: {idempotency_key}")
                return self.event_results.get(idempotency_key, False)
            
            # 이벤트에 메타데이터 추가
            enriched_event = self._enrich_event(event)
            
            # JSONL 형식으로 저장
            log_line = json.dumps(enriched_event, ensure_ascii=False) + "\n"
            
            # 파일 크기 확인 및 로테이션
            if self.current_file_size + len(log_line.encode('utf-8')) > self.max_file_size:
                self._rotate_log_file()
                
            # 로그 파일에 추가
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_line)
                
            # 파일 크기 업데이트
            self.current_file_size += len(log_line.encode('utf-8'))
            
            # 처리된 이벤트로 기록
            self.processed_events.add(idempotency_key)
            self.event_results[idempotency_key] = True
            
            return True
            
        except Exception as e:
            print(f"[LogStore] Failed to append log: {e}")
            return False
            
    def _enrich_event(self, event: Dict) -> Dict:
        """
        이벤트에 메타데이터 추가
        
        Args:
            event: 원본 이벤트
            
        Returns:
            메타데이터가 추가된 이벤트
        """
        enriched = event.copy()
        
        # 기본 메타데이터 추가
        enriched["log_timestamp"] = time.time()
        enriched["log_id"] = self._generate_log_id()
        
        # 이벤트 타입이 없으면 추론
        if "event_type" not in enriched:
            enriched["event_type"] = self._infer_event_type(event)
            
        return enriched
        
    def _generate_log_id(self) -> str:
        """로그 ID 생성"""
        import uuid
        return str(uuid.uuid4())
        
    def _infer_event_type(self, event: Dict) -> str:
        """이벤트 타입 추론"""
        if "delta" in event:
            return "delta"
        elif "drift" in event:
            return "drift"
        elif "heal" in event:
            return "heal"
        elif "snapshot" in event:
            return "snapshot"
        else:
            return "unknown"
            
    def _rotate_log_file(self) -> None:
        """로그 파일 로테이션"""
        timestamp = int(time.time())
        rotated_file = self.log_file.parent / f"{self.log_file.stem}_{timestamp}.jsonl"
        
        # 현재 파일을 로테이션된 파일로 이동
        if self.log_file.exists():
            self.log_file.rename(rotated_file)
            
        # 새 파일 생성
        self.log_file.touch()
        self.current_file_size = 0
        
        print(f"[LogStore] Log file rotated: {rotated_file}")
        
    def read_logs(self, start_time: Optional[float] = None, 
                 end_time: Optional[float] = None,
                 event_type: Optional[str] = None,
                 limit: Optional[int] = None) -> List[Dict]:
        """
        로그 조회
        
        Args:
            start_time: 시작 시간 (timestamp)
            end_time: 종료 시간 (timestamp)
            event_type: 이벤트 타입 필터
            limit: 조회할 로그 수 제한
            
        Returns:
            필터링된 로그 목록
        """
        logs = []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if limit and len(logs) >= limit:
                        break
                        
                    try:
                        log_entry = json.loads(line.strip())
                        
                        # 시간 필터
                        if start_time and log_entry.get("log_timestamp", 0) < start_time:
                            continue
                        if end_time and log_entry.get("log_timestamp", 0) > end_time:
                            continue
                            
                        # 이벤트 타입 필터
                        if event_type and log_entry.get("event_type") != event_type:
                            continue
                            
                        logs.append(log_entry)
                        
                    except json.JSONDecodeError:
                        continue
                        
        except FileNotFoundError:
            pass
            
        return logs
        
    def read_logs_iterator(self, start_time: Optional[float] = None,
                          end_time: Optional[float] = None,
                          event_type: Optional[str] = None) -> Iterator[Dict]:
        """
        로그 스트림 조회 (이터레이터)
        
        Args:
            start_time: 시작 시간 (timestamp)
            end_time: 종료 시간 (timestamp)
            event_type: 이벤트 타입 필터
            
        Yields:
            필터링된 로그 엔트리
        """
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line.strip())
                        
                        # 시간 필터
                        if start_time and log_entry.get("log_timestamp", 0) < start_time:
                            continue
                        if end_time and log_entry.get("log_timestamp", 0) > end_time:
                            continue
                            
                        # 이벤트 타입 필터
                        if event_type and log_entry.get("event_type") != event_type:
                            continue
                            
                        yield log_entry
                        
                    except json.JSONDecodeError:
                        continue
                        
        except FileNotFoundError:
            pass
            
    def get_log_statistics(self) -> Dict:
        """로그 통계 정보 조회"""
        try:
            total_lines = 0
            event_types = {}
            time_range = {"start": None, "end": None}
            
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    total_lines += 1
                    
                    try:
                        log_entry = json.loads(line.strip())
                        
                        # 이벤트 타입 통계
                        event_type = log_entry.get("event_type", "unknown")
                        event_types[event_type] = event_types.get(event_type, 0) + 1
                        
                        # 시간 범위
                        log_time = log_entry.get("log_timestamp", 0)
                        if time_range["start"] is None or log_time < time_range["start"]:
                            time_range["start"] = log_time
                        if time_range["end"] is None or log_time > time_range["end"]:
                            time_range["end"] = log_time
                            
                    except json.JSONDecodeError:
                        continue
                        
            return {
                "total_logs": total_lines,
                "file_size_bytes": self.current_file_size,
                "event_type_counts": event_types,
                "time_range": time_range,
                "log_file": str(self.log_file)
            }
            
        except FileNotFoundError:
            return {
                "total_logs": 0,
                "file_size_bytes": 0,
                "event_type_counts": {},
                "time_range": {"start": None, "end": None},
                "log_file": str(self.log_file)
            }
            
    def search_logs(self, query: str, fields: List[str] = None) -> List[Dict]:
        """
        로그 검색
        
        Args:
            query: 검색 쿼리
            fields: 검색할 필드 목록 (None이면 모든 필드)
            
        Returns:
            검색 결과 목록
        """
        results = []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line.strip())
                        
                        # 검색 필드 결정
                        search_fields = fields or list(log_entry.keys())
                        
                        # 쿼리 매칭 검사
                        if self._matches_query(log_entry, query, search_fields):
                            results.append(log_entry)
                            
                    except json.JSONDecodeError:
                        continue
                        
        except FileNotFoundError:
            pass
            
        return results
        
    def _matches_query(self, log_entry: Dict, query: str, fields: List[str]) -> bool:
        """
        쿼리 매칭 검사
        
        Args:
            log_entry: 로그 엔트리
            query: 검색 쿼리
            fields: 검색 필드 목록
            
        Returns:
            매칭 여부
        """
        query_lower = query.lower()
        
        for field in fields:
            if field in log_entry:
                value = str(log_entry[field]).lower()
                if query_lower in value:
                    return True
                    
        return False
        
    def export_logs(self, output_file: str, start_time: Optional[float] = None,
                   end_time: Optional[float] = None, event_type: Optional[str] = None) -> bool:
        """
        로그 내보내기
        
        Args:
            output_file: 출력 파일 경로
            start_time: 시작 시간 (timestamp)
            end_time: 종료 시간 (timestamp)
            event_type: 이벤트 타입 필터
            
        Returns:
            내보내기 성공 여부
        """
        try:
            logs = self.read_logs(start_time, end_time, event_type)
            
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
                
            print(f"[LogStore] Exported {len(logs)} logs to {output_file}")
            return True
            
        except Exception as e:
            print(f"[LogStore] Failed to export logs: {e}")
            return False
            
    def check_idempotency(self, conversation_id: str, turn_id: str) -> bool:
        """
        Idempotency 키 확인
        
        Args:
            conversation_id: 대화 ID
            turn_id: 턴 ID
            
        Returns:
            이미 처리된 이벤트인지 여부
        """
        idempotency_key = (conversation_id, turn_id)
        return idempotency_key in self.processed_events
        
    def get_event_result(self, conversation_id: str, turn_id: str) -> Dict:
        """
        이벤트 결과 조회
        
        Args:
            conversation_id: 대화 ID
            turn_id: 턴 ID
            
        Returns:
            이벤트 결과 또는 빈 딕셔너리
        """
        idempotency_key = (conversation_id, turn_id)
        if idempotency_key in self.event_results:
            return {
                "processed": True,
                "result": self.event_results[idempotency_key],
                "idempotency_key": idempotency_key
            }
        return {"processed": False}
        
    def clear_idempotency_cache(self) -> None:
        """Idempotency 캐시 초기화"""
        self.processed_events.clear()
        self.event_results.clear()
        print("[LogStore] Idempotency cache cleared")
        
    def get_idempotency_statistics(self) -> Dict:
        """Idempotency 통계 정보 조회"""
        return {
            "processed_events_count": len(self.processed_events),
            "cached_results_count": len(self.event_results),
            "cache_size_bytes": len(str(self.processed_events)) + len(str(self.event_results))
        }
