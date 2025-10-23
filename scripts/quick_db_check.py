#!/usr/bin/env python3
"""
Quick Database Check
"""
import sqlite3
import os

def check_recent_events():
    conn = sqlite3.connect('./data_ollama/memoryos.db')
    cursor = conn.cursor()
    
    # Check total events
    cursor.execute('SELECT COUNT(*) FROM event_chain')
    total = cursor.fetchone()[0]
    print(f'Total events: {total}')
    
    # Check recent events (last 24 hours)
    cursor.execute('SELECT COUNT(*) FROM event_chain WHERE ts > datetime("now", "-24 hours")')
    recent = cursor.fetchone()[0]
    print(f'Recent events (24h): {recent}')
    
    # Check latest event
    cursor.execute('SELECT ts, type FROM event_chain ORDER BY ts DESC LIMIT 1')
    latest = cursor.fetchone()
    if latest:
        print(f'Latest event: {latest[0]} - {latest[1]}')
    
    conn.close()

if __name__ == "__main__":
    check_recent_events()
