#!/usr/bin/env python3
"""
北向资金获取脚本入口
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_ingestion.akshare.north_money import main

if __name__ == "__main__":
    main()
