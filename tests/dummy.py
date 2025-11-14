import time
import sys
import random

# Force unbuffered output so prints appear immediately in Slurm output files
print("Dummy job started", flush=True)
print(f"Running on node: {sys.platform}", flush=True)

seed = 42
random.seed(seed)
print(f"Set seed: {seed}", flush=True)

# Simulate some work
for i in range(10):
    print(f"Progress: {i*20}%", flush=True)
    rnd_num = random.random()
    print(f"  Value: {rnd_num:.4f}")
    print("waiting...", flush=True)
    time.sleep(15)

print("Dummy job completed successfully", flush=True)