# 🧬 Group 2: Structural & Decoupling

## Overview

**"The only constant is change. Architecture is the art of making change easy."**

If Group 1 was about keeping the system *alive*, Group 2 is about keeping the system *maintainable*. As systems grow, they tend to become "Big Balls of Mud"—tangled webs of dependencies where changing one line of code breaks a feature three modules away.

These patterns provide the strategies to modularize systems, isolate dependencies, and modernize legacy codebases without the risky "Big Bang Rewrite." They allow you to swap out databases, upgrade frameworks, or split monoliths with surgical precision.

## 📜 Pattern Index

| Pattern | Goal | Senior "Soundbite" |
| :--- | :--- | :--- |
| **[07. Strangler Fig](https://www.google.com/search?q=./07-strangler-fig.md)** | **Legacy Migration** | "Don't rewrite the monolith. Grow the new system around it until the old one dies." |
| **[08. Anti-Corruption Layer](https://www.google.com/search?q=./08-anti-corruption-layer.md)** | **Boundary Protection** | "Never let the legacy system's bad naming conventions leak into our clean domain." |
| **[09. Sidecar Pattern](https://www.google.com/search?q=./09-sidecar-pattern.md)** | **Infra Offloading** | "The application code shouldn't know how to encrypt SSL or ship logs." |
| **[10. Hexagonal Architecture](https://www.google.com/search?q=./10-hexagonal-architecture.md)** | **Logic Isolation** | "I should be able to test the core business logic without spinning up a database." |
| **[11. Backend for Frontend](https://www.google.com/search?q=./11-backend-for-frontend-bff.md)** | **UI Optimization** | "The mobile app has different data needs than the desktop app. Don't force them to share one generic API." |

## 🧠 The Structural Checklist

Before approving a pull request or design document, a Senior Architect asks:

1.  **The "Database Swap" Test:** If we decided to switch from MySQL to MongoDB next year, how much business logic would we have to rewrite? (Ideally: None, only the Adapters).
2.  **The "Vendor Lock-in" Test:** If the 3rd-party Shipping Provider changes their API format, does it break our internal `Order` class? (It shouldn't, if an ACL is present).
3.  **The "Team Autonomy" Test:** Can the Mobile Team release a new feature without begging the Backend Team to change the core database schema? (BFF helps here).
4.  **The "Zombie" Test:** Do we have a plan to *finish* the migration, or will we be running the Strangler Fig pattern for 5 years?

## ⚠️ Common Pitfalls in This Module

  * **The Distributed Monolith:** You split your code into microservices, but they are so tightly coupled (sharing databases, synchronous calls) that you still have to deploy them all at once. This is worse than a regular monolith.
  * **Abstraction Overdose:** Creating 15 layers of interfaces (Ports/Adapters) for a simple "Hello World" app. Structural patterns pay off *only* when complexity is high.
  * **The "Universal" API:** Trying to build one single REST API that perfectly serves Mobile, Web, Watch, and IoT devices. It inevitably serves none of them well.

