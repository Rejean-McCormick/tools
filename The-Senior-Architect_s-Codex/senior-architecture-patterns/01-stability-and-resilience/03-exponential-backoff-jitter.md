# 03\. Exponential Backoff with Jitter

## 1\. The Concept

Exponential Backoff with Jitter is a standard algorithm for handling retries in distributed systems. Instead of retrying a failed request immediately, the client waits for a period of time that increases exponentially with each failure ($1s, 2s, 4s, 8s$). "Jitter" adds a randomized variance to this wait time to prevent all clients from retrying at the exact same moment.

## 2\. The Problem

  * **Scenario:** Your database goes down briefly for a restart. 10,000 users are currently online trying to save their work. All 10,000 requests fail simultaneously.
  * **The Risk (The Thundering Herd):**
      * **Naive Retries:** If every client retries immediately (or on a fixed 5-second interval), the database is hit with 10,000 requests the instant it comes back up.
      * **The Death Spiral:** This massive spike creates a new outage immediately. The database goes down again, the clients wait 5 seconds, and then they all hit it *again* at the exact same timestamp. The system never recovers.

## 3\. The Solution

We modify the retry logic to introduce two factors:

1.  **Exponential Delay:** Increase the wait time significantly after each failure to give the struggling subsystem breathing room.
2.  **Jitter (Randomness):** Add a random number to the wait time. This spreads out the requests over a window of time, ensuring the database sees a smooth curve of traffic rather than a vertical spike.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "If the request fails, put it in a `while` loop and keep trying until it succeeds." | **Self-Inflicted DDoS.** The application essentially attacks its own backend servers, ensuring they stay down. |
| **Senior** | "Wait $Base \times 2^{Attempt} + Random$ seconds. Cap it at a Max Delay." | **Smooth Recovery.** The retries are desynchronized. The backend receives a manageable trickle of traffic as it reboots. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Transient Failures:** Network blips, database locks, or temporary service unavailability (HTTP 503).
      * **Throttling:** If you receive an HTTP 429 (Too Many Requests), you *must* back off.
      * **Background Jobs:** Queue consumers that fail to process a message.
  * ❌ **Avoid when:**
      * **Permanent Errors:** If the error is HTTP 400 (Bad Request) or 401 (Unauthorized), retrying will never fix it. Fail immediately.
      * **User-Facing Latency:** If a user is waiting for a page to load, you probably can't wait 30 seconds for a retry. Fail fast and show an error message.

## 6\. Implementation Example (Pseudo-code)

The formula usually looks like this:
$$Sleep = min(Cap, Base \times 2^{Attempt}) + Random(0, Base)$$

```python
import time
import random

def call_with_backoff(api_function, max_retries=5):
    base_delay = 1  # seconds
    max_delay = 32  # seconds cap
    
    for attempt in range(max_retries):
        try:
            return api_function()
        except Exception as e:
            # Check if this is the last attempt
            if attempt == max_retries - 1:
                print("Max retries reached. Giving up.")
                raise e
            
            # Calculate Exponential Backoff
            sleep_time = min(max_delay, base_delay * (2 ** attempt))
            
            # Add Jitter (Randomness between 0 and 1 second)
            # This desynchronizes this client from others
            jitter = random.uniform(0, 1)
            total_sleep = sleep_time + jitter
            
            print(f"Attempt {attempt + 1} failed. Retrying in {total_sleep:.2f}s...")
            time.sleep(total_sleep)
```

## 7\. Configuration Strategy

  * **Base Delay:** Start small (e.g., 100ms or 1s).
  * **Max Delay (Cap):** Always set a ceiling. You don't want a client waiting 3 hours for a retry. usually 30s or 60s is the limit.
  * **Max Retries:** Infinite retries are dangerous. Give up after 3 to 5 attempts to release the thread.