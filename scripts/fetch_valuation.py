#!/usr/bin/env python3
"""
估值数据获取脚本入口
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_ingestion.tushare.valuation import main

if __name__ == "__main__":
    main()
