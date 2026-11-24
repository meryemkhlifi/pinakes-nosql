# Bot detection with a z-score (member B, notes for report section 6)

## Idea
A normal visitor makes a few requests per minute. A bot makes hundreds. We count the requests
x of every (IP, minute) pair over the last 30 minutes and ask: how far is x from the usual?

    z = (x - mean) / std

mean and std are computed over all the (IP, minute) counts of the window (population standard
deviation). z says how many standard deviations x is above the mean. We alert when z > 3:
for normally distributed counts this happens for about 0.1 % of the pairs, so alerts are rare.

## Rules around the formula (and why)
- At least 10 (IP, minute) pairs: with very little history, "normal" is unknown.
- std = 0 (all counts equal): z is undefined, no alert.
- x >= 20 requests: avoids an alert for 5 requests when everyone else sends 1.
- Only the last 3 minutes are reported: an old burst is not announced again at every check.
- One alert document per (IP, minute): running the check every 20 s never creates duplicates.

## Limits (good to write in the report)
- The burst itself raises the mean and the std, so a huge burst is a little less extreme than
  it would be against a clean baseline. With one outlier among n pairs, z cannot exceed
  about sqrt(n): we need enough pairs, hence the minimum of 10.
- Slow bots (a few requests per minute) are invisible. A bot behind many IPs is invisible.
- The z-score assumes counts that look like a bell curve. Real traffic is skewed, so a
  robust version (median and MAD) would be a possible improvement.

## Pipeline
`bot_simulator.py` -> API (JSON log line) -> Filebeat -> Logstash -> Elasticsearch (logs)
-> `zscore_alert.py` (aggregation per minute and IP) -> index `pinakes-alerts`
-> `GET /monitoring/alerts` -> Monitoring page (Day 5).
