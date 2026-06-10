import sys
import time
import base64
import urllib.request
from pathlib import Path
from mcp.types import CallToolResult, ImageContent, TextContent
from typing import Literal, Optional

sys.path.append("/app")
from DOGZILLALib.DOGZILLALibClient import DOGZILLA

dog = DOGZILLA()

def register_tools(mcp):

    @mcp.tool()
    def body_move(
        action: Literal["step", "turn", "stop"], 
            direction: Literal["forward", "back", "left", "right"] = None,
            steps: int = 15, 
            duration: float = 1.0, 
            pace: Literal["slow", "normal", "high"] = "normal"
        ) -> str:
    
        """
        Execute a low-level chassis movement command to change the robot's
        physical location by step action or facing direction by turn action.

        Parameters:
        - action: Must be exactly one of the allowed movement strings.
            * 'step': Move in the specified direction by taking steps.
            * 'turn': Rotate in place to change facing direction.
            * 'stop': Immediately stop all movement. Ignores other parameters.
        - direction: The direction of movement or turn. Required for 'step' and 'turn'.
        - steps: Used ONLY by linear movements ('forward', 'back', 'left', 'right'). Ignored by rotational actions and 'stop'.
        - duration: The duration cap in seconds, applicable to all moving actions. Max value is 3.0.
        - pace: The movement speed profile, applicable to all moving actions.

        Returns:
        - str: A message describing the action taken or an error status.
        """

        print(f'Called: body_move with action={action}, direction={direction}, steps={steps}, duration={duration}, pace={pace}')    
        duration = min(duration, 3.0)
        dog.pace(pace)

        if action == "step":
            if direction == "forward":
                dog.forward(steps)
            elif direction == "back":
                dog.back(steps)
            elif direction == "left":
                dog.left(steps)
            elif direction == "right":
                dog.right(steps)
            else:
                return f"Unknown direction for step action: {direction}"                

        elif action == "turn":
            if direction == "left":
                dog.turnleft(50)
            elif direction == "right":
                dog.turnright(50)
            else:
                return f"Unknown direction for turn action: {direction}"

        elif action == "stop":
            dog.stop()
            return "Stopped"
        else:
            return f"Unknown action: {action}"

        time.sleep(duration)
        dog.stop()
        return f"Performed {action} with direction={direction}, steps={steps}, duration={duration}s, pace={pace}"

    _pitch = 0
    _yaw = 0

    @mcp.tool()
    def body_attitude(
        action: Literal["twist", "tilt", "reset_attitude"], 
        direction: Literal["left", "right", "up", "down"], 
        amount: int = 8
    ) -> str:
        """
        In-place torso adjustment. Shifts the robot's body attitude (pitch/yaw) 
        while keeping all feet completely stationary on the ground. The robot 
        will not rotate its global position or take any steps.

        CRITICAL: The robot will NOT walk, will NOT change its global heading, and 
        will NOT actually turn around to face a new direction. Do NOT use this tool 
        if the user wants the robot to turn around, face a different way, or move.

        Parameters:
        - action: The attitude control action to perform.
            * 'twist': Rotate the body around its vertical axis (yaw).
            * 'tilt': Tilt the body up or down (pitch).
            * 'reset_attitude': Reset the body's attitude to its default centered position.
        - direction: The direction of the action. 
            * Required for 'twist' ('left' or 'right') and 'tilt' ('up' or 'down').
            * Ignored for 'reset_attitude'.
        - amount: The magnitude of the twist or tilt. Clamped between 0 and 20. (default: 8).

        Returns:
        - str: A message describing the action taken or an error status.
        """

        nonlocal _pitch, _yaw
        print(f'Called: body_attitude with action={action}, direction={direction}, amount={amount}')
        amount = min(amount, 20)

        if action == "reset_attitude":
            dog.attitude(["y", "p", "r"], [0, 0, 0])
            _yaw = 0
            _pitch = 0
            return "Body reset to center"

        # Validate that direction was provided for actions that require it
        if not direction:
            return f"Error: 'direction' is required for action '{action}'"

        if action == "twist":
            if direction not in ["left", "right"]:
                return f"Error: Invalid direction '{direction}' for 'twist'. Use 'left' or 'right'."
            yaw = amount if direction == "left" else -amount
            dog.attitude(["y", "p", "r"], [yaw, _pitch, 0])
            _yaw = yaw
            return f"Twisted {direction} by {amount}"

        elif action == "tilt":
            if direction not in ["up", "down"]:
                return f"Error: Invalid direction '{direction}' for 'tilt'. Use 'up' or 'down'."
            pitch = -amount if direction == "up" else amount
            dog.attitude(["y", "p", "r"], [_yaw, pitch, 0])
            _pitch = pitch
            return f"Tilted {direction} by {amount}"

        return f"Unknown action: {action}"

    # Not possible becuase of ambiguity
    # lookup: Bend the knees and look up.
    # look_around: Look down and move around curiously

    @mcp.tool()
    def body_action(
            action: Literal["sit", "wave", "dance", "happy", "handshake",
             "spin", "stretch", "shake_head", "pee", "squat", "crawl",
             "march","three_squats", "seesaw", "sway", "full_dance",
             "swing", "fancy_stretch", "head_circle", "body_circle", "nod"]
        ) -> str:
        """
        Perform a predefined body action. Available actions:
        - sit: Sit on the back legs.
        - wave: Wave with the left front leg.
        - dance: Perform a dance by moving left and right.
        - happy: Act happy, such as wagging a tail.
        - handshake: Sit and offer a handshake with the left leg.
        - spin: Spin 360 degrees.
        - stretch: Stretch all legs.
        - shake_head: Shake the head left and right.
        - pee: Perform a peeing action.
        - squat: Bend the knees and squat once.
        - crawl: Crawl or crouch low to the ground. Moves forward.
        - march: Walk on the spot.
        - three_squats: Perform three squats in a row.
        - seesaw: Perform a seesaw-like motion.
        - sway: Sway the body left and right like a kid.
        - full_dance: Perform a full dance sequence combining head shake, seesaw, and sway.
        - swing: Perform a front and back swinging motion.
        - fancy_stretch: Stretch back legs, then crouch and raise front legs.
        - head_circle: Move the head in a clockwise and anticlockwise circle.
        - body_circle: Perform a slanting circular body motion.
        - nod: Nod the head up and down.

        Parameters:
        - action: The body action to perform.

        Returns:
        - str: A message describing the action taken or an error status.
        """

        print(f'Called: body_action with action={action}')
        actions = {
            "squat": 1,
            "lookup": 2,
            "crawl": 3,
            "spin": 4,
            "march": 5,
            "three_squats": 6,
            "shake_head": 7,
            "seesaw": 8,
            "sway": 9,
            "full_dance": 10,
            "pee": 11,
            "sit": 12,
            "wave": 13,
            "stretch": 14,
            "swing": 15,
            "dance": 16,
            "happy": 17,
            "look_around": 18,
            "handshake": 19,
            "fancy_stretch": 21,
            "head_circle": 22,
            "body_circle": 23,
            "nod": 24
        }

        if action in actions:
            dog.action(actions[action])
            return f"Performed action: {action}"
        else:
            return f"Unknown action: {action}"