# -*- coding: utf-8 -*-
"""
Memory Aging - Adjust the weight of memories based on their recency.
Older memories get lower weights, allowing the model to focus on recent ones.
"""
import os
from datetime import datetime, timedelta

# Configuration: Age decay settings
AGING_DECAY_RATE = float(os.environ.get("MEMORYOS_AGING_DECAY_RATE", "0.95"))  # 0.95 means 5% decay per interval
AGING_INTERVAL = int(os.environ.get("MEMORYOS_AGING_INTERVAL", "60"))  # in minutes
TIME_THRESHOLD = timedelta(minutes=AGING_INTERVAL)  # Max time to consider memories fresh

def age_memory(ts: str, weight: float) -> float:
    """Age the memory based on its timestamp and decay rate"""
    try:
        current_time = datetime.now()
        memory_time = datetime.fromisoformat(ts)
        time_diff = current_time - memory_time

        if time_diff > TIME_THRESHOLD:
            age_factor = (time_diff.total_seconds() / 60) / AGING_INTERVAL  # Decay factor based on time passed
            return weight * (AGING_DECAY_RATE ** age_factor)  # Apply decay
        else:
            return weight  # Fresh memory retains original weight
    except (ValueError, TypeError):
        # If timestamp parsing fails, return original weight
        return weight

def apply_aging_to_items(items: list, default_weight: float = 1.0) -> list:
    """Apply memory aging to a list of items with timestamps"""
    aged_items = []
    for item in items:
        ts = item.get("timestamp", item.get("ts", ""))
        if ts:
            aged_weight = age_memory(ts, default_weight)
            aged_item = {**item, "weight": aged_weight}
            aged_items.append(aged_item)
        else:
            # If no timestamp, use default weight
            aged_item = {**item, "weight": default_weight}
            aged_items.append(aged_item)
    return aged_items
