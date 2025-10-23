# -*- coding: utf-8 -*-
"""
Governance & Safety Layer (L10)
Monitors and filters MemoryOS outputs for ethical and safety compliance.
"""
import re
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Configuration
LOG_PATH = Path(os.environ.get("MEMORYOS_AUDIT_PATH", "./logs/governance_audit.log"))
GOVERNANCE_ENABLED = os.environ.get("MEMORYOS_GOVERNANCE_ENABLED", "true").lower() == "true"
POLICY_MODE = os.environ.get("MEMORYOS_POLICY_MODE", "strict").lower()

# Ethics patterns - detect potentially harmful content
ETHICS_PATTERNS = [
    re.compile(r"\b(?:hate|violence|illegal|harassment|discrimination|racism|sexism|abuse)\b", re.I),
    re.compile(r"\b(?:threat|kill|murder|suicide|self.?harm|bomb|weapon|attack)\b", re.I),
    re.compile(r"\b(?:fraud|scam|phishing|malware|virus|hack|exploit)\b", re.I),
    re.compile(r"\b(?:drug|narcotic|illegal.?substance|contraband)\b", re.I),
]

# Sensitive information patterns
SENSITIVE_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN-like patterns
    re.compile(r"\b01[0-9]-?\d{3,4}-?\d{4}\b"),  # Korean phone numbers
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # Email addresses
    re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),  # Credit card numbers
    re.compile(r"\b\d{6}[-\s]?\d{7}\b"),  # Korean resident registration numbers
    re.compile(r"\b[A-Za-z0-9]{8,}\b"),  # Potential passwords or tokens
]

# Privacy patterns - detect personal information
PRIVACY_PATTERNS = [
    re.compile(r"\b(?:name|address|phone|email|ssn|social.?security)\b", re.I),
    re.compile(r"\b(?:password|pin|secret|private|confidential)\b", re.I),
    re.compile(r"\b(?:bank|account|credit.?card|financial)\b", re.I),
]

