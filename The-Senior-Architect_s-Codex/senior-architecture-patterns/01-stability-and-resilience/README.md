# 🛡️ Group 1: Stability & Resilience

## Overview

**"The goal is not to never fail. The goal is to fail without hurting the user."**

This module covers the foundational patterns required to keep a distributed system running when its sub-components break. In a monolithic application, a single function error might crash the process. In a distributed system, a single service failure must not crash the platform.

These patterns shift your architecture from **Fragile** (breaks under stress) to **Resilient** (bends but recovers).

## 📜 Pattern Index

| Pattern | Goal | Senior "Soundbite" |
| :--- | :--- | :--- |
| **[01. Circuit Breaker](https://www.google.com/search?q=./01-circuit-breaker.md)** | **Stop Cascading Failures** | "If the service is down, stop calling it. Fail fast." |
| **[02. Bulkhead](https://www.google.com/search?q=./02-bulkhead-pattern.md)** | **Fault Isolation** | "If the Reporting feature crashes, the Login feature must stay up." |
| **[03. Exponential Backoff](https://www.google.com/search?q=./03-exponential-backoff-jitter.md)** | **Responsible Retries** | "Don't hammer a rebooting database. Wait, then wait longer." |
| **[04. Graceful Degradation](https://www.google.com/search?q=./04-graceful-degradation.md)** | **User Experience Protection** | "If the recommendations engine fails, just show the product without them." |
| **[05. Rate Limiting](https://www.google.com/search?q=./05-rate-limiting-throttling.md)** | **Traffic Control** | "Protect the database from the noisy neighbor." |
| **[06. Timeout Budgets](https://www.google.com/search?q=./06-timeout-budgets.md)** | **Latency Management** | "If the client stopped waiting 2 seconds ago, stop working." |

## 🧠 The Stability Checklist

Before marking a system architecture as "Production Ready," a Senior Architect asks these questions:

1.  **The "Plug-Pull" Test:** If I unplug the network cable for the Payment Service, does the Browse Products page still load? (It should).
2.  **The "DDoS" Test:** If one user sends 10,000 requests/second, do they take down the system for everyone else? (Rate Limiting).
3.  **The "Slow-Loris" Test:** If the database starts taking 20 seconds to respond, do our web servers run out of threads? (Timeouts & Circuit Breakers).
4.  **The "Recovery" Test:** When the database comes back online after an outage, does it immediately crash again due to a retry storm? (Backoff & Jitter).

## ⚠️ Common Pitfalls in This Module

  * **Over-Engineering:** Implementing a full Circuit Breaker + Bulkhead + Fallback for a simple internal tool used by 5 people.
  * **Infinite Retries:** The default setting in many HTTP clients is "Retry 3 times" or "Retry Forever." Check your defaults.
  * **Silent Failures:** Graceful degradation is good, but you must **Log** that you degraded. Otherwise, you might run for months without realizing the "Recommendations" widget is broken.

