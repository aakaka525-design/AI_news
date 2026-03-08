"use client";

import { useState, useEffect } from "react";

interface TradingSession {
  isTrading: boolean;
  statusText: string;
}

/**
 * 获取当前中国时区 (UTC+8) 的日期时间信息
 */
function getChinaTime(): { day: number; hours: number; minutes: number } {
  const now = new Date();
  // 转换为 UTC+8 的毫秒时间戳
  const utc = now.getTime() + now.getTimezoneOffset() * 60_000;
  const chinaTime = new Date(utc + 8 * 3600_000);
  return {
    day: chinaTime.getDay(), // 0=Sunday, 6=Saturday
    hours: chinaTime.getHours(),
    minutes: chinaTime.getMinutes(),
  };
}

/**
 * 根据中国时区判断当前交易状态
 */
function computeSession(): TradingSession {
  const { day, hours, minutes } = getChinaTime();
  const timeMinutes = hours * 60 + minutes;

  // 周末
  if (day === 0 || day === 6) {
    return { isTrading: false, statusText: "周末休市" };
  }

  // 上午开盘前 (< 9:30)
  if (timeMinutes < 9 * 60 + 30) {
    return { isTrading: false, statusText: "盘前" };
  }

  // 上午盘中 (9:30 - 11:30)
  if (timeMinutes < 11 * 60 + 30) {
    return { isTrading: true, statusText: "盘中" };
  }

  // 午间休市 (11:30 - 13:00)
  if (timeMinutes < 13 * 60) {
    return { isTrading: false, statusText: "午间休市" };
  }

  // 下午盘中 (13:00 - 15:00)
  if (timeMinutes < 15 * 60) {
    return { isTrading: true, statusText: "盘中" };
  }

  // 已收盘 (>= 15:00)
  return { isTrading: false, statusText: "已收盘" };
}

/**
 * 判断当前是否处于 A 股交易时段的 React Hook
 *
 * - 时区: UTC+8 (中国)
 * - 交易日: 周一至周五
 * - 盘中时段: 9:30-11:30, 13:00-15:00
 * - 每分钟自动刷新
 */
export function useTradingSession(): TradingSession {
  const [session, setSession] = useState<TradingSession>(() => computeSession());

  useEffect(() => {
    // 立即计算一次
    setSession(computeSession());

    // 每 60 秒刷新
    const timer = setInterval(() => {
      setSession(computeSession());
    }, 60_000);

    return () => clearInterval(timer);
  }, []);

  return session;
}
