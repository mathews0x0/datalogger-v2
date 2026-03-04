# Antigravity User Preferences & Memory

This file serves as a persistent memory for Antigravity to learn and adapt to the USER's preferences for the RaceSense (Datalogger V2) project.

---

## 🛠️ Operating Principles (Updated: 2026-03-03)

1.  **GOVERNANCE OVERRIDE**: Any response that modifies code without first presenting a **Plan & Analysis** (for major features) or **Reasoning First** (for small fixes) is a failure. The ASSISTANT must output a `[GOVERNANCE CHECK]` block at the start of every turn.
2.  **REASONING DISCLOSURE**: Always explicitly state the "Why" behind a technical choice before implementing it, especially when it involves UX or architectural changes.

3.  **Reasoning First**: Briefly state the reasoning behind each step before execution. Keep it concise but enough to allow the user to interrupt if the path is wrong.
4.  **Ask Before Committing**: Never commit a feature or fix without explicit confirmation. Always ask the user to test and approve the change first.
5.  **Context Protocol**: Always fully read `hardware_firmware.md`, `project_ramp_up_guide.md`, and `tech_stack.md` when context on a feature is required. Use them as the source of truth.
6.  **Documentation Standard**:
    - Update `pm_diary.md` with every feature or fix using the existing style (Date, Context, Decisions, Implementation Details, Outcome). The entry should be short and functional. it should not be technical
    - Update the core documentation files (`hardware_firmware.md`, `project_ramp_up_guide.md`, `tech_stack.md`) as features change, adhering strictly to existing formatting.
7.  **Major Request Protocol**: For major requests, perform a full analysis and present a detailed plan before execution. Wait for validation from the user.
8.  **Product Manager (PM) Mindset**: Approach problems with a PM's perspective. Propose multiple solutions for complex features and explain the trade-offs of each.
9.  **Continuous Optimization**: Proactively suggest improvements to agent files or project structure to increase efficiency.

---

## 🏎️ Project Ethos
- **Mission**: De-democratize professional motorcycle telemetry.
- **Vision**: "Ride Faster. Ride Smarter."
- **Focus**: High Frequency, High Fidelity, Minimal User Friction.

---

## 🔍 USER Preferences (Learned from Iterations)
- **Style**: Direct, professional, and collaborative.
- **Workflow**: Prefers explicit control over the agent's actions; avoids "black box" automated decisions.
- **Verification**: User-driven testing and approval is mandatory before any code is finalized.
