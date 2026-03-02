# Antigravity Operating Rules

These rules are MANDATORY for all agents working on the RaceSense (Datalogger V2) project. They ensure a high-quality, transparent, and collaborative development process.

---

## 🏛️ Rule 0: Always Reference Project Memory
**CRITICAL**: Every session must begin by reading [`.agent/memory.md`](file:///Users/mj/Documents/datalogger-v2/.agent/memory.md). This file contains the latest USER preferences, learned behaviors, and historical context.

---

## 🏎️ Core Operating Protocol

1.  **Reasoning Disclosure**: Proactively state the reasoning behind EACH step before execution. Keep it brief and actionable.
2.  **Explicit Approval Flow**:
    - Complete the feature/fix.
    - Request the USER to test and verify.
    - **COMMIT ONLY AFTER EXPLICIT USER APPROVAL**.
3.  **Mandatory Context Reading**: Always fully read the following three documents before working on any feature:
    - [`docs/hardware_firmware.md`](file:///Users/mj/Documents/datalogger-v2/docs/hardware_firmware.md)
    - [`docs/project_ramp_up_guide.md`](file:///Users/mj/Documents/datalogger-v2/docs/project_ramp_up_guide.md)
    - [`docs/tech_stack.md`](file:///Users/mj/Documents/datalogger-v2/docs/tech_stack.md)
4.  **Documentation Continuity**: 
    - Maintain the existing style of [`docs/pm_diary.md`](file:///Users/mj/Documents/datalogger-v2/docs/pm_diary.md).
    - Update all core `docs/*.md` files when features are added or modified.
5.  **Analyzed Planning**: For major requests, generate a detailed implementation plan and wait for USER validation before proceeding.
6.  **Continuous Learning**: Update [`.agent/memory.md`](file:///Users/mj/Documents/datalogger-v2/.agent/memory.md) after key interactions to capture new preferences. Call out these updates explicitly to the user.
7.  **PM-Led Design**: Think like a Product Manager. Evaluate trade-offs and propose multiple solutions for complex features.
8.  **Proactive Optimization**: Suggest improvements to project files or agent configuration to streamline the workflow.

---

## 🏁 Technical Standards
- **Silo Pattern**: Strictly adhere to the per-user data isolation in `server/instance/data/users/<user_id>/`.
- **Worker Isolation**: All long-running analysis must be queued via the background `worker.py`.
- **SQLite Awareness**: Respect database connection limits and minimize lock times.
