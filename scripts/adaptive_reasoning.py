# -*- coding: utf-8 -*-
"""
Adaptive Reasoning Layer (L9)
Generates insights from the Memory Graph through pattern and trend analysis.
"""
import json
import statistics
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Configuration
GRAPH_PATH = Path(os.environ.get("MEMORYOS_GRAPH_PATH", "./data_ollama/memory_graph.json"))
INSIGHT_LOG = Path(os.environ.get("MEMORYOS_INSIGHT_LOG", "./logs/memoryos_insights.log"))
INSIGHT_MAX = int(os.environ.get("MEMORYOS_INSIGHT_MAX", "5"))
TREND_FACTOR = float(os.environ.get("MEMORYOS_TREND_FACTOR", "1.5"))
ANOMALY_THRESHOLD = int(os.environ.get("MEMORYOS_ANOMALY_THRESHOLD", "1"))
REASONING_ENABLED = os.environ.get("MEMORYOS_REASONING_ENABLED", "true").lower() == "true"
INSIGHT_INTERVAL = int(os.environ.get("MEMORYOS_INSIGHT_INTERVAL", "50"))

def _load_graph() -> Dict:
    """Load graph data from file"""
    try:
        graph_path = Path(os.environ.get("MEMORYOS_GRAPH_PATH", "./data_ollama/memory_graph.json"))
        
        if not graph_path.exists():
            return {"nodes": {}, "edges": [], "metadata": {}}
        
        with open(graph_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Ensure required structure
        if "nodes" not in data:
            data["nodes"] = {}
        if "edges" not in data:
            data["edges"] = []
        if "metadata" not in data:
            data["metadata"] = {}
        
        return data
        
    except Exception:
        return {"nodes": {}, "edges": [], "metadata": {}}

def _log_insight(text: str) -> None:
    """Log insight to file"""
    try:
        insight_log_path = Path(os.environ.get("MEMORYOS_INSIGHT_LOG", "./logs/memoryos_insights.log"))
        insight_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(insight_log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().isoformat()}] {text}\n")
    except Exception:
        pass  # Silently fail if logging fails

def extract_trends(g: Dict) -> List[str]:
    """
    Analyze frequency changes in node activity to identify trending topics
    
    Args:
        g: Graph data structure
        
    Returns:
        List of trend insights
    """
    try:
        nodes = g.get("nodes", {})
        if not nodes:
            return []
        
        # Calculate average activity
        counts = [node_data.get("count", 0) for node_data in nodes.values()]
        if not counts:
            return []
        
        avg_count = statistics.mean(counts)
        if avg_count == 0:
            return []
        
        # Find trending topics (above threshold)
        trending_topics = []
        for topic, data in nodes.items():
            count = data.get("count", 0)
            if count > avg_count * TREND_FACTOR:
                trending_topics.append(topic)
        
        # Generate trend insights
        insights = []
        for topic in trending_topics[:3]:  # Limit to top 3 trends
            insights.append(f"Topic '{topic}' showing higher activity")
        
        return insights
        
    except Exception:
        return []

def detect_anomalies(g: Dict) -> List[str]:
    """
    Detect isolated nodes or sudden drops in activity
    
    Args:
        g: Graph data structure
        
    Returns:
        List of anomaly insights
    """
    try:
        nodes = g.get("nodes", {})
        edges = g.get("edges", [])
        
        if not nodes:
            return []
        
        anomalies = []
        
        # Detect inactive nodes
        inactive_topics = []
        for topic, data in nodes.items():
            count = data.get("count", 0)
            if count <= ANOMALY_THRESHOLD:
                inactive_topics.append(topic)
        
        for topic in inactive_topics[:3]:  # Limit to top 3 anomalies
            anomalies.append(f"Topic '{topic}' appears inactive")
        
        # Detect isolated nodes (nodes with few connections)
        node_connections = {}
        for edge in edges:
            src = edge.get("src")
            tgt = edge.get("tgt")
            if src:
                node_connections[src] = node_connections.get(src, 0) + 1
            if tgt:
                node_connections[tgt] = node_connections.get(tgt, 0) + 1
        
        # Find nodes with very few connections
        total_nodes = len(nodes)
        if total_nodes > 1:
            avg_connections = sum(node_connections.values()) / total_nodes
            isolated_topics = []
            
            for topic in nodes.keys():
                connections = node_connections.get(topic, 0)
                if connections < avg_connections * 0.3 and connections > 0:  # Some connections but below average
                    isolated_topics.append(topic)
            
            for topic in isolated_topics[:2]:  # Limit to top 2 isolated topics
                anomalies.append(f"Topic '{topic}' appears isolated")
        
        return anomalies
        
    except Exception:
        return []

