import subprocess
import sys

def run_cmd(cmd):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}\n{result.stdout}")
        sys.exit(1)
    print(result.stdout)

# 1. Add changes
run_cmd("git add index.html tinvest/chart_exporter.py Output/")

# 2. Commit
run_cmd("git commit -m \"Fix whatif charts and restore tabs\"")

# 3. Pull rebase
run_cmd("git pull origin main --rebase")

# 4. Push
run_cmd("git push")

print("All done successfully!")
