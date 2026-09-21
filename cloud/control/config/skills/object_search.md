---
id: object-search-skill
name: Object searching skill
description: "Turn-based exploration loop with downward tilt to locate target objects while inspecting for immediate floor hazards."
required_mcp_tools: [body_attitude, body_move, vision_prompt]
optional_mcp_tools: [todos]
tags: [search, navigation, perception]
---

# Downward-Tilted Search Skill

## Rules
- No backward steps (`body_move`).
- Always verify floor path before moving forward.
- Max 10 loop iterations.

## Execution Protocol

1. **Setup:** Call `body_attitude` (`action="tilt"`, `direction="down"`, `amount=15`).
2. **Perceive:** Call `vision_prompt` (`answer_length="short"`):
   "TARGET: Is [TARGET_OBJECT] visible? (YES/NO). PATH: Is floor ahead clear within 0.5m? (CLEAR/BLOCKED)"
3. **Decide & Act:**
   - **TARGET == YES:** Reset posture (`body_attitude` `action="reset_attitude"`), report success, STOP.
   - **TARGET == NO & PATH == CLEAR:** Call `body_move` (`action="step"`, `direction="forward"`, `steps=15`) OR (`action="turn"`, `direction="left"`, `steps=15`). GOTO 2.
   - **TARGET == NO & PATH == BLOCKED:** Call `body_move` (`action="turn"`, `direction="right"`, `steps=20`). GOTO 2.
4. **Timeout (10 Loops):** Reset posture (`body_attitude` `action="reset_attitude"`), report failure, STOP.