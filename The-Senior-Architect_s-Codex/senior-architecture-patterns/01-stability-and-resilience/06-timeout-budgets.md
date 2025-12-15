# 06\. Timeout Budgets

## 1\. The Concept

A Timeout is the maximum amount of time an operation is allowed to take before being aborted. A **Timeout Budget** takes this concept further in distributed systems: instead of every service having its own arbitrary static timeout (e.g., "every call gets 10 seconds"), the request is assigned a *total* time budget at the entry point. As the request passes from Service A to Service B to Service C, the budget is decremented. If the budget hits zero, all downstream processing stops immediately.

## 2\. The Problem

  * **Scenario:** A user request hits the **Frontend API**.
      * **Frontend API** calls **Service A** (Timeout: 10s).
      * **Service A** calls **Service B** (Timeout: 10s).
      * **Service B** calls **Database** (Timeout: 10s).
  * **The Risk (Latency Amplification):**
      * If the Database takes 9 seconds, Service B succeeds.
      * But Service A might have spent 2 seconds doing its own logic before calling B.
      * Total time so far: 2s + 9s = 11s.
      * **The Result:** The Frontend API times out (at 10s) and returns an error to the user *before* Service A finishes. However, Service A and B *continue working*, consuming resources to compute a result that no one is listening for. This is "Ghost Work."

## 3\. The Solution

Implement **Distributed Timeouts (Deadlines)**.
The Frontend sets a strict deadline (e.g., `Start Time + 5000ms`). It passes this absolute timestamp in the HTTP headers (e.g., `X-Deadline`). Every service checks this header:

1.  **Check:** "Is `now() > X-Deadline`?" If yes, abort immediately.
2.  **Pass it on:** Forward the `X-Deadline` header to the next downstream service.
3.  **Local Timeout:** When making a network call, set the socket timeout to `(X-Deadline - now())`.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "I'll just set a default timeout of 60 seconds on every `HttpClient` to be safe." | **Resource Zombie Apocalypse.** If the system slows down, requests pile up, holding connections open for a full minute. The system locks up completely. |
| **Senior** | "The User UI gives up after 2 seconds. Therefore, the backend *must* kill processing at 1.9 seconds. Pass the deadline down the stack." | **Efficiency.** We stop processing exactly when the client stops listening. We save CPU/IO for requests that can actually still succeed. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Deep Call Chains:** Microservices with 3+ layers of depth (A -\> B -\> C -\> DB).
      * **High Concurrency:** Systems where "thread starvation" is a real risk.
      * **User-Facing APIs:** Where the human user has a natural patience limit (approx. 2-3 seconds).
  * ❌ **Avoid when:**
      * **Async/Background Jobs:** If a job runs in a queue, it doesn't have a user waiting. It might need a 5-minute timeout, not 2 seconds.
      * **Streaming/WebSockets:** Connections meant to stay open indefinitely.

## 6\. Implementation Example (Pseudo-code)

**Scenario:** Service A calls Service B.

```python
import time
import requests

# 1. THE ENTRY POINT (Service A)
def handle_request(request):
    # We decide the total budget is 3 seconds from NOW.
    total_budget_ms = 3000
    deadline = time.time() + (total_budget_ms / 1000)
    
    try:
        call_service_b(deadline)
    except TimeoutError:
        return HTTP_503("Service B took too long")

# 2. THE CLIENT LOGIC
def call_service_b(deadline):
    # Calculate how much time is left right now
    time_remaining = deadline - time.time()
    
    if time_remaining <= 0:
        # Don't even open the connection. We are already late.
        raise TimeoutError("Budget exhausted before call")
    
    # Pass the deadline downstream via headers
    headers = {"X-Deadline": str(deadline)}
    
    # Set the actual socket timeout to the remaining time
    # If we have 1.5s left, don't wait 10s!
    response = requests.get(
        "http://service-b/api", 
        headers=headers, 
        timeout=time_remaining
    )
    return response

# 3. THE DOWNSTREAM SERVICE (Service B)
def handle_downstream_request(request):
    deadline = float(request.headers.get("X-Deadline"))
    
    if time.time() > deadline:
        # Fail fast! Don't query the DB.
        return HTTP_504("Deadline exceeded")
        
    # Continue processing...
    db.query("SELECT *...", timeout=(deadline - time.time()))
```

## 7\. Configuration Strategy: The "Default" Timeout

What if there is no deadline header?

  * You must enforce a **Default Sanity Timeout** on the infrastructure level (e.g., 5 seconds).
  * **Do not use infinite timeouts.** There is *never* a valid reason for a web request to hang for infinite time.
  * **The Database is the Bottleneck:** Your application timeouts should generally be *shorter* than your database timeouts to allow the app to handle the error gracefully before the DB kills the connection.
