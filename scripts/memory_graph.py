# -*- coding: utf-8 -*-
"""
Memory Graph Layer (L7)
Builds and queries relationships between validated memories.
"""
import json
import re
import hashlib
import os
import time
from typing import List, Dict
from pathlib import Path
from datetime import datetime

# Configuration
GRAPH_PATH = Path(os.environ.get("MEMORYOS_GRAPH_PATH", "./data_ollama/memory_graph.json"))
MAX_NODES = int(os.environ.get("MEMORYOS_GRAPH_MAXNODES", "500"))
GRAPH_ENABLED = os.environ.get("MEMORYOS_GRAPH_ENABLED", "true").lower() == "true"
MIN_KEYWORD_LENGTH = int(os.environ.get("MEMORYOS_GRAPH_MIN_KEYWORD_LENGTH", "3"))
MAX_RELATED_TERMS = int(os.environ.get("MEMORYOS_GRAPH_MAX_RELATED_TERMS", "5"))

def _normalize(text: str) -> List[str]:
    """Extract and normalize keywords from text"""
    if not text:
        return []
    
    # Extract words (alphanumeric + Korean + underscore)
    words = re.findall(r"[A-Za-z0-9가-힣_]+", text)
    
    # Filter by minimum length and convert to lowercase
    keywords = [w.lower() for w in words if len(w) >= MIN_KEYWORD_LENGTH]
    
    # Remove common stop words
    stop_words = {
        'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
        'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did',
        'will', 'would', 'could', 'should', 'may', 'might', 'can', 'must', 'shall',
        'this', 'that', 'these', 'those', 'a', 'an', 'some', 'any', 'all', 'each', 'every',
        'system', 'error', 'data', 'file', 'time', 'user', 'test', 'check', 'run', 'get', 'set'
    }
    
    return [kw for kw in keywords if kw not in stop_words]

def _hash_key(a: str, b: str) -> str:
    """Generate consistent hash key for edge"""
    # Ensure consistent ordering for bidirectional edges
    if a > b:
        a, b = b, a
    return hashlib.sha1(f"{a}->{b}".encode("utf-8")).hexdigest()[:12]

def _extract_memory_content(memory: Dict) -> str:
    """Extract searchable content from memory"""
    content_parts = []
    
    # Extract from proposal if available
    if "proposal" in memory:
        proposal = memory["proposal"]
        if isinstance(proposal, dict):
            for field in ["text", "message", "summary", "note"]:
                if field in proposal:
                    content_parts.append(str(proposal[field]))
        else:
            content_parts.append(str(proposal))
    
    # Extract from validation result
    if "validation_result" in memory:
        validation = memory["validation_result"]
        if isinstance(validation, dict):
            reasons = validation.get("reasons", [])
            if reasons:
                content_parts.extend([str(r) for r in reasons])
    
    # Extract from direct fields
    for field in ["summary", "note", "message", "text"]:
        if field in memory:
            content_parts.append(str(memory[field]))
    
    return " ".join(content_parts)

def build_graph(memories: List[Dict]) -> Dict:
    """
    Build relationship graph from validated memories
    
    Args:
        memories: List of validated memory objects
        
    Returns:
        Graph structure with nodes and edges
    """
    if not GRAPH_ENABLED or not memories:
        return {"nodes": {}, "edges": [], "metadata": {"last_build": "disabled"}}
    
    start_time = time.perf_counter()
    
    graph = {
        "nodes": {},
        "edges": [],
        "metadata": {
            "last_build": datetime.now().isoformat(),
            "total_memories": len(memories),
            "build_time_ms": 0
        }
    }
    
    try:
        # Process each memory
        for memory in memories:
            content = _extract_memory_content(memory)
            if not content:
                continue
            
            keywords = _normalize(content)
            if len(keywords) < 2:
                continue
            
            # Create edges between all keyword pairs in this memory
            for i, src in enumerate(keywords):
                for tgt in keywords[i+1:]:
                    edge_id = _hash_key(src, tgt)
                    
                    # Check if edge already exists
                    existing_edge = None
                    for edge in graph["edges"]:
                        if edge["id"] == edge_id:
                            existing_edge = edge
                            break
                    
                    if existing_edge:
                        # Increment weight for existing edge
                        existing_edge["weight"] = existing_edge.get("weight", 1) + 1
                        existing_edge["last_seen"] = memory.get("timestamp", datetime.now().isoformat())
                    else:
                        # Create new edge
                        graph["edges"].append({
                            "id": edge_id,
                            "src": src,
                            "tgt": tgt,
                            "weight": 1,
                            "first_seen": memory.get("timestamp", datetime.now().isoformat()),
                            "last_seen": memory.get("timestamp", datetime.now().isoformat())
                        })
                    
                    # Update node counts
                    graph["nodes"].setdefault(src, {"count": 0, "first_seen": memory.get("timestamp", datetime.now().isoformat())})
                    graph["nodes"].setdefault(tgt, {"count": 0, "first_seen": memory.get("timestamp", datetime.now().isoformat())})
                    
                    graph["nodes"][src]["count"] += 1
                    graph["nodes"][tgt]["count"] += 1
                    
                    # Update last seen for nodes
                    graph["nodes"][src]["last_seen"] = memory.get("timestamp", datetime.now().isoformat())
                    graph["nodes"][tgt]["last_seen"] = memory.get("timestamp", datetime.now().isoformat())
        
        # Limit nodes if exceeding maximum
        if len(graph["nodes"]) > MAX_NODES:
            # Keep most frequent nodes
            sorted_nodes = sorted(graph["nodes"].items(), key=lambda x: x[1]["count"], reverse=True)
            graph["nodes"] = dict(sorted_nodes[:MAX_NODES])
            
            # Remove edges involving removed nodes
            valid_nodes = set(graph["nodes"].keys())
            graph["edges"] = [
                edge for edge in graph["edges"]
                if edge["src"] in valid_nodes and edge["tgt"] in valid_nodes
            ]
        
        # Update metadata
        graph["metadata"]["total_nodes"] = len(graph["nodes"])
        graph["metadata"]["total_edges"] = len(graph["edges"])
        graph["metadata"]["build_time_ms"] = (time.perf_counter() - start_time) * 1000
        
        # Save graph to file
        try:
            GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
            GRAPH_PATH.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass  # Continue even if save fails
        
        # Log telemetry
        try:
            from pathlib import Path as PathLib
            PathLib("./logs").mkdir(exist_ok=True)
            PathLib("./logs/memoryos_metrics.log").write_text(
                f"[{time.time():.0f}] graph edges={len(graph['edges'])} nodes={len(graph['nodes'])} last_build=OK build_time={graph['metadata']['build_time_ms']:.1f}ms\n",
                encoding="utf-8"
            )
        except Exception:
            pass
        
        return graph
        
    except Exception as e:
        # Return empty graph on error
        return {
            "nodes": {},
            "edges": [],
            "metadata": {
                "last_build": "error",
                "error": str(e),
                "build_time_ms": (time.perf_counter() - start_time) * 1000
            }
        }

