# 🔭 Group 7: Observability & Maintenance

## Overview

**"If you can't measure it, you can't improve it. If you can't see it, you can't fix it."**

In a monolithic architecture, debugging involves checking one server and one log file. In a distributed architecture with 50 microservices, a single user request might traverse 10 distinct servers. When things break (and they will), you cannot rely on luck or intuition.

This module provides the "X-Ray Vision" required to run complex systems. It moves operations from **Reactive** (waiting for a customer to complain) to **Proactive** (fixing the issue before the customer notices).

## 📜 Pattern Index

| Pattern | Goal | Senior "Soundbite" |
| :--- | :--- | :--- |
| **[26. Distributed Tracing](https://www.google.com/search?q=./26-distributed-tracing.md)** | **Transaction Flow** | "Don't guess which service is slow. Look at the trace ID and see the waterfall chart." |
| **[27. Health Check API](https://www.google.com/search?q=./27-health-check-api.md)** | **Self-Healing** | "The orchestrator needs to know if the app is dead (restart it) or just busy (stop routing traffic)." |
| **[28. Log Aggregation](https://www.google.com/search?q=./28-log-aggregation.md)** | **Debugging** | "Grepping logs on a server is for amateurs. Query the centralized log index using a Correlation ID." |
| **[29. Metrics & Alerting](https://www.google.com/search?q=./29-metrics-and-alerting.md)** | **System Pulse** | "Alert on symptoms (User Error Rate), not causes (High CPU). Avoid pager fatigue." |

## 🧠 The Observability Checklist

Before marking a system as "Production Ready," a Senior Architect asks:

1.  **The "Needle in a Haystack" Test:** If a specific user reports an error, can I find their specific log lines among 1 million other logs within 1 minute? (Requires Structured Logging + Trace IDs).
2.  **The "Silent Failure" Test:** If the database locks up but the web server process is still running, does the Load Balancer keep sending traffic to the black hole? (Requires Readiness Probes).
3.  **The "3 AM" Test:** Will the on-call engineer get woken up because a disk is 80% full (which is fine), or only when the site is actually down? (Requires Golden Signal Alerting).

## ⚠️ Common Pitfalls in This Module

  * **Logging Too Much:** Logging every entry/exit of every function. This fills up the disk, costs a fortune in ingestion fees, and makes finding real errors impossible.
  * **Blind Spots:** Monitoring the Backend APIs but ignoring the Frontend JavaScript errors. The API might be fine, but the users see a blank white screen.
  * **The "Dashboard Graveyard":** Creating 50 Grafana dashboards that nobody ever looks at. Stick to a few high-value dashboards based on the Golden Signals.
