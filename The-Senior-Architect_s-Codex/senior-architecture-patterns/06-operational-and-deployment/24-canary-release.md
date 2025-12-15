
# 24\. Canary Release

## 1\. The Concept

A Canary Release is a technique to reduce the risk of introducing a new software version in production by slowly rolling out the change to a small subset of users before making it available to everyone. It is named after the "canary in a coal mine"—if the canary (the small subset of users) stops singing (encounters errors), you evacuate the mine (rollback) before the miners (the rest of your user base) get hurt.

## 2\. The Problem

  * **Scenario:** You have 1 million active users. You deploy version 2.0 using a standard "Rolling Update" or "Blue-Green" switch.
  * **The Bug:** Version 2.0 has a subtle memory leak that only appears under high load, or a UI bug that breaks the "Checkout" button for users on iPads.
  * **The Impact:** Because you switched 100% of traffic to the new version, **all 1 million users** are affected instantly. Support lines are flooded, revenue drops to zero, and your reputation takes a hit.

## 3\. The Solution

Instead of switching 0% to 100%, you switch gradually: 0% -\> 1% -\> 10% -\> 50% -\> 100%.

1.  **Phase 1:** Deploy v2 to a small capacity. Route 1% of live traffic to it.
2.  **Verification:** Monitor Error Rates, Latency, and Business Metrics (e.g., "Orders per minute").
3.  **Expansion:** If metrics are healthy, increase traffic to 10%.
4.  **Completion:** Continue until 100% of traffic is on v2. Then decommission v1.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "We tested it in Staging. It works. Just deploy it to all servers." | **High Risk.** Staging is never exactly like Production. Real users do weird things that QA didn't predict. |
| **Senior** | "Staging is a rehearsal. Production is the show. Let 500 random users try the new code first. If they don't complain, let 5,000 try it." | **Blast Radius Containment.** If v2 is broken, only 1% of users had a bad day. The other 99% never noticed. We roll back the 1% instantly. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **High Scale:** You have enough traffic that "1%" is statistically significant.
      * **Critical Business Flows:** Changing the Payment Gateway or Login logic.
      * **Cloud Native:** You are using Kubernetes, Istio, or AWS ALB, which make weighted routing easy.
  * ❌ **Avoid when:**
      * **Low Traffic:** If you get 1 request per minute, "1% traffic" means waiting 100 minutes for a data point. Just do Blue-Green.
      * **Client-Side Apps:** It is harder (though not impossible) to do Canary releases for Mobile Apps (App Store delays) or Desktop software.
      * **Database Schema Changes:** Like Blue-Green, Canary requires the database to support *both* versions simultaneously.

## 6\. Implementation Example (Kubernetes/Istio)

In a standard Kubernetes setup, you can do a rough Canary by scaling replicas (1 pod v2, 9 pods v1 = 10% traffic).
For precise control, you use a Service Mesh like **Istio** or an Ingress Controller like **Nginx**.

### Istio `VirtualService` Configuration

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: payment-service
spec:
  hosts:
  - payment-service
  http:
  - route:
    - destination:
        host: payment-service
        subset: v1  # The Stable Version
      weight: 90
    - destination:
        host: payment-service
        subset: v2  # The Canary Version
      weight: 10
```

### The Rollout Strategy (Automated)

Manual Canary updates are tedious. Tools like **Flagger** or **Argo Rollouts** automate this:

1.  **09:00 AM:** Deploy v2. Flagger sets traffic to 5%.
2.  **09:05 AM:** Flagger checks Prometheus: "Is HTTP 500 rate \< 1%?".
3.  **09:06 AM:** Success. Flagger increases traffic to 20%.
4.  **09:10 AM:** Failure detected (Latency spiked \> 500ms). Flagger automatically reverts traffic to 0% and sends a Slack alert.

## 7\. What to Monitor (The Canary Analysis)

It is not enough to just check "Is the server up?" You must compare the **Baseline (v1)** vs. the **Canary (v2)**.

1.  **Technical Metrics:**
      * HTTP Error Rate (5xx).
      * Latency (p99).
      * CPU/Memory Saturation.
2.  **Business Metrics (The Senior level):**
      * "Add to Cart" conversion rate.
      * "Ad Impressions" count.
      * *Why?* v2 might be technically "stable" (no crashes), but if a CSS bug hides the "Buy" button, revenue drops. Only business metrics catch this.

## 8\. Sticky Sessions

A common challenge: A user hits the site and gets the Canary (v2). They refresh the page and get the Stable (v1). This is jarring.
**Solution:** Enable **Session Affinity** (Sticky Sessions) based on a Cookie or User ID. Once a user is assigned to the Canary group, they should stay there until the deployment finishes.

## 9\. Canary vs. Blue-Green vs. Rolling

  * **Rolling Update:** Update server 1, then server 2, etc. (Easiest, but hard to rollback).
  * **Blue-Green:** Switch 100% traffic at once. (Safest for rollback, but risky impact).
  * **Canary:** Switch traffic gradually. (Safest for impact, but most complex setup).