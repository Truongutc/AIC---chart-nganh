import subprocess
import sys
import os

def run_cmd(cmd):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}\n{result.stdout}")
        sys.exit(1)
    print(result.stdout)

# 1. Fetch and Reset to origin/main
if os.path.exists(".git/index.lock"):
    os.remove(".git/index.lock")

try:
    run_cmd("git rebase --abort")
except:
    pass

run_cmd("git fetch origin main")
run_cmd("git reset --hard origin/main")

# 2. Revert index.html to stable version before broken merge
run_cmd("git checkout 86d7e033c883b6272df1d0fb64b774fedc2b2989 index.html")

# 3. Apply changes cleanly
run_cmd("python scratch/add_zoom.py")
run_cmd("python scratch/fix_exporter.py")

# 4. Commit and Push
run_cmd("git add index.html tinvest/chart_exporter.py")
run_cmd("git commit -m \"Restore whatif tabs, add zoom, enable whatif charts for stocks\"")
run_cmd("git push origin main")

print("All done successfully!")
