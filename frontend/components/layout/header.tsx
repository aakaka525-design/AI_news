"use client";

import { useState } from "react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Menu, TrendingUp, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { navGroups } from "@/lib/nav-config";
import { StockSearch } from "@/components/layout/stock-search";

export function Header() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="flex h-14 items-center border-b px-4 md:px-6">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" className="md:hidden">
            <Menu className="h-5 w-5" />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-56 p-0">
          <div className="flex h-14 items-center justify-between border-b px-4 font-semibold">
            <span className="flex items-center">
              <TrendingUp className="mr-2 h-5 w-5" />
              AI News
            </span>
            <Button variant="ghost" size="icon" onClick={() => setOpen(false)} aria-label="关闭菜单">
              <X className="h-4 w-4" />
            </Button>
          </div>
          <nav className="overflow-y-auto p-2">
            {navGroups.map((group, gi) => (
              <div key={group.label}>
                {gi > 0 && <div className="my-2 border-t" />}
                <p className="px-3 py-1 text-xs text-muted-foreground uppercase tracking-wider">
                  {group.label}
                </p>
                <div className="space-y-1">
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const active =
                      item.href === "/"
                        ? pathname === "/"
                        : pathname.startsWith(item.href);
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={() => setOpen(false)}
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
                </div>
              </div>
            ))}
          </nav>
        </SheetContent>
      </Sheet>
      <div className="flex-1 flex justify-end ml-2">
        <StockSearch />
      </div>
    </header>
  );
}
