import os
with open('env_test.txt', 'w') as f:
    for k, v in os.environ.items():
        f.write(f"{k}={v}\n")
