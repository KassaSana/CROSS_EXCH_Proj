import { memo } from "react";
import { PairRecord, TopOfBook } from "../api/client";

type Props = {
  pairs: PairRecord[];
  books: Record<string, TopOfBook>;
};

function spreadText(entries: TopOfBook[]): string {
  if (entries.length < 2) {
    return "--";
  }
  const bestBid = Math.max(...entries.map((entry) => Number(entry.best_bid_price)));
  const bestAsk = Math.min(...entries.map((entry) => Number(entry.best_ask_price)));
  if (bestBid <= bestAsk) {
    return "--";
  }
  return (((bestBid - bestAsk) / bestAsk) * 100).toFixed(3);
}

export const LiveSpreads = memo(function LiveSpreads({ pairs, books }: Props) {
  const grouped = pairs.reduce<Record<string, TopOfBook[]>>((acc, pair) => {
    const key = `${pair.exchange}:${pair.pair}`;
    const book = books[key];
    if (!acc[pair.pair]) {
      acc[pair.pair] = [];
    }
    if (book) {
      acc[pair.pair].push(book);
    }
    return acc;
  }, {});

  return (
    <section className="rounded-[2rem] border border-stone-300 bg-white/70 p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-2xl text-ink">Live Spreads</h2>
        <p className="text-sm text-stone-500">Cross-venue top-of-book comparison</p>
      </div>
      <div className="mt-5 overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-stone-500">
            <tr>
              <th className="pb-3">Pair</th>
              <th className="pb-3">Venues</th>
              <th className="pb-3">Best Bid / Ask</th>
              <th className="pb-3">Spread %</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(grouped).map(([pair, entries]) => {
              const spread = spreadText(entries);
              return (
                <tr key={pair} className="border-t border-stone-200 align-top">
                  <td className="py-4 font-medium text-ink">{pair}</td>
                  <td className="py-4">{entries.map((entry) => entry.exchange).join(", ") || "--"}</td>
                  <td className="py-4">
                    {entries.map((entry) => (
                      <div key={entry.exchange} className="text-stone-600">
                        {entry.exchange}: {entry.best_bid_price} / {entry.best_ask_price}
                      </div>
                    ))}
                  </td>
                  <td className={`py-4 ${spread !== "--" && Number(spread) > 0.1 ? "text-emerald-700" : "text-stone-500"}`}>{spread}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
});
