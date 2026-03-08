import {
  LayoutDashboard,
  BarChart3,
  Wallet,
  Trophy,
  Grid3X3,
  Filter,
  Star,
  Newspaper,
  Target,
  AlertTriangle,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const navGroups: NavGroup[] = [
  {
    label: "概览",
    items: [{ href: "/", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    label: "市场数据",
    items: [
      { href: "/market", label: "市场行情", icon: BarChart3 },
      { href: "/flow", label: "资金流向", icon: Wallet },
      { href: "/dragon", label: "龙虎榜", icon: Trophy },
      { href: "/sector", label: "板块行情", icon: Grid3X3 },
      { href: "/screens", label: "筛选", icon: Filter },
      { href: "/watchlist", label: "自选", icon: Star },
    ],
  },
  {
    label: "情报分析",
    items: [
      { href: "/news", label: "新闻中心", icon: Newspaper },
      { href: "/polymarket", label: "预测市场", icon: Target },
      { href: "/strategy/anomaly", label: "异常信号", icon: AlertTriangle },
    ],
  },
  {
    label: "系统",
    items: [{ href: "/settings", label: "系统设置", icon: Settings }],
  },
];
