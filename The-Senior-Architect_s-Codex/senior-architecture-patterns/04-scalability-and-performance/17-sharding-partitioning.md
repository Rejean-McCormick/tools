# 17\. Sharding (Database Partitioning)

## 1\. The Concept

Sharding is a method of splitting and storing a single logical dataset (like a "Users" table) across multiple databases or machines. By distributing the data, you distribute the load. Instead of one massive server handling 100% of the traffic, you might have 10 servers, each handling 10% of the traffic.

## 2\. The Problem

  * **Scenario:** Your application has hit 100 million users.
  * **The Vertical Limit:** You have already upgraded your database server to the largest instance available (128 cores, 2TB RAM). It's still hitting 100% CPU during peak hours. You physically cannot buy a bigger computer (Vertical Scaling limit reached).
  * **The Bottleneck:** Writes are slow because of lock contention. Indexes are too big to fit in RAM, causing disk thrashing. Backups take 48 hours to run.

## 3\. The Solution

Break the database into smaller chunks called **Shards**.
Each shard holds a subset of the data. The application uses a **Shard Key** to determine which server to talk to.

  * **Shard A:** Users ID 1 - 1,000,000
  * **Shard B:** Users ID 1,000,001 - 2,000,000
  * ...

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "The database is slow. Let's just add a Read Replica." | **Write Bottleneck.** Replicas help with reads, but every write still has to go to the single Master. The Master eventually dies. |
| **Senior** | "We are write-bound. We need to Shard. Let's partition by `RegionID` so users in Europe hit the EU Shard and users in US hit the US Shard." | **Linear Scalability.** We can theoretically scale to infinity by just adding more servers. Write throughput multiplies by N. |

## 4\. Visual Diagram

## 5\. Sharding Strategies

Choosing the right **Shard Key** is the most critical decision.

### A. Range Based (e.g., by User ID)

  * *Method:* IDs 1-100 go to DB1, 101-200 go to DB2.
  * *Pro:* Easy to implement.
  * *Con:* **Hotspots.** If all new users (IDs 900+) are active, and old users (IDs 1-100) are inactive, DB1 is idle while DB9 is melting down.

### B. Hash Based (e.g., `hash(UserID) % 4`)

  * *Method:* Apply a hash function to the ID to assign it to a server.
  * *Pro:* Even distribution of data. No hotspots.
  * *Con:* **Resharding is painful.** If you add a 5th server, the formula changes (`% 5`), and you have to move almost ALL data to new locations.

### C. Directory Based (Lookup Table)

  * *Method:* A separate "Lookup Service" tells you where "User A" lives.
  * *Pro:* Total flexibility. You can move individual users without changing code.
  * *Con:* **Single Point of Failure.** If the Lookup Service goes down, nobody can find their data.

## 6\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Massive Data:** TBs or PBs of data.
      * **Write Heavy:** You have more write traffic than a single node can handle.
      * **Geographic Needs:** You want EU user data to physically stay in EU servers (GDPR).
  * ❌ **Avoid when:**
      * **You haven't optimized queries:** Bad SQL is usually the problem, not the server size. Fix the code first.
      * **You need complex Joins:** You cannot easily JOIN tables across two different servers. You have to do it in application code (slow).
      * **Small Teams:** The operational complexity of managing 10 databases instead of 1 is huge.

## 7\. Implementation Example (Pseudo-code)

**Scenario:** A library wrapper that routes queries to the correct shard based on `user_id`.

```python
# Configuration: Map shards to connection strings
SHARD_MAP = {
    0: "postgres://db-shard-alpha...",
    1: "postgres://db-shard-beta...",
    2: "postgres://db-shard-gamma..."
}

def get_shard_connection(user_id):
    # 1. Determine Shard ID (Hash Strategy)
    # Using modulo to distribute users evenly across 3 shards
    num_shards = len(SHARD_MAP)
    shard_id = hash(user_id) % num_shards
    
    # 2. Connect to the specific database
    connection_string = SHARD_MAP[shard_id]
    return connect_to_db(connection_string)

def save_user(user):
    # The application logic doesn't know about the physical servers.
    # It just asks for "the right connection".
    conn = get_shard_connection(user.id)
    
    conn.execute("INSERT INTO users ...", user)
    conn.close()
```

## 8\. The "Resharding" Nightmare

Eventually, Shard A will get full. You need to split it into Shard A and Shard B.

  * **The Senior Reality:** This is terrifying.
  * **The Strategy:** Consistent Hashing or Virtual Buckets.
      * Instead of mapping `User -> Server`, map `User -> Bucket` (e.g., 1024 buckets).
      * Then map `Bucket -> Server`.
      * When you add a server, you just move a few buckets over, rather than calculating new hashes for every user.

## 9\. Limitations (The Trade-offs)

1.  **No Cross-Shard Transactions:** You cannot start a transaction that updates User A (Shard 1) and User B (Shard 2). You must use **Sagas (Pattern \#14)**.
2.  **No Cross-Shard Joins:** You cannot `SELECT * FROM Orders JOIN Users`. You must fetch User, then fetch Orders, and combine them in Python/Java.
3.  **Unique Constraints:** You cannot enforce "Unique Email" across the whole system easily, because Shard 1 doesn't know what emails Shard 2 has.