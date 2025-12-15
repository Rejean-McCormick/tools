# 02\. Bulkhead Pattern

## 1\. The Concept

The Bulkhead Pattern isolates elements of an application into pools so that if one fails, the others continue to function. It is named after the structural partitions (bulkheads) in a ship's hull. If a ship's hull is breached, water fills only the damaged compartment, preventing the entire ship from sinking.

## 2\. The Problem

  * **Scenario:** You have a monolithic application that handles three tasks: `User Login`, `Image Processing`, and `Report Generation`. You use a single, global thread pool (e.g., Tomcat defaults) for all requests.
  * **The Risk:**
      * **Resource Saturation:** `Report Generation` is CPU-heavy and slow. If 50 users request reports simultaneously, they consume all available threads in the global pool.
      * **The Crash:** When a user tries to perform a lightweight `User Login`, there are no threads left to handle the request. The entire server hangs. A feature nobody uses (Reporting) just killed the most critical feature (Login).

## 3\. The Solution

Partition service instances into different groups (pools), based on consumer load and availability requirements. Assign resources (Connection Pools, Thread Pools, Semaphores) specifically to those groups.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "Why complicate things? Just use the default connection pool settings. If we run out of connections, we'll just increase the `max_connections` limit." | **Single Point of Failure.** A memory leak or high load in one obscure module starves the entire application of resources. |
| **Senior** | "Create a dedicated thread pool for the Admin Dashboard and a separate one for Public Traffic. If the Admin dashboard queries hang, the public site stays up." | **Fault Isolation.** Failures are contained within their specific compartment. The 'ship' stays afloat even if one room is flooded. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * You have **heterogeneous** workloads (e.g., fast, lightweight APIs mixed with slow, heavy batch jobs).
      * You consume multiple external downstream services (e.g., separate connection pools for Service A and Service B).
      * You have tiered customers (e.g., "Platinum" users get a guaranteed pool of resources; "Free" users share a smaller pool).
  * ❌ **Avoid when:**
      * The application is a simple, single-purpose microservice.
      * You are constrained by extreme memory limits (managing multiple thread pools has overhead).

## 6\. Implementation Example (Concept)

### Without Bulkhead (The Risk)

```java
// ONE shared pool for everything
ExecutorService globalPool = Executors.newFixedThreadPool(100);

public void handleRequest(Request req) {
    // If 100 "ProcessVideo" requests come in, "Login" is blocked.
    globalPool.submit(() -> process(req));
}
```

### With Bulkhead (The Solution)

Using standard Java `ExecutorService` or libraries like **Resilience4j** to enforce concurrency limits.

```java
// 1. Critical Pool for User Operations (High priority, fast)
ExecutorService userPool = Executors.newFixedThreadPool(40);

// 2. Reporting Pool (Low priority, slow, CPU intense)
ExecutorService reportingPool = Executors.newFixedThreadPool(10);

// 3. Third-Party API Pool (Network bound, unreliable)
ExecutorService externalApiPool = Executors.newFixedThreadPool(20);

public void handleLogin(User user) {
    try {
        userPool.submit(() -> loginService.authenticate(user));
    } catch (RejectedExecutionException e) {
        // Only Login is failing, Reporting works fine
        throw new ServerOverloadException("Login service busy");
    }
}

public void generateReport(ReportRequest req) {
    try {
        reportingPool.submit(() -> reportService.build(req));
    } catch (RejectedExecutionException e) {
        // Reporting is down, but Login works fine!
        throw new ServerOverloadException("Reports queue full, try later");
    }
}
```

## 7\. Configuration Strategy

How do you size the bulkheads?

  * **Don't Guess:** Use observability tools to measure the throughput and latency of each operation.
  * **The "Golden Function":** Size the bulkheads such that `(Threads * Throughput) < System Capacity`.
  * **Start Small:** It is better to have a small pool that rejects excess traffic (load shedding) than a large pool that crashes the CPU.