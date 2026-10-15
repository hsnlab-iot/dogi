import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from DOGZILLALib.DOGZILLALib import DOGZILLALibClient as dog

dogControl = dog.DOGZILLA("/dev/ttyAMA0") # Ignored!

# Usage example: python test_webapi.py move_x 1
method_name = sys.argv[1]
args = sys.argv[2:]  # remaining arguments

method = getattr(dogControl, method_name)

# Convert numeric args, keep strings as-is
converted = [int(a) if a.lstrip('-').isdigit() else a for a in args]

result = method(*converted)
print(result)