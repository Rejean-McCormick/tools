
# 23\. Blue-Green Deployment

## 1\. The Concept

Blue-Green Deployment is a release strategy that reduces downtime and risk by running two identical production environments, called "Blue" and "Green."

  * **Blue:** The currently live version (v1) handling 100% of user traffic.
  * **Green:** The new version (v2), currently idle or accessible only to internal testers.

To release, you deploy v2 to Green, test it thoroughly, and then switch the Load Balancer to route all traffic from Blue to Green. If anything goes wrong, you switch back instantly.

## 2\. The Problem

  * **Scenario:** You are deploying a critical update to a banking app.
  * **The "In-Place" Risk:** You stop the server, unzip the new jar file, and restart the server.
      * **Downtime:** The user sees a "502 Bad Gateway" for 2 minutes.
      * **The Panic:** The new version crashes on startup. You now have to scramble to find the old jar file and redeploy it. The system is down for 15 minutes.
      * **The Consequence:** Deployment becomes a scary event that teams avoid doing. "Don't deploy on Fridays\!"

## 3\. The Solution

Decouple the "Deployment" (installing bits) from the "Release" (serving traffic).

1.  **Deployment:** You spin up the Green environment. The public cannot see it yet. You run smoke tests against it.
2.  **Cutover:** You change the Router/Load Balancer configuration. Traffic flows to Green. Blue is now idle.
3.  **Rollback:** If Green throws errors, you just flip the switch back to Blue. It is instantaneous because Blue is still running.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "I'll use `rsync` to overwrite the files on the live server. It's fast and easy." | **Maintenance Windows.** "The site will be down from 2 AM to 4 AM." If the deploy fails, you are stuck debugging live in production. |
| **Senior** | "Infrastructure is disposable. Spin up a completely new stack (Green). Verify it. Switch the pointer. Kill the old stack (Blue) only when we are 100% sure." | **Zero Downtime.** Deployments are boring and safe. Rollback is a single button press. We can deploy at 2 PM on a Friday. |

## 4\. Visual Diagram

## 5\. The Hard Part: The Database

The infrastructure part is easy (especially with Kubernetes). **The Database is the bottleneck.**

  * You usually have **one** shared database for both Blue and Green (syncing two databases in real-time is too complex).
  * **The Constraint:** The database schema must be compatible with *both* v1 (Blue) and v2 (Green) at the same time.

### The "Expand-Contract" Pattern

If you need to rename a column from `address` to `full_address`:

1.  **Migration 1 (Expand):** Add `full_address` column. Copy data from `address`. Keep `address`.
      * *Result:* DB has both. Blue uses `address`. Green uses `full_address`.
2.  **Deploy:** Blue-Green Switch.
3.  **Migration 2 (Contract):** Once Green is stable, delete the `address` column.

## 6\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Critical Uptime:** You cannot afford 5 minutes of downtime.
      * **Instant Rollback:** You need a safety net.
      * **Monoliths:** It is often easier to Blue/Green a monolith than to do rolling updates.
  * ❌ **Avoid when:**
      * **Stateful Apps:** If users have active WebSocket connections or in-memory sessions on Blue, switching them to Green cuts them off. (Requires sticky sessions or external session stores like Redis).
      * **Destructive DB Changes:** If the new version drops a table, you cannot roll back to Blue (Blue will crash querying the missing table).

## 7\. Implementation Example (Kubernetes)

In Kubernetes, this is often done using `Service` selectors.

### Step 1: The Current State (Blue)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app-service
spec:
  selector:
    version: v1  # POINTS TO BLUE
  ports:
    - port: 80
```

### Step 2: Deploy Green (v2)

We deploy a new Deployment named `app-v2`. It starts up, but receives NO traffic because the Service is still looking for `version: v1`.

  * We can port-forward to `app-v2` to test it manually.

### Step 3: The Switch

We patch the Service to look for `v2`.

```bash
kubectl patch service my-app-service -p '{"spec":{"selector":{"version":"v2"}}}'
```

  * **Result:** The Service instantly routes new packets to the v2 pods. The v1 pods stop receiving traffic.
  * **Cleanup:** After 1 hour, delete the `app-v1` deployment.

## 8\. Blue-Green vs. Canary

  * **Blue-Green:** Instant switch. 100% of traffic moves at once. Great for simple applications.
  * **Canary:** Gradual shift. 1% -\> 10% -\> 50% -\> 100%. Better for high-scale systems where a bug affecting 100% of users instantly would be catastrophic.

## 9\. Strategic Note on Cost

Blue-Green implies running **double the infrastructure** during the deployment window.

  * If your production cluster costs $10k/month, you need capacity to spike to $20k/month temporarily.
  * **Senior Tip:** In the Cloud, this is cheap (you only pay for the extra hour). On-premise, this is hard (you need double the physical servers).