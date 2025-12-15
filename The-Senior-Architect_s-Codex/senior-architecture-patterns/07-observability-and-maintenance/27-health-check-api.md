# 27\. Health Check API (Liveness & Readiness)

## 1\. The Concept

A Health Check API provides a standard endpoint (e.g., `/health`) that an external monitoring system (like Kubernetes, AWS Load Balancer, or Uptime Robot) can ping to verify the status of the service. It answers two distinct questions:

1.  **Liveness:** "Is the process running, or has it crashed/frozen?"
2.  **Readiness:** "Is the service ready to accept traffic, or is it still booting up/overloaded?"

## 2\. The Problem

  * **Scenario:** You deploy a Java application. It takes 45 seconds to initialize the Spring Context and connect to the database.
  * **The Liveness Failure:** If the Load Balancer sends traffic immediately after the process starts (second 1), the request fails. Users see 502 Errors.
  * **The Zombie Process:** The application runs out of memory and stops processing requests, but the PID (Process ID) is still active. The orchestrator thinks it's "alive" and keeps sending traffic to a dead process.

## 3\. The Solution

Implement two separate endpoints:

1.  **`/health/live` (Liveness Probe):** Returns `200 OK` if the basic server process is up. If this fails, the Orchestrator **kills and restarts** the container.
2.  **`/health/ready` (Readiness Probe):** Returns `200 OK` only if the application can actually do work (DB connection is active, cache is warm). If this fails, the Load Balancer **stops sending traffic** to this instance (but does not kill it).

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "I added a `/health` endpoint that returns 'OK'. It checks the DB, Redis, and 3rd Party APIs." | **Cascading Outage.** If the 3rd Party API goes down, *every* instance reports 'Unhealthy'. Kubernetes kills *all* your pods simultaneously. The system self-destructs. |
| **Senior** | "Split Liveness and Readiness. Liveness is dumb (return true). Readiness checks local dependencies (DB) but *not* weak dependencies (External APIs). Use 'Circuit Breakers' for external failures, not Health Checks." | **Resilience.** If an external API is down, we degrade gracefully. We don't restart the whole fleet. |

## 4\. Visual Diagram

## 5\. Implementation Example (Pseudo-code)

```python
# GET /health/live
def liveness_probe():
    # Only checks if the thread is not deadlocked
    return HTTP_200("Alive")

# GET /health/ready
def readiness_probe():
    # 1. Check Database (Critical)
    try:
        db.ping()
    except DBError:
        return HTTP_503("Database Unreachable")

    # 2. Check Cache (Critical)
    try:
        redis.ping()
    except RedisError:
        return HTTP_503("Cache Unreachable")
        
    # 3. DO NOT Check External APIs (e.g., Stripe/Google)
    # If Stripe is down, we are still "Ready" to serve other requests.
    
    return HTTP_200("Ready")
```