def add(a, b):
    return a + b


def average(nums):
    return sum(nums) / len(nums)


def percent(part, whole):
    return round(part / whole * 100, 1)


def clamp(x, lo, hi):
    return max(lo, min(x, hi))
