# -*- coding: utf-8 -*-
"""
Meta-Learning Layer (L12)
Adaptive policy and parameter tuning engine for MemoryOS.
"""
import os
import json
import time
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Configuration
METRICS_PATH = Path(os.environ.get("MEMORYOS_METRICS_PATH", "./logs/memoryos_metrics.log"))
POLICY_PATH = Path(os.environ.get("MEMORYOS_POLICY_PATH", "./data_ollama/meta_policy.json"))
AUDIT_PATH = Path(os.environ.get("MEMORYOS_AUDIT_PATH", "./logs/governance_audit.log"))
INSIGHT_PATH = Path(os.environ.get("MEMORYOS_INSIGHT_LOG", "./logs/memoryos_insights.log"))

UPDATE_INTERVAL_MIN = int(os.environ.get("MEMORYOS_POLICY_INTERVAL_MIN", "60"))
TUNING_MODE = os.environ.get("MEMORYOS_TUNING_MODE", "auto").lower()
LATENCY_TARGET = float(os.environ.get("MEMORYOS_LATENCY_TARGET", "2.5"))
META_LEARNING_ENABLED = os.environ.get("MEMORYOS_META_LEARNING_ENABLED", "true").lower() == "true"

# Default policy configuration
DEFAULT_POLICY = {
    "MEMORYOS_SIM_THRESHOLD": 0.5,
    "MEMORYOS_AGING_DECAY_RATE": 0.95,
    "MEMORYOS_REINJECT_TOPK": 3,
    "MEMORYOS_CONF_MIN": 0.3,
    "MEMORYOS_CONF_MAX": 1.0,
    "MEMORYOS_HEAL_THRESHOLD": 0.4,
    "MEMORYOS_TREND_FACTOR": 1.5,
    "MEMORYOS_ANOMALY_THRESHOLD": 1,
    "MEMORYOS_INSIGHT_MAX": 5,
    "MEMORYOS_GRAPH_MAXNODES": 500,
    "MEMORYOS_HEAL_INTERVAL": 100,
    "MEMORYOS_INSIGHT_INTERVAL": 50
}

def _load_metrics(lines: int = 200) -> List[str]:
    """Load recent metrics from log file"""
    try:
        metrics_path = Path(os.environ.get("MEMORYOS_METRICS_PATH", "./logs/memoryos_metrics.log"))
        if not metrics_path.exists():
            return []
        
        with open(metrics_path, encoding="utf-8") as f:
            data = f.readlines()
        
        # Get last N lines
        recent_lines = data[-lines:] if len(data) > lines else data
        return [line.strip() for line in recent_lines if line.strip()]
        
    except Exception:
        return []

def _load_audit_log(lines: int = 100) -> List[str]:
    """Load recent audit log entries"""
    try:
        audit_path = Path(os.environ.get("MEMORYOS_AUDIT_PATH", "./logs/governance_audit.log"))
        if not audit_path.exists():
            return []
        
        with open(audit_path, encoding="utf-8") as f:
            data = f.readlines()
        
        recent_lines = data[-lines:] if len(data) > lines else data
        return [line.strip() for line in recent_lines if line.strip()]
        
    except Exception:
        return []

def _load_insight_log(lines: int = 50) -> List[str]:
    """Load recent insight log entries"""
    try:
        insight_path = Path(os.environ.get("MEMORYOS_INSIGHT_LOG", "./logs/memoryos_insights.log"))
        if not insight_path.exists():
            return []
        
        with open(insight_path, encoding="utf-8") as f:
            data = f.readlines()
        
        recent_lines = data[-lines:] if len(data) > lines else data
        return [line.strip() for line in recent_lines if line.strip()]
        
    except Exception:
        return []

def analyze_metrics(metrics: List[str]) -> Dict:
    """
    Analyze metrics data to extract performance indicators
    
    Args:
        metrics: List of metric log lines
        
    Returns:
        Dictionary with analysis results
    """
    try:
        latency_values = []
        context_counts = []
        governance_counts = []
        healing_counts = []
        reasoning_counts = []
        
        for line in metrics:
            # Extract latency values
            if "latency=" in line:
                try:
                    latency_str = line.split("latency=")[1].split("ms")[0]
                    latency_values.append(float(latency_str))
                except Exception:
                    continue
            
            # Count context operations
            if "l1=on" in line or "l0=" in line:
                context_counts.append(line)
            
            # Count governance operations
            if "governance=" in line:
                governance_counts.append(line)
            
            # Count healing operations
            if "self_heal" in line:
                healing_counts.append(line)
            
            # Count reasoning operations
            if "insights generated=" in line:
                reasoning_counts.append(line)
        
        # Calculate statistics
        avg_latency = round(statistics.mean(latency_values), 3) if latency_values else 0
        max_latency = max(latency_values) if latency_values else 0
        min_latency = min(latency_values) if latency_values else 0
        
        return {
            "avg_latency": avg_latency,
            "max_latency": max_latency,
            "min_latency": min_latency,
            "latency_samples": len(latency_values),
            "context_operations": len(context_counts),
            "governance_operations": len(governance_counts),
            "healing_operations": len(healing_counts),
            "reasoning_operations": len(reasoning_counts),
            "total_metrics": len(metrics)
        }
        
    except Exception:
        return {
            "avg_latency": 0,
            "max_latency": 0,
            "min_latency": 0,
            "latency_samples": 0,
            "context_operations": 0,
            "governance_operations": 0,
            "healing_operations": 0,
            "reasoning_operations": 0,
            "total_metrics": 0
        }

