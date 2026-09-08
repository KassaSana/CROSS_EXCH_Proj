import { memo } from "react";
import { Opportunity } from "../api/client";

type Props = {
  opportunities: Opportunity[];
};

export const OpportunityFeed = memo(function OpportunityFeed({ opportunities }: Props) {
  return (
    <section className="rounded-[2rem] border border-stone-300 bg-white/70 p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-2xl text-ink">Recent Opportunities</h2>
        <span className="text-sm text-stone-500">{opportunities.length} tracked</span>
      </div>
      <div className="mt-5 space-y-3">
        {opportunities.map((opportunity) => (
          <div key={`${opportunity.timestamp_ns}-${opportunity.pair}-${opportunity.buy_exchange}-${opportunity.sell_exchange}`} className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
            <div className="flex items-center justify-between">
              <strong>{opportunity.pair}</strong>
              <span className="text-sm text-emerald-700">{opportunity.spread_pct}%</span>
            </div>
            <p className="mt-2 text-sm text-stone-600">
              Buy on {opportunity.buy_exchange} at {opportunity.buy_price}, sell on {opportunity.sell_exchange} at {opportunity.sell_price}
            </p>
            <p className="mt-1 text-sm text-stone-500">Theoretical profit: ${opportunity.theoretical_profit_usd}</p>
          </div>
        ))}
      </div>
    </section>
  );
});
