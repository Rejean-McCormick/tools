# 08\. Anti-Corruption Layer (ACL)

## 1\. The Concept

The Anti-Corruption Layer (ACL) is a design pattern used to create a boundary between two subsystems that have different data models or semantics. It acts as a translator, ensuring that the "messy" or incompatible design of an external (or legacy) system does not leak into ("corrupt") the clean design of your modern application.

## 2\. The Problem

  * **Scenario:** You are building a new, modern E-commerce system with a clean domain model (e.g., `Customer`, `Order`, `Product`). However, you must fetch customer data from a 20-year-old mainframe Legacy ERP.
  * **The Legacy Reality:** The ERP uses cryptic column names like `CUST_ID_99`, `KUNNR`, `X_FLAG_2`, and stores dates as strings like `"2023.12.31"`.
  * **The Risk:**
      * **Pollution:** If you use the ERP's variable names and structures directly in your new code, your new business logic becomes tightly coupled to the old system's quirks.
      * **Vendor Lock-in:** If you switch ERPs later, you have to rewrite your entire business logic because it is littered with `KUNNR` references.

## 3\. The Solution

Build a dedicated layer (class, module, or service) that sits between the two systems.

1.  **Incoming:** It retrieves the ugly data from the Legacy System and **translates** it into your clean Domain Objects.
2.  **Outgoing:** It takes your clean Domain Objects and **translates** them back into the ugly format required by the Legacy System.

Your core business logic *never* sees the Legacy model. It only sees clean objects.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "The API returns a field called `xml_blob_v2`. I'll just pass that string around to the frontend and parse it where we need it." | **Infection.** The entire codebase becomes dependent on the specific XML format. If the external API changes, the whole app breaks. |
| **Senior** | "Create an ACL Service. Parse `xml_blob_v2` immediately at the edge. Convert it to a strongly-typed `Invoice` object. The rest of the app should not know XML exists." | **Isolation.** The core logic remains pure. If the external API changes to JSON, we only update the ACL. The business logic is untouched. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Legacy Migration:** Integrating a new microservice with a monolith.
      * **Third-Party APIs:** Integrating with vendors (Salesforce, SAP, Stripe) whose data models don't match yours.
      * **Mergers & Acquisitions:** Connecting two different systems from different companies.
  * ❌ **Avoid when:**
      * **Simple CRUD:** If your app is just a UI viewer for the external system, translating the data is unnecessary overhead.
      * **Internal Communication:** If both services share the same "Bounded Context" and language, an ACL is overkill.

## 6\. Implementation Example (Pseudo-code)

**Scenario:** We need to get a user's address.

  * **Legacy System:** Returns a pipe-separated string: `"123 Main St|New York|NY|10001"`
  * **Our System:** Expects a structured `Address` object.

### The Wrong Way (Pollution)

```python
# Business Logic
def print_label(user_id):
    # BAD: Leaking the external format into the core logic
    raw_data = legacy_api.get_user(user_id) # Returns "123 Main St|New York|NY|10001"
    parts = raw_data.split("|") 
    print(f"Ship to: {parts[1]}") # If order of parts changes, this breaks.
```

### The Right Way (ACL)

```python
# 1. The Domain Model (Clean)
class Address:
    def __init__(self, street, city, state, zip_code):
        self.street = street
        self.city = city
        self.state = state
        self.zip_code = zip_code

# 2. The Anti-Corruption Layer (The Translator)
class LegacyUserACL:
    def get_user_address(self, user_id) -> Address:
        # Call the ugly external system
        raw_response = legacy_api.get_user(user_id) 
        
        # Translate / Adapt
        try:
            parts = raw_response.split("|")
            return Address(
                street=parts[0],
                city=parts[1],
                state=parts[2],
                zip_code=parts[3]
            )
        except IndexError:
            raise DataCorruptionException("Legacy data format changed")

# 3. The Business Logic (Pure)
def print_label(user_id):
    # The logic doesn't know about pipes or strings. It just knows 'Address'.
    acl = LegacyUserACL()
    address = acl.get_user_address(user_id)
    print(f"Ship to: {address.city}") 
```

## 7\. Strategic Value

The ACL is not just code; it is a **Negotiation Boundary**.

  * By implementing an ACL, you are explicitly deciding: *"We will not let the technical debt of System A become the technical debt of System B."*
  * It makes testing easier. You can mock the ACL interface and test your business logic without ever spinning up the heavy legacy system.