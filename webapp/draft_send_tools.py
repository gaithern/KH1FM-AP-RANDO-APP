"""Delivers drafted items into a player's own live AP room.

Connects to a room as the room's (only) slot using CommonContext directly
- no subprocess/stdin piping needed, unlike the CLI-driven approach the
sibling Discord-Card-Game-Draft-Bot project uses. `!admin` commands are
plain `Say` packets (confirmed against MultiServer.py's _cmd_admin), so a
minimal headless client modeled on CommonClient.py's own
run_as_textclient()/TextContext is enough.
"""

import asyncio
import collections

from CommonClient import CommonContext, server_loop

CONNECT_TIMEOUT_SECONDS = 30


class _AdminSendContext(CommonContext):
    tags = CommonContext.tags | {"TextOnly"}
    game = ""  # empty matches any game (server negotiates), same as run_as_textclient
    items_handling = 0b111
    want_slot_data = False

    def __init__(self, server_address: str, slot_name: str):
        super().__init__(server_address, password=None)
        self.auth = slot_name
        self.connected_event = asyncio.Event()

    async def server_auth(self, password_requested: bool = False):
        await self.send_connect(game="")

    def on_package(self, cmd: str, args: dict):
        if cmd in ("Connected", "ConnectionRefused"):
            self.connected_event.set()


async def send_drafted_items(server_address: str, slot_name: str, server_password: str,
                              item_names: list[str]) -> None:
    """Connects to the room at server_address as slot_name, logs in as admin
    using server_password, and grants each drafted item via !admin /send_multiple.
    Raises RuntimeError if the connection or admin login doesn't succeed."""
    ctx = _AdminSendContext(server_address, slot_name)
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="draft admin server loop")
    try:
        await asyncio.wait_for(ctx.connected_event.wait(), timeout=CONNECT_TIMEOUT_SECONDS)
        if ctx.slot is None:
            raise RuntimeError(f"Could not connect to {server_address} as slot '{slot_name}'")

        await ctx.send_msgs([{"cmd": "Say", "text": f"!admin login {server_password}"}])
        await asyncio.sleep(1)

        counts = collections.Counter(item_names)
        for item_name, count in counts.items():
            await ctx.send_msgs(
                [{"cmd": "Say", "text": f"!admin /send_multiple {count} {slot_name} {item_name}"}]
            )
            await asyncio.sleep(0.5)
    finally:
        await ctx.shutdown()
