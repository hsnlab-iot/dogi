import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DOGZILLALib.DOGZILLALib import DOGZILLALib as dog

dogControl = dog.DOGZILLA("/dev/ttyAMA0")
time.sleep(1)

action_param = int(sys.argv[1]) if len(sys.argv) > 1 else 11
dogControl.action(action_param)
