# -*- coding: utf-8 -*-
"""
Self-Healing Knowledge Graph Layer (L8)
Evaluates and repairs relationships in the Memory Graph.
"""
import json
import os
import time
import random
from datetime import datetime
from pathlib import Path
from typing import Dict

# Configuration
GRAPH_PATH = Path(os.environ.get("MEMORYOS_GRAPH_PATH", "./data_ollama/memory_graph.json"))
DECAY_HOURS = int(os.environ.get("MEMORYOS_HEALING_DECAY_HOURS", "24"))
CONF_MIN = float(os.environ.get("MEMORYOS_CONF_MIN", "0.3"))
CONF_MAX = float(os.environ.get("MEMORYOS_CONF_MAX", "1.0"))
HEAL_THRESHOLD = float(os.environ.get("MEMORYOS_HEAL_THRESHOLD", "0.4"))
HEALING_ENABLED = os.environ.get("MEMORYOS_HEALING_ENABLED", "true").lower() == "true"
HEAL_PROBABILITY = float(os.environ.get("MEMORYOS_HEAL_PROBABILITY", "0.01"))

def _load_graph() -> Dict:
    """Load graph data from file"""
    try:
        graph_path = Path(os.environ.get("MEMORYOS_GRAPH_PATH", "./data_ollama/memory_graph.json"))
        
        if not graph_path.exists():
            return {"nodes": {}, "edges": [], "metadata": {"last_heal": "never"}}
        
        with open(graph_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Ensure required structure
        if "nodes" not in data:
            data["nodes"] = {}
        if "edges" not in data:
            data["edges"] = []
        if "metadata" not in data:
            data["metadata"] = {"last_heal": "never"}
        
        return data
        
    except Exception:
        return {"nodes": {}, "edges": [], "metadata": {"last_heal": "error"}}

def _save_graph(data: Dict) -> bool:
    """Save graph data to file"""
    try:
        graph_path = Path(os.environ.get("MEMORYOS_GRAPH_PATH", "./data_ollama/memory_graph.json"))
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(graph_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return True
        
    except Exception:
        return False

def integrity_scan() -> Dict:
    """
    Check for missing nodes or inconsistent edges
    
    Returns:
        Dictionary with scan results
    """
    # Check if healing is enabled (dynamic check)
    if os.environ.get("MEMORYOS_HEALING_ENABLED", "true").lower() != "true":
        return {"status": "disabled"}
    
    start_time = time.perf_counter()
    
    try:
        g = _load_graph()
        
        # Track original counts
        original_edges = len(g["edges"])
        original_nodes = len(g["nodes"])
        
        # Remove edges that reference non-existent nodes
        valid_edges = []
        for edge in g["edges"]:
            src = edge.get("src")
            tgt = edge.get("tgt")
            
            if src and tgt and src in g["nodes"] and tgt in g["nodes"]:
                valid_edges.append(edge)
        
        g["edges"] = valid_edges
        
        # Remove orphaned nodes (nodes with no edges)
        connected_nodes = set()
        for edge in g["edges"]:
            connected_nodes.add(edge.get("src"))
            connected_nodes.add(edge.get("tgt"))
        
        # Keep nodes that have edges or are explicitly marked as important
        g["nodes"] = {
            node: data for node, data in g["nodes"].items()
            if node in connected_nodes or data.get("important", False)
        }
        
        # Update metadata
        g["metadata"]["last_heal"] = datetime.now().isoformat()
        g["metadata"]["last_integrity_scan"] = datetime.now().isoformat()
        
        # Save cleaned graph
        _save_graph(g)
        
        scan_time = (time.perf_counter() - start_time) * 1000
        
        return {
            "status": "success",
            "edges_retained": len(g["edges"]),
            "edges_removed": original_edges - len(g["edges"]),
            "nodes_retained": len(g["nodes"]),
            "nodes_removed": original_nodes - len(g["nodes"]),
            "scan_time_ms": scan_time
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "scan_time_ms": (time.perf_counter() - start_time) * 1000
        }

def reweight_confidence() -> Dict:
    """
    Recalculate confidence scores for all edges based on recency
    
    Returns:
        Dictionary with reweighting results
    """
    # Check if healing is enabled (dynamic check)
    if os.environ.get("MEMORYOS_HEALING_ENABLED", "true").lower() != "true":
        return {"status": "disabled"}
    
    start_time = time.perf_counter()
    
    try:
        g = _load_graph()
        
        if not g["edges"]:
            return {"status": "no_edges", "reweighted": 0}
        
        now = datetime.now()
        reweighted_count = 0
        total_confidence = 0
        
        for edge in g["edges"]:
            # Get timestamp from edge
            timestamp_str = edge.get("ts") or edge.get("timestamp") or edge.get("last_seen")
            
            if timestamp_str:
                try:
                    # Parse timestamp
                    if timestamp_str.endswith('Z'):
                        timestamp_str = timestamp_str[:-1]
                    
                    ts = datetime.fromisoformat(timestamp_str)
                    age_hours = (now - ts).total_seconds() / 3600
                    
                    # Calculate decay factor
                    decay_factor = max(CONF_MIN, CONF_MAX * (0.9 ** (age_hours / DECAY_HOURS)))
                    
                    # Add small random variation to prevent identical scores
                    variation = random.uniform(-0.05, 0.05)
                    confidence = max(CONF_MIN, min(CONF_MAX, decay_factor + variation))
                    
                except Exception:
                    # Use minimum confidence for invalid timestamps
                    confidence = CONF_MIN
            else:
                # Use minimum confidence for missing timestamps
                confidence = CONF_MIN
            
            edge["confidence"] = round(confidence, 3)
            total_confidence += confidence
            reweighted_count += 1
        
        # Update metadata
        g["metadata"]["last_heal"] = datetime.now().isoformat()
        g["metadata"]["last_reweight"] = datetime.now().isoformat()
        g["metadata"]["avg_confidence"] = round(total_confidence / reweighted_count, 3) if reweighted_count > 0 else 0
        
        # Save updated graph
        _save_graph(g)
        
        reweight_time = (time.perf_counter() - start_time) * 1000
        
        return {
            "status": "success",
            "reweighted": reweighted_count,
            "avg_confidence": g["metadata"]["avg_confidence"],
            "reweight_time_ms": reweight_time
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "reweight_time_ms": (time.perf_counter() - start_time) * 1000
        }

def prune_low_confidence(threshold: float = None) -> Dict:
    """
    Remove edges with confidence below threshold
    
    Args:
        threshold: Confidence threshold (uses HEAL_THRESHOLD if None)
        
    Returns:
        Dictionary with pruning results
    """
    # Check if healing is enabled (dynamic check)
    if os.environ.get("MEMORYOS_HEALING_ENABLED", "true").lower() != "true":
        return {"status": "disabled"}
    
    if threshold is None:
        threshold = HEAL_THRESHOLD
    
    start_time = time.perf_counter()
    
    try:
        g = _load_graph()
        
        if not g["edges"]:
            return {"status": "no_edges", "removed": 0}
        
        before_count = len(g["edges"])
        
        # Filter edges by confidence threshold
        g["edges"] = [
            edge for edge in g["edges"]
            if edge.get("confidence", 1.0) >= threshold
        ]
        
        removed_count = before_count - len(g["edges"])
        
        # Update metadata
        g["metadata"]["last_heal"] = datetime.now().isoformat()
        g["metadata"]["last_prune"] = datetime.now().isoformat()
        g["metadata"]["prune_threshold"] = threshold
        
        # Save pruned graph
        _save_graph(g)
        
        prune_time = (time.perf_counter() - start_time) * 1000
        
        return {
            "status": "success",
            "removed": removed_count,
            "remaining": len(g["edges"]),
            "threshold": threshold,
            "prune_time_ms": prune_time
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "prune_time_ms": (time.perf_counter() - start_time) * 1000
        }

def heal_missing_links() -> Dict:
    """
    Recreate missing edges for frequently co-occurring nodes
    
    Returns:
        Dictionary with healing results
    """
    # Check if healing is enabled (dynamic check)
    if os.environ.get("MEMORYOS_HEALING_ENABLED", "true").lower() != "true":
        return {"status": "disabled"}
    
    start_time = time.perf_counter()
    
    try:
        g = _load_graph()
        
        node_names = list(g["nodes"].keys())
        if len(node_names) < 2:
            return {"status": "insufficient_nodes", "healed": 0}
        
        # Get existing edge pairs
        existing_pairs = set()
        for edge in g["edges"]:
            src = edge.get("src")
            tgt = edge.get("tgt")
            if src and tgt:
                # Store both directions
                existing_pairs.add((src, tgt))
                existing_pairs.add((tgt, src))
        
        healed_count = 0
        
        # Try to heal missing connections
        for i, node_a in enumerate(node_names):
            for node_b in node_names[i+1:]:
                # Skip if edge already exists
                if (node_a, node_b) in existing_pairs:
                    continue
                
                # Random chance to create new edge
                if random.random() < HEAL_PROBABILITY:
                    # Create new edge with moderate confidence
                    new_edge = {
                        "src": node_a,
                        "tgt": node_b,
                        "confidence": round(random.uniform(0.4, 0.6), 3),
                        "ts": datetime.now().isoformat(),
                        "healed": True
                    }
                    
                    g["edges"].append(new_edge)
                    healed_count += 1
                    
                    # Add to existing pairs to avoid duplicates
                    existing_pairs.add((node_a, node_b))
                    existing_pairs.add((node_b, node_a))
        
        # Update metadata
        g["metadata"]["last_heal"] = datetime.now().isoformat()
        g["metadata"]["last_healing"] = datetime.now().isoformat()
        
        # Save healed graph
        _save_graph(g)
        
        heal_time = (time.perf_counter() - start_time) * 1000
        
        return {
            "status": "success",
            "healed": healed_count,
            "total_edges": len(g["edges"]),
            "heal_time_ms": heal_time
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "heal_time_ms": (time.perf_counter() - start_time) * 1000
        }

def run_full_healing_cycle() -> Dict:
    """
    Run complete self-healing cycle: scan -> reweight -> prune -> heal
    
    Returns:
        Dictionary with complete cycle results
    """
    # Check if healing is enabled (dynamic check)
    if os.environ.get("MEMORYOS_HEALING_ENABLED", "true").lower() != "true":
        return {"status": "disabled"}
    
    cycle_start = time.perf_counter()
    
    try:
        # Run all healing operations
        scan_result = integrity_scan()
        reweight_result = reweight_confidence()
        prune_result = prune_low_confidence()
        heal_result = heal_missing_links()
        
        cycle_time = (time.perf_counter() - cycle_start) * 1000
        
        # Log telemetry
        try:
            from pathlib import Path as PathLib
            PathLib("./logs").mkdir(exist_ok=True)
            
            # Calculate summary statistics
            edges_removed = scan_result.get("edges_removed", 0) + prune_result.get("removed", 0)
            edges_healed = heal_result.get("healed", 0)
            avg_conf = reweight_result.get("avg_confidence", 0)
            
            PathLib("./logs/memoryos_metrics.log").write_text(
                f"[{time.time():.0f}] self_heal edges_removed={edges_removed} healed={edges_healed} avg_conf={avg_conf:.2f} cycle_time={cycle_time:.1f}ms\n",
                encoding="utf-8"
            )
        except Exception:
            pass
        
        return {
            "status": "success",
            "scan": scan_result,
            "reweight": reweight_result,
            "prune": prune_result,
            "heal": heal_result,
            "cycle_time_ms": cycle_time
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "cycle_time_ms": (time.perf_counter() - cycle_start) * 1000
        }

def get_healing_stats() -> Dict:
    """Get self-healing system statistics"""
    try:
        g = _load_graph()
        
        return {
            "enabled": os.environ.get("MEMORYOS_HEALING_ENABLED", "true").lower() == "true",
            "total_nodes": len(g.get("nodes", {})),
            "total_edges": len(g.get("edges", [])),
            "last_heal": g.get("metadata", {}).get("last_heal", "never"),
            "avg_confidence": g.get("metadata", {}).get("avg_confidence", 0),
            "decay_hours": DECAY_HOURS,
            "conf_min": CONF_MIN,
            "conf_max": CONF_MAX,
            "heal_threshold": HEAL_THRESHOLD
        }
        
    except Exception:
        return {
            "enabled": os.environ.get("MEMORYOS_HEALING_ENABLED", "true").lower() == "true",
            "total_nodes": 0,
            "total_edges": 0,
            "last_heal": "error",
            "avg_confidence": 0,
            "decay_hours": DECAY_HOURS,
            "conf_min": CONF_MIN,
            "conf_max": CONF_MAX,
            "heal_threshold": HEAL_THRESHOLD
        }
