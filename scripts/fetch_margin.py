#!/usr/bin/env python3
"""融资融券数据获取脚本"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_ingestion.akshare.margin_trading import main

if __name__ == "__main__":
    main()
