import os

for root, dirs, files in os.walk('..'):
    for file in files:
        if file.endswith('.py'):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if 'OCT' in content or 'Octopus' in content:
                    print(f"Found in {path}")
                    # Print matching lines
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if 'OCT' in line or 'Octopus' in line:
                            print(f"  {i+1}: {line.strip()}")
            except Exception as e:
                pass
