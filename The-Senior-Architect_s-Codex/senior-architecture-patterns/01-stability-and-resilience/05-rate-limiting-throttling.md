# 05\. Rate Limiting (Throttling)

## 1\. The Concept

Rate Limiting is the process of controlling the rate of traffic sent or received by a network interface or service. It sets a cap on how many requests a user (or system) can make in a given timeframe (e.g., "100 requests per minute"). If the cap is exceeded, the server rejects the request—usually with HTTP status `429 Too Many Requests`—to protect itself from being overwhelmed.

## 2\. The Problem

  * **Scenario:** You have a public API. One customer writes a script with a bug in it that accidentally hits your API 10,000 times per second. Alternatively, a malicious actor launches a Denial of Service (DoS) attack.
  * **The Risk:**
      * **The Noisy Neighbor:** One aggressive user consumes 99% of your database connections and CPU.
      * **Service Denial:** The other 99% of your legitimate users get timeouts because the server is too busy processing the spam. Your system becomes unusable for everyone because of one bad actor.

## 3\. The Solution

Implement an interceptor at the entry point of your system (API Gateway or Load Balancer). This interceptor tracks the usage count for each user (based on IP, API Key, or User ID). If the count exceeds the defined quota, the request is dropped immediately before it touches the expensive business logic or database.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "Our servers are fast; let's process every request as it comes in. If we get slow, we'll just auto-scale more servers." | **Financial & Technical Ruin.** Scaling costs skyrocket during an attack. The database (which can't auto-scale easily) eventually melts down. |
| **Senior** | "Implement a Token Bucket algorithm. Unverified IPs get 10 req/min. Authenticated users get 1000 req/min. Drop the 1001st request instantly." | **Stability.** The system stays up for legitimate users. Malicious/buggy traffic is blocked at the gate at zero cost to the database. |

## 4\. Visual Diagram

## 5\. Common Algorithms

Rate limiting is not just "counting." There are specific algorithms with different trade-offs:

1.  **Fixed Window:** "100 requests between 12:00 and 12:01."
      * *Flaw:* If a user sends 100 requests at 12:00:59 and another 100 at 12:01:01, they effectively sent 200 requests in 2 seconds, potentially overloading the system.
2.  **Sliding Window:** Smoothes out the edges of the fixed window to prevent spikes at the boundary.
3.  **Token Bucket:** The standard industry algorithm.
      * Imagine a bucket that holds 10 tokens.
      * Every time a request comes in, it takes a token. No token? Request rejected.
      * The bucket refills at a constant rate (e.g., 1 token per second).
      * *Benefit:* Allows for "bursts" of traffic (you can use all 10 tokens at once) but enforces a long-term average.
4.  **Leaky Bucket:** Similar to Token Bucket, but processes requests at a constant, steady rate, smoothing out bursts completely.

## 6\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Public APIs:** Essential to prevent abuse.
      * **Login Endpoints:** To prevent Brute Force password guessing.
      * **Heavy Operations:** APIs that generate PDFs or reports need strict limits (e.g., 5 per minute).
      * **SaaS Tiers:** Enforcing business plans (Free Tier = 100 req/day; Pro Tier = 10,000 req/day).
  * ❌ **Avoid when:**
      * **Internal High-Trust Traffic:** If Service A calls Service B inside a private cluster, aggressive rate limiting might cause false positives during valid traffic spikes. Use **Backpressure** instead.

## 7\. Implementation Example (Pseudo-code)

A simple implementation using **Redis** to store the counters (since Redis is fast and atomic).

```python
import redis
import time

r = redis.Redis()

def is_rate_limited(user_id, limit=10, window_seconds=60):
    # Create a unique key for this user and window
    # e.g., "rate_limit:user_123"
    key = f"rate_limit:{user_id}"
    
    # 1. Increment the counter
    current_count = r.incr(key)
    
    # 2. If this is the first request, set the expiry (TTL)
    if current_count == 1:
        r.expire(key, window_seconds)
        
    # 3. Check against limit
    if current_count > limit:
        return True # Rate Limited!
        
    return False # Allowed

# API Controller
def handle_request(request):
    user_id = request.headers.get("API-Key")
    
    if is_rate_limited(user_id):
        return HTTP_429("Too Many Requests. Try again in 1 minute.")
        
    # Proceed to business logic...
    return process_data(request)
```

## 8\. Header Standards

When you rate limit a user, you should be polite and tell them *why* and *when* they can come back. Use standard HTTP headers:

  * `X-RateLimit-Limit`: The ceiling for this timeframe (e.g., 100).
  * `X-RateLimit-Remaining`: The number of requests left in the current window (e.g., 42).
  * `X-RateLimit-Reset`: The time at which the current window resets (Unix timestamp).
  * `Retry-After`: The number of seconds to wait before making a new request.