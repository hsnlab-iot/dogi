import sys
import time
import base64
import urllib.request
from enum import Enum
from pathlib import Path
from mcp.types import CallToolResult, ImageContent, TextContent
from typing import Optional

sys.path.append("/app")
from DOGZILLALib.DOGZILLALibClient import DOGZILLA

dog = DOGZILLA()

# ==========================================
# ENUM DEFINÍCIÓK A HALLUCINÁCIÓK ELLEN
# ==========================================

class MoveAction(str, Enum):
    STEP = "step"
    TURN = "turn"
    STOP = "stop"

class Direction(str, Enum):
    FORWARD = "forward"
    BACK = "back"
    LEFT = "left"
    RIGHT = "right"

class Pace(str, Enum):
    SLOW = "slow"
    NORMAL = "normal"
    HIGH = "high"

class AttitudeAction(str, Enum):
    TWIST = "twist"
    TILT = "tilt"
    RESET_ATTITUDE = "reset_attitude"

class AttitudeDirection(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"

class BodyActionType(str, Enum):
    SQUAT = "squat"
    CRAWL = "crawl"
    SPIN = "spin"
    MARCH = "march"
    THREE_SQUATS = "three_squats"
    SHAKE_HEAD = "shake_head"
    SEESAW = "seesaw"
    SWAY = "sway"
    FULL_DANCE = "full_dance"
    PEE = "pee"
    SIT = "sit"
    WAVE = "wave"
    STRETCH = "stretch"
    SWING = "swing"
    DANCE = "dance"
    HAPPY = "happy"
    HANDSHAKE = "handshake"
    FANCY_STRETCH = "fancy_stretch"
    HEAD_CIRCLE = "head_circle"
    BODY_CIRCLE = "body_circle"
    NOD = "nod"


# Átadási kódok leképezése
BODY_ACTION_MAP = {
    BodyActionType.SQUAT: 1,
    BodyActionType.CRAWL: 3,
    BodyActionType.SPIN: 4,
    BodyActionType.MARCH: 5,
    BodyActionType.THREE_SQUATS: 6,
    BodyActionType.SHAKE_HEAD: 7,
    BodyActionType.SEESAW: 8,
    BodyActionType.SWAY: 9,
    BodyActionType.FULL_DANCE: 10,
    BodyActionType.PEE: 11,
    BodyActionType.SIT: 12,
    BodyActionType.WAVE: 13,
    BodyActionType.STRETCH: 14,
    BodyActionType.SWING: 15,
    BodyActionType.DANCE: 16,
    BodyActionType.HAPPY: 17,
    BodyActionType.HANDSHAKE: 19,
    BodyActionType.FANCY_STRETCH: 21,
    BodyActionType.HEAD_CIRCLE: 22,
    BodyActionType.BODY_CIRCLE: 23,
    BodyActionType.NOD: 24
}


def register_tools(mcp):

    @mcp.tool()
    def body_move(
        action: MoveAction, 
        direction: Optional[Direction] = None,
        steps: int = 15, 
        duration: float = 1.0, 
        pace: Pace = Pace.NORMAL
    ) -> str:
        """
        Execute a low-level chassis movement command to change the robot's
        physical location by step action or facing direction by turn action.
        """
        print(f'Called: body_move with action={action}, direction={direction}, steps={steps}, duration={duration}, pace={pace}')    
        duration = min(duration, 3.0)
        dog.pace(pace.value)

        if action == MoveAction.STEP:
            if direction == Direction.FORWARD:
                dog.forward(steps)
            elif direction == Direction.BACK:
                dog.back(steps)
            elif direction == Direction.LEFT:
                dog.left(steps)
            elif direction == Direction.RIGHT:
                dog.right(steps)
            else:
                return f"Error: Direction required for step action."

        elif action == MoveAction.TURN:
            if direction == Direction.LEFT:
                dog.turnleft(50)
            elif direction == Direction.RIGHT:
                dog.turnright(50)
            else:
                return f"Error: Invalid or missing direction for turn action."

        elif action == MoveAction.STOP:
            dog.stop()
            return "Stopped"

        time.sleep(duration)
        dog.stop()
        return f"Performed {action.value} with direction={direction.value if direction else None}, steps={steps}, duration={duration}s, pace={pace.value}"

    _pitch = 0
    _yaw = 0

    @mcp.tool()
    def body_attitude(
        action: AttitudeAction, 
        direction: Optional[AttitudeDirection] = None, 
        amount: int = 8
    ) -> str:
        """
        In-place torso adjustment (pitch/yaw) while feet stay stationary.
        """
        nonlocal _pitch, _yaw
        print(f'Called: body_attitude with action={action}, direction={direction}, amount={amount}')
        amount = min(amount, 20)

        if action == AttitudeAction.RESET_ATTITUDE:
            dog.attitude(["y", "p", "r"], [0, 0, 0])
            _yaw = 0
            _pitch = 0
            return "Body reset to center"

        if not direction:
            return f"Error: 'direction' is required for action '{action.value}'"

        if action == AttitudeAction.TWIST:
            if direction not in [AttitudeDirection.LEFT, AttitudeDirection.RIGHT]:
                return f"Error: Invalid direction '{direction.value}' for 'twist'."
            yaw = amount if direction == AttitudeDirection.LEFT else -amount
            dog.attitude(["y", "p", "r"], [yaw, _pitch, 0])
            _yaw = yaw
            return f"Twisted {direction.value} by {amount}"

        elif action == AttitudeAction.TILT:
            if direction not in [AttitudeDirection.UP, AttitudeDirection.DOWN]:
                return f"Error: Invalid direction '{direction.value}' for 'tilt'."
            pitch = -amount if direction == AttitudeDirection.UP else amount
            dog.attitude(["y", "p", "r"], [_yaw, pitch, 0])
            _pitch = pitch
            return f"Tilted {direction.value} by {amount}"

    @mcp.tool()
    def body_action(action: BodyActionType) -> str:
        """
        Perform a predefined body action sequence.
        """
        print(f'Called: body_action with action={action}')

        if action in BODY_ACTION_MAP:
            dog.action(BODY_ACTION_MAP[action])
            return f"Performed action: {action.value}"
        
        return f"Unknown action: {action}"