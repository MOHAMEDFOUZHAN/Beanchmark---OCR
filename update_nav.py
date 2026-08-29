import os
import re

# Target navigation block
NEW_NAV = """  <nav>
    <a href="/dashboard">Dashboard</a>
    <a href="/invoices">Invoices</a>
    <a href="/transfers">Transfers</a>
    <a href="/materials">Materials</a>
    <a href="/storage">Storage</a>
    <a href="/vendors">Vendors</a>
    <a href="/dispatch">Dispatch</a>
    <a href="/warehouse/categories">Shelf Mapping</a>
    <a href="/reports/utilization">MUR</a>
    <a href="/reports">Reports</a>
  </nav>"""

TEMPLATE_DIR = r"d:\Beanchmark\templates"

def update_nav_in_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Regex to find <nav> ... </nav> block, accounting for potential attributes
        # Using re.DOTALL to match across multiple lines
        # Using [^>]* to catch any class/style attributes
        nav_pattern = re.compile(r'<nav[^>]*>.*?</nav>', re.DOTALL)
        
        if not nav_pattern.search(content):
            # print(f"No <nav> found in: {file_path}")
            return

        new_content = nav_pattern.sub(NEW_NAV, content)
        
        if content != new_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated: {file_path}")
        else:
            print(f"Already correct: {file_path}")
    except Exception as e:
        print(f"Error processing {file_path}: {e}")

def main():
    print(f"Starting update in {TEMPLATE_DIR}")
    for root, dirs, files in os.walk(TEMPLATE_DIR):
        for file in files:
            if file.endswith('.html'):
                file_path = os.path.join(root, file)
                update_nav_in_file(file_path)

if __name__ == "__main__":
    main()
