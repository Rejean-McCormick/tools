# 14\. Saga Pattern

## 1\. The Concept

The Saga Pattern is a mechanism for managing long-running transactions in a distributed system. Instead of relying on a global "lock" across multiple databases (which is slow and fragile), a Saga breaks the transaction into a sequence of smaller, local transactions. If any step fails, the Saga executes a series of "Compensating Transactions" to undo the changes made by the previous steps.

## 2\. The Problem

  * **Scenario:** A Travel Booking System. To book a trip, you must:
    1.  Book a Flight (Flight Service).
    2.  Reserve a Hotel (Hotel Service).
    3.  Charge the Credit Card (Payment Service).
  * **The Constraint:** These are three different microservices with three different databases. You cannot use a standard SQL Transaction (`BEGIN TRANSACTION ... COMMIT`).
  * **The Risk:**
      * You successfully book the flight.
      * You successfully reserve the hotel.
      * **The Payment Fails** (insufficient funds).
      * **Result:** The system is in an inconsistent state. The user has a flight and hotel but hasn't paid. The airline and hotel hold onto seats/rooms that will never be used (Zombie Reservations).

## 3\. The Solution

We define a workflow where every "Do" action has a corresponding "Undo" action.

| Step | Action (Transaction) | Compensation (Undo) |
| :--- | :--- | :--- |
| **1** | `BookFlight()` | `CancelFlight()` |
| **2** | `ReserveHotel()` | `CancelHotel()` |
| **3** | `ChargeCard()` | `RefundCard()` |

If Step 3 (`ChargeCard`) fails, the Saga Orchestrator catches the error and runs the compensations in reverse order:

1.  Execute `CancelHotel()`.
2.  Execute `CancelFlight()`.
3.  Report "Booking Failed" to the user.

The system eventually returns to a consistent state (nothing booked, nothing charged).

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "Use Two-Phase Commit (2PC / XA Transactions) across all databases to ensure everything commits at the exact same time." | **Gridlock.** 2PC holds locks on all databases until the slowest one finishes. Performance plummets. If the coordinator crashes, the databases stay locked. |
| **Senior** | "Accept that we can't lock the world. Use Sagas. If the payment fails, we issue a refund. It's how real-world business works." | **Scalability.** Services are loosely coupled. No global locks. The system handles partial failures gracefully. |

## 4\. Visual Diagram

## 5\. Types of Sagas

There are two main ways to coordinate a Saga:

### A. Choreography (Event-Driven)

  * **Concept:** Services talk to each other directly via events. No central manager.
  * **Flow:** Flight Service does its job -\> Emits `FlightBooked` -\> Hotel Service listens, does its job -\> Emits `HotelBooked`.
  * **Pros:** Simple, decentralized, no single point of failure.
  * **Cons:** Hard to debug. "Who triggered this refund?" can be a mystery. Circular dependencies are possible.

### B. Orchestration (Command-Driven)

  * **Concept:** A central "Orchestrator" (State Machine) tells each service what to do.
  * **Flow:** Orchestrator calls `FlightService.book()`. If success, Orchestrator calls `HotelService.reserve()`.
  * **Pros:** Clear logic, centralized monitoring, easy to handle timeouts.
  * **Cons:** The Orchestrator can become a bottleneck or a "God Service" with too much logic.

## 6\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Distributed Data:** Transactions span multiple microservices.
      * **Long-Running Flows:** The process takes minutes or hours (e.g., "Order Fulfillment").
      * **Reversible Actions:** You can logically "Undo" an action (Refund, Cancel, Restock).
  * ❌ **Avoid when:**
      * **Irreversible Actions:** If Step 1 is "Send Email" or "Fire Missile," you can't undo it. (You might need a pseudo-compensation like sending a "Sorry" email).
      * **Read Isolation:** Sagas do not support ACID "Isolation." A user might see the Flight booked *before* the Payment fails. This is called a "Dirty Read."

## 7\. Implementation Example (Pseudo-code)

**Scenario:** Orchestration-based Saga for the Travel App.

```python
class TravelSaga:
    def __init__(self, flight_svc, hotel_svc, pay_svc):
        self.flight_svc = flight_svc
        self.hotel_svc = hotel_svc
        self.pay_svc = pay_svc

    def execute_booking(self, user_id, trip_details):
        # 1. Step 1: Flight
        try:
            flight_id = self.flight_svc.book_flight(trip_details)
        except Exception:
            # Failed at start. No compensation needed.
            return "Failed"

        # 2. Step 2: Hotel
        try:
            hotel_id = self.hotel_svc.reserve_hotel(trip_details)
        except Exception:
            # Hotel failed. UNDO Flight.
            self.flight_svc.cancel_flight(flight_id)
            return "Failed"

        # 3. Step 3: Payment
        try:
            self.pay_svc.charge_card(user_id)
        except Exception:
            # Payment failed. UNDO Hotel AND Flight.
            self.hotel_svc.cancel_hotel(hotel_id)
            self.flight_svc.cancel_flight(flight_id)
            return "Failed"

        return "Success"
```

## 8\. Strategic Note: The "Pending" State

Because Sagas lack Isolation (the "I" in ACID), other users might see intermediate states.

  * **Senior Tip:** Don't show the flight as "Booked" immediately.
  * Show it as **"Pending Approval"**.
  * Only flip the status to "Confirmed" once the Saga completes successfully.
  * If the Saga fails, flip it to "Rejected."
  * This manages user expectations and prevents "Dirty Reads" from confusing the customer.