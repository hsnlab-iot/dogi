import sys
import time
import base64
import urllib.request
from pathlib import Path
from mcp.types import CallToolResult, ImageContent, TextContent

sys.path.append("/app")
from DOGZILLALib.DOGZILLALibClient import DOGZILLA

dog = DOGZILLA()

def register_tools(mcp):

    @mcp.tool()
    def body_move(action: str, steps: int = 15, duration: float = 1.0, pace: str = "normal") -> str:
        """
        Perform a movement action. Available actions:
        - forward: Move forward by a specified number of steps.
        - back: Move backward by a specified number of steps.
        - left: Move to the left by a specified number of steps.
        - right: Move to the right by a specified number of steps.
        - turnleft: Rotate the body to the left without moving forward.
        - turnright: Rotate the body to the right without moving forward.
        - stop: Immediately stop all movement.

        Parameters:
        - action: The movement action to perform.
        - steps: The number of steps to take (default: 15).
        - duration: The duration of the movement in seconds (default: 1.0).
        - pace: The speed of the movement (slow, normal, or high; default: normal).
        """
        duration = min(duration, 3.0)
        dog.pace(pace)

        if action == "forward":
            dog.forward(steps)
        elif action == "back":
            dog.back(steps)
        elif action == "left":
            dog.left(steps)
        elif action == "right":
            dog.right(steps)
        elif action == "turnleft":
            dog.turnleft(50)
        elif action == "turnright":
            dog.turnright(50)
        elif action == "stop":
            dog.stop()
            return "Stopped"
        else:
            return f"Unknown action: {action}"

        time.sleep(duration)
        dog.stop()
        return f"Performed {action} with steps={steps}, duration={duration}s, pace={pace}"

    @mcp.tool()
    def attitude_control(action: str, direction: str = "left", amount: int = 8) -> str:
        """
        Control the body's attitude. Available actions:
        - twist: Rotate the body around its vertical axis (yaw). Direction can be left or right.
        - tilt: Tilt the body up or down (pitch). Direction can be up or down.
        - reset_attitude: Reset the body's attitude to its default centered position.

        Parameters:
        - action: The attitude control action to perform.
        - direction: The direction of the twist or tilt (default: left for twist, up for tilt).
        - amount: The magnitude of the twist or tilt (default: 8).
        """
        amount = min(amount, 20)

        if action == "twist":
            yaw = amount if direction == "left" else -amount
            dog.attitude(["y", "p", "r"], [yaw, 0, 0])
            return f"Twisted {direction} by {amount}"
        elif action == "tilt":
            pitch = -amount if direction == "up" else amount
            dog.attitude(["y", "p", "r"], [0, pitch, 0])
            return f"Tilted {direction} by {amount}"
        elif action == "reset_attitude":
            dog.attitude(["y", "p", "r"], [0, 0, 0])
            return "Body reset to center"
        else:
            return f"Unknown action: {action}"

    @mcp.tool()
    def body_action(action: str) -> str:
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
        - lookup: Bend the knees and look up.
        - crawl: Crawl or crouch low to the ground.
        - march: Walk on the spot.
        - three_squats: Perform three squats in a row.
        - seesaw: Perform a seesaw-like motion.
        - sway: Sway the body left and right like a kid.
        - full_dance: Perform a full dance sequence combining head shake, seesaw, and sway.
        - swing: Perform a front and back swinging motion.
        - look_around: Look down and move around curiously.
        - fancy_stretch: Stretch back legs, then crouch and raise front legs.
        - head_circle: Move the head in a clockwise and anticlockwise circle.
        - body_circle: Perform a slanting circular body motion.
        - nod: Nod the head up and down.

        Parameters:
        - action: The body action to perform.
        """
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