import { HealthCard } from "@/components/dashboard/health-card";
import { HotspotCloud } from "@/components/dashboard/hotspot-cloud";
import { SentimentPie } from "@/components/dashboard/sentiment-pie";
import { AnomalyList } from "@/components/dashboard/anomaly-list";
import { ReportSummary } from "@/components/dashboard/report-summary";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <HealthCard />
        <SentimentPie />
        <HotspotCloud />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <AnomalyList />
        <ReportSummary />
      </div>
    </div>
  );
}
