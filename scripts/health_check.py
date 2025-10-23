#!/usr/bin/env python3
"""
MemoryOS System Health Check Script
"""
import os
import sqlite3
import json
from pathlib import Path

def check_database():
    """Check database connectivity and integrity"""
    print("=== Database Health Check ===")
    try:
        db_path = os.getenv('MEMORYOS_DB', './data_ollama/memoryos.db')
        print(f"Database Path: {db_path}")
        print(f"Database Exists: {os.path.exists(db_path)}")
        
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            print(f"Tables: {[t[0] for t in tables]}")
            
            # Check event_chain table
            if any('event_chain' in t[0] for t in tables):
                cursor.execute("SELECT COUNT(*) FROM event_chain")
                count = cursor.fetchone()[0]
                print(f"Event Chain Records: {count}")
            
            conn.close()
            print("✅ Database connection successful")
        else:
            print("⚠️ Database file not found")
            
    except Exception as e:
        print(f"❌ Database error: {e}")

def check_logs():
    """Check log files"""
    print("\n=== Log Files Check ===")
    log_dirs = ['./logs', './logs_ollama']
    
    for log_dir in log_dirs:
        if os.path.exists(log_dir):
            print(f"Log Directory: {log_dir}")
            files = os.listdir(log_dir)
            for file in files:
                file_path = os.path.join(log_dir, file)
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path)
                    print(f"  {file}: {size} bytes")
        else:
            print(f"⚠️ Log directory not found: {log_dir}")

def check_data_files():
    """Check data files"""
    print("\n=== Data Files Check ===")
    data_files = [
        './data_ollama/memoryos.db',
        './data_ollama/memory_graph.json',
        './data_ollama/meta_policy.json',
        './data_ollama/approvals.json'
    ]
    
    for file_path in data_files:
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            print(f"✅ {file_path}: {size} bytes")
        else:
            print(f"⚠️ {file_path}: Not found")

def check_environment():
    """Check environment configuration"""
    print("\n=== Environment Configuration ===")
    env_vars = [
        'MEMORYOS_CONTEXT_ENABLED',
        'MEMORYOS_GRAPH_ENABLED', 
        'MEMORYOS_META_LEARNING_ENABLED',
        'MEMORYOS_GOVERNANCE_ENABLED',
        'MEMORYOS_REASONING_ENABLED',
        'MEMORYOS_HEALING_ENABLED',
        'MEMORYOS_DB'
    ]
    
    for var in env_vars:
        value = os.getenv(var, 'not set')
        print(f"{var}: {value}")

def check_modules():
    """Check if all modules can be imported"""
    print("\n=== Module Import Check ===")
    modules = [
        'scripts.build_context',
        'scripts.memory_graph',
        'scripts.self_healing_graph',
        'scripts.adaptive_reasoning',
        'scripts.governance_layer',
        'scripts.meta_learning'
    ]
    
    for module in modules:
        try:
            __import__(module)
            print(f"✅ {module}: OK")
        except Exception as e:
            print(f"❌ {module}: {e}")

if __name__ == "__main__":
    print("MemoryOS System Health Check")
    print("=" * 50)
    
    check_database()
    check_logs()
    check_data_files()
    check_environment()
    check_modules()
    
    print("\n" + "=" * 50)
    print("Health check completed")
