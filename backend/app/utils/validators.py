def clamp_top_k(value: int, minimum: int = 1, maximum: int = 20) -> int:
    return max(minimum, min(value, maximum))
