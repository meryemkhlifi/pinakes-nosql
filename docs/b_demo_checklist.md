# Demo checklist (12 minutes) - Pinakes 2.0

Run `python scripts/check_day5_demo.py --ui` just before: every line must be `[OK]`.
Open these tabs first: Streamlit http://localhost:8501, Kibana http://localhost:5601,
API docs http://localhost:8000/docs. Keep `python scripts/zscore_alert.py` running in a terminal.

| # | Who | What to show | What you should see |
|---|---|---|---|
| 1 | A | Page **Search**: type `republc` (typo), then filter on a genre | « The Republic » found, text highlighted, suggestions, facets. Repeat the same search: the API answers faster (cache) |
| 2 | B | Page **Graph**: pick two authors, **Find the path**. Then the PageRank table | A drawing of the path, then the 10 most influential authors |
| 3 | A | Page **Browse**: genre > author > work > **Open this work** | The work with its first line |
| 4 | A | Page **Popular** with **Live** ticked. Open works in **Browse** (other tab) | The ranking and the view counts move within 3 seconds |
| 5 | B | Terminal: `python scripts/bot_simulator.py`. Kibana dashboard, then page **Monitoring**, then page **Events** | Spike in « Requests per minute », bot IP first in « Top client IPs », an alert in the table, then reads per day of a work |
| 6 | Both | The two benchmark charts (Day 6) and the conclusion | - |

Tips: the bot needs about 2 minutes to raise an alert, so start it at the end of scenario 4.
If a service is slow to answer, say what the database does while you wait (inverted index,
sorted set, graph traversal, partition read): it is part of the presentation.
