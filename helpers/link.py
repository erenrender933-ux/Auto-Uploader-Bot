import base64


def encode(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def make_link(bot_username: str, db_channel: int, msg_id: int) -> str:
    # Common file store bot format: get-<msg_id * abs(channel_id)>
    payload = encode(f"get-{msg_id * abs(db_channel)}")
    return f"https://t.me/{bot_username}?start={payload}"
