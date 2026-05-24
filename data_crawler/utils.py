import re
from urllib.parse import parse_qs, urlparse

def roman_to_int(roman_num: str) -> int:
    roman_num = roman_num.upper()
    roman_to_num = {'I': 10, 'V': 50, 'X': 100, 'L': 500, 'C': 1000, 'D': 5000, 'M': 10000}
    alphabet = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']
    num = 0
    for i in range(len(roman_num)):
        romain_char = roman_num[i]
        if romain_char not in roman_to_num.keys():
            num += alphabet.index(romain_char) + 1
            continue
        if i > 0 and roman_to_num[romain_char] > roman_to_num[roman_num[i - 1]]:
            num += roman_to_num[romain_char] - 2 * roman_to_num[roman_num[i - 1]]
        else:
            num += roman_to_num[romain_char]
    return num

def extract_input(input_string):
    # Define a regular expression pattern to match the content inside parentheses
    pattern = r"\((.*?)\)"

    # Use re.search to find the first match in the input string
    match = re.search(pattern, input_string)

    # Check if a match is found
    if match:
        # Extract and return the content inside parentheses
        return match.group(1)
    else:
        # Return None if no match is found
        return None


def extract_vbpl_document_id(href):
    if href is None:
        return None

    href = str(href).strip()
    if not href:
        return None

    parsed = urlparse(href)
    path = parsed.path.rstrip("/")

    match = re.search(r"/van-ban/chi-tiet/(?:.*-)?(\d+)$", path)
    if match:
        return match.group(1)

    match = re.search(r"ItemID=(\d+)", href)
    if match:
        return match.group(1)

    query_item_id = parse_qs(parsed.query).get("ItemID")
    if query_item_id and query_item_id[0].isdigit():
        return query_item_id[0]

    match = re.search(r"(\d+)(?:\?.*)?$", path)
    if match:
        return match.group(1)

    return None
