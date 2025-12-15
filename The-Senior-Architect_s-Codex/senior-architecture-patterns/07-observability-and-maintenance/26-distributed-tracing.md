# 26\. Distributed Tracing

## 1\. The Concept

Distributed Tracing is a method used to profile and monitor applications, especially those built using a microservices architecture. It tracks a single request as it propagates through various services, databases, and message queues, providing a holistic view of the request's journey.

It relies on generating a unique **Trace ID** at the entry point of the system and passing that ID (via HTTP headers) to every downstream service.

## 2\. The Problem

  * **Scenario:** A user reports that the "Checkout" page is taking 10 seconds to load.
  * **The Architecture:** The Checkout Service calls the Inventory Service, which calls the Warehouse DB, and then calls the Shipping Service, which calls a 3rd Party API.
  * **The Investigation:**
      * The Checkout Team says: "Our logs show we sent the request and waited 9.9 seconds. It's not us."
      * The Inventory Team says: "We processed it in 50ms. It's not us."
      * The Database Team says: "CPU is low. It's not us."
  * **The Reality:** Without tracing, you are hunting ghosts. You have no way to prove *where* the time was spent.

## 3\. The Solution

Implement **OpenTelemetry** (or Zipkin/Jaeger).

1.  **Trace ID:** When the request hits the Load Balancer, generate a UUID (`abc-123`).
2.  **Context Propagation:** Pass `X-Trace-ID: abc-123` in the header of *every* internal API call.
3.  **Spans:** Each service records a "Span" (Start Time, End Time, Trace ID).
4.  **Visualization:** A central dashboard aggregates all Spans with ID `abc-123` into a waterfall chart.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "I'll grep the logs on Server A, then SSH to Server B and grep the logs there, trying to match timestamps." | **Needle in a Haystack.** Impossible at scale. Timestamps drift. You can't verify if Log A corresponds to Log B. |
| **Senior** | "I'll look up the Trace ID in Jaeger. The waterfall view shows a 9-second gap between the Inventory Service and the Shipping Service." | **Instant Root Cause.** You immediately see that the *network connection* between A and B caused the timeout, not the code itself. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Microservices:** Mandatory. You cannot debug without it.
      * **Performance Tuning:** Identifying bottlenecks (e.g., "Why is this API call slow?").
      * **Error Analysis:** Finding out which service in a chain of 10 threw the 500 error.
  * ❌ **Avoid when:**
      * **Monoliths:** If everything happens in one process, a standard profiler or stack trace is sufficient.
      * **Privacy:** Be careful not to include PII (Credit Card Numbers, Passwords) in the Trace spans / Tags.

## 6\. Implementation Example (Pseudo-code)

**Scenario:** Service A calls Service B.

### Service A (The Initiator)

```python
import requests
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def checkout_handler(request):
    # Start the "Root Span"
    with tracer.start_as_current_span("checkout_process") as span:
        span.set_attribute("user_id", request.user_id)
        
        # Inject Trace ID into Headers
        headers = {}
        trace.get_current_span().get_span_context().inject(headers)
        
        # Headers now contains: { "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" }
        requests.get("http://service-b/inventory", headers=headers)
```

### Service B (The Downstream)

```python
def inventory_handler(request):
    # Extract Trace ID from Headers
    context = trace.extract(request.headers)
    
    # Start a "Child Span" linked to the parent
    with tracer.start_as_current_span("check_inventory", context=context):
        db.query("SELECT * FROM items...")
        # This span will appear NESTED under Service A in the UI
```

## 7\. The Three Pillars of Observability

Tracing is just one part. A Senior Architect implements all three:

1.  **Logs:** "What happened?" (Error: NullPointerException).
2.  **Metrics:** "Is it happening a lot?" (Error Rate: 15%).
3.  **Traces:** "Where is it happening?" (Service B, Line 45).

## 8\. Sampling Strategies

Tracing every single request (100% sampling) is expensive (storage costs).

  * **Head-Based Sampling:** Decide at the start. "Trace 1% of all requests."
  * **Tail-Based Sampling:** Keep all traces in memory, but only write them to disk *if an error occurs* or latency is high. (More complex, but captures the "interesting" data).