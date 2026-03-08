# Phase 4: 前端可视化 Implementation Plan

> **状态：已完成**
> Next.js 14 前端已建成，包含 Dashboard、新闻、市场、筛选、自选、设置等页面及 BFF 层，计划核心目标已达成。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建 Next.js 14 前端，提供 Dashboard、新闻、个股详情等页面，对接现有 FastAPI 后端 30+ API 端点。

**Architecture:** Next.js 14 App Router + shadcn/ui + Tailwind CSS 作为 UI 层；TanStack Query 管理 API 数据缓存与轮询；TradingView Lightweight Charts 渲染 K 线图；ECharts 渲染饼图/热力图。前端通过 `NEXT_PUBLIC_API_URL` 环境变量连接 FastAPI 后端（浏览器端 `http://localhost:8000`，SSR 端 `http://dashboard:8000`）。

**Tech Stack:** Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui, TanStack Query v5, TradingView Lightweight Charts, ECharts (echarts-for-react), Docker multi-stage build

---

## 前置说明

### 现有后端 API 端点（前端会用到的核心端点）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/health` | GET | 健康检查 → Dashboard 状态卡 |
| `/api/news` | GET | 新闻列表 → 新闻页面 |
| `/api/hotspots` | GET | 热点统计 → Dashboard 热词云 |
| `/api/rss` | GET | RSS 列表 → 新闻页面标签 |
| `/api/rss/sentiment_stats` | GET | 情感统计 → Dashboard 情感饼图 |
| `/api/research/reports` | GET | 研报列表 → Dashboard + 个股详情 |
| `/api/research/stats` | GET | 评级统计 → Dashboard 评级分布图 |
| `/api/anomalies` | GET | 异常信号 → Dashboard + 异常页面 |
| `/api/anomalies/stats` | GET | 异常统计 → Dashboard 异常概览 |
| `/api/scheduler/jobs` | GET | 调度状态 → 设置页面 |
| `/api/integrity/freshness` | GET | 数据新鲜度 → 设置页面 |
| `/api/calendar/is_trading_day` | GET | 交易日判断 → 全局状态栏 |

### 目标页面结构

```
frontend/
├── app/
│   ├── layout.tsx          # 根布局（侧边栏 + 顶栏）
│   ├── page.tsx            # Dashboard 首页
│   ├── news/page.tsx       # 新闻中心
│   ├── stock/[code]/page.tsx  # 个股详情
│   ├── strategy/
│   │   └── anomaly/page.tsx   # 异常信号
│   └── settings/page.tsx   # 系统设置
```

---

## Task 1: Next.js 项目脚手架 + shadcn/ui

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/next.config.ts`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/page.tsx`
- Create: `frontend/lib/utils.ts`
- Create: `frontend/.env.local`

**Step 1: 初始化 Next.js 项目**

```bash
cd /Users/xa/Desktop/projiect/AI_news
npx create-next-app@14 frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src-dir=false \
  --import-alias="@/*" \
  --no-turbopack
```

选项说明：不使用 src 目录（app 直接在根），`@/*` 别名方便导入。

**Step 2: 安装 shadcn/ui**

```bash
cd frontend
npx shadcn@latest init -d
```

选择默认配置。这会生成 `components.json`、更新 `tailwind.config.ts`、创建 `lib/utils.ts`。

**Step 3: 安装核心 shadcn 组件**

```bash
npx shadcn@latest add card button badge separator skeleton tabs scroll-area sheet input
```

**Step 4: 安装项目依赖**

```bash
npm install @tanstack/react-query @tanstack/react-query-devtools
npm install lightweight-charts
npm install echarts echarts-for-react
npm install lucide-react
npm install date-fns
```

**Step 5: 配置环境变量**

创建 `frontend/.env.local`：
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Step 6: 创建 API 基础 URL 配置**

创建 `frontend/lib/api-config.ts`：
```typescript
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
```

**Step 7: 验证开发服务器启动**

```bash
cd frontend && npm run dev
```

预期：`http://localhost:3000` 显示 Next.js 默认页面。

