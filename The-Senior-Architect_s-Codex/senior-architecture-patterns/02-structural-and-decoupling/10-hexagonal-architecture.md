# 10\. Hexagonal Architecture (Ports & Adapters)

## 1\. The Concept

Hexagonal Architecture (also known as Ports and Adapters) is a pattern used to create loosely coupled application components that can be easily connected to their software environment by means of ports and adapters. It aims to make your application core independent of frameworks, user interfaces, databases, and external systems.

## 2\. The Problem

  * **Scenario:** You build a standard "Layered Architecture" (Controller -\> Service -\> Repository -\> Database).
  * **The Risk:**
      * **Database Coupling:** Your Service layer (Business Logic) often imports SQL libraries or ORM objects (like `SQLAlchemy` or `Hibernate`). If you want to switch from SQL to MongoDB, you have to rewrite your Business Logic.
      * **Testing Pain:** To test your logic, you have to spin up a real database or use complex mocking because the logic is inextricably linked to the data access code.
      * **Framework Lock-in:** Your core logic becomes cluttered with annotations (`@Entity`, `@Controller`) that tie you to a specific web framework.

## 3\. The Solution

We treat the application as a **Hexagon** (the Core).

1.  **The Core:** Contains the Business Logic and Domain Entities. It has **zero dependencies** on the outside world.
2.  **Ports:** Interfaces defined by the Core. The Core says, "I need a way to Save a User" (Output Port) or "I handle the command Create User" (Input Port).
3.  **Adapters:** The implementation of those interfaces.
      * **Driving Adapters (Primary):** The things that start the action (REST API, CLI, Test Suite). They call the Input Ports.
      * **Driven Adapters (Secondary):** The things the application needs to talk to (Postgres, SMTP, Redis). They implement the Output Ports.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "I'll put the SQL query inside the `UserService` class because that's where the data is needed." | **Tight Coupling.** The business rules are mixed with infrastructure concerns. You cannot test the logic without a running database. |
| **Senior** | "The `UserService` should define a `UserRepository` interface. The implementation (`SqlUserRepository`) lives outside the core. The service never imports SQL code." | **Testability & Flexibility.** We can swap SQL for a CSV file or a Mock for unit testing without touching a single line of business logic. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Complex Domain Logic:** The business rules are complicated and need to be tested in isolation.
      * **Long-Term Maintenance:** You expect the app to live for years and might change technologies (e.g., swapping REST for gRPC, or Oracle for Mongo).
      * **TDD (Test Driven Development):** You want to write tests for the core logic before the database schema even exists.
  * ❌ **Avoid when:**
      * **CRUD Apps:** If the app just reads rows from a DB and shows them as JSON, this architecture adds massive boilerplate (Interface + Impl + DTOs) for zero value. Use a simple MVC framework instead.

## 6\. Implementation Example (Pseudo-code)

**Goal:** Create a user.

### 1\. The Core (Inner Hexagon)

*Pure Python/Java. No frameworks. No SQL.*

```python
# --- The Domain Entity ---
class User:
    def __init__(self, username, email):
        if "@" not in email:
            raise ValueError("Invalid email")
        self.username = username
        self.email = email

# --- The Output Port (Interface) ---
# The Core asks: "I need someone to save this."
class UserRepositoryPort:
    def save(self, user: User):
        raise NotImplementedError()

# --- The Input Port (Service/UseCase) ---
class CreateUserUseCase:
    def __init__(self, user_repo: UserRepositoryPort):
        self.user_repo = user_repo

    def execute(self, username, email):
        # 1. Business Logic
        user = User(username, email)
        
        # 2. Use the Port (we don't know HOW it saves, just THAT it saves)
        self.user_repo.save(user)
        return user
```

### 2\. The Adapters (Outer Layer)

*Frameworks, Database Drivers, HTTP.*

```python
# --- Driven Adapter (Infrastructure) ---
import sqlite3

class SqliteUserRepository(UserRepositoryPort):
    def save(self, user: User):
        # Specific SQL implementation details
        conn = sqlite3.connect("db.sqlite")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users VALUES (?, ?)", (user.username, user.email))
        conn.commit()

# --- Driving Adapter (Web Controller) ---
from flask import Flask, request

app = Flask(__name__)

# Wire it up (Dependency Injection)
repo = SqliteUserRepository()
use_case = CreateUserUseCase(repo) 

@app.route("/users", methods=["POST"])
def create_user():
    data = request.json
    use_case.execute(data['username'], data['email'])
    return "Created", 201
```

### 3\. The Test Adapter (Why this is powerful)

We can run the core logic tests in milliseconds because we don't need a real DB.

```python
class MockRepo(UserRepositoryPort):
    def save(self, user):
        print("Pretend saved to DB")

def test_create_user_logic():
    repo = MockRepo()
    use_case = CreateUserUseCase(repo)
    
    # This runs purely in memory
    user = use_case.execute("john", "john@example.com")
    assert user.username == "john"
```

## 7\. Key Takeaway

Hexagonal Architecture allows you to delay technical decisions. You can write the entire application core before you even decide which database to use. The database becomes a detail, not the foundation.