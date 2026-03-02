---
name: RaceSense Project Governance
description: Mandatory rules and context protocols for the Datalogger V2 project. MUST be read before any action.
---

# 🚨 MANDATORY GOVERNANCE
This skill defines the non-negotiable operating procedures for the RaceSense project.

## 🏛️ Rule 1: Always Reference Project Memory (Rule 0 from rules.md)
**CRITICAL**: Every session must begin by fully reading [`.agent/memory.md`](file:///Users/mj/Documents/datalogger-v2/.agent/memory.md). This file contains the latest USER preferences, learned behaviors, and historical context.

## 🏎️ Rule 2: Mandatory Context Reading (Rule 3 from rules.md)
If the task involves any feature development, debugging, or architectural queries, you MUST fully read the following documents from `/docs/` as the primary source of truth BEFORE reading source code or modifying files:
- [`docs/hardware_firmware.md`](file:///Users/mj/Documents/datalogger-v2/docs/hardware_firmware.md)
- [`docs/project_ramp_up_guide.md`](file:///Users/mj/Documents/datalogger-v2/docs/project_ramp_up_guide.md)
- [`docs/tech_stack.md`](file:///Users/mj/Documents/datalogger-v2/docs/tech_stack.md)

## ⚖️ Rule 3: Explicit Approval Flow
Adhere strictly to the "Reasoning Disclosure" and "Explicit Approval Flow" defined in `rules.md`:
1.  **Reasoning First**: Briefly state the reasoning behind EACH step before execution.
2.  **Request Verification**: Before completing a task, ask the USER to test and verify the fix/feature.
3.  **No Unapproved Commits**: Never commit code until explicit USER approval is granted.

## 📝 Rule 4: Documentation Continuity
Always update [`.agent/memory.md`](file:///Users/mj/Documents/datalogger-v2/.agent/memory.md) and [`docs/pm_diary.md`](file:///Users/mj/Documents/datalogger-v2/docs/pm_diary.md) after key interactions or modifications to capture new preferences and maintain the project's historical record.
