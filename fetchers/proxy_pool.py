#!/usr/bin/env python3
"""
代理池管理模块

从 89ip.cn 获取免费代理，支持自动轮换和失效剔除
"""

import re
import time
import random
import requests
from typing import Optional
from datetime import datetime


class ProxyPool:
    """代理池管理器"""

    # 青果网按量代理 API（每次获取100个）
    PROXY_API = "https://share.proxy.qg.net/get?key=4IUZXC7F&num=100&format=json"

    # 账密认证信息
    AUTH_KEY = "4IUZXC7F"
    AUTH_PWD = "D3E9D5EF62D7"

    # 代理有效期（秒）- 青果网短效代理2分钟
    PROXY_TTL = 100  # 设为100秒，留10秒余量

    def __init__(self, min_proxies: int = 5):
        self.proxies: list[str] = []
        self.bad_proxies: set[str] = set()
        self.min_proxies = min_proxies
        self.last_fetch = 0
        self.current_index = 0

    def is_expired(self) -> bool:
        """检查代理是否已过期"""
        if self.last_fetch == 0:
            return True
        return (time.time() - self.last_fetch) > self.PROXY_TTL

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [代理池] {msg}", flush=True)

    def fetch_proxies(self) -> list[str]:
        """从青果网 API 获取代理列表"""
        try:
            resp = requests.get(self.PROXY_API, timeout=10)
            data = resp.json()

            if data.get("code") == "SUCCESS":
                # 成功获取，解析 server 字段（格式: IP:PORT）
                proxies = [item["server"] for item in data.get("data", []) if "server" in item]
                # 过滤已知失效的
                valid = [p for p in proxies if p not in self.bad_proxies]

                if valid:
                    self.log(f"获取到 {len(valid)} 个代理（青果网）")
                    self.last_fetch = time.time()

                return valid
            else:
                self.log(f"获取代理失败: {data.get('message', '未知错误')}")
                return []
        except Exception as e:
            self.log(f"获取代理失败: {e}")
            return []

    def ensure_proxies(self):
        """确保有足够的代理"""
        if len(self.proxies) < self.min_proxies:
            new_proxies = self.fetch_proxies()
            self.proxies.extend(new_proxies)
            # 打乱顺序
            random.shuffle(self.proxies)

    def get_fresh_proxy(self) -> Optional[str]:
        """实时获取一个新代理（不缓存）"""
        try:
            # 每次获取10个，随机选一个
            resp = requests.get(
                "https://share.proxy.qg.net/get?key=4IUZXC7F&num=10&format=json",
                timeout=5
            )
            data = resp.json()
            if data.get("code") == "SUCCESS" and data.get("data"):
                import random
                proxies = [p["server"] for p in data["data"]]
                return random.choice(proxies)
        except Exception:  # noqa: BLE001
            pass
        return self.get_proxy()  # 回退到缓存

    def get_verified_proxy(self, max_attempts: int = 5) -> Optional[str]:
        """获取一个经过验证可用的代理"""
        for _ in range(max_attempts):
            proxy = self.get_fresh_proxy()
            if not proxy:
                continue

            # 使用国内站点快速测试代理可用性
            proxy_url = f"http://{self.AUTH_KEY}:{self.AUTH_PWD}@{proxy}"
            try:
                resp = requests.get(
                    "http://test.ipw.cn",  # 国内测试站点
                    proxies={"http": proxy_url, "https": proxy_url},
                    timeout=5
                )
                if resp.status_code == 200:
                    return proxy
            except Exception:  # noqa: BLE001
                pass

        return None  # 所有尝试都失败

    def get_proxy(self) -> Optional[str]:
        """获取一个代理"""
        self.ensure_proxies()

        if not self.proxies:
            return None

        # 轮换使用
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return self.proxies[self.current_index]

    def mark_bad(self, proxy: str):
        """标记代理为失效"""
        self.bad_proxies.add(proxy)
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            self.log(f"移除失效代理: {proxy}")

    def get_proxy_dict(self) -> Optional[dict]:
        """获取 requests 格式的代理字典（使用账密模式）"""
        proxy = self.get_proxy()
        if proxy:
            # 账密模式: http://user:password@proxy_ip:port
            proxy_url = f"http://{self.AUTH_KEY}:{self.AUTH_PWD}@{proxy}"
            return {
                "http": proxy_url,
                "https": proxy_url
            }
        return None


def test_proxy(proxy: str, auth_key: str, auth_pwd: str, timeout: int = 5) -> bool:
    """测试代理是否可用（账密模式）"""
    try:
        proxy_url = f"http://{auth_key}:{auth_pwd}@{proxy}"
        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }
        resp = requests.get(
            "http://test.ipw.cn",  # 国内测试站点
            proxies=proxies,
            timeout=timeout
        )
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


# 全局代理池实例
proxy_pool = ProxyPool()


def main():
    """测试代理池"""
    print("=== 代理池测试（账密模式）===")

    pool = ProxyPool(min_proxies=5)

    # 获取代理
    for i in range(5):
        proxy = pool.get_proxy()
        if proxy:
            print(f"代理 {i+1}: {proxy}")
            # 测试可用性（使用账密）
            if test_proxy(proxy, pool.AUTH_KEY, pool.AUTH_PWD, timeout=5):
                print(f"  ✅ 可用")
            else:
                print(f"  ❌ 不可用")
                pool.mark_bad(proxy)
        else:
            print(f"代理 {i+1}: 无可用代理")

    print(f"\n剩余代理: {len(pool.proxies)}")
    print(f"失效代理: {len(pool.bad_proxies)}")


if __name__ == "__main__":
    main()
