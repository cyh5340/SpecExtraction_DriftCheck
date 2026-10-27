def add(a, b):
    return a + b


def average(nums):
    return sum(nums) / len(nums)


def percent(part, whole):
    return round(part / whole * 100, 1)


def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