**Step 8: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): scaffold Next.js 14 + shadcn/ui + dependencies"
```

---

## Task 2: API Client + TypeScript 类型定义

**Files:**
- Create: `frontend/lib/types.ts`
- Create: `frontend/lib/api.ts`
- Create: `frontend/lib/query-provider.tsx`
- Modify: `frontend/app/layout.tsx`

**Step 1: 定义 TypeScript 类型**

创建 `frontend/lib/types.ts`（对应后端返回的 JSON 结构）：

```typescript
// ===== News =====
export interface NewsItem {
  id: number;
  title: string;
  content: string;
  content_html: string;
  received_at: string;
  cleaned_data?: {
    summary?: string;
    facts?: Array<{ fact: string; category: string }>;
    hotspots?: string[];
    keywords?: string[];
    cleaned_at?: string;
  } | null;
}

export interface NewsListResponse {
  total: number;
  data: NewsItem[];
}

// ===== Hotspots =====
export interface HotspotItem {
  keyword: string;
  count: number;
}

export interface HotspotsResponse {
  total: number;
  data: HotspotItem[];
}

// ===== RSS =====
export interface RssItem {
  id: number;
  title: string;
  link?: string;
  summary?: string;
  source?: string;
  published?: string;
  sentiment_score?: number;
  sentiment_label?: string;
}

export interface RssResponse {
  total: number;
  data: RssItem[];
}

export interface SentimentStats {
  total: number;
  positive: number;
  negative: number;
  neutral: number;
}

// ===== Research Reports =====
export interface ResearchReport {
  id?: number;
  ts_code?: string;
  stock_code?: string;
  stock_name?: string;
  title: string;
  institution?: string;
  rating?: string;
  target_price?: number | null;
  publish_date?: string;
  key_points?: string[];
  sentiment_score?: number | null;
}

export interface ResearchReportsResponse {
  total: number;
  data: ResearchReport[];
}

export interface RatingStats {
  [rating: string]: number;
}

// ===== Anomalies =====
export interface AnomalySignal {
  id?: number;
  stock_code: string;
  stock_name?: string;
  date?: string;
  signal_type: string;
  description?: string;
  severity?: string;
}

export interface AnomaliesResponse {
  total: number;
  data: AnomalySignal[];
}

export interface AnomalyStats {
  [signal_type: string]: number;
}

// ===== Health =====
export interface HealthResponse {
  status: "healthy" | "degraded";
  db: { url: string; ok: boolean; error?: string | null };
  scheduler: { running: boolean; error?: string | null };
  version: string;
}

// ===== Scheduler =====
export interface SchedulerJob {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  next_run: string | null;
  last_run: string | null;
  last_result: string | null;
  run_count: number;
}

export interface SchedulerJobsResponse {
  running: boolean;
  jobs: SchedulerJob[];
}

// ===== Calendar =====
export interface TradingDayResponse {
  date: string;
  is_trading_day: boolean;
  latest_trading_day: string;
}

// ===== Data Freshness =====
export interface TableFreshness {
  table: string;
  latest_date?: string;
  row_count?: number;
}

export interface FreshnessResponse {
  tables: TableFreshness[];
}
```

**Step 2: 创建 API 客户端**

创建 `frontend/lib/api.ts`：

```typescript
import { API_BASE_URL } from "./api-config";
import type {
  AnomaliesResponse,
  AnomalyStats,
  FreshnessResponse,
  HealthResponse,
  HotspotsResponse,
  NewsListResponse,
  RatingStats,
  ResearchReportsResponse,
  RssResponse,
  SchedulerJobsResponse,
  SentimentStats,
  TradingDayResponse,
} from "./types";

async function fetchApi<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, v);
    });
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// Health
export const fetchHealth = () => fetchApi<HealthResponse>("/health");

// News
export const fetchNews = (limit = 50) =>
  fetchApi<NewsListResponse>("/api/news", { limit: String(limit) });

// Hotspots
export const fetchHotspots = () => fetchApi<HotspotsResponse>("/api/hotspots");

// RSS
export const fetchRss = (limit = 50) =>
  fetchApi<RssResponse>("/api/rss", { limit: String(limit) });

export const fetchSentimentStats = () =>
  fetchApi<SentimentStats>("/api/rss/sentiment_stats");

// Research Reports
export const fetchReports = (stockCode?: string, limit = 20) =>
  fetchApi<ResearchReportsResponse>("/api/research/reports", {
    ...(stockCode ? { stock_code: stockCode } : {}),
    limit: String(limit),
  });

export const fetchRatingStats = () =>
  fetchApi<RatingStats>("/api/research/stats");

