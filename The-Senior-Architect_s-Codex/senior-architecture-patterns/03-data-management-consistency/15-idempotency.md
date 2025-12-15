# 15\. Idempotency

## 1\. The Concept

Idempotency is a property of an operation whereby it can be applied multiple times without changing the result beyond the initial application. In distributed systems, this means that if a client sends the same request twice (due to a retry, a network glitch, or a double-click), the server processes it only once and returns the same response.

Mathematically, $f(f(x)) = f(x)$.

## 2\. The Problem

  * **Scenario:** A user is purchasing a concert ticket. They click "Pay $100."
      * **The Glitch:** The user's WiFi flickers. The browser doesn't receive the "Success" confirmation, so the frontend code (or the impatient user) retries the request.
      * **The Backend Reality:** The first request *did* reach the server and charged the credit card. The second request *also* reaches the server.
  * **The Risk (Double Charge):** Without idempotency, the server sees two valid requests and charges the user $200. This destroys trust and creates a customer support nightmare.

## 3\. The Solution

Assign a unique **Idempotency Key** (or Request ID) to every transactional request.

1.  **Client:** Generates a unique UUID (e.g., `req_123`) for the "Pay" action.
2.  **Server:** Checks its cache/database: "Have I seen `req_123` before?"
      * **No:** Process the payment. Save `req_123` + Response in the database. Return Success.
      * **Yes:** Stop\! Do not process again. Retrieve the saved Response from the database and return it immediately.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "I'll just check if the user has bought a ticket in the last 5 minutes." | **Race Conditions.** If two requests arrive at the exact same millisecond, both might pass the check before the database records the first one. |
| **Senior** | "Require an `Idempotency-Key` header. Use a unique constraint in the database or an atomic `SET NX` in Redis to ensure strict exactly-once processing." | **Correctness.** No matter how many times the user clicks or the network retries, the side effect happens exactly once. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Payments:** Essential for any financial transaction.
      * **Creation:** `POST` requests that create resources (e.g., "Create Order").
      * **Webhooks:** Receiving events from Stripe/Twilio (they will retry if you don't respond 200 OK, so you must handle duplicates).
  * ❌ **Avoid when:**
      * **GET Requests:** Reading data is naturally idempotent. (Reading a blog post twice doesn't change the blog post).
      * **PUT Requests:** Often naturally idempotent (Updating "Name=John" to "Name=John" twice is usually fine), but be careful with relative updates ("Add +1 to Score").

## 6\. Implementation Example (Pseudo-code)

**Scenario:** A Payment API using Redis for deduplication.

```python
import redis

# Redis connection
cache = redis.Redis(host='localhost', port=6379, db=0)

def process_payment(request):
    # 1. Extract the Idempotency Key
    idem_key = request.headers.get('Idempotency-Key')
    if not idem_key:
        return HTTP_400("Missing Idempotency-Key header")

    # 2. Check if we've seen this key (Atomic Check)
    # redis_key structure: "idem:req_123"
    redis_key = f"idem:{idem_key}"
    
    # Try to lock this key. 
    # If setnx returns 0, it means the key already exists (Duplicate Request).
    # We set a 24-hour expiration so keys don't fill up RAM forever.
    is_new_request = cache.setnx(redis_key, "PROCESSING")
    cache.expire(redis_key, 86400) # 24 hours

    if not is_new_request:
        # 3. Handle Duplicate
        # Wait for the first request to finish if it's still processing
        stored_response = wait_for_result(redis_key)
        return stored_response

    # 4. Process the Actual Logic (The dangerous part)
    try:
        result = payment_gateway.charge(request.amount)
        response_data = {"status": "success", "tx_id": result.id}
        
        # 5. Update the cache with the real result
        cache.set(redis_key, json.dumps(response_data))
        
        return HTTP_200(response_data)
        
    except Exception as e:
        # If it failed, delete the key so they can retry? 
        # Or store the error? Depends on business logic.
        cache.delete(redis_key)
        return HTTP_500("Payment Failed")
```

## 7\. The "Scope" of Idempotency Keys

A common mistake is reusing keys inappropriately.

  * **Scope by User:** The key `order_1` for User A is different from `order_1` for User B? Usually, yes.
  * **Expiration:** How long do you keep the keys?
      * **Too short (5s):** If a retry comes 6 seconds later, it duplicates.
      * **Too long (Forever):** You run out of storage.
      * **Senior Rule:** Keep keys for slightly longer than your maximum retry window (e.g., 24 to 48 hours).

## 8\. HTTP Verbs & Idempotency

  * `GET`: Idempotent (Safe).
  * `PUT`: Idempotent (Usually replaces state).
  * `DELETE`: Idempotent (Deleting a deleted record returns 404, but state remains "deleted").
  * `POST`: **NOT Idempotent.** This is where you strictly need the pattern.