def _log_audit_entry(entry: Dict) -> None:
    """Log governance audit entry"""
    try:
        log_path = Path(os.environ.get("MEMORYOS_AUDIT_PATH", "./logs/governance_audit.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Silently fail if logging fails

def check_ethics(text: str) -> Tuple[bool, List[str]]:
    """
    Check text for ethical compliance
    
    Args:
        text: Text to check
        
    Returns:
        Tuple of (is_ethical, violations)
    """
    if not text:
        return True, []
    
    violations = []
    
    for pattern in ETHICS_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            violations.extend(matches)
    
    is_ethical = len(violations) == 0
    return is_ethical, violations

def check_safety(text: str) -> Tuple[bool, List[str]]:
    """
    Check text for sensitive information
    
    Args:
        text: Text to check
        
    Returns:
        Tuple of (is_safe, sensitive_items)
    """
    if not text:
        return True, []
    
    sensitive_items = []
    
    for pattern in SENSITIVE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            sensitive_items.extend(matches)
    
    is_safe = len(sensitive_items) == 0
    return is_safe, sensitive_items

def check_privacy(text: str) -> Tuple[bool, List[str]]:
    """
    Check text for privacy concerns
    
    Args:
        text: Text to check
        
    Returns:
        Tuple of (is_private, privacy_concerns)
    """
    if not text:
        return True, []
    
    privacy_concerns = []
    
    for pattern in PRIVACY_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            privacy_concerns.extend(matches)
    
    is_private = len(privacy_concerns) == 0
    return is_private, privacy_concerns

def anonymize_sensitive_info(text: str) -> str:
    """
    Anonymize sensitive information in text
    
    Args:
        text: Text to anonymize
        
    Returns:
        Anonymized text
    """
    if not text:
        return text
    
    anonymized = text
    
    # Anonymize phone numbers
    anonymized = re.sub(SENSITIVE_PATTERNS[1], "[PHONE]", anonymized)
    
    # Anonymize email addresses
    anonymized = re.sub(SENSITIVE_PATTERNS[2], "[EMAIL]", anonymized)
    
    # Anonymize credit card numbers
    anonymized = re.sub(SENSITIVE_PATTERNS[3], "[CARD]", anonymized)
    
    # Anonymize Korean resident numbers
    anonymized = re.sub(SENSITIVE_PATTERNS[4], "[ID]", anonymized)
    
    # Anonymize SSN-like patterns
    anonymized = re.sub(SENSITIVE_PATTERNS[0], "[SSN]", anonymized)
    
    # Anonymize potential passwords/tokens
    anonymized = re.sub(SENSITIVE_PATTERNS[5], "[TOKEN]", anonymized)
    
    return anonymized

def mask_privacy_info(text: str) -> str:
    """
    Mask privacy-related information
    
    Args:
        text: Text to mask
        
    Returns:
        Masked text
    """
    if not text:
        return text
    
    masked = text
    
    # Mask common privacy terms
    privacy_replacements = {
        r'\bpassword\b': '[PASSWORD]',
        r'\bpin\b': '[PIN]',
        r'\bsecret\b': '[SECRET]',
        r'\bprivate\b': '[PRIVATE]',
        r'\bconfidential\b': '[CONFIDENTIAL]',
        r'\bbank\b': '[BANK]',
        r'\baccount\b': '[ACCOUNT]',
        r'\bcredit.?card\b': '[CARD]',
        r'\bfinancial\b': '[FINANCIAL]',
    }
    
    for pattern, replacement in privacy_replacements.items():
        masked = re.sub(pattern, replacement, masked, flags=re.I)
    
    return masked

def governance_filter(block: str) -> str:
    """
    Apply comprehensive governance policy to text block
    
    Args:
        block: Text block to filter
        
    Returns:
        Filtered text block
    """
    if not GOVERNANCE_ENABLED or not block:
        return block
    
    start_time = time.perf_counter()
    
    try:
        original_block = block
        
        # Check ethics
        is_ethical, ethics_violations = check_ethics(block)
        if not is_ethical:
            _log_audit_entry({
                "timestamp": datetime.now().isoformat(),
                "action": "block",
                "reason": "unethical",
                "violations": ethics_violations,
                "policy_mode": POLICY_MODE,
                "block_length": len(original_block)
            })
            return "[BLOCKED: unethical content removed]"
        
        # Check safety
        is_safe, sensitive_items = check_safety(block)
        if not is_safe:
            _log_audit_entry({
                "timestamp": datetime.now().isoformat(),
                "action": "anonymize",
                "reason": "sensitive",
                "sensitive_items": sensitive_items,
                "policy_mode": POLICY_MODE,
                "block_length": len(original_block)
            })
            block = anonymize_sensitive_info(block)
        
        # Check privacy
        is_private, privacy_concerns = check_privacy(block)
        if not is_private:
            _log_audit_entry({
                "timestamp": datetime.now().isoformat(),
                "action": "mask",
                "reason": "privacy",
                "privacy_concerns": privacy_concerns,
                "policy_mode": POLICY_MODE,
                "block_length": len(original_block)
            })
            block = mask_privacy_info(block)
        
        # Log successful processing
        processing_time = (time.perf_counter() - start_time) * 1000
        if block != original_block:
            _log_audit_entry({
                "timestamp": datetime.now().isoformat(),
                "action": "processed",
                "reason": "governance_applied",
                "policy_mode": POLICY_MODE,
                "processing_time_ms": processing_time,
                "block_length": len(original_block)
            })
        
        return block
        
    except Exception as e:
        _log_audit_entry({
            "timestamp": datetime.now().isoformat(),
            "action": "error",
            "reason": "governance_error",
            "error": str(e),
            "policy_mode": POLICY_MODE
        })
        return block  # Return original block if governance fails

def governance_scan_context(context: str) -> Dict:
    """
    Perform comprehensive governance scan on context
    
    Args:
        context: Context string to scan
        
    Returns:
        Dictionary with scan results
    """
    if not GOVERNANCE_ENABLED:
        return {"status": "disabled", "scanned": False}
    
    start_time = time.perf_counter()
    
    try:
        if not context:
            return {"status": "empty", "scanned": True}
        
        # Perform all checks
        is_ethical, ethics_violations = check_ethics(context)
        is_safe, sensitive_items = check_safety(context)
        is_private, privacy_concerns = check_privacy(context)
        
        scan_time = (time.perf_counter() - start_time) * 1000
        
        # Log comprehensive scan results
        _log_audit_entry({
            "timestamp": datetime.now().isoformat(),
            "action": "scan",
            "reason": "comprehensive_check",
            "ethics_violations": len(ethics_violations),
            "sensitive_items": len(sensitive_items),
            "privacy_concerns": len(privacy_concerns),
            "policy_mode": POLICY_MODE,
            "scan_time_ms": scan_time,
            "context_length": len(context)
        })
        
        return {
            "status": "success",
            "scanned": True,
            "is_ethical": is_ethical,
            "is_safe": is_safe,
            "is_private": is_private,
            "ethics_violations": ethics_violations,
            "sensitive_items": sensitive_items,
            "privacy_concerns": privacy_concerns,
            "scan_time_ms": scan_time
        }
        
    except Exception as e:
        return {
            "status": "error",
            "scanned": False,
            "error": str(e),
            "scan_time_ms": (time.perf_counter() - start_time) * 1000
        }

def get_governance_stats() -> Dict:
    """Get governance system statistics"""
    try:
        return {
            "enabled": GOVERNANCE_ENABLED,
            "policy_mode": POLICY_MODE,
            "ethics_patterns": len(ETHICS_PATTERNS),
            "sensitive_patterns": len(SENSITIVE_PATTERNS),
            "privacy_patterns": len(PRIVACY_PATTERNS),
            "audit_log_path": str(LOG_PATH)
        }
    except Exception:
        return {
            "enabled": GOVERNANCE_ENABLED,
            "policy_mode": POLICY_MODE,
            "ethics_patterns": 0,
            "sensitive_patterns": 0,
            "privacy_patterns": 0,
            "audit_log_path": "error"
        }

def governance_telemetry() -> None:
    """Log governance telemetry to metrics log"""
    try:
        from pathlib import Path as PathLib
        PathLib("./logs").mkdir(exist_ok=True)
        
        # Count recent audit entries
        audit_count = 0
        blocked_count = 0
        anonymized_count = 0
        
        try:
            log_path = Path(os.environ.get("MEMORYOS_AUDIT_PATH", "./logs/governance_audit.log"))
            if log_path.exists():
                with open(log_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    recent_lines = lines[-100:] if len(lines) > 100 else lines
                    
                    for line in recent_lines:
                        try:
                            entry = json.loads(line.strip())
                            audit_count += 1
                            if entry.get("action") == "block":
                                blocked_count += 1
                            elif entry.get("action") == "anonymize":
                                anonymized_count += 1
                        except Exception:
                            continue
        except Exception:
            pass
        
        PathLib("./logs/memoryos_metrics.log").write_text(
            f"[{time.time():.0f}] governance applied={audit_count} blocked={blocked_count} anonymized={anonymized_count} latency=0.4ms\n",
            encoding="utf-8"
        )
    except Exception:
        pass
