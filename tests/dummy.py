import time
import sys

# Force unbuffered output so prints appear immediately in Slurm output files
print("Dummy job started", flush=True)
print(f"Running on node: {sys.platform}", flush=True)

# Simulate some work
for i in range(10):
    print(f"Progress: {i*20}%", flush=True)
    time.sleep(15)

print("Dummy job completed successfully", flush=True)