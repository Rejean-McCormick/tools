
# 21\. Pub/Sub (Publish-Subscribe)

## 1\. The Concept

The Publish-Subscribe (Pub/Sub) pattern is a messaging pattern where senders of messages (Publishers) do not program the messages to be sent directly to specific receivers (Subscribers). Instead, messages are categorized into classes (Topics) without knowledge of which subscribers, if any, there may be. Similarly, subscribers express interest in one or more classes and only receive messages that are of interest, without knowledge of which publishers are sending them.

## 2\. The Problem

  * **Scenario:** An E-commerce system. When a user places an `Order`, three things need to happen:
    1.  The `Email Service` sends a confirmation.
    2.  The `Inventory Service` reserves the stock.
    3.  The `Rewards Service` adds points to the user's account.
  * **The Monolithic/Coupled approach:** The `Order Service` calls `EmailService.send()`, then `InventoryService.reserve()`, then `RewardsService.addPoints()`.
  * **The Risk:**
      * **Coupling:** The `Order Service` knows too much about the other services. If you want to add a fourth service (e.g., `Analytics`), you have to modify and redeploy the `Order Service`.
      * **Latency:** The user has to wait for all three services to finish before they see the "Order Success" screen.
      * **Fragility:** If the `Rewards Service` is down, the whole Order fails (or requires complex error handling).

## 3\. The Solution

Decouple the sender from the receivers.

1.  **Publisher:** The `Order Service` simply publishes an event: `OrderCreated`. It doesn't care who listens. It completes its job immediately.
2.  **Topic:** A message channel (e.g., `events.orders`).
3.  **Subscribers:** The `Email`, `Inventory`, and `Rewards` services all subscribe to the `events.orders` topic. They receive the copy of the message independently and process it at their own speed.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "I'll just add another HTTP POST call in the `checkout()` function to notify the new Analytics service." | **Spaghetti Code.** The `checkout` function becomes a 500-line monster managing 10 different downstream dependencies. |
| **Senior** | "The Checkout service emits `OrderPlaced`. That's it. If the Analytics team wants that data, they can subscribe to the queue. I don't need to change my code." | **Extensibility.** You can add 50 new subscribers without touching the Order Service. The system is loosely coupled and highly cohesive. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **One-to-Many:** One event triggers actions in multiple independent systems.
      * **Decoupling:** You want teams to work independently (Analytics team shouldn't block Checkout team).
      * **Eventual Consistency:** It's okay if the "Rewards Points" update 2 seconds after the order is placed.
  * ❌ **Avoid when:**
      * **Strict Sequencing:** If Step B *must* happen strictly after Step A finishes successfully (e.g., "Charge Card" -\> "Ship Item"), a Saga or direct orchestration is safer.
      * **Simple Systems:** If you only have one monolithic app, adding a message broker (Kafka/RabbitMQ) is over-engineering.

## 6\. Implementation Example (Pseudo-code)

**Scenario:** User Sign-up.

### The Publisher (User Service)

```python
# The User Service doesn't know about Email or Slack.
def register_user(user_data):
    # 1. Save to DB
    user = db.save(user_data)
    
    # 2. Publish Event
    event = {
        "event_type": "UserRegistered",
        "user_id": user.id,
        "email": user.email,
        "timestamp": time.now()
    }
    message_broker.publish(topic="user_events", payload=event)
    
    return "Welcome!"
```

### The Subscribers (Downstream Consumers)

```python
# Subscriber A: Email Service
@subscribe("user_events")
def handle_email(event):
    if event.type == "UserRegistered":
        email_client.send_welcome(event.email)

# Subscriber B: Slack Bot
@subscribe("user_events")
def handle_slack(event):
    if event.type == "UserRegistered":
        slack.post_message(f"New user {event.email} just joined!")
```

## 7\. Fan-Out vs. Work Queues

It is important to distinguish Pub/Sub from Work Queues.

  * **Work Queue (Load Balancing):** 100 messages arrive. You have 5 workers. Each worker gets 20 messages. The message is processed *once*.
  * **Pub/Sub (Fan-Out):** 1 message arrives. You have 5 subscribers (Email, Analytics, etc.). *Each* subscriber gets a copy of that 1 message. The message is processed *5 times* (once per different intent).

## 8\. Idempotency Warning

In Pub/Sub systems, brokers often guarantee "At Least Once" delivery. This means your `Email Service` might receive the `UserRegistered` event twice.
**Crucial:** Your subscribers must be **Idempotent** (Pattern \#15).

  * Check: "Did I already send a welcome email to this User ID?"
  * If yes, ignore the duplicate message.

## 9\. Technology Choices

  * **Kafka:** Best for high throughput, log retention, and replayability. (Events are stored for days/weeks).
  * **RabbitMQ / ActiveMQ:** Best for complex routing rules and standard messaging. (Messages are deleted after consumption).
  * **AWS SNS/SQS / Google PubSub:** Managed cloud services. Simplest to operate.