def analyze_audit_log(audit_logs: List[str]) -> Dict:
    """
    Analyze audit logs to understand governance patterns
    
    Args:
        audit_logs: List of audit log entries
        
    Returns:
        Dictionary with audit analysis
    """
    try:
        blocked_count = 0
        anonymized_count = 0
        masked_count = 0
        processed_count = 0
        
        for line in audit_logs:
            try:
                entry = json.loads(line)
                action = entry.get("action", "")
                
                if action == "block":
                    blocked_count += 1
                elif action == "anonymize":
                    anonymized_count += 1
                elif action == "mask":
                    masked_count += 1
                elif action == "processed":
                    processed_count += 1
                    
            except Exception:
                continue
        
        total_actions = blocked_count + anonymized_count + masked_count + processed_count
        
        return {
            "blocked_count": blocked_count,
            "anonymized_count": anonymized_count,
            "masked_count": masked_count,
            "processed_count": processed_count,
            "total_actions": total_actions,
            "block_rate": round(blocked_count / max(total_actions, 1), 3),
            "anonymize_rate": round(anonymized_count / max(total_actions, 1), 3)
        }
        
    except Exception:
        return {
            "blocked_count": 0,
            "anonymized_count": 0,
            "masked_count": 0,
            "processed_count": 0,
            "total_actions": 0,
            "block_rate": 0,
            "anonymize_rate": 0
        }

def analyze_insights(insight_logs: List[str]) -> Dict:
    """
    Analyze insight logs to understand reasoning patterns
    
    Args:
        insight_logs: List of insight log entries
        
    Returns:
        Dictionary with insight analysis
    """
    try:
        total_insights = len(insight_logs)
        trend_insights = 0
        anomaly_insights = 0
        pattern_insights = 0
        
        for line in insight_logs:
            if "showing higher activity" in line.lower() or "trending" in line.lower():
                trend_insights += 1
            if "inactive" in line.lower() or "isolated" in line.lower():
                anomaly_insights += 1
            if "connectivity" in line.lower() or "confidence" in line.lower():
                pattern_insights += 1
        
        return {
            "total_insights": total_insights,
            "trend_insights": trend_insights,
            "anomaly_insights": anomaly_insights,
            "pattern_insights": pattern_insights,
            "insight_rate": round(total_insights / max(len(insight_logs), 1), 3)
        }
        
    except Exception:
        return {
            "total_insights": 0,
            "trend_insights": 0,
            "anomaly_insights": 0,
            "pattern_insights": 0,
            "insight_rate": 0
        }

def detect_performance_drift(analysis: Dict) -> Tuple[bool, str]:
    """
    Detect performance drift and degradation patterns
    
    Args:
        analysis: Combined analysis results
        
    Returns:
        Tuple of (is_drift_detected, drift_description)
    """
    try:
        avg_latency = analysis.get("avg_latency", 0)
        max_latency = analysis.get("max_latency", 0)
        latency_samples = analysis.get("latency_samples", 0)
        
        # Check for performance degradation
        if avg_latency > LATENCY_TARGET * 1.5:
            return True, f"High average latency: {avg_latency}ms (target: {LATENCY_TARGET}ms)"
        
        if max_latency > LATENCY_TARGET * 3:
            return True, f"Very high peak latency: {max_latency}ms (target: {LATENCY_TARGET}ms)"
        
        if latency_samples < 10:
            return True, f"Low sample count: {latency_samples} samples"
        
        # Check for governance issues
        block_rate = analysis.get("block_rate", 0)
        if block_rate > 0.1:  # More than 10% blocked
            return True, f"High block rate: {block_rate:.1%}"
        
        # Check for insight generation issues
        insight_rate = analysis.get("insight_rate", 0)
        if insight_rate < 0.01:  # Very low insight generation
            return True, f"Low insight generation rate: {insight_rate:.1%}"
        
        return False, "No significant drift detected"
        
    except Exception:
        return False, "Drift detection failed"

