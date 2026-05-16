import argparse
import time
from DogiLib import DogiLib

parser = argparse.ArgumentParser()
parser.add_argument('--duration', type=float, default=1.0)
parser.add_argument('--pace', type=str, default='normal')
args = parser.parse_args()

# A szavak lefordítása számokra (step)
pace_to_step = {
    'slow': 1,
    'normal': 3,
    'fast': 5
}
aktualis_step = pace_to_step.get(args.pace, 3)

print(f"Indulas elore '{args.pace}' (lépéshossz: {aktualis_step}) tempoval, {args.duration} masodpercig...")

try:
    dogi = DogiLib()
    
    # A JAVÍTOTT SOR: Szótár {} helyett listaként [] küldjük be a számot!
    dogi.control('forward', [aktualis_step])
    
    time.sleep(args.duration)
    
    dogi.control('stop')
    print("Sikeresen megalltam a biztonsagi idokorlat utan!")
    
except Exception as e:
    print(f"Hiba tortent a mozgas kozben: {e}")
