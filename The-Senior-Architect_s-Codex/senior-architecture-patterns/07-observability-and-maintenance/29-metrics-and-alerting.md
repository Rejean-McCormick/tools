# 29\. Metrics & Alerting (The 4 Golden Signals)

## 1\. The Concept

While Logs tell you *why* something happened (debugging context), **Metrics** tell you *what* is happening right now (operational health). Metrics are numerical time-series data (e.g., CPU Usage, Request Count, Latency, Queue Depth) sampled at regular intervals.

**Alerting** is the automated system that monitors these metrics and notifies a human when values cross a dangerous threshold.

## 2\. The Problem

  * **Scenario:** You want to ensure your site is running well.
  * **The Noise (Alert Fatigue):** You set up alerts for everything. "Alert if CPU \> 80%." "Alert if Memory \> 70%." "Alert if Disk \> 60%."
  * **The Fatigue:** At 3:00 AM, the CPU spikes to 81% because of a routine backup job. The pager wakes you up. You check it, see it's harmless, and go back to sleep.
  * **The Failure:** At 4:00 AM, the database thread pool deadlocks. The CPU drops to 0% (because it's doing nothing). No alert fires. The site is down, users are angry, and you are asleep.

## 3\. The Solution: The 4 Golden Signals

Google SRE principles suggest monitoring the four key **symptoms** of a problem, rather than trying to guess every possible **cause**. If these four signals are healthy, the users are happy, regardless of what the CPU is doing.

1.  **Latency:** The time it takes to service a request. (e.g., "Alert if p99 latency \> 2 seconds").
2.  **Traffic:** A measure of how much demand is being placed on your system (e.g., "HTTP Requests per second").
3.  **Errors:** The rate of requests that fail. (e.g., "Alert if HTTP 500 rate \> 1%").
4.  **Saturation:** How "full" your service is. (e.g., "Thread Pool 95% full", "Memory 99% used").

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "I'll alert on every server resource: CPU, RAM, Disk, Network. If any line goes red, page the team." | **Pager Fatigue.** The team ignores the pager because 90% of alerts are false alarms ("Wolf\!"). When a real fire happens, nobody reacts. |
| **Senior** | "Page a human **only** if the user is in pain (High Latency or High Error Rate). If the disk is full but the app is still serving traffic, send a ticket to Jira for morning review, don't wake me up." | **Actionable Alerts.** Every page means immediate action is required. The team trusts the monitoring system. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Production Systems:** Essential for any live service.
      * **Capacity Planning:** Using long-term metric trends (Traffic) to decide when to buy more servers.
      * **Auto-Scaling:** Kubernetes uses metrics (CPU/Memory) to decide when to add more pods.
  * ❌ **Avoid when:**
      * **Debugging Logic:** Metrics are bad at explaining *why* a specific user failed. Use Logs or Tracing for that.
      * **High Cardinality Data:** Do not put "User ID" or "Email" into a metric label. If you have 1 million users, you will create 1 million distinct metric time-series, which will crash your Prometheus server.

## 6\. Implementation Example (Prometheus Alert Rules)

Prometheus is the industry standard for cloud-native metrics.

```yaml
groups:
- name: golden-signals
  rules:
  
  # 1. ERROR RATE ALERT (The "Is it broken?" signal)
  # Page the engineer if > 1% of requests are failing for 2 minutes straight.
  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[2m]) 
          / 
          rate(http_requests_total[2m]) > 0.01
    for: 2m
    labels:
      severity: critical  # Wakes up the human
    annotations:
      summary: "High Error Rate detected"
      description: "More than 1% of requests are failing on {{ $labels.service }}."

  # 2. LATENCY ALERT (The "Is it slow?" signal)
  # Warning if p99 latency is high, but maybe don't wake up the human immediately.
  - alert: HighLatency
    expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 2.0
    for: 5m
    labels:
      severity: warning   # Sends a Slack message, doesn't page
    annotations:
      summary: "API is slow"
      description: "99% of requests are taking longer than 2 seconds."
```

## 7\. Percentiles vs. Averages (The Senior Math)

**Never use Averages (Mean).**

  * **Scenario:** 100 requests.
      * 99 requests take 10ms.
      * 1 request takes 100 seconds (Process crashed).
  * **The Average:** \~1 second. (Looks fine).
  * **The p99 (99th Percentile):** 100 seconds. (Reveals the disaster).
  * **Senior Rule:** Always alert on **p95** or **p99** latency. This captures the experience of your slowest users, which is usually where the bugs are hiding.

## 8\. Strategy: The "Delete" Rule

If an alert fires, wakes you up, and you check the system and decide "Eh, it's fine, I don't need to do anything," then **delete the alert**.

  * An alert that requires no action is not an alert; it is noise.
  * Maintenance work (cleaning up alerts) is just as important as writing code.