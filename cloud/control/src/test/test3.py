from DOGZILLALib.DOGZILLALib import DOGZILLALib as dog
import time

dogControl = dog.DOGZILLA("/dev/ttyAMA0")

time.sleep(1)
print(dogControl.read_battery())
time.sleep(0.5)
print(dogControl.read_motor())

dogControl.reset()
time.sleep(1)

#dogControl.motor(31,-73)
#time.sleep(2)
#dogControl.motor(31,0)
#time.sleep(2)
#dogControl.motor(31,57)
#time.sleep(2)

#dogControl.motor(32,-66)
#time.sleep(2)
#dogControl.motor(32,0)
#time.sleep(2)
#dogControl.motor(32,93)
#time.sleep(2)

dogControl.motor(13,31)
dogControl.motor(43,31)
time.sleep(1)
dogControl.motor(13,-31)
dogControl.motor(43,-31)
