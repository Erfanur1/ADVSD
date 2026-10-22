# multi-agent-server (Release 2, Task 1)

Shared, non-containerised local service coordinating a **Planner**,
**Worker** and **Reviewer** agent, with a mandatory **Human Review**
step, following the same pattern as the Release 1 `mcp-server` and
`rag-server`.

## Run it
## Task type: `review_portfolio` (Student 2 -- Portfolio & Position Tracker)

Reviews one portfolio before a person acts on it.

- **Planner:** plans two read-only MCP calls and lists the evidence required.
- **Worker:** calls the MCP tools `validate_portfolio` and `get_exposure_summary` (MCP server on port 8100; it reads the Student 2 API on port 5002).
- **Reviewer:** flags validation errors and warnings, plus any category over 50% of total exposure. Recommends `reject_insufficient_evidence`, `reject_invalid_positions`, `approve_with_caution` or `approve`.
- **Human Review:** approve / correct / partial / reject, from the Student 2 frontend panel or the terminal.

```bash
# HTTP (what the Student 2 backend calls)
curl -X POST localhost:8300/multi-agent/run -H "Content-Type: application/json" \
  -d '{"task_type":"review_portfolio","params":{"feature":"portfolio","portfolio_id":2}}'
# Terminal
python cli.py --task-type review_portfolio --feature portfolio --portfolio-id 2
```

## Task type: `review_mispricing_analysis` (Student 4 -- AI Market Analyst Assistant)

Reviews one cross-exchange mispricing signal before a person acts on it (saves it as an analysis, trades on it, etc.).

- **Planner:** plans a single re-check of the two markets and lists the evidence required.
- **Worker:** calls the MCP tool `compare_markets` (MCP server on port 8100; it reads live Polymarket/Kalshi data) -- the client's numbers are never trusted, the comparison is always re-run server-side.
- **Reviewer:** flags a last-trade (incomplete order book) basis and any gap over 20 points (often a market-definition mismatch, not real mispricing). Recommends `reject_insufficient_evidence`, `reject_not_actionable` (status is `fair`, nothing to act on), `approve_with_caution` or `approve`.
- **Human Review:** approve / correct / partial / reject, from the Student 4 frontend panel (next to "Save as analysis" once a pair has been compared) or the terminal.

```bash
# HTTP (what the Student 4 backend calls)
curl -X POST localhost:8300/multi-agent/run -H "Content-Type: application/json" \
  -d '{"task_type":"review_mispricing_analysis","params":{"feature":"market-analyst","polymarket_id":"666861","kalshi_ticker":"KXIMPEACH-27-JAN01"}}'
# Terminal
python cli.py --task-type review_mispricing_analysis --feature market-analyst \
  --polymarket-id 666861 --kalshi-ticker KXIMPEACH-27-JAN01
```
