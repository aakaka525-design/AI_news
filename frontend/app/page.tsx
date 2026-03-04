import { StatsRow } from "@/components/dashboard/stats-row";
import { HotspotCloud } from "@/components/dashboard/hotspot-cloud";
import { SentimentPie } from "@/components/dashboard/sentiment-pie";
import { AnomalyList } from "@/components/dashboard/anomaly-list";
import { ReportSummary } from "@/components/dashboard/report-summary";
import { PolymarketSummary } from "@/components/dashboard/polymarket-summary";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Quick stats */}
      <StatsRow />

      {/* Main content: left = polymarket + anomalies, right = sentiment + hotspot + reports */}
      <div className="grid gap-4 lg:grid-cols-5">
        {/* Left column — wider */}
        <div className="lg:col-span-3 space-y-4">
          <PolymarketSummary />
          <div className="grid gap-4 md:grid-cols-2">
            <AnomalyList />
            <ReportSummary />
          </div>
        </div>

        {/* Right column — narrower */}
        <div className="lg:col-span-2 space-y-4">
          <SentimentPie />
          <HotspotCloud />
        </div>
      </div>
    </div>
  );
}
