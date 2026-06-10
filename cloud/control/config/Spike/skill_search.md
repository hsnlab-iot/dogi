# SEARCHING SKILL (Hazard‑Aware Object Search)

## Purpose

A general, tool‑agnostic search behavior enabling the robot to locate a requested object by visually scanning the environment, turning to gain new perspectives, and moving safely through space without ever stepping backward.

---

## Behavioral Contract

1. **Never abandon the search** until the object is found or the user cancels.  
2. **Never hallucinate** object presence; rely only on fresh visual data.  
3. **Never step backward** (no rear camera).  
4. **Always inspect the ground ahead before stepping forward.**  
5. **Avoid hazards** at all times.  
6. **Use a single visual analysis per viewpoint** to detect both the target object and obstacles.  
7. **Maintain a downward tilt** throughout the search unless the user instructs otherwise.

---

## High‑Level Search Loop

The robot repeats the following loop until the target is found:

1. **Look forward (with downward tilt)**  
   - Capture a snapshot using the available visual tool.  
   - Run a single analysis prompt such as:  
     *“Is the requested object visible, and is the area ahead safe and free of obstacles?”*

2. **If the object is found:**  
   - Stop searching.  
   - Report success.

3. **If not found:**  
   - **Turn** left by a small angle.  
   - Capture → analyze (same combined prompt).  
   - If found → stop.  
   - Return to the original orientation.

4. **If still not found:**  
   - **Turn** right by a small angle.  
   - Capture → analyze.  
   - If found → stop.  
   - Return to the original orientation.

5. **If still not found:**  
   - **Turn** the body (left or right) to face a new direction.  
   - Capture → analyze for hazards.  
   - If safe → take a **forward step**.  
   - Continue the search loop from step 1.

---

## Detailed Operational Rules

### 1. Vision & Orientation

- The robot has a fixed forward-facing camera.  
- To inspect different directions, it must **turn its entire body**.  
- The body may remain **tilted downward** during the entire search.  
- Downward tilt provides optimal visibility for:  
  - Detecting the target object  
  - Detecting obstacles  
  - Evaluating ground safety  
- No need to reset to neutral tilt unless explicitly required.

### 2. Visual Tool Usage

This skill assumes the existence of:

- A **capture mechanism** (snapshot from the camera)  
- A **visual analysis mechanism** (prompt-based evaluation)

The skill does not name these tools.  
Any tool with equivalent functionality may be used.

Prompts should combine object detection and hazard detection, e.g.:

- “Is the requested object visible, and is the area ahead safe for stepping?”  
- “Does this image contain the target object, and are there any obstacles or hazards?”

### 3. Movement Safety

- **Never step backward.**  
- **Never step forward without hazard analysis.**  
- **Never step if the visual tool reports uncertainty or danger.**  
- **Turning in place is allowed** (left or right).  
- **Side-stepping is not used** for search.  
- **Forward stepping requires a fresh downward-tilted snapshot**.

### 4. Persistence & Resilience

- Continue searching indefinitely until success or user cancellation.  
- If a tool fails or returns an error:  
  - Capture again  
  - Turn slightly to gain a new perspective  
  - Try again  
- If all perspectives and movement options are exhausted:  
  - Stop  
  - Report the blockage  
  - Request human assistance
