def roman_to_int(roman: str) -> int:
    roman_values = {
        "I": 1,
        "V": 5,
        "X": 10,
        "L": 50,
        "C": 100,
        "D": 500,
        "M": 1000
    }

    total = 0
    prev_value = 0

    # Duyệt từ phải sang trái
    for char in reversed(roman.upper()):
        value = roman_values[char]

        if value < prev_value:
            total -= value
        else:
            total += value
            prev_value = value

    return total