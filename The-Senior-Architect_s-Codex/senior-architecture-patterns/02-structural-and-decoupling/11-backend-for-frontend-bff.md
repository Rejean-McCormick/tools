# 11\. Backend for Frontend (BFF)

## 1\. The Concept

The Backend for Frontend (BFF) pattern creates separate backend services to be consumed by specific frontend applications. Instead of having one "General Purpose API" that tries to satisfy the Mobile App, the Web Dashboard, and the 3rd Party Integrations all at once, you build a dedicated API layer for each interface.

## 2\. The Problem

  * **Scenario:** You have a single "User Service" API.
      * The **Desktop Web App** needs rich data: User details, last 10 orders, invoices, and activity logs to fill a large screen.
      * The **Mobile App** (running on 4G) needs minimal data: Just the User Name and Avatar to show in the header.
  * **The Risk (The One-Size-Fits-None):**
      * **Over-fetching (Mobile Pain):** If the Mobile App calls the generic API, it downloads a massive 50KB JSON object just to display a name. This wastes the user's data plan and drains the battery.
      * **Under-fetching (Chatty Interfaces):** If the API is too granular, the Desktop App has to make 5 parallel network calls just to render one page.

## 3\. The Solution

Build a specific adapter layer for each frontend experience.

  * **Mobile BFF:** Calls the downstream microservices, strips out heavy data, and returns a lean JSON response tailored exactly to the mobile screen size.
  * **Web BFF:** Calls multiple microservices, aggregates the responses into a single rich object, and sends it to the browser.

The BFF is owned by the *Frontend Team*, not the Backend Team. It is part of the "client experience," just running on the server.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "We have one REST API. If the mobile team needs less data, they can just ignore the fields they don't need." | **Performance Bloat.** Mobile users suffer from slow load times. The API becomes a mess of optional parameters like `?exclude_logs=true&include_orders=false`. |
| **Senior** | "The Mobile team builds a Node.js BFF. It formats the data exactly how their UI needs it. The Core API stays generic and clean." | **Optimized UX.** Mobile gets tiny payloads. Web gets rich payloads. The Core Services don't need to change every time the UI changes. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Distinct Interfaces:** The Mobile UI is significantly different from the Web UI (e.g., simplified flows, different data requirements).
      * **Team Scaling:** You have separate teams for Mobile and Web. The Mobile team can update their BFF without waiting for the Backend team to deploy API changes.
      * **Aggregating Microservices:** Your frontend needs to call 6 different services to build the home page. Do that aggregation in the BFF (server-side, low latency) rather than the browser.
  * ❌ **Avoid when:**
      * **Single Interface:** If you only have a Web App, a BFF is just useless extra code.
      * **Similar Needs:** If the Mobile App and Web App look exactly the same and use the same data, just use a common API.

## 6\. Implementation Example (Pseudo-code)

**Scenario:** We need to render the "Order History" page.

### The Downstream Microservices (Generic)

  * `OrderService`: Returns massive JSON with shipping details, tax codes, warehouse IDs.
  * `ProductService`: Returns images, descriptions, specs.

### 1\. The Mobile BFF (Optimized for Bandwidth)

*The Mobile screen only shows a list of Item Names and Prices.*

```javascript
// MobileBFF/controllers/orders.js
async function getMobileOrders(userId) {
    // 1. Fetch raw data
    const rawOrders = await OrderService.getAll(userId);
    
    // 2. Transform & Strip Data
    const mobileData = rawOrders.map(order => ({
        id: order.id,
        date: order.created_at,
        total: order.final_price_usd, // Formatted string
        status: order.status
        // REMOVED: tax_details, shipping_address, warehouse_logs, item_specs
    }));

    return mobileData; // Payload size: 2KB
}
```

### 2\. The Web BFF (Optimized for Richness)

*The Web Dashboard shows everything, plus product images.*

```javascript
// WebBFF/controllers/orders.js
async function getWebOrders(userId) {
    // 1. Fetch raw orders
    const orders = await OrderService.getAll(userId);
    
    // 2. Fetch extra product details for every item (Aggregation)
    // The browser doesn't have to make these calls!
    for (let order of orders) {
        order.product_images = await ProductService.getImages(order.product_ids);
        order.invoices = await InvoiceService.getByOrder(order.id);
    }

    return orders; // Payload size: 50KB
}
```

## 7\. Operational Notes

  * **Keep it Logic-Free:** The BFF should contain **Presentation Logic** (formatting, sorting, aggregating), not **Business Logic** (calculating tax, validating inventory). Business logic belongs in the Core Services.
  * **GraphQL as a BFF:** Many teams use GraphQL as a "Universal BFF." The frontend queries exactly what it needs (`{ user { name } }`), effectively solving the over-fetching problem without writing manual BFF controllers.
