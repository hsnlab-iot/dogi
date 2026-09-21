---
id: cautious-navigation-skill
name: Cautious Navigation Skill
description: "Safe point-to-point movement and obstacle avoidance protocol utilizing tilt-look-step safety cycles."
required_mcp_tools: [body_attitude, body_move, vision_prompt]
optional_mcp_tools: [todos]
tags: [navigation, safety, locomotion, obstacle-avoidance]
---

# Cautious Navigation & Obstacle Avoidance Skill

## Purpose
A highly conservative movement protocol designed to navigate the quadruped chassis through an environment. It strictly enforces a "Look-Before-You-Leap" policy to ensure no collisions occur with ground hazards, drops, or physical barriers.

---

## Behavioral Rules & Constraints
1. **Never step backward** (`direction="backward"` is strictly forbidden).
2. **Never move forward blind:** Every forward step MUST be preceded by a downward-tilted visual inspection of the immediate ground area.
3. **Incremental Progress:** Move in short, controlled increments (max 10-15 steps) before re-evaluating the path.
4. **Safety Margin:** Maintain a minimum 0.5-meter safety buffer from any detected obstacle.

---

## Operational Execution Protocol

### Step 1: Initial Posture Preparation
Set the chassis posture to inspect the ground immediately ahead:
- Call `body_attitude` (`action="tilt"`, `direction="down"`, `amount=15`).

### Step 2: Immediate Path Inspection
Capture an image and query the vision system to verify path safety:
- Call `vision_prompt` (`answer_length="short"`):
  > *"PATH CHECK: Is the ground directly in front of the robot (within 1 meter) completely free of obstacles, wires, drops, or dynamic hazards? Answer: CLEAR or BLOCKED (with a brief 1-sentence reason if BLOCKED)."*

### Step 3: Decision Matrix & Action
Evaluate the output from Step 2:

* **IF PATH == CLEAR:**
  1. Call `body_move` (`action="step"`, `direction="forward"`, `steps=10`).
  2. Maintain downward attitude or re-apply `body_attitude` (`action="tilt"`, `direction="down"`, `amount=15`).
  3. Loop back to **Step 2** until target location/distance is reached.

* **IF PATH == BLOCKED:**
  1. Do NOT move forward.
  2. Perform an exploratory turn to locate a clear vector:
     - Call `body_move` (`action="turn"`, `direction="right"`, `steps=20`).
  3. Reset orientation view and loop back to **Step 2**.

### Step 4: Finalizing & Posture Reset
When the movement goal is achieved or the process is halted:
- Reset the chassis body attitude to normal:
  - Call `body_attitude` (`action="reset_attitude"`).
- Report status/completion to user.

---

## Emergency & Recovery Protocols

- **Repeated Blockage (3 consecutive turns blocked):** 
  - Stop all movement.
  - Call `body_attitude` (`action="reset_attitude"`).
  - Execute Stuck Protocol: Issue notification detailing the environment blockage and request assistance from Gabor/operator.
- **Tool Execution Failure:** 
  - Halt motor commands immediately. Re-try vision capture once. If persistent, stop and report a hardware/telemetry error.