// Anomalies
export const fetchAnomalies = (stockCode?: string, days = 7, limit = 50) =>
  fetchApi<AnomaliesResponse>("/api/anomalies", {
    ...(stockCode ? { stock_code: stockCode } : {}),
    days: String(days),
    limit: String(limit),
  });

export const fetchAnomalyStats = () =>
  fetchApi<AnomalyStats>("/api/anomalies/stats");

// Scheduler
export const fetchSchedulerJobs = () =>
  fetchApi<SchedulerJobsResponse>("/api/scheduler/jobs");

// Calendar
export const fetchTradingDay = (date?: string) =>
  fetchApi<TradingDayResponse>(
    "/api/calendar/is_trading_day",
    date ? { date } : {},
  );

// Freshness
export const fetchFreshness = () =>
  fetchApi<FreshnessResponse>("/api/integrity/freshness");
```

**Step 3: 创建 QueryProvider**

创建 `frontend/lib/query-provider.tsx`：

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState, type ReactNode } from "react";

export function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30 * 1000, // 30秒
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
```

**Step 4: 在 layout.tsx 引入 QueryProvider**

修改 `frontend/app/layout.tsx`：

```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/lib/query-provider";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AI News Dashboard",
  description: "AI 驱动的 A 股情报分析平台",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className={inter.className}>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
```

**Step 5: Commit**

```bash
git add frontend/lib/ frontend/app/layout.tsx
git commit -m "feat(frontend): add API client, TypeScript types, and QueryProvider"
```

---

## Task 3: App Shell（侧边栏 + 顶栏 + 响应式布局）

**Files:**
- Create: `frontend/components/layout/sidebar.tsx`
- Create: `frontend/components/layout/header.tsx`
- Create: `frontend/components/layout/app-shell.tsx`
- Modify: `frontend/app/layout.tsx`

**Step 1: 创建侧边栏组件**

创建 `frontend/components/layout/sidebar.tsx`：

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Newspaper,
  TrendingUp,
  AlertTriangle,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/news", label: "新闻中心", icon: Newspaper },
  { href: "/strategy/anomaly", label: "异常信号", icon: AlertTriangle },
  { href: "/settings", label: "系统设置", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex md:w-56 md:flex-col md:border-r bg-muted/40">
      <div className="flex h-14 items-center border-b px-4 font-semibold">
        <TrendingUp className="mr-2 h-5 w-5" />
        AI News
      </div>
      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
```

**Step 2: 创建顶栏组件**

创建 `frontend/components/layout/header.tsx`：

```tsx
"use client";

import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Menu, TrendingUp } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/news", label: "新闻中心" },
  { href: "/strategy/anomaly", label: "异常信号" },
  { href: "/settings", label: "系统设置" },
];

