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
