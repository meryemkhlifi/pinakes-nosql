# Kibana dashboard: step by step (member B, task B6)

Goal: one dashboard "Pinakes - API monitoring" with 5 panels: requests per minute, status
codes, slowest requests, top IPs, map. Kibana 8.15. Keep the API running and send traffic first
(`python scripts/smoke_traffic.py --n 500 --pause 0.02`), so that the charts have data.
Set the time range (top right) to **Last 15 minutes**.

## 0. Create the dashboard
Menu (three lines) > Analytics > **Dashboard** > **Create dashboard**.
For each Lens panel: click **Create visualization**, pick the data view **Pinakes API logs**
(top left), build the chart, give it a title (pencil icon at the top), then **Save and return**.

## 1. Requests per minute (line or bar)
- Visualization type (top right dropdown): **Bar vertical** (or Line).
- Drag the field `@timestamp` to the horizontal axis. Click that axis, set **Minimum interval** to `1 minute`.
- Drag **Records** to the vertical axis (it is the count of requests).
- Title: `Requests per minute`.

## 2. Status codes (donut)
- Visualization type: **Donut** (or Pie).
- Slice by: drag `status`, keep **Top values** (10 values).
- Size by: **Records**.
- Title: `Status codes`.

## 3. Slowest requests (table)
- Visualization type: **Table**.
- Rows: drag `path`. Click it: **Number of values** 10, **Rank by** `Maximum of latency_ms`, direction **Descending**.
- Metrics: add **Maximum** of `latency_ms`, **Average** of `latency_ms` and **Count of records**.
- Title: `Slowest requests (ms)`.

## 4. Top IPs (table)
- Visualization type: **Table**.
- Rows: drag `client_ip` (Top values, 10, rank by Count of records).
- Metric: **Count of records**.
- Title: `Top client IPs`. The bot IP will be at the top after the bot script.

## 5. Map
- In the dashboard click **Add panel > Create visualization > Maps** (or Menu > Maps > Create map).
- **Add layer > Documents**, data view **Pinakes API logs**, geospatial field `geoip.location`, then **Add and continue**.
- **Save** with the title `Clients map`, then add it to the dashboard (**Add from library**).
- Only public IPs have a position. `smoke_traffic.py` uses public IPs from several countries.
- If the layer says there is no geo field: the logs were indexed without the template. Run
  `python elk/setup_elk.py --reset`, restart nothing, send traffic again.

## 6. Save and export
- Arrange the panels (drag the corners). Top right: time **Last 15 minutes**, auto-refresh **10 seconds** (calendar icon).
- **Save**, title `Pinakes - API monitoring`, tick **Store time with dashboard**.
- Export for Git: `python elk/dashboard_io.py export` (writes `elk/dashboard.ndjson`), then `git add elk/dashboard.ndjson`.
- To get it back later: `python elk/dashboard_io.py import`.
- Take a screenshot for the report (once normally, once during the bot burst).

## If a panel says "Saved field ... is invalid for use with the Terms aggregation"
The log index has the wrong field types (for example `path` is `text` instead of `keyword`), or Kibana
kept an old list of fields. Check, then fix:
1. `python elk/setup_elk.py --check` (it says which field has the wrong type).
2. If it prints `[FAIL]`: `python elk/setup_elk.py --reset`, send traffic again
   (`python scripts/smoke_traffic.py --n 300`), wait 30 seconds, run `--check` again.
3. In Kibana: Menu > Stack Management > Data Views > **Pinakes API logs** > refresh icon
   (top right, "Refresh field list") > confirm. Then reload the dashboard.
4. Export again (`python elk/dashboard_io.py export`): the export now leaves out the cached field list.
