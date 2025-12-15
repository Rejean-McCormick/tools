# 01\. Circuit Breaker

## 1\. The Concept

The Circuit Breaker is a defensive mechanism that prevents an application from repeatedly trying to execute an operation that's likely to fail. Like a physical electrical circuit breaker, it "trips" (opens) when it detects a fault, instantly cutting off the connection to the failing component to prevent catastrophic overload.

## 2\. The Problem

  * **Scenario:** Your "Order Service" calls an external "Inventory Service" to check stock. The Inventory Service is currently under heavy load and responding very slowly (or returning errors).
  * **The Risk:**
      * **Resource Exhaustion:** Your Order Service keeps waiting for timeouts (e.g., 30 seconds). All your threads get blocked waiting for the Inventory Service.
      * **Cascading Failure:** Because your Order Service is blocked, it stops responding to the "User Interface." Eventually, the entire system crashes, even though only one small component (Inventory) was actually broken.

## 3\. The Solution

Wrap the dangerous function call in a proxy that monitors for failures. The proxy operates as a state machine with three states:

1.  **CLOSED (Normal):** Requests flow through normally. If failures cross a threshold (e.g., 5 failures in 10 seconds), the breaker trips to **OPEN**.
2.  **OPEN (Tripped):** The proxy intercepts calls and *immediately* returns an error or a fallback value (Fail Fast). It does not send traffic to the struggling service. This gives the failing service time to recover.
3.  **HALF-OPEN (Testing):** After a "Cool-down" period, the proxy allows *one* test request to pass through.
      * If it succeeds, the breaker resets to **CLOSED**.
      * If it fails, it goes back to **OPEN**.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "The API is failing? Let's increase the timeout to 60 seconds and put it in a `while` loop to retry until it works." | **System Death.** The calling service ties up all its threads waiting. The failing service gets hammered with retries, ensuring it never recovers. |
| **Senior** | "If the API fails 5 times, stop calling it. Return a cached value or a 'Try again later' message instantly. Don't waste our own CPU waiting for a dead service." | **Survival.** The calling service remains responsive. The failing service gets a break to reboot or auto-scale. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * Calling **external** third-party APIs (Stripe, Twilio, Google Maps).
      * Calling internal microservices that are network-bound.
      * Database connections that are prone to timeouts during high load.
  * ❌ **Avoid when:**
      * **Local function calls:** Don't wrap in-memory logic; exceptions are sufficient there.
      * **Synchronous strict consistency:** If you *must* have the data (e.g., withdrawing money from a bank ledger), failing fast with a default value isn't an option. You might need a transaction manager instead.

## 6\. Implementation Example (Pseudo-code)

Here is a simplified Python implementation demonstrating the logic. In production, use libraries like **Resilience4j** (Java), **Polly** (.NET), or **PyBreaker** (Python).

```python
import time

class CircuitBreaker:
    def __init__(self):
        self.state = "CLOSED"
        self.failure_count = 0
        self.threshold = 5          # Trip after 5 failures
        self.reset_timeout = 10     # Wait 10s before trying again
        self.last_failure_time = None

    def call_service(self, service_function):
        if self.state == "OPEN":
            # Check if cool-down period has passed
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF_OPEN"
            else:
                # FAIL FAST: Don't even try to call the service
                raise Exception("Circuit is OPEN. Service unavailable.")

        try:
            # Attempt the actual call
            result = service_function()
            
            # If successful in HALF_OPEN, reset to CLOSED
            if self.state == "HALF_OPEN":
                self.reset()
            return result
            
        except Exception as e:
            self.record_failure()
            raise e

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.threshold:
            self.state = "OPEN"
            print("⚠️ Circuit Tripped! Entering OPEN state.")

    def reset(self):
        self.state = "CLOSED"
        self.failure_count = 0
        print("✅ Service recovered. Circuit Closed.")
```

## 7\. Real-World Fallbacks

When the circuit is Open, what do you return to the user?

1.  **Cache:** Return the data from 5 minutes ago (better than nothing).
2.  **Stubbed Data:** Return an empty list `[]` or `null`.
3.  **Drop Functionality:** If the "Recommendations" service is down, just hide the "Recommended for You" widget on the UI.