from DOGZILLALib.DOGZILLALib import DOGZILLALib as dog
import time

dogControl = dog.DOGZILLA("/dev/ttyAMA0")

time.sleep(1)
dogControl.unload_allmotor()
