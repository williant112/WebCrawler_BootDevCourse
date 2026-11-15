import json
from crawl import *

def write_json_report(page_data:dict[str, PageData], filename="report.json"):
    # Sort page_data
    pages = sorted(page_data.values(), key=lambda p: p["url"])
    
    # Write json to file
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(pages, f, indent=2)