
# 31\. Modular Monolith

## 1\. The Concept

A Modular Monolith is a software architecture where the entire application is deployed as a single unit (one binary, one container, one process), but the internal code is structured into strictly isolated "Modules" that align with Business Domains.

Crucially, these modules cannot import each other's internal classes. They can only communicate via defined **Public APIs** (Java Interfaces, Public Classes), similar to how Microservices talk via HTTP, but using in-process function calls.

## 2\. The Problem

  * **Scenario:** A startup follows the "Microservices First" hype. They build 15 services (User, Billing, Notification, etc.) for a team of 5 developers.
  * **The "Distributed Monolith":**
      * **Refactoring Hell:** Changing a user's `email` field requires updating proto files in 3 repos and deploying them in a specific order.
      * **Latency:** A simple "Load Profile" request hits 6 different services. The network overhead makes the app feel sluggish.
      * **Debugging:** You need distributed tracing just to see why a variable is null.
      * **Cost:** You are paying for 15 Load Balancers and 15 RDS instances for a system that has 100 concurrent users.

## 3\. The Solution

Build a Monolith, but design it like Microservices.

1.  **Strict Boundaries:** Create root folders: `/modules/users`, `/modules/billing`.
2.  **Encapsulation:** The `Billing` module cannot access the `users` database table directly. It must ask the `UserModule` public interface.
3.  **Synchronous Speed:** Communication happens via function calls (nanoseconds), not HTTP (milliseconds).
4.  **ACID Transactions:** You can use a single database transaction across modules, guaranteeing consistency without complex Sagas.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "Monoliths are legacy. Netflix uses Microservices, so we should too. I'll split the Login logic into a separate `AuthService`." | **Resume-Driven Development.** You introduce network failures, serialization costs, and eventual consistency problems to a system that doesn't need them. Development velocity slows to a crawl. |
| **Senior** | "We don't have Netflix's scale. We have a small team. Build a Modular Monolith. If the 'Billing' module eventually requires 100x scaling, *then* we can extract it into a microservice." | **Optionality.** You get the simplicity of a Monolith today, with the structure to migrate to Microservices tomorrow if you win the lottery. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Startups / Scale-ups:** Teams of 1–50 developers.
      * **Unclear Boundaries:** You don't know yet if "Authors" and "Books" should be separate domains. Refactoring a monolith is easy (Drag & Drop files). Refactoring microservices is hard.
      * **Performance:** High-frequency interactions between components where HTTP latency is unacceptable.
  * ❌ **Avoid when:**
      * **Heterogeneous Tech Stack:** If Module A *must* be written in Python (Data Science) and Module B *must* be in Java.
      * **Massive Scale:** If you have 500 developers working on the same repo, the CI/CD pipeline becomes the bottleneck (merge conflicts, slow builds).

## 6\. Implementation Example (Java/Spring style)

The key is enforcing boundaries. In Java, this is done with package-private visibility or tools like **ArchUnit**.

```java
// ❌ BAD (Spaghetti Monolith)
// Any code can access the User Entity directly
import com.myapp.users.internal.UserEntity; 
UserEntity user = userRepo.findById(1);


// ✅ GOOD (Modular Monolith)

// MODULE 1: USERS
package com.myapp.modules.users.api;

public interface UserService {
    // Only DTOs (Data Transfer Objects) are exposed.
    // The internal "UserEntity" (Database Row) never leaves the module.
    UserDTO getUser(String id);
}

// MODULE 2: BILLING
package com.myapp.modules.billing;

import com.myapp.modules.users.api.UserService; // Can only import API package

public class BillingService {
    private final UserService userService; // Dependency Injection

    public void chargeUser(String userId) {
        // Fast in-process call. No HTTP. No JSON parsing.
        UserDTO user = userService.getUser(userId);
        
        if (user.hasCreditCard()) {
            // ... charge logic
        }
    }
}
```

## 7\. Enforcing the Architecture (ArchUnit)

If you don't enforce the rules, entropy will turn your Modular Monolith into a Spaghetti Monolith. Use a linter or test tool.

```java
@Test
public void modules_should_respect_boundaries() {
    slices().matching("com.myapp.modules.(*)..")
        .should().notDependOnEachOther()
        .ignoreDependency(
            ResideInAPackage("..billing.."),
            ResideInAPackage("..users.api..") // Whitelist public APIs
        )
        .check(importedClasses);
}
```

## 8\. The "Extraction" Strategy

The Modular Monolith is often a stepping stone.

  * **Phase 1:** `Billing` is a module inside the Monolith.
  * **Phase 2 (Scale):** Billing needs to handle millions of webhooks. It's slowing down the main app.
  * **Phase 3 (Extraction):**
    1.  Create a new Microservice repo for Billing.
    2.  Copy the `/modules/billing` folder code into it.
    3.  In the Monolith, replace the `BillingService` implementation with a **gRPC Client** that calls the new Microservice.
    4.  The rest of the Monolith code **doesn't change** because it was programmed against the Interface, not the implementation.