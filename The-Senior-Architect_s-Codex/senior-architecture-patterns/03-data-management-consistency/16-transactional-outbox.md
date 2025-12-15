# 16\. Transactional Outbox Pattern

## 1\. The Concept

The Transactional Outbox pattern ensures **consistency** between the application's database and a message broker (like Kafka or RabbitMQ). It solves the "Dual Write Problem" by saving the message to a database table (the "Outbox") *in the same transaction* as the business data change. A separate background process then reads the Outbox and safely publishes the messages to the broker.

## 2\. The Problem

  * **Scenario:** A user signs up. You need to:
    1.  Insert the user into the `Users` table (Postgres).
    2.  Publish a `UserCreated` event to Kafka so the Email Service can send a welcome email.
  * **The Dual Write Problem:** You cannot transactionally write to Postgres and Kafka simultaneously.
      * **Scenario A:** You save to DB, then crash before publishing to Kafka.
          * *Result:* User exists, but no email is sent. System is inconsistent.
      * **Scenario B:** You publish to Kafka, then the DB insert fails (rollback).
          * *Result:* Email is sent for a user that doesn't exist. System is inconsistent.

## 3\. The Solution

Use the database transaction to guarantee atomicity.

1.  **The Atomic Write:** In a single SQL transaction, insert the user into the `Users` table **AND** insert the event payload into a standard SQL table called `Outbox`. If the DB transaction rolls back, both vanish. If it commits, both exist.
2.  **The Relay:** A separate process (The "Message Relay" or "Poller") repeatedly checks the `Outbox` table.
3.  **The Publish:** The Relay picks up the pending messages and pushes them to Kafka.
4.  **The Cleanup:** Once Kafka confirms receipt (ACK), the Relay marks the Outbox record as "Sent" or deletes it.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "Just put the `producer.send()` call right after the `db.save()` call. It works on my machine." | **Data Loss.** In production, networks blink. The app crashes. You end up with "ghost" users who never triggered downstream workflows. |
| **Senior** | "I trust the database transaction. I write the event to the `Outbox` table inside the SQL transaction. I let a Debezium connector or a Poller handle the actual network call to Kafka." | **Guaranteed Delivery.** (At-Least-Once). Even if the power goes out the millisecond after the commit, the event is safely on disk and will be sent when the system recovers. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Critical Events:** Financial transactions, user signups, inventory changes where downstream consistency is mandatory.
      * **Distributed Systems:** Any time a microservice needs to notify another microservice about a state change.
      * **Legacy Systems:** You can add an Outbox table to a legacy monolith to start emitting events without changing the core code much.
  * ❌ **Avoid when:**
      * **Fire-and-Forget:** Logging, metrics, or non-critical notifications where losing 0.1% of messages is acceptable.
      * **High Throughput / Low Latency:** Writing every single message to a SQL table adds I/O overhead. If you need millions of events per second, streaming logs directly might be better.

## 6\. Implementation Example (Pseudo-code)

**Scenario:** User Signup.

### Step 1: The Application (Atomic Commit)

```python
def register_user(username, email):
    # Start SQL Transaction
    with db.transaction():
        # 1. Write Business Data
        user = db.execute(
            "INSERT INTO users (username, email) VALUES (?, ?)", 
            (username, email)
        )
        
        # 2. Write Event to Outbox (Same Transaction!)
        event_payload = json.dumps({"type": "UserCreated", "id": user.id})
        db.execute(
            "INSERT INTO outbox (topic, payload, status) VALUES (?, ?, 'PENDING')",
            ("user_events", event_payload)
        )
    
    # Commit happens here automatically.
    # Either BOTH exist, or NEITHER exists.
```

### Step 2: The Message Relay (The Poller)

*Runs in a background loop or separate process.*

```python
def process_outbox():
    while True:
        # 1. Fetch pending messages
        messages = db.query("SELECT * FROM outbox WHERE status='PENDING' LIMIT 10")
        
        for msg in messages:
            try:
                # 2. Publish to Broker (e.g., Kafka/RabbitMQ)
                kafka_producer.send(topic=msg.topic, value=msg.payload)
                
                # 3. Mark as Sent (or Delete)
                db.execute("UPDATE outbox SET status='SENT' WHERE id=?", (msg.id,))
                
            except KafkaError:
                # Log and retry later (don't mark as sent)
                logger.error(f"Failed to send msg {msg.id}")

        time.sleep(1)
```

## 7\. Advanced: Log Tailing (CDC)

The "Polling" approach (Querying SQL every 1 second) can hurt database performance.
**The Senior approach** is often **Change Data Capture (CDC)**.

  * Instead of a Poller code, use a tool like **Debezium**.
  * Debezium reads the database's *Transaction Log* (Postgres WAL or MySQL Binlog) directly.
  * It sees the insert into the `Outbox` table and streams it to Kafka automatically.
  * This has lower latency and zero performance impact on the query engine.

## 8\. Idempotency on the Consumer

The Outbox pattern guarantees **At-Least-Once** delivery.

  * If the Relay sends the message to Kafka, but crashes *before* updating the DB to "SENT," it will send the message again when it restarts.
  * **Crucial:** The Consumer (the Email Service) must be **Idempotent** (Pattern \#15) to handle receiving the same "UserCreated" event twice without sending two emails.