def analyze_patterns(g: Dict) -> List[str]:
    """
    Analyze patterns in the graph structure
    
    Args:
        g: Graph data structure
        
    Returns:
        List of pattern insights
    """
    try:
        nodes = g.get("nodes", {})
        edges = g.get("edges", [])
        
        if not nodes or not edges:
            return []
        
        patterns = []
        
        # Analyze edge density
        total_nodes = len(nodes)
        total_edges = len(edges)
        
        if total_nodes > 1:
            max_possible_edges = total_nodes * (total_nodes - 1) / 2
            density = total_edges / max_possible_edges if max_possible_edges > 0 else 0
            
            if density > 0.7:
                patterns.append("High connectivity detected in knowledge graph")
            elif density < 0.2:
                patterns.append("Low connectivity detected in knowledge graph")
        
        # Analyze confidence distribution
        confidences = [edge.get("confidence", 1.0) for edge in edges if "confidence" in edge]
        if confidences:
            avg_confidence = statistics.mean(confidences)
            if avg_confidence > 0.8:
                patterns.append("High confidence relationships detected")
            elif avg_confidence < 0.4:
                patterns.append("Low confidence relationships detected")
        
        # Analyze temporal patterns
        recent_edges = 0
        now = datetime.now()
        for edge in edges:
            timestamp_str = edge.get("ts") or edge.get("timestamp") or edge.get("last_seen")
            if timestamp_str:
                try:
                    if timestamp_str.endswith('Z'):
                        timestamp_str = timestamp_str[:-1]
                    ts = datetime.fromisoformat(timestamp_str)
                    if (now - ts).total_seconds() < 3600:  # Last hour
                        recent_edges += 1
                except Exception:
                    continue
        
        if recent_edges > len(edges) * 0.5:
            patterns.append("Recent high activity detected")
        
        return patterns[:2]  # Limit to top 2 patterns
        
    except Exception:
        return []

def generate_insights() -> Dict:
    """
    Generate comprehensive insights from the graph
    
    Returns:
        Dictionary with insight generation results
    """
    if not REASONING_ENABLED:
        return {"status": "disabled", "insights": []}
    
    start_time = time.perf_counter()
    
    try:
        g = _load_graph()
        
        if not g.get("nodes"):
            return {"status": "no_data", "insights": []}
        
        # Extract different types of insights
        trends = extract_trends(g)
        anomalies = detect_anomalies(g)
        patterns = analyze_patterns(g)
        
        # Combine all insights
        all_insights = trends + anomalies + patterns
        
        # Limit total insights
        all_insights = all_insights[:INSIGHT_MAX]
        
        generation_time = (time.perf_counter() - start_time) * 1000
        
        return {
            "status": "success",
            "insights": all_insights,
            "trends": len(trends),
            "anomalies": len(anomalies),
            "patterns": len(patterns),
            "generation_time_ms": generation_time
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "insights": [],
            "generation_time_ms": (time.perf_counter() - start_time) * 1000
        }

def summarize_insights() -> str:
    """
    Generate and format insights for context injection
    
    Returns:
        Formatted insight text for LLM prompt
    """
    if not REASONING_ENABLED:
        return ""
    
    try:
        result = generate_insights()
        
        if result["status"] != "success" or not result["insights"]:
            return ""
        
        insights = result["insights"]
        
        # Format insights
        insight_text = " | ".join(insights)
        
        # Log insights
        _log_insight(insight_text)
        
        # Log telemetry
        try:
            from pathlib import Path as PathLib
            PathLib("./logs").mkdir(exist_ok=True)
            PathLib("./logs/memoryos_metrics.log").write_text(
                f"[{time.time():.0f}] insights generated={len(insights)} trends={result['trends']} anomalies={result['anomalies']} latency={result['generation_time_ms']:.1f}ms\n",
                encoding="utf-8"
            )
        except Exception:
            pass
        
        return f"[ADAPTIVE INSIGHTS]\n{insight_text}"
        
    except Exception:
        return ""

def get_reasoning_stats() -> Dict:
    """Get adaptive reasoning system statistics"""
    try:
        g = _load_graph()
        
        return {
            "enabled": REASONING_ENABLED,
            "total_nodes": len(g.get("nodes", {})),
            "total_edges": len(g.get("edges", [])),
            "insight_max": INSIGHT_MAX,
            "trend_factor": TREND_FACTOR,
            "anomaly_threshold": ANOMALY_THRESHOLD,
            "insight_interval": INSIGHT_INTERVAL
        }
        
    except Exception:
        return {
            "enabled": REASONING_ENABLED,
            "total_nodes": 0,
            "total_edges": 0,
            "insight_max": INSIGHT_MAX,
            "trend_factor": TREND_FACTOR,
            "anomaly_threshold": ANOMALY_THRESHOLD,
            "insight_interval": INSIGHT_INTERVAL
        }

def analyze_user_context(user_input: str) -> str:
    """
    Analyze user input context and generate relevant insights
    
    Args:
        user_input: User's input text
        
    Returns:
        Context-specific insights
    """
    if not REASONING_ENABLED or not user_input:
        return ""
    
    try:
        # Extract keywords from user input
        import re
        keywords = [w.lower() for w in re.findall(r"[A-Za-z0-9가-힣_]+", user_input) if len(w) >= 3]
        
        if not keywords:
            return summarize_insights()  # Fallback to general insights
        
        g = _load_graph()
        nodes = g.get("nodes", {})
        
        if not nodes:
            return ""
        
        # Find insights related to user keywords
        relevant_insights = []
        
        for keyword in keywords[:3]:  # Check top 3 keywords
            if keyword in nodes:
                node_data = nodes[keyword]
                count = node_data.get("count", 0)
                
                if count > 0:
                    relevant_insights.append(f"Topic '{keyword}' has {count} occurrences")
        
        if relevant_insights:
            insight_text = " | ".join(relevant_insights[:3])
            return f"[CONTEXT INSIGHTS]\n{insight_text}"
        
        # Fallback to general insights if no specific context found
        return summarize_insights()
        
    except Exception:
        return ""
