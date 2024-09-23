# Sit motors: [27.43, 1.96, 1.09, 28.45, 1.96, 0.85, -72.49, 93.0, 1.09, -71.98, 93.0, 0.61]
# 1: Front right, 2: Front left, 3: Back left, 4: Back right
# x1: Up, x2: Down, x3: Side


from DOGZILLALib.DOGZILLALib import DOGZILLALib as dog
import time

dogControl = dog.DOGZILLA("/dev/ttyAMA0")

time.sleep(1)
print(dogControl.read_motor())
dogControl.motor(32, 93)
dogControl.motor(42, 93)
dogControl.motor(31, -73)
dogControl.motor(41, -73)
dogControl.motor(12, 10)
dogControl.motor(22, 10)
dogControl.motor(11, 30)
dogControl.motor(21, 30)
time.sleep(1)
print(dogControl.read_motor())