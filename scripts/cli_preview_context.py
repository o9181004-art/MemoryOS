# -*- coding: utf-8 -*-
"""
MemoryOS Context Preview CLI Tool
Dry-run preview for context injection testing
"""
import sys
from scripts.build_context import build_context

def main():
    user_input = " ".join(sys.argv[1:]).strip()
    if not user_input:
        print("usage: python -m scripts.cli_preview_context \"your input here\"")
        sys.exit(1)
    ctx = build_context(user_input)
    print(ctx or "[no context injected]")

if __name__ == "__main__":
    main()
