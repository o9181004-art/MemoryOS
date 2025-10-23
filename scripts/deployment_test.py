#!/usr/bin/env python3
"""
MemoryOS Deployment Readiness Test
"""
import sys
import os
import time
from pathlib import Path

# Add current directory to Python path
sys.path.append('.')

def test_core_functionality():
    """Test core MemoryOS functionality"""
    print("=== Core Functionality Test ===")
    
    try:
        # Test context building
        from scripts.build_context import build_context_main
        result = build_context_main("test deployment readiness")
        print(f"✅ Context Building: {'OK' if result is not None else 'No context (expected)'}")
        
        # Test memory graph
        from scripts.memory_graph import get_related_context
        related = get_related_context("test")
        print(f"✅ Memory Graph: OK")
        
        # Test self-healing
        from scripts.self_healing_graph import get_healing_stats
        stats = get_healing_stats()
        print(f"✅ Self-Healing: OK")
        
        # Test adaptive reasoning
        from scripts.adaptive_reasoning import get_reasoning_stats
        stats = get_reasoning_stats()
        print(f"✅ Adaptive Reasoning: OK")
        
        # Test governance
        from scripts.governance_layer import get_governance_stats
        stats = get_governance_stats()
        print(f"✅ Governance: OK")
        
        # Test meta-learning
        from scripts.meta_learning import get_meta_learning_stats
        stats = get_meta_learning_stats()
        print(f"✅ Meta-Learning: OK")
        
        return True
        
    except Exception as e:
        print(f"❌ Core functionality error: {e}")
        return False

def test_performance():
    """Test system performance"""
    print("\n=== Performance Test ===")
    
    try:
        start_time = time.perf_counter()
        
        # Test context building performance
        from scripts.build_context import build_context_main
        for i in range(10):
            build_context_main(f"performance test {i}")
        
        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 10 * 1000  # Convert to ms
        
        print(f"✅ Average context building time: {avg_time:.2f}ms")
        
        if avg_time < 100:  # Should be under 100ms
            print("✅ Performance: EXCELLENT")
            return True
        elif avg_time < 500:
            print("✅ Performance: GOOD")
            return True
        else:
            print("⚠️ Performance: SLOW")
            return False
            
    except Exception as e:
        print(f"❌ Performance test error: {e}")
        return False

def test_data_integrity():
    """Test data integrity"""
    print("\n=== Data Integrity Test ===")
    
    try:
        import sqlite3
        
        # Check database integrity
        conn = sqlite3.connect('./data_ollama/memoryos.db')
        cursor = conn.cursor()
        
        # Check for corruption
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        
        if result == "ok":
            print("✅ Database integrity: OK")
        else:
            print(f"❌ Database integrity: {result}")
            return False
        
        # Check data consistency
        cursor.execute("SELECT COUNT(*) FROM event_chain")
        count = cursor.fetchone()[0]
        
        if count > 0:
            print(f"✅ Data consistency: OK ({count} events)")
        else:
            print("⚠️ No events in database")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Data integrity error: {e}")
        return False

def test_logging():
    """Test logging functionality"""
    print("\n=== Logging Test ===")
    
    try:
        # Check log directories exist
        log_dirs = ['./logs', './logs_ollama']
        
        for log_dir in log_dirs:
            if os.path.exists(log_dir):
                print(f"✅ Log directory exists: {log_dir}")
            else:
                print(f"⚠️ Log directory missing: {log_dir}")
        
        # Test log writing
        test_log_path = './logs/deployment_test.log'
        with open(test_log_path, 'w') as f:
            f.write(f"Deployment test at {time.time()}\n")
        
        if os.path.exists(test_log_path):
            print("✅ Log writing: OK")
            os.remove(test_log_path)  # Clean up
        else:
            print("❌ Log writing: FAILED")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Logging test error: {e}")
        return False

def test_configuration():
    """Test configuration"""
    print("\n=== Configuration Test ===")
    
    try:
        # Check critical environment variables
        critical_vars = [
            'MEMORYOS_GRAPH_ENABLED',
            'MEMORYOS_META_LEARNING_ENABLED',
            'MEMORYOS_GOVERNANCE_ENABLED'
        ]
        
        for var in critical_vars:
            value = os.getenv(var, 'not set')
            if value != 'not set':
                print(f"✅ {var}: {value}")
            else:
                print(f"⚠️ {var}: not set (using default)")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration test error: {e}")
        return False

def main():
    """Run all deployment readiness tests"""
    print("MemoryOS Deployment Readiness Test")
    print("=" * 50)
    
    tests = [
        test_core_functionality,
        test_performance,
        test_data_integrity,
        test_logging,
        test_configuration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"Deployment Readiness: {passed}/{total} tests passed")
    
    if passed == total:
        print("🚀 READY FOR DEPLOYMENT")
        return True
    else:
        print("⚠️ NOT READY FOR DEPLOYMENT")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
