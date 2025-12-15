# 07\. Strangler Fig Pattern

## 1\. The Concept

The Strangler Fig Pattern involves incrementally migrating a legacy system by gradually replacing specific pieces of functionality with new applications and services. As features are migrated, the new system grows around the old one (like a Strangler Fig tree around a host tree), eventually intercepting all calls until the legacy system is strangled (decommissioned).

## 2\. The Problem

  * **Scenario:** You have a massive 10-year-old Monolith ("The Legacy App") that is hard to maintain, full of bugs, and written in an outdated language. Business leadership wants to modernize it.
  * **The Risk (The Big Bang Rewrite):**
      * **The Freeze:** You stop adding features to the old app to focus on the rewrite. Business halts for 18 months.
      * **The Moving Target:** By the time the rewrite is "done" 2 years later, the business requirements have changed, and the new app is already obsolete.
      * **The Failure:** Most Big Bang rewrites are abandoned before they ever reach production.

## 3\. The Solution

Instead of rewriting everything at once, you place a **Facade** (API Gateway, Load Balancer, or Proxy) in front of the legacy system.

1.  Initially, the Facade routes 100% of traffic to the Legacy App.
2.  You build **one** new microservice (e.g., "User Profile").
3.  You update the Facade to route `/users` traffic to the new service, while everything else (`/orders`, `/products`) still goes to the Legacy App.
4.  Repeat this process until the Legacy App has zero traffic.
5.  Turn off the Legacy App.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "This old code is trash. Let's delete it all and start a fresh repository. We can probably rewrite it in 3 months." | **Catastrophe.** The rewrite takes 12 months. The team discovers hidden business logic in the old code that they missed. The project is cancelled. |
| **Senior** | "Don't touch the old code. Put a proxy in front of it. We will migrate the 'Search' module to a new service next sprint. If it works, we keep going. If it fails, we switch the route back instantly." | **Safety & Value.** Value is delivered continuously (weeks, not years). If the new architecture is bad, we find out early. The business never stops running. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * Migrating a Monolith to Microservices.
      * Moving from On-Premise to Cloud.
      * The legacy system is too large to rewrite in a single release cycle.
      * You need to deliver new features *while* refactoring.
  * ❌ **Avoid when:**
      * **Small Systems:** If the app is small (e.g., \< 20k lines of code), just rewrite it. The overhead of the Strangler pattern isn't worth it.
      * **Tightly Coupled Database:** If the legacy code relies on massive 50-table SQL joins, you can't easily peel off one service without breaking the data layer. (See *Anti-Corruption Layer*).

## 6\. Implementation Strategy (The Routing Logic)

The magic happens in the **Routing Layer** (e.g., Nginx, AWS ALB, or a code-level Interceptor).

### Step 1: The Setup (100% Legacy)

```nginx
# Nginx Configuration
upstream legacy_backend {
    server 10.0.0.1:8080;
}

server {
    listen 80;
    
    # Catch-all: Send everything to Legacy
    location / {
        proxy_pass http://legacy_backend;
    }
}
```

### Step 2: The Strangle (90% Legacy, 10% New)

We identified that `/api/v1/search` is the first candidate for migration. We build the `New Search Service`.

```nginx
upstream legacy_backend {
    server 10.0.0.1:8080;
}

upstream new_search_service {
    server 10.0.0.5:5000;
}

server {
    listen 80;

    # 1. Intercept Search traffic
    location /api/v1/search {
        proxy_pass http://new_search_service;
    }

    # 2. Everything else still goes to Legacy
    location / {
        proxy_pass http://legacy_backend;
    }
}
```

### Step 3: Handling Data Synchronization

The hardest part is data. If the New Service needs data that the Legacy App writes, or vice versa, you often need a temporary sync mechanism.

  * **Double Write:** The application writes to *both* the old DB and the new DB.
  * **Change Data Capture (CDC):** A tool (like Debezium) watches the Legacy DB logs and syncs changes to the New DB in near real-time.

## 7\. Operational Notes

  * **The "Zombie" Risk:** Sometimes the Strangler process stops halfway (e.g., 50% migrated). You are left with two systems to maintain (the worst of both worlds). You must commit to finishing the job.
  * **Url Mapping:** You might need to maintain the old URL structure (`/old-app/user.php?id=1`) even in the new system to avoid breaking clients, or use the proxy to rewrite paths (`/users/1`).