# SEARCHING SKILL (Downward‑Tilted, Turn‑Based Exploration)

## Purpose

A general, tool‑agnostic search behavior enabling the robot to locate a requested object by maintaining a maximally downward‑tilted posture, turning in small increments, and safely exploring the environment. The robot focuses on **close‑range** hazard detection and avoids unnecessary stationary behavior.

---

## Behavioral Contract

1. **Never abandon the search** until the object is found or the user cancels.  
2. **Never hallucinate** object presence; rely only on fresh visual data.  
3. **Never step backward** (no rear camera).  
4. **Always inspect the close‑range ground area before stepping forward.**  
5. **Avoid hazards** at all times.  
6. **Use a single visual analysis per snapshot** (object + close‑range obstacles).  
7. **Maintain maximum downward tilt** throughout the entire search.  
8. **Turn in small increments** (1–2 seconds of rotation) to gain new perspectives.  
9. **Actively walk around the area** when safe, instead of staying in one place.  
10. **No twisting** — only full‑body turning.

---

## High‑Level Search Loop

The robot repeats the following loop until the target is found:

1. **Tilt down fully**  
   - This is the first action of the search.  
   - Maintain this tilt for the entire search session.

2. **Look forward (with maximum downward tilt)**  
   - Capture a snapshot.  
   - Run a single combined analysis prompt:  
     *“Is the requested object visible, and are there any close‑range obstacles or dangers ahead?”*

3. **If the object is found:**  
   - Stop searching.  
   - Report success.

4. **If not found:**  
   - **Turn left slightly** (1–2 seconds).  
   - Capture → analyze (same combined prompt).  
   - If found → stop.  
   - Return to the original orientation.

5. **If still not found:**  
   - **Turn right slightly** (1–2 seconds).  
   - Capture → analyze.  
   - If found → stop.  
   - Return to the original orientation.

6. **If still not found:**  
   - **Turn the body** (left or right) to face a new direction.  
   - Capture → analyze for close‑range hazards.  
   - If safe → take a **forward step** to explore new ground.  
   - Continue the search loop from step 2.

---

## Detailed Operational Rules

### 1. Vision & Orientation

- The robot has a fixed forward-facing camera.  
- To inspect different directions, it must **turn its entire body**.  
- The robot must **begin the search by tilting down as far as possible**.  
- This downward tilt must be **maintained** throughout the entire search.  
- Downward tilt ensures visibility of:  
  - Close objects  
  - Edges, holes, drops  
  - Immediate hazards  
  - The area where the next step will land

### 2. Visual Tool Usage

This skill assumes the existence of:

- A **capture mechanism** (snapshot from the camera)  
- A **visual analysis mechanism** (prompt-based evaluation)

The skill does not name these tools.  
Any tool with equivalent functionality may be used.

Prompts should combine object detection and close‑range hazard detection, e.g.:

- “Is the requested object visible, and is the close‑range area ahead safe for stepping?”  
- “Does this image contain the target object, and are there any nearby obstacles or dangers?”

### 3. Movement Safety

- **Never step backward.**  
- **Never step forward without checking the close‑range area.**  
- **Never step if the visual tool reports uncertainty or danger.**  
- **Turning in place is allowed** (left or right).  
- **No twisting** — twisting is replaced by turning.  
- **Forward stepping requires a fresh downward‑tilted snapshot**.  
- **Small incremental turns** (1–2 seconds) prevent overshooting.

### 4. Exploration Behavior

- The robot should **not remain stationary**.  
- When no object is found and no hazards are detected, the robot should:  
  - Turn to a new direction  
  - Capture → analyze  
  - If safe → step forward  
  - Continue exploring  
- This ensures coverage of a larger area and increases the chance of finding the object.

### 5. Persistence & Resilience

- Continue searching indefinitely until success or user cancellation.  
- If a tool fails or returns an error:  
  - Capture again  
  - Turn slightly to gain a new perspective  
  - Try again  
- If all perspectives and movement options are exhausted:  
  - Stop  
  - Report the blockage  
  - Request human assistance

---

## Search Strategy Summary (Compact Form)

1. **Tilt down fully** (first action).  
2. Capture → analyze for **object + close‑range hazards**.  
3. If not found → small left turn → capture → analyze.  
4. Small right turn → capture → analyze.  
5. If still not found → turn to a new direction.  
6. Capture → analyze for close‑range hazards.  
7. If safe → step forward to explore.  
8. Repeat from step 2.

