---
id: visual-vlm-analysis-skill
name: Visual VLM prompt
description: "Actual, direct environmental inspection and visual query evaluation using VLM interpretation."
required_mcp_tools:
  - vision_prompt
tags: [image, analysis]
---

# Visual VLM Analysis Skill

## Purpose
Use when the user asks a visual question about the immediate environment ("What do you see?", "Is X present?") and automated visual processing is required.

## Execution Rules
1. **Freshness Mandate:** Never answer a present-tense visual query using past historical logs. Always invoke `vision_prompt` to capture a fresh visual observation.
2. **Prompt Construction:** Formulate a clear, concise instruction for the `vision_prompt` tool matching the user's explicit intent.
   - Example: For *"Do you see a red ball?"*, pass `"Is there a red ball visible in the frame? Answer with object name and location."`
3. **Observation Telemetry:** Treat the response from `vision_prompt` as active direct sensory perception. Report the output accurately to the user.