export function Header() {
  const pathname = usePathname();

  return (
    <header className="flex h-14 items-center border-b px-4 md:px-6">
      {/* Mobile menu */}
      <Sheet>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" className="md:hidden">
            <Menu className="h-5 w-5" />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-56 p-0">
          <div className="flex h-14 items-center border-b px-4 font-semibold">
            <TrendingUp className="mr-2 h-5 w-5" />
            AI News
          </div>
          <nav className="space-y-1 p-2">
            {navItems.map((item) => {
              const active =
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "block rounded-md px-3 py-2 text-sm",
                    active
                      ? "bg-primary/10 text-primary font-medium"
                      : "text-muted-foreground",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </SheetContent>
      </Sheet>

      <div className="flex-1" />

      {/* 右侧可预留头像 / 暗色切换等 */}
    </header>
  );
}
```

**Step 3: 创建 AppShell**

创建 `frontend/components/layout/app-shell.tsx`：

```tsx
import type { ReactNode } from "react";
import { Sidebar } from "./sidebar";
import { Header } from "./header";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
```

**Step 4: 更新 layout.tsx 使用 AppShell**

修改 `frontend/app/layout.tsx`，在 `<QueryProvider>` 内嵌套 `<AppShell>`：

```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/lib/query-provider";
import { AppShell } from "@/components/layout/app-shell";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AI News Dashboard",
  description: "AI 驱动的 A 股情报分析平台",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className={inter.className}>
        <QueryProvider>
          <AppShell>{children}</AppShell>
        </QueryProvider>
      </body>
    </html>
  );
}
```

**Step 5: 验证布局**

```bash
cd frontend && npm run dev
```

预期：`http://localhost:3000` 展示带侧边栏的空壳布局，手机宽度下侧边栏自动收起、顶栏汉堡菜单可展开。

**Step 6: Commit**

```bash
git add frontend/components/layout/ frontend/app/layout.tsx
git commit -m "feat(frontend): add app shell with responsive sidebar and header"
```

---

## Task 4: Dashboard 首页

**Files:**
- Create: `frontend/app/page.tsx`
- Create: `frontend/components/dashboard/health-card.tsx`
- Create: `frontend/components/dashboard/hotspot-cloud.tsx`
- Create: `frontend/components/dashboard/sentiment-pie.tsx`
- Create: `frontend/components/dashboard/anomaly-list.tsx`
- Create: `frontend/components/dashboard/report-summary.tsx`
- Create: `frontend/lib/hooks.ts`

**Step 1: 创建自定义 hooks**

创建 `frontend/lib/hooks.ts`（封装 TanStack Query hooks）：

```typescript
import { useQuery } from "@tanstack/react-query";
import {
  fetchHealth,
  fetchHotspots,
  fetchSentimentStats,
  fetchAnomalies,
  fetchAnomalyStats,
  fetchReports,
  fetchRatingStats,
  fetchNews,
  fetchRss,
  fetchSchedulerJobs,
  fetchFreshness,
  fetchTradingDay,
} from "./api";

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 60_000 });

export const useHotspots = () =>
  useQuery({ queryKey: ["hotspots"], queryFn: fetchHotspots });

export const useSentimentStats = () =>
  useQuery({ queryKey: ["sentiment-stats"], queryFn: fetchSentimentStats });

export const useAnomalies = (stockCode?: string, days = 7, limit = 50) =>
  useQuery({
    queryKey: ["anomalies", stockCode, days, limit],
    queryFn: () => fetchAnomalies(stockCode, days, limit),
  });

export const useAnomalyStats = () =>
  useQuery({ queryKey: ["anomaly-stats"], queryFn: fetchAnomalyStats });

export const useReports = (stockCode?: string, limit = 20) =>
  useQuery({
    queryKey: ["reports", stockCode, limit],
    queryFn: () => fetchReports(stockCode, limit),
  });

export const useRatingStats = () =>
  useQuery({ queryKey: ["rating-stats"], queryFn: fetchRatingStats });

export const useNews = (limit = 50) =>
  useQuery({ queryKey: ["news", limit], queryFn: () => fetchNews(limit) });

export const useRss = (limit = 50) =>
  useQuery({ queryKey: ["rss", limit], queryFn: () => fetchRss(limit) });

export const useSchedulerJobs = () =>
  useQuery({ queryKey: ["scheduler-jobs"], queryFn: fetchSchedulerJobs });

export const useFreshness = () =>
  useQuery({ queryKey: ["freshness"], queryFn: fetchFreshness });

export const useTradingDay = (date?: string) =>
  useQuery({ queryKey: ["trading-day", date], queryFn: () => fetchTradingDay(date) });
```

**Step 2: 健康状态卡**

创建 `frontend/components/dashboard/health-card.tsx`：

```tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Activity } from "lucide-react";
import { useHealth } from "@/lib/hooks";

export function HealthCard() {
  const { data, isLoading, isError } = useHealth();

  if (isLoading) return <Skeleton className="h-28" />;
  if (isError || !data) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">系统状态</CardTitle>
        </CardHeader>
        <CardContent>
          <Badge variant="destructive">离线</Badge>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">系统状态</CardTitle>
        <Activity className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <Badge variant={data.status === "healthy" ? "default" : "secondary"}>
          {data.status === "healthy" ? "正常运行" : "部分降级"}
        </Badge>
        <p className="mt-2 text-xs text-muted-foreground">
          数据库: {data.db.ok ? "正常" : "异常"} · 调度器:{" "}
          {data.scheduler.running ? "运行中" : "已停止"} · v{data.version}
        </p>
      </CardContent>
    </Card>
  );
}
```

**Step 3: 热点词云**

创建 `frontend/components/dashboard/hotspot-cloud.tsx`：

```tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useHotspots } from "@/lib/hooks";

export function HotspotCloud() {
  const { data, isLoading } = useHotspots();

  if (isLoading) return <Skeleton className="h-40" />;

  const items = data?.data ?? [];
  const maxCount = Math.max(...items.map((i) => i.count), 1);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">热点关键词</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {items.slice(0, 20).map((item) => {
            const scale = 0.75 + (item.count / maxCount) * 0.5;
            return (
              <Badge
                key={item.keyword}
                variant="outline"
                style={{ fontSize: `${scale}rem` }}
              >
                {item.keyword}
                <span className="ml-1 text-muted-foreground">{item.count}</span>
              </Badge>
            );
          })}
        </div>
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground">暂无热点数据</p>
        )}
      </CardContent>
    </Card>
  );
}
```

**Step 4: 情感分析饼图**

创建 `frontend/components/dashboard/sentiment-pie.tsx`：

```tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSentimentStats } from "@/lib/hooks";
import dynamic from "next/dynamic";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

export function SentimentPie() {
  const { data, isLoading } = useSentimentStats();

  if (isLoading) return <Skeleton className="h-52" />;

  if (!data || data.total === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">市场情绪</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">暂无情感分析数据</p>
        </CardContent>
      </Card>
    );
  }

  const option = {
    tooltip: { trigger: "item" },
    series: [
      {
        type: "pie",
        radius: ["40%", "70%"],
        data: [
          { value: data.positive, name: "积极", itemStyle: { color: "#22c55e" } },
          { value: data.neutral, name: "中性", itemStyle: { color: "#94a3b8" } },
          { value: data.negative, name: "消极", itemStyle: { color: "#ef4444" } },
        ],
        label: { formatter: "{b}: {d}%" },
      },
    ],
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">市场情绪</CardTitle>
      </CardHeader>
      <CardContent>
        <ReactECharts option={option} style={{ height: 200 }} />
      </CardContent>
    </Card>
  );
}
```

**Step 5: 异常信号列表**

创建 `frontend/components/dashboard/anomaly-list.tsx`：

```tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertTriangle } from "lucide-react";
import { useAnomalies } from "@/lib/hooks";

export function AnomalyList() {
  const { data, isLoading } = useAnomalies(undefined, 3, 10);

  if (isLoading) return <Skeleton className="h-52" />;

  const items = data?.data ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">最新异常信号</CardTitle>
        <AlertTriangle className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">近期无异常信号</p>
        ) : (
          <ScrollArea className="h-44">
            <div className="space-y-2">
              {items.map((item, i) => (
                <div
                  key={`${item.stock_code}-${item.signal_type}-${i}`}
                  className="flex items-center justify-between rounded-md border p-2 text-sm"
                >
                  <div>
                    <span className="font-medium">{item.stock_code}</span>
                    {item.stock_name && (
                      <span className="ml-1 text-muted-foreground">
                        {item.stock_name}
                      </span>
                    )}
                  </div>
                  <Badge variant="outline">{item.signal_type}</Badge>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
```

**Step 6: 研报概览**

创建 `frontend/components/dashboard/report-summary.tsx`：

```tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FileText } from "lucide-react";
import { useReports } from "@/lib/hooks";

export function ReportSummary() {
  const { data, isLoading } = useReports(undefined, 8);

  if (isLoading) return <Skeleton className="h-52" />;

  const items = data?.data ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">最新研报</CardTitle>
        <FileText className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无研报数据</p>
        ) : (
          <ScrollArea className="h-44">
            <div className="space-y-2">
              {items.map((item, i) => (
                <div
                  key={`${item.ts_code ?? item.stock_code}-${i}`}
                  className="flex items-start justify-between rounded-md border p-2 text-sm"
                >
                  <div className="flex-1 min-w-0">
                    <p className="truncate font-medium">{item.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {item.institution} · {item.publish_date}
                    </p>
                  </div>
                  {item.rating && (
                    <Badge variant="secondary" className="ml-2 shrink-0">
                      {item.rating}
                    </Badge>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
```

**Step 7: 组装 Dashboard 页面**

修改 `frontend/app/page.tsx`：

```tsx
import { HealthCard } from "@/components/dashboard/health-card";
import { HotspotCloud } from "@/components/dashboard/hotspot-cloud";
import { SentimentPie } from "@/components/dashboard/sentiment-pie";
import { AnomalyList } from "@/components/dashboard/anomaly-list";
import { ReportSummary } from "@/components/dashboard/report-summary";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* 第一行：状态卡 + 情感饼图 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <HealthCard />
        <SentimentPie />
        <HotspotCloud />
      </div>

      {/* 第二行：异常信号 + 最新研报 */}
      <div className="grid gap-4 md:grid-cols-2">
        <AnomalyList />
        <ReportSummary />
      </div>
    </div>
  );
}
```

**Step 8: 验证 Dashboard 渲染**

```bash
cd frontend && npm run dev
```

预期：`http://localhost:3000` 显示包含 5 个卡片组件的 Dashboard 页面。如果后端未启动，各卡片显示 loading skeleton 后降级为空状态 / 错误状态。

**Step 9: Commit**

```bash
git add frontend/lib/hooks.ts frontend/components/dashboard/ frontend/app/page.tsx
git commit -m "feat(frontend): add dashboard page with health, hotspots, sentiment, anomalies, reports"
```

---

## Task 5: 新闻中心页面

**Files:**
- Create: `frontend/app/news/page.tsx`
- Create: `frontend/components/news/news-list.tsx`
- Create: `frontend/components/news/rss-list.tsx`

**Step 1: 创建新闻列表组件**

创建 `frontend/components/news/news-list.tsx`：

```tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useNews } from "@/lib/hooks";
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";

export function NewsList() {
  const { data, isLoading } = useNews(100);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    );
  }

  const items = data?.data ?? [];

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无新闻数据</p>;
  }

  return (
    <ScrollArea className="h-[calc(100vh-14rem)]">
      <div className="space-y-3">
        {items.map((item) => (
          <Card key={item.id}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="text-sm font-medium leading-tight">
                  {item.title}
                </CardTitle>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {item.received_at
                    ? formatDistanceToNow(new Date(item.received_at), {
                        addSuffix: true,
                        locale: zhCN,
                      })
                    : ""}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              {item.cleaned_data?.summary ? (
                <p className="text-sm text-muted-foreground">
                  {item.cleaned_data.summary}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground line-clamp-2">
                  {item.content}
                </p>
              )}
              {item.cleaned_data?.hotspots &&
                item.cleaned_data.hotspots.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {item.cleaned_data.hotspots.map((h) => (
                      <Badge key={h} variant="outline" className="text-xs">
                        {h}
                      </Badge>
                    ))}
                  </div>
                )}
            </CardContent>
          </Card>
        ))}
      </div>
    </ScrollArea>
  );
}
```

**Step 2: 创建 RSS 列表组件**

创建 `frontend/components/news/rss-list.tsx`：

```tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useRss } from "@/lib/hooks";

function sentimentColor(label?: string): "default" | "secondary" | "destructive" {
  if (label === "positive") return "default";
  if (label === "negative") return "destructive";
  return "secondary";
}

export function RssList() {
  const { data, isLoading } = useRss(100);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
    );
  }

  const items = data?.data ?? [];

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无 RSS 数据</p>;
  }

  return (
    <ScrollArea className="h-[calc(100vh-14rem)]">
      <div className="space-y-3">
        {items.map((item) => (
          <Card key={item.id}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="text-sm font-medium leading-tight">
                  {item.link ? (
                    <a
                      href={item.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline"
                    >
                      {item.title}
                    </a>
                  ) : (
                    item.title
                  )}
                </CardTitle>
                {item.sentiment_label && (
                  <Badge
                    variant={sentimentColor(item.sentiment_label)}
                    className="shrink-0 text-xs"
                  >
                    {item.sentiment_label}
                  </Badge>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {item.summary && (
                <p className="text-sm text-muted-foreground line-clamp-2">
                  {item.summary}
                </p>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                {item.source} · {item.published}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </ScrollArea>
  );
}
```

**Step 3: 组装新闻页面**

创建 `frontend/app/news/page.tsx`：

```tsx
"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { NewsList } from "@/components/news/news-list";
import { RssList } from "@/components/news/rss-list";

export default function NewsPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">新闻中心</h1>
      <Tabs defaultValue="webhook">
        <TabsList>
          <TabsTrigger value="webhook">推送新闻</TabsTrigger>
          <TabsTrigger value="rss">RSS 订阅</TabsTrigger>
        </TabsList>
        <TabsContent value="webhook">
          <NewsList />
        </TabsContent>
        <TabsContent value="rss">
          <RssList />
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

**Step 4: 验证**

```bash
cd frontend && npm run dev
```

预期：`http://localhost:3000/news` 显示 Tabs 切换的新闻列表。

**Step 5: Commit**

```bash
git add frontend/components/news/ frontend/app/news/
git commit -m "feat(frontend): add news center page with webhook and RSS tabs"
```

---

## Task 6: 异常信号页面 + 设置页面

**Files:**
- Create: `frontend/app/strategy/anomaly/page.tsx`
- Create: `frontend/app/settings/page.tsx`

**Step 1: 异常信号页面**

创建 `frontend/app/strategy/anomaly/page.tsx`：

```tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useAnomalies, useAnomalyStats } from "@/lib/hooks";
import dynamic from "next/dynamic";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

function StatsChart() {
  const { data, isLoading } = useAnomalyStats();

  if (isLoading) return <Skeleton className="h-52" />;
  if (!data || Object.keys(data).length === 0) {
    return (
      <Card>
        <CardContent className="py-6">
          <p className="text-sm text-muted-foreground">暂无异常统计数据</p>
        </CardContent>
      </Card>
    );
  }

  const entries = Object.entries(data).filter(([k]) => k !== "error");
  const option = {
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: entries.map(([k]) => k),
      axisLabel: { rotate: 30, fontSize: 11 },
    },
    yAxis: { type: "value" },
    series: [
      {
        type: "bar",
        data: entries.map(([, v]) => v),
        itemStyle: { color: "#6366f1" },
      },
    ],
    grid: { left: 40, right: 20, bottom: 60, top: 20 },
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">信号分布</CardTitle>
      </CardHeader>
      <CardContent>
        <ReactECharts option={option} style={{ height: 220 }} />
      </CardContent>
    </Card>
  );
}

export default function AnomalyPage() {
  const { data, isLoading } = useAnomalies(undefined, 7, 100);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">异常信号监控</h1>

      <StatsChart />

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            最近 7 天异常信号（{data?.total ?? 0} 条）
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12" />
              ))}
            </div>
          ) : (data?.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">近期无异常信号</p>
          ) : (
            <ScrollArea className="h-[calc(100vh-26rem)]">
              <div className="space-y-2">
                {(data?.data ?? []).map((item, i) => (
                  <div
                    key={`${item.stock_code}-${item.signal_type}-${i}`}
                    className="flex items-center justify-between rounded-md border p-3 text-sm"
                  >
                    <div>
                      <span className="font-medium">{item.stock_code}</span>
                      {item.stock_name && (
                        <span className="ml-2 text-muted-foreground">
                          {item.stock_name}
                        </span>
                      )}
                      {item.description && (
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {item.description}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{item.signal_type}</Badge>
                      {item.date && (
                        <span className="text-xs text-muted-foreground">
                          {item.date}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

**Step 2: 设置页面**

创建 `frontend/app/settings/page.tsx`：

```tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useSchedulerJobs, useFreshness, useHealth } from "@/lib/hooks";

