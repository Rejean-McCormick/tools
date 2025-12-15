# 04\. Graceful Degradation

## 1\. The Concept

Graceful Degradation is the strategy of allowing a system to continue operating, perhaps at a reduced level of functionality, when some of its components or dependencies fail. Instead of a "Hard Crash" (total system failure), the system performs a "Soft Landing."

Think of it like a car with a flat tire. You can't drive at 100 mph, but you can still drive at 30 mph to get to the mechanic. You don't just explode on the highway.

## 2\. The Problem

  * **Scenario:** An e-commerce Product Page consists of:
    1.  Product Details (Price/Title) - **Core**
    2.  Inventory Check - **Core**
    3.  User Reviews - **Auxiliary**
    4.  "People also bought" Recommendations - **Auxiliary**
  * **The Risk:** The "Recommendations Service" (an AI engine) goes down.
      * **The Monolith Mindset:** The Product Page API throws an exception because it failed to fetch recommendations. The user sees a 500 Server Error.
      * **The Result:** We lost a sale because a non-essential "nice-to-have" feature broke the essential "must-have" feature.

## 3\. The Solution

We categorize all system features into **Critical** and **Non-Critical**.

  * If a **Critical** component fails, we return an error (we cannot proceed).
  * If a **Non-Critical** component fails, we catch the error, log it, and render the page *without* that specific feature. The user usually doesn't even notice.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "The `getRecommendations()` call threw an exception, so I let it bubble up to the global error handler." | **Total Outage.** A minor feature failure makes the entire application unusable for the customer. |
| **Senior** | "Wrap the recommendation call in a `try/catch`. If it fails, return an empty list. The UI will just collapse that section." | **Resilience.** The customer can still buy the product. We sacrifice 5% of the experience to save 95% of the value. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Auxiliary Content:** Reviews, comments, recommendations, advertising banners, social media feeds.
      * **Enhancements:** High-res images (fallback to low-res), personalized sorting (fallback to default sorting).
      * **Search:** Detailed search is down? Fallback to a simple SQL `LIKE` query.
  * ❌ **Avoid when:**
      * **Transactional Consistency:** You cannot "gracefully degrade" a bank transfer. It either happens or it doesn't.
      * **Legal/Compliance:** If you are required by law to show a "Health Warning" and that service fails, you must block the page.

## 6\. Implementation Example (Pseudo-code)

The key is identifying the **Critical Path**.

```python
def load_product_page(product_id):
    response = {}

    # 1. CRITICAL: Product Details (Must succeed)
    try:
        response['product'] = db.get_product(product_id)
        response['price'] = pricing_service.get_price(product_id)
    except Exception:
        # If this fails, the page is useless. Fail hard.
        raise HTTP_500("Core product data unavailable")

    # 2. NON-CRITICAL: Recommendations (Can fail safely)
    try:
        response['recommendations'] = ai_service.get_recommendations(product_id)
    except TimeoutError:
        # Log the error for the dev team, but don't crash the user's request
        logger.error("AI Service timeout")
        response['recommendations'] = []  # Return empty list

    # 3. NON-CRITICAL: User Reviews (Can fail safely)
    try:
        response['reviews'] = review_service.get_top_reviews(product_id)
    except ServiceUnavailable:
        logger.error("Review Service down")
        response['reviews'] = None # UI handles 'None' by hiding the widget

    return response
```

## 7\. The Frontend's Role

Graceful degradation often requires coordination with the Frontend (UI/Client).

  * The API returns a partial response (missing fields).
  * The Frontend must be coded defensively: "If `reviews` is missing, just don't render the `<div>`. Don't show a spinning wheel forever and don't show a standard 'Error' alert."

## 8\. Related Patterns

  * **Circuit Breaker:** Often used to trigger the degradation. If the circuit is open, we immediately degrade to the fallback.
  * **Cache-Aside:** If the live service fails, degrading to "Stale Data" (cached data from 10 minutes ago) is often the best form of degradation.