def tune_policy(analysis: Dict) -> Dict:
    """
    Adjust policy parameters based on comprehensive analysis
    
    Args:
        analysis: Combined analysis results
        
    Returns:
        Updated policy dictionary
    """
    try:
        policy = DEFAULT_POLICY.copy()
        
        avg_latency = analysis.get("avg_latency", 0)
        block_rate = analysis.get("block_rate", 0)
        anonymize_rate = analysis.get("anonymize_rate", 0)
        insight_rate = analysis.get("insight_rate", 0)
        
        # Performance-based tuning
        if avg_latency > LATENCY_TARGET * 1.2:  # Performance degradation
            # Reduce thresholds to improve performance
            policy["MEMORYOS_SIM_THRESHOLD"] = max(0.3, policy["MEMORYOS_SIM_THRESHOLD"] - 0.05)
            policy["MEMORYOS_AGING_DECAY_RATE"] = min(0.98, policy["MEMORYOS_AGING_DECAY_RATE"] + 0.02)
            policy["MEMORYOS_REINJECT_TOPK"] = max(1, policy["MEMORYOS_REINJECT_TOPK"] - 1)
            policy["MEMORYOS_INSIGHT_MAX"] = max(2, policy["MEMORYOS_INSIGHT_MAX"] - 1)
            
        elif avg_latency < LATENCY_TARGET * 0.8:  # Performance headroom
            # Increase thresholds to improve accuracy
            policy["MEMORYOS_SIM_THRESHOLD"] = min(0.7, policy["MEMORYOS_SIM_THRESHOLD"] + 0.05)
            policy["MEMORYOS_AGING_DECAY_RATE"] = max(0.9, policy["MEMORYOS_AGING_DECAY_RATE"] - 0.01)
            policy["MEMORYOS_REINJECT_TOPK"] = min(5, policy["MEMORYOS_REINJECT_TOPK"] + 1)
            policy["MEMORYOS_INSIGHT_MAX"] = min(8, policy["MEMORYOS_INSIGHT_MAX"] + 1)
        
        # Governance-based tuning
        if block_rate > 0.05:  # High block rate
            # Adjust governance sensitivity
            policy["MEMORYOS_CONF_MIN"] = max(0.2, policy["MEMORYOS_CONF_MIN"] - 0.05)
            
        if anonymize_rate > 0.1:  # High anonymization rate
            # Reduce sensitivity to avoid over-anonymization
            policy["MEMORYOS_CONF_MIN"] = min(0.5, policy["MEMORYOS_CONF_MIN"] + 0.05)
        
        # Insight-based tuning
        if insight_rate < 0.02:  # Low insight generation
            # Increase insight generation frequency
            policy["MEMORYOS_INSIGHT_INTERVAL"] = max(20, policy["MEMORYOS_INSIGHT_INTERVAL"] - 10)
            policy["MEMORYOS_TREND_FACTOR"] = max(1.2, policy["MEMORYOS_TREND_FACTOR"] - 0.1)
            
        elif insight_rate > 0.1:  # High insight generation
            # Reduce insight generation frequency
            policy["MEMORYOS_INSIGHT_INTERVAL"] = min(100, policy["MEMORYOS_INSIGHT_INTERVAL"] + 10)
            policy["MEMORYOS_TREND_FACTOR"] = min(2.0, policy["MEMORYOS_TREND_FACTOR"] + 0.1)
        
        # Healing-based tuning
        healing_ops = analysis.get("healing_operations", 0)
        if healing_ops > 50:  # Frequent healing
            # Increase healing interval to reduce overhead
            policy["MEMORYOS_HEAL_INTERVAL"] = min(200, policy["MEMORYOS_HEAL_INTERVAL"] + 20)
            
        elif healing_ops < 5:  # Infrequent healing
            # Decrease healing interval for more proactive maintenance
            policy["MEMORYOS_HEAL_INTERVAL"] = max(50, policy["MEMORYOS_HEAL_INTERVAL"] - 10)
        
        return policy
        
    except Exception:
        return DEFAULT_POLICY.copy()

