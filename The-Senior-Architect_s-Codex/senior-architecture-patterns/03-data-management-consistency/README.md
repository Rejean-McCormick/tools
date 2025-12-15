# 💾 Group 3: Data Management & Consistency

## Overview

**"Data outlives code. If you corrupt the state, no amount of bug fixing will save you."**

In a monolithic application, you have one database and ACID transactions. Life is simple. In a distributed system, you have many databases, network partitions, and no global clock. Life is hard.

This module addresses the hardest problems in software architecture:

1.  **Distributed Transactions:** How to update two databases at once without a global lock.
2.  **State Synchronization:** How to keep the search index in sync with the primary database.
3.  **Reliability:** How to ensure a message is processed exactly once (or at least once) despite network failures.

The patterns here move you away from "Strong Consistency" (everything is instantly correct everywhere) to "Eventual Consistency" (everything will be correct... eventually).

## 📜 Pattern Index

| Pattern | Goal | Senior "Soundbite" |
| :--- | :--- | :--- |
| **[12. CQRS](https://www.google.com/search?q=./12-cqrs.md)** | **Read/Write Separation** | "Don't use the same model for complex validation and high-speed searching." |
| **[13. Event Sourcing](https://www.google.com/search?q=./13-event-sourcing.md)** | **Audit & History** | "Don't just store the current balance. Store every deposit and withdrawal that got us there." |
| **[14. Saga Pattern](https://www.google.com/search?q=./14-saga-pattern.md)** | **Distributed Transactions** | "We can't use 2-Phase Commit. If the Hotel fails, trigger a Compensating Transaction to refund the Flight." |
| **[15. Idempotency](https://www.google.com/search?q=./15-idempotency.md)** | **Duplicate Handling** | "If the user clicks 'Pay' twice, we must only charge them once. Check the Request ID." |
| **[16. Transactional Outbox](https://www.google.com/search?q=./16-transactional-outbox.md)** | **Message Reliability** | "Never fire-and-forget to Kafka. Write the event to the DB first, then relay it." |

## 🧠 The Data Checklist

Before deploying a distributed data system, a Senior Architect asks:

1.  **The "Split-Brain" Test:** If the network between the US and EU regions fails, do we stop writing (Consistency) or allow divergent writes (Availability)?
2.  **The "Replay" Test:** If a bug corrupted the data last Tuesday, can we replay the event log to fix the state, or is the data lost forever? (Event Sourcing).
3.  **The "Partial Failure" Test:** If the Order Service succeeds but the Email Service fails, is the system in a broken state? (Saga).
4.  **The "Double-Click" Test:** What happens if I send the exact same API request 10 times in 10 milliseconds? (Idempotency).

## ⚠️ Common Pitfalls in This Module

  * **Premature CQRS:** Implementing full Command/Query separation for a simple CRUD app. It doubles your code volume for zero gain.
  * **The "Magic" Event Bus:** Assuming that if you publish a message to RabbitMQ, it *will* arrive. It won't. You need Outboxes and Acknowledgments.
  * **Ignoring Order:** Distributed events often arrive out of order. If "User Updated" arrives before "User Created," your system must handle it (or reject it).

