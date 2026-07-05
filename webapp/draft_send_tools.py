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
        self.connection_error: str | None = None

    async def server_auth(self, password_requested: bool = False):
        await self.send_connect(game="")

    def on_package(self, cmd: str, args: dict):
        if cmd == "ConnectionRefused":
            self.connection_error = f"server refused the connection: {args.get('errors')}"
        if cmd in ("Connected", "ConnectionRefused"):
            self.connected_event.set()

    def handle_connection_loss(self, msg: str) -> None:
        # Called from server_loop's except blocks for transport-level failures
        # (refused/invalid URI/timeout/etc.) that never reach the AP protocol
        # handshake, so on_package's cmd-based branches above never fire.
        self.connection_error = msg
        super().handle_connection_loss(msg)


async def send_drafted_items(server_address: str, slot_name: str, server_password: str,
                              item_names: list[str]) -> None:
    """Connects to the room at server_address as slot_name, logs in as admin
    using server_password, and grants each drafted item via !admin /send_multiple.
    Raises RuntimeError, with a specific reason, if the connection or admin
    login doesn't succeed."""
    ctx = _AdminSendContext(server_address, slot_name)
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="draft admin server loop")
    try:
        connected_wait = asyncio.ensure_future(ctx.connected_event.wait())
        await asyncio.wait([ctx.server_task, connected_wait], timeout=CONNECT_TIMEOUT_SECONDS,
                           return_when=asyncio.FIRST_COMPLETED)
        if not ctx.connected_event.is_set():
            connected_wait.cancel()
            reason = ctx.connection_error or f"no response within {CONNECT_TIMEOUT_SECONDS}s"
            raise RuntimeError(f"Could not connect to {server_address} as slot '{slot_name}': {reason}")
        if ctx.slot is None:
            reason = ctx.connection_error or "unknown reason (check the slot name matches the YAML's name: exactly)"
            raise RuntimeError(f"Connected to {server_address} but slot '{slot_name}' was rejected: {reason}")

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
