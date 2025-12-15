# 13\. Event Sourcing

## 1\. The Concept

Event Sourcing is an architectural pattern where the state of an application is determined by a sequence of events, rather than just the current state. Instead of overwriting data in a database (CRUD), you store every change that has ever happened as an immutable "Event" in an append-only log. The current state is derived by replaying these events from the beginning.

## 2\. The Problem

  * **Scenario:** A Banking System.
      * **Day 1:** User A opens an account with $0.
      * **Day 2:** User A deposits $100.
      * **Day 3:** User A withdraws $50.
  * **The CRUD Reality:** In a standard SQL database, the `Accounts` table just says `Balance: $50`.
  * **The Risk:**
      * **Loss of History:** We have lost the information about *how* we got to $50. Did they deposit $50? Or did they deposit $1000 and withdraw $950?
      * **Auditability:** If the user claims "I never withdrew that money," you have no proof in the primary database state. You have to dig through messy text logs (if they exist).
      * **Debugging:** If a bug corrupted the balance to -$10, you can't replay the sequence to find out exactly which transaction caused the math error.

## 3\. The Solution

Store the **Events**, not the **State**.
Instead of a table with a "Balance" column, you have an "Events" table:

1.  `AccountOpened { Id: 1, Balance: 0 }`
2.  `MoneyDeposited { Id: 1, Amount: 100 }`
3.  `MoneyWithdrawn { Id: 1, Amount: 50 }`

To find the balance, the system loads all events for ID 1 and does the math: `0 + 100 - 50 = 50`.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "We just need the current address. `UPDATE users SET address = 'New York' WHERE id=1`." | **Data Amnesia.** The old address is gone forever. We cannot answer questions like "Where did this user live last year?" |
| **Senior** | "Don't overwrite. Append an `AddressChanged` event. We can project the 'Current State' for the UI, but the source of truth is the history." | **Time Travel.** We can query the state of the system at *any point in time*. We have a perfect audit trail by default. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Audit is Critical:** Banking, Healthcare, Law, Insurance.
      * **Debugging is Hard:** Complex logic where "how we got here" matters as much as "where we are."
      * **Temporal Queries:** You need to answer "What was the inventory level on December 24th?"
      * **Intent Capture:** "CartAbandoned" is a valuable business event that is lost if you just delete the cart row in SQL.
  * ❌ **Avoid when:**
      * **Simple CRUD:** A blog post or a to-do list. Overkill.
      * **High Churn, Low Value:** Storing every mouse movement or temporary session data (unless for analytics).
      * **GDPR Nightmares:** If you write personal data into an immutable log, you need a strategy (like Crypto-Shredding) to "forget" it later.

## 6\. Implementation Example (Pseudo-code)

**Scenario:** A Bank Account.

```python
# 1. THE EVENTS (Immutable Data Classes)
class AccountCreated:
    def __init__(self, account_id, owner):
        self.type = "AccountCreated"
        self.account_id = account_id
        self.owner = owner

class MoneyDeposited:
    def __init__(self, amount):
        self.type = "MoneyDeposited"
        self.amount = amount

class MoneyWithdrawn:
    def __init__(self, amount):
        self.type = "MoneyWithdrawn"
        self.amount = amount

# 2. THE AGGREGATE (The Logic)
class BankAccount:
    def __init__(self):
        self.balance = 0
        self.id = None
        self.changes = [] # New events to be saved

    # The Decision: Validate and create event
    def withdraw(self, amount):
        if self.balance < amount:
            raise Exception("Insufficient Funds")
        
        event = MoneyWithdrawn(amount)
        self.changes.append(event)
        self.apply(event)

    # The State Change: Apply event to current state
    def apply(self, event):
        if event.type == "AccountCreated":
            self.id = event.account_id
        elif event.type == "MoneyDeposited":
            self.balance += event.amount
        elif event.type == "MoneyWithdrawn":
            self.balance -= event.amount

    # The Hydration: Rebuild from history
    def load_from_history(self, events):
        for event in events:
            self.apply(event)

# 3. USAGE
# Load from DB
history = event_store.get_events(account_id="ACC_123")
account = BankAccount()
account.load_from_history(history) # Balance is now calculated

# Do logic
account.withdraw(50)

# Save new events
event_store.save(account.changes)
```

## 7\. Performance: The Snapshot Pattern

**Problem:** If an account is 10 years old and has 50,000 transactions, replaying 50k events every time the user logs in is too slow.

**Solution:** **Snapshots.**
Every 100 events (or every night), calculate the state and save it to a separate "Snapshot Store."

  * *Snapshot (Event \#49,900):* `Balance = $4050`.
  * To load the account, load the latest Snapshot + any events that happened *after* it.
  * You now only replay 5 events instead of 50,000.

## 8\. Deleting Data (The "Right to be Forgotten")

Since the Event Log is immutable (Write Once, Read Many), you cannot `DELETE` a user's address to comply with GDPR.

**Strategy: Crypto-Shredding.**

1.  Encrypt all PII (Personally Identifiable Information) in the event payload using a specific key for that user ID.
2.  Store the Key in a separate "Key Vault" (standard SQL DB).
3.  To "Delete" the user: **Delete the Key.**
4.  The events remain in the log, but the data is essentially garbage/unreadable.