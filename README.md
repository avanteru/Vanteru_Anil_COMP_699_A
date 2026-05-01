# ADITS — Assumption Dependency & Impact Tracking System

## About This Project

This project is a web-based system I built to handle one of the most ignored but critical parts of project management — assumptions. In real-world projects, many decisions depend on assumptions, but teams rarely track them properly. When one assumption fails, it can silently affect multiple parts of the project.

To solve this, I designed ADITS. This system allows users to create assumptions, define relationships between them, and understand how changes in one assumption can impact others. It helps teams stay aware of risks and make better decisions.

---

## What Problem It Solves

In most teams:

* Assumptions are not tracked in a structured way
* Dependencies between assumptions are not visible
* Risk is not measured clearly
* Changes are not documented properly

ADITS solves these by:

* Giving a central place to manage assumptions
* Linking assumptions with dependencies
* Automatically evaluating impact when changes happen
* Calculating overall project risk

---

## Key Capabilities

### Assumption Management

* Create, update, and delete assumptions
* Assign categories and ownership
* Track confidence level and impact weight
* Maintain status like Valid, At Risk, or Invalid

### Dependency Handling

* Link assumptions with each other
* Prevent circular dependencies
* Automatically evaluate cascading effects

### Risk Evaluation

* Calculate risk index based on confidence and impact
* Show risk visually for quick understanding
* Update risk dynamically when assumptions change

### Version Tracking

* Store history of changes for each assumption
* Compare previous and current values
* Maintain transparency in updates

### Role-Based Access

* Project Owner — full control
* Analyst — manage assumptions
* Viewer — read-only access

### Audit Logging

* Track all major actions in the system
* Maintain accountability and traceability

### Search and Filtering

* Filter assumptions by category, status, or keyword
* Quickly locate required data

---

## Technology Used

* Python for backend logic
* Streamlit for building the UI
* SQLite for database storage
* Pandas for handling data

---

## How to Run the Project

Install required packages:

```bash
python -m pip install streamlit pandas plotly
```

Run the application:

```bash
streamlit run helpdesk_app.py
```

---

## Default Access

Initial login credentials:

* Username: admin
* Password: admin123

You can create additional users after login.

---

## How the System Works

1. User logs into the system
2. Creates or selects a project
3. Adds assumptions with details
4. Defines dependencies between assumptions
5. Updates status when conditions change
6. System recalculates impact and risk automatically
7. Users track results through dashboard and reports

---

## Design Approach

While building this system, I focused on:

* Keeping the UI simple and easy to use
* Making the logic clear and structured
* Ensuring data consistency
* Supporting real-world use cases

Even though it is a single-file application, the structure is modular and can be extended into a larger system.

---

## Limitations

* Uses SQLite, so not ideal for high concurrency
* No external authentication system
* UI can be further improved for scalability

---

## Future Improvements

* Move to PostgreSQL for better scalability
* Add API layer for integration
* Improve authentication with token-based system
* Add real-time notifications
* Enhance reporting with more visual insights

---

## Final Note

This project shows how assumptions, which are usually unmanaged, can be structured and tracked properly. It improves visibility, reduces hidden risks, and helps teams make better decisions.

---
