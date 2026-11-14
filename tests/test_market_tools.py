import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from shepard.market_tools import collect_market_evidence, parse_stooq_history


def price_csv(start_price=20.0, sessions=70):
    start = date(2026, 7, 1)
    rows = ["Date,Open,High,Low,Close,Volume"]
    for index in range(sessions):
        price = start_price + index * 0.1
        day = start + timedelta(days=index)
        rows.append(f"{day.isoformat()},{price:.2f},{price + .2:.2f},{price - .2:.2f},{price:.2f},{100000 + index * 1000}")
    return "\n".join(rows)


class MarketToolsTests(unittest.TestCase):
    def test_price_history_produces_auditable_metrics(self):
        snapshot = parse_stooq_history(
            "TEST", price_csv(), source_url="https://example.test/test.csv"
        )
        self.assertEqual(snapshot.symbol, "TEST")
        self.assertAlmostEqual(snapshot.price, 26.9)
        self.assertGreater(snapshot.change_20d, 0)
        self.assertIsNotNone(snapshot.volatility_20d)
        self.assertEqual(snapshot.source_url, "https://example.test/test.csv")

    def test_evidence_packet_labels_scope_and_sec_filings(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "watchlist.json"
            config.write_text(
                '{"price_cap_usd": 50, "symbols": ["TEST"]}', encoding="utf-8"
            )
            chart = '{"chart":{"result":[{"timestamp":[' + ",".join(
                str(1782864000 + index * 86400) for index in range(70)
            ) + '],"indicators":{"quote":[{"close":[' + ",".join(
                str(20 + index * .1) for index in range(70)
            ) + '],"volume":[' + ",".join("100000" for _ in range(70)) + '] }]}}],"error":null}}'
            ipo = '{"data":{"upcoming":{"upcomingTable":{"rows":[{"proposedTickerSymbol":"EXM","companyName":"Example Corp","proposedExchange":"NASDAQ","proposedSharePrice":"10-12","expectedPriceDate":"11/20/2026"}]}},"priced":{"rows":[]}}}'

            def downloader(url, **kwargs):
                return ipo if "nasdaq.com" in url else chart

            packet = collect_market_evidence(config, downloader=downloader)
            self.assertIn("configured watchlist scan, not the entire market", packet)
            self.assertIn("| TEST |", packet)
            self.assertIn("Example Corp", packet)
            self.assertIn("not proof that an offering will occur", packet)


if __name__ == "__main__":
    unittest.main()
