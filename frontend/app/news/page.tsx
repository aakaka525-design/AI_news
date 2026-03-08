"use client";

import { Suspense } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { NewsList } from "@/components/news/news-list";
import { RssList } from "@/components/news/rss-list";

function NewsLoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-20 rounded-lg bg-muted" />
      ))}
    </div>
  );
}

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
          <Suspense fallback={<NewsLoadingSkeleton />}>
            <NewsList />
          </Suspense>
        </TabsContent>
        <TabsContent value="rss">
          <Suspense fallback={<NewsLoadingSkeleton />}>
            <RssList />
          </Suspense>
        </TabsContent>
      </Tabs>
    </div>
  );
}