def query_related(term: str, limit: int = None) -> List[str]:
    """
    Return related keywords from graph
    
    Args:
        term: Search term to find related keywords for
        limit: Maximum number of related terms to return
        
    Returns:
        List of related keywords sorted by frequency
    """
    if not GRAPH_ENABLED or not term:
        return []
    
    if limit is None:
        limit = MAX_RELATED_TERMS
    
    try:
        if not GRAPH_PATH.exists():
            return []
        
        with open(GRAPH_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if "edges" not in data:
            return []
        
        # Find edges connected to the search term
        connected_edges = []
        for edge in data["edges"]:
            if edge["src"] == term.lower() or edge["tgt"] == term.lower():
                connected_edges.append(edge)
        
        if not connected_edges:
            return []
        
        # Count frequency of related terms
        freq = {}
        for edge in connected_edges:
            neighbor = edge["tgt"] if edge["src"] == term.lower() else edge["src"]
            weight = edge.get("weight", 1)
            freq[neighbor] = freq.get(neighbor, 0) + weight
        
        # Sort by frequency and return top terms
        sorted_terms = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [term for term, _ in sorted_terms[:limit]]
        
    except Exception:
        return []

def query_graph_stats() -> Dict:
    """Get graph statistics"""
    try:
        if not GRAPH_PATH.exists():
            return {
                "total_nodes": 0,
                "total_edges": 0,
                "last_build": "never",
                "enabled": GRAPH_ENABLED
            }
        
        with open(GRAPH_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return {
            "total_nodes": len(data.get("nodes", {})),
            "total_edges": len(data.get("edges", [])),
            "last_build": data.get("metadata", {}).get("last_build", "unknown"),
            "enabled": GRAPH_ENABLED,
            "max_nodes": MAX_NODES
        }
        
    except Exception:
        return {
            "total_nodes": 0,
            "total_edges": 0,
            "last_build": "error",
            "enabled": GRAPH_ENABLED
        }

def rebuild_graph_from_approvals() -> Dict:
    """
    Rebuild graph from current approval queue
    
    Returns:
        Graph structure
    """
    try:
        from scripts.approval_queue import get_approval_queue
        
        queue = get_approval_queue()
        all_approvals = queue.queue
        
        # Filter for processed approvals
        processed_approvals = [
            approval for approval in all_approvals
            if approval.get("status") == "processed"
        ]
        
        return build_graph(processed_approvals)
        
    except ImportError:
        return {"nodes": {}, "edges": [], "metadata": {"last_build": "approval_queue_unavailable"}}
    except Exception as e:
        return {"nodes": {}, "edges": [], "metadata": {"last_build": "error", "error": str(e)}}

def get_related_context(user_input: str) -> str:
    """
    Get related context based on user input keywords
    
    Args:
        user_input: User's input text
        
    Returns:
        Formatted related topics string
    """
    if not GRAPH_ENABLED or not user_input:
        return ""
    
    # Extract first meaningful keyword from user input
    keywords = _normalize(user_input)
    if not keywords:
        return ""
    
    primary_keyword = keywords[0]
    related_terms = query_related(primary_keyword)
    
    if not related_terms:
        return ""
    
    return f"[RELATED TOPICS]\n{', '.join(related_terms)}"