export default function SettingsPage() {
  const health = useHealth();
  const scheduler = useSchedulerJobs();
  const freshness = useFreshness();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">系统设置</h1>

      {/* 系统信息 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">系统状态</CardTitle>
        </CardHeader>
        <CardContent>
          {health.isLoading ? (
            <Skeleton className="h-16" />
          ) : health.data ? (
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <span>状态:</span>
                <Badge
                  variant={
                    health.data.status === "healthy" ? "default" : "secondary"
                  }
                >
                  {health.data.status}
                </Badge>
              </div>
              <p>数据库: {health.data.db.ok ? "正常" : "异常"}</p>
              <p>
                调度器: {health.data.scheduler.running ? "运行中" : "已停止"}
              </p>
              <p>版本: {health.data.version}</p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">无法连接后端</p>
          )}
        </CardContent>
      </Card>

      {/* 调度任务 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">调度任务</CardTitle>
        </CardHeader>
        <CardContent>
          {scheduler.isLoading ? (
            <Skeleton className="h-32" />
          ) : (scheduler.data?.jobs ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">无调度任务</p>
          ) : (
            <div className="space-y-2">
              {scheduler.data!.jobs.map((job) => (
                <div
                  key={job.id}
                  className="flex items-center justify-between rounded-md border p-3 text-sm"
                >
                  <div>
                    <p className="font-medium">{job.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {job.description}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      上次运行: {job.last_run ?? "无"} · 执行次数: {job.run_count}
                    </p>
                  </div>
                  <Badge variant={job.enabled ? "default" : "secondary"}>
                    {job.enabled ? "启用" : "禁用"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 数据新鲜度 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">数据新鲜度</CardTitle>
        </CardHeader>
        <CardContent>
          {freshness.isLoading ? (
            <Skeleton className="h-32" />
          ) : !(freshness.data?.tables ?? []).length ? (
            <p className="text-sm text-muted-foreground">无数据</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2">数据表</th>
                    <th className="pb-2">最新日期</th>
                    <th className="pb-2">行数</th>
                  </tr>
                </thead>
                <tbody>
                  {freshness.data!.tables.map((t) => (
                    <tr key={t.table} className="border-b">
                      <td className="py-2 font-mono text-xs">{t.table}</td>
                      <td className="py-2">{t.latest_date ?? "-"}</td>
                      <td className="py-2">{t.row_count ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

**Step 3: 验证**

```bash
cd frontend && npm run dev
```

预期：
- `http://localhost:3000/strategy/anomaly` 显示异常信号统计图 + 列表
- `http://localhost:3000/settings` 显示系统状态 / 调度任务 / 数据新鲜度

**Step 4: Commit**

```bash
git add frontend/app/strategy/ frontend/app/settings/
git commit -m "feat(frontend): add anomaly signals page and settings page"
```

---

## Task 7: 后端 CORS 配置 + Docker 集成

**Files:**
- Modify: `api/main.py` (添加 CORS middleware)
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`
- Modify: `docker-compose.yml` (添加 frontend service)

**Step 1: 添加 CORS middleware**

在 `api/main.py` 中，在 `app = FastAPI(...)` 后添加：

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://frontend:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Step 2: 创建前端 Dockerfile**

创建 `frontend/Dockerfile`：

```dockerfile
FROM node:20-alpine AS base

# 安装依赖
FROM base AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# 构建
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# 运行
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
CMD ["node", "server.js"]
```

**Step 3: 创建 .dockerignore**

创建 `frontend/.dockerignore`：

```
node_modules
.next
.env.local
```

**Step 4: 更新 next.config.ts 启用 standalone 输出**

在 `frontend/next.config.ts` 中确保 `output: "standalone"` 设置：

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

**Step 5: 添加 frontend 到 docker-compose.yml**

在 `docker-compose.yml` 的 `services` 下添加 `frontend` 服务（在 `dashboard` 之后）：

```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: ainews_frontend
    restart: unless-stopped
    networks:
      - news_network
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on:
      - dashboard
```

**Step 6: 验证构建**

```bash
cd frontend && npm run build
```

预期：构建成功，无 TypeScript / ESLint 错误。

**Step 7: Commit**

```bash
git add api/main.py frontend/Dockerfile frontend/.dockerignore frontend/next.config.ts docker-compose.yml
git commit -m "feat(frontend): add CORS config, Dockerfile, and docker-compose frontend service"
```

---

## Task 8: Lint 修复 + 最终验证

**Step 1: 运行 ESLint**

```bash
cd frontend && npx next lint
```

修复所有 lint 错误。

**Step 2: 运行 TypeScript 类型检查**

```bash
cd frontend && npx tsc --noEmit
```

确保零类型错误。

**Step 3: 运行 Python lint**

```bash
cd /Users/xa/Desktop/projiect/AI_news && ruff check . --fix && ruff format .
```

确保 `api/main.py` 的 CORS 修改通过 lint。

**Step 4: 运行后端测试确保无回归**

```bash
pytest tests/ -x -q
```

预期：346+ passed。

**Step 5: 最终构建验证**

```bash
cd frontend && npm run build
```

预期：构建成功。

**Step 6: Commit**

```bash
git add -A
git commit -m "chore(frontend): lint fixes and final build verification"
```

---

## DoD 检查清单

- [ ] Dashboard 首页包含：健康状态、热点词云、情感饼图、异常信号、研报概览
- [ ] 新闻中心页面：推送新闻 + RSS 标签切换
- [ ] 异常信号页面：统计图 + 信号列表
- [ ] 设置页面：系统状态 + 调度任务 + 数据新鲜度
- [ ] 移动端响应式（侧边栏折叠 + 汉堡菜单）
- [ ] 所有页面有 loading / error / empty 状态处理
- [ ] Docker Compose 一键启动（`docker compose up -d`）
- [ ] 后端 CORS 配置正确
- [ ] ESLint + TypeScript 零错误
- [ ] 后端测试无回归
