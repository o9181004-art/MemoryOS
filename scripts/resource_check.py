#!/usr/bin/env python3
"""
System Resource Check
"""
import os
import shutil

def check_resources():
    """Check system resources"""
    print("=== System Resources ===")
    
    try:
        # Check disk space
        total, used, free = shutil.disk_usage(".")
        print(f"Disk Space:")
        print(f"  Total: {total // (1024**3)} GB")
        print(f"  Used: {used // (1024**3)} GB")
        print(f"  Free: {free // (1024**3)} GB")
        print(f"  Usage: {(used/total)*100:.1f}%")
        
        # Check MemoryOS specific files
        data_files = [
            './data_ollama/memoryos.db',
            './logs/event_log.jsonl',
            './logs_ollama/event_log.jsonl'
        ]
        
        total_size = 0
        for file_path in data_files:
            if os.path.exists(file_path):
                size = os.path.getsize(file_path)
                total_size += size
                print(f"  {file_path}: {size // (1024**2)} MB")
        
        print(f"Total MemoryOS data: {total_size // (1024**2)} MB")
        
        return True
        
    except Exception as e:
        print(f"❌ Resource check error: {e}")
        return False

if __name__ == "__main__":
    check_resources()
