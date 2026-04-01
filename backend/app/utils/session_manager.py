import uuid


def generate_new_session_id() -> str:
    return str(uuid.uuid4())
