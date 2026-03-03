#!/usr/bin/env python3
"""
主力资金流获取脚本入口
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_ingestion.tushare.moneyflow import main

if __name__ == "__main__":
    main()