def apply_policy(policy: Dict) -> bool:
    """
    Apply updated policy to environment and save to file
    
    Args:
        policy: Policy dictionary to apply
        
    Returns:
        Success status
    """
    try:
        # Save policy to file
        policy_path = Path(os.environ.get("MEMORYOS_POLICY_PATH", "./data_ollama/meta_policy.json"))
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        
        policy_with_metadata = {
            "policy": policy,
            "metadata": {
                "last_updated": datetime.now().isoformat(),
                "tuning_mode": TUNING_MODE,
                "latency_target": LATENCY_TARGET,
                "version": "1.0"
            }
        }
        
        with open(policy_path, "w", encoding="utf-8") as f:
            json.dump(policy_with_metadata, f, indent=2, ensure_ascii=False)
        
        # Apply to environment variables
        for key, value in policy.items():
            os.environ[key] = str(value)
        
        return True
        
    except Exception:
        return False

def run_meta_learning() -> Dict:
    """
    Execute complete meta-learning cycle
    
    Returns:
        Dictionary with meta-learning results
    """
    # Check if meta-learning is enabled (dynamic check)
    if os.environ.get("MEMORYOS_META_LEARNING_ENABLED", "true").lower() != "true":
        return {"status": "disabled"}
    
    start_time = time.perf_counter()
    
    try:
        # Load and analyze data
        metrics = _load_metrics(200)
        audit_logs = _load_audit_log(100)
        insight_logs = _load_insight_log(50)
        
        if not metrics:
            return {"status": "no_data", "message": "No metrics available"}
        
        # Perform analysis
        metrics_analysis = analyze_metrics(metrics)
        audit_analysis = analyze_audit_log(audit_logs)
        insight_analysis = analyze_insights(insight_logs)
        
        # Combine analysis
        combined_analysis = {**metrics_analysis, **audit_analysis, **insight_analysis}
        
        # Detect drift
        drift_detected, drift_description = detect_performance_drift(combined_analysis)
        
        # Tune policy
        updated_policy = tune_policy(combined_analysis)
        
        # Apply policy
        policy_applied = apply_policy(updated_policy)
        
        # Log telemetry
        processing_time = (time.perf_counter() - start_time) * 1000
        
        try:
            from pathlib import Path as PathLib
            PathLib("./logs").mkdir(exist_ok=True)
            
            # Log meta-learning results
            PathLib("./logs/memoryos_metrics.log").write_text(
                f"[{time.time():.0f}] meta_learning updated SIM_THRESHOLD={updated_policy['MEMORYOS_SIM_THRESHOLD']:.2f} "
                f"DECAY={updated_policy['MEMORYOS_AGING_DECAY_RATE']:.2f} latency={processing_time:.1f}ms "
                f"drift={'yes' if drift_detected else 'no'}\n",
                encoding="utf-8"
            )
        except Exception:
            pass
        
        return {
            "status": "success",
            "policy_applied": policy_applied,
            "drift_detected": drift_detected,
            "drift_description": drift_description,
            "updated_policy": updated_policy,
            "analysis": combined_analysis,
            "processing_time_ms": processing_time
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "processing_time_ms": (time.perf_counter() - start_time) * 1000
        }

def get_meta_learning_stats() -> Dict:
    """Get meta-learning system statistics"""
    try:
        # Load current policy
        current_policy = DEFAULT_POLICY.copy()
        policy_path = Path(os.environ.get("MEMORYOS_POLICY_PATH", "./data_ollama/meta_policy.json"))
        if policy_path.exists():
            try:
                with open(policy_path, "r", encoding="utf-8") as f:
                    policy_data = json.load(f)
                    current_policy = policy_data.get("policy", DEFAULT_POLICY)
            except Exception:
                pass
        
        metrics_path = Path(os.environ.get("MEMORYOS_METRICS_PATH", "./logs/memoryos_metrics.log"))
        audit_path = Path(os.environ.get("MEMORYOS_AUDIT_PATH", "./logs/governance_audit.log"))
        insight_path = Path(os.environ.get("MEMORYOS_INSIGHT_LOG", "./logs/memoryos_insights.log"))
        
        return {
            "enabled": os.environ.get("MEMORYOS_META_LEARNING_ENABLED", "true").lower() == "true",
            "tuning_mode": TUNING_MODE,
            "latency_target": LATENCY_TARGET,
            "update_interval_min": UPDATE_INTERVAL_MIN,
            "current_policy": current_policy,
            "policy_file_exists": policy_path.exists(),
            "metrics_file_exists": metrics_path.exists(),
            "audit_file_exists": audit_path.exists(),
            "insight_file_exists": insight_path.exists()
        }
        
    except Exception:
        return {
            "enabled": META_LEARNING_ENABLED,
            "tuning_mode": TUNING_MODE,
            "latency_target": LATENCY_TARGET,
            "update_interval_min": UPDATE_INTERVAL_MIN,
            "current_policy": DEFAULT_POLICY,
            "policy_file_exists": False,
            "metrics_file_exists": False,
            "audit_file_exists": False,
            "insight_file_exists": False
        }
