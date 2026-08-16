
"""Trigger an outbound call.

Accepts either:
    +15551234567
    sip:username@domain.com
    username@domain.com

For the configured Linphone trunk, SIP URIs are converted to the SIP
username because the trunk already provides the SIP server address.
"""

import argparse
import asyncio
import json
import re
import uuid

from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")

AGENT_NAME = "outbound-agent"

E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def normalize_destination(destination: str) -> str:
    """Convert a SIP URI into the SIP user expected by LiveKit."""

    destination = destination.strip()

    # sip:thush_ar_palo@sip.linphone.org
    if destination.lower().startswith("sip:"):
        destination = destination[4:]

    # thush_ar_palo@sip.linphone.org
    if "@" in destination:
        destination = destination.split("@", 1)[0]

    return destination


async def dial(phone_number: str, room_name: str) -> None:
    """Create the room and dispatch the outbound agent."""

    lk = api.LiveKitAPI()

    try:
        await lk.room.create_room(
            api.CreateRoomRequest(name=room_name)
        )

        await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=json.dumps(
                    {"phone_number": phone_number}
                ),
            )
        )

    finally:
        await lk.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Place an outbound call."
    )

    parser.add_argument(
        "--to",
        required=True,
        help=(
            "Phone number or SIP destination. "
            "Examples: +15551234567 or "
            "sip:username@sip.example.com"
        ),
    )

    parser.add_argument(
        "--room",
        default=None,
        help="Room name to use. Defaults to a generated one.",
    )

    args = parser.parse_args()

    destination = normalize_destination(args.to)

    if not destination:
        raise SystemExit("Empty SIP destination.")

    room_name = args.room or f"outbound-{uuid.uuid4().hex[:8]}"

    asyncio.run(
        dial(destination, room_name)
    )

    print(
        f"Dispatched {AGENT_NAME} to room "
        f"'{room_name}' to call {destination}."
    )
    print("Watch the worker terminal for call progress.")


if __name__ == "__main__":
    main()


