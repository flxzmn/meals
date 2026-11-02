def without_empty(data: dict) -> dict:
    """Leave out keys without a value (None, empty list or dict): in a tool result they cost tokens and say nothing."""
    return {key: value for key, value in data.items() if value is not None and value != [] and value != {}}
