try:
    with open('results_full.txt', 'r', encoding='utf-16le') as f:
        print(f.read())
except Exception as e:
    with open('results_full.txt', 'r', encoding='utf-8') as f:
        print(f.read())
