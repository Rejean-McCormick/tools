# 📨 Group 5: Messaging & Communication

## Overview

**"Decoupling in time is just as important as decoupling in space."**

Direct HTTP calls (REST/gRPC) are synchronous: the client waits for the server. This couples them in time. If the server is busy, the client hangs. If the server is down, the client fails.

Messaging patterns allow systems to communicate asynchronously. The Sender places a message in a box and walks away. The Receiver picks it up when they are ready—milliseconds or days later. This group covers the patterns necessary to build loose coupling, reliable delivery, and high throughput in distributed systems.

## 📜 Pattern Index

| Pattern | Goal | Senior "Soundbite" |
| :--- | :--- | :--- |
| **[20. Dead Letter Queue (DLQ)](https://www.google.com/search?q=./20-dead-letter-queue-dlq.md)** | **Error Handling** | "Don't let one bad message block the entire queue. Move the poison pill aside and keep working." |
| **[21. Pub/Sub](https://www.google.com/search?q=./21-pub-sub.md)** | **Decoupling** | "The Checkout Service shouldn't know that the Email Service exists. It should just announce 'Order Placed'." |
| **[22. Claim Check Pattern](https://www.google.com/search?q=./22-claim-check-pattern.md)** | **Payload Management** | "Don't send a 50MB PDF through Kafka. Send a link to S3 instead." |

## 🧠 The Messaging Checklist

Before introducing a Message Broker (Kafka/RabbitMQ/SQS) into the stack, a Senior Architect asks:

1.  **The "Poison Pill" Test:** If a user sends a message that crashes the consumer, does the consumer loop forever, or does it eventually give up and move the message to a DLQ?
2.  **The "Ordering" Test:** Does the business logic break if "Order Cancelled" arrives 1 second before "Order Created"? (It usually does). How are we handling race conditions?
3.  **The "Payload" Test:** Are we trying to shove 10MB images into a queue meant for 2KB JSON events? (Use Claim Check).
4.  **The "Idempotency" Test:** Since brokers guarantee "At-Least-Once" delivery, what happens if the consumer receives the same message twice? (Must handle duplicates).

## ⚠️ Common Pitfalls in This Module

  * **Treating Queues like Databases:** Trying to "query" the queue to find a specific message. Queues are for moving data, not storing/indexing it.
  * **Assuming FIFO is Free:** Strict First-In-First-Out (FIFO) usually reduces throughput significantly and adds complexity. Standard queues are "Best-Effort Ordering."
  * **The "Black Hole" DLQ:** Setting up a Dead Letter Queue but never creating an alert or process to check it. The errors just pile up silently until the customer complains.

