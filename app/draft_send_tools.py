import asyncio
from collections import Counter

CONNECT_TIMEOUT_SECONDS = 30
RECEIVE_ALL_ITEMS = 0b111
ANY_GAME = ""


def build_admin_context_class():
    from CommonClient import CommonContext

    class AdminSendContext(CommonContext):
        tags = CommonContext.tags | {"TextOnly"}
        game = ANY_GAME
        items_handling = RECEIVE_ALL_ITEMS
        want_slot_data = False

        def __init__(self, server_address: str, slot_name: str):
            super().__init__(server_address, password=None)
            self.auth = slot_name
            self.connected_event = asyncio.Event()
            self.connection_error: str | None = None

        async def server_auth(self, password_requested: bool = False):
            await self.send_connect(game=ANY_GAME)

        def on_package(self, cmd: str, args: dict):
            if cmd == "ConnectionRefused":
                self.connection_error = f"server refused the connection: {args.get('errors')}"
            if cmd == "Connected" or cmd == "ConnectionRefused":
                self.connected_event.set()

        def handle_connection_loss(self, msg: str) -> None:
            self.connection_error = msg
            super().handle_connection_loss(msg)

    return AdminSendContext


async def say(context, text):
    await context.send_msgs([{"cmd": "Say", "text": text}])


async def send_drafted_items(server_address: str, slot_name: str, server_password: str,
                             item_names: list[str]) -> None:
    from CommonClient import server_loop

    AdminSendContext = build_admin_context_class()
    context = AdminSendContext(server_address, slot_name)
    context.server_task = asyncio.create_task(server_loop(context), name="draft admin server loop")
    try:
        wait_for_connection = asyncio.ensure_future(context.connected_event.wait())
        await asyncio.wait(
            [context.server_task, wait_for_connection],
            timeout=CONNECT_TIMEOUT_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if not context.connected_event.is_set():
            wait_for_connection.cancel()
            reason = context.connection_error
            if not reason:
                reason = f"no response within {CONNECT_TIMEOUT_SECONDS}s"
            raise RuntimeError(f"Could not connect to {server_address} as slot '{slot_name}': {reason}")

        if context.slot is None:
            reason = context.connection_error
            if not reason:
                reason = "unknown reason (check the slot name matches the YAML's name: exactly)"
            raise RuntimeError(f"Connected to {server_address} but slot '{slot_name}' was rejected: {reason}")

        await say(context, f"!admin login {server_password}")
        await asyncio.sleep(1)

        copies_by_item_name = Counter(item_names)
        for item_name, copies in copies_by_item_name.items():
            await say(context, f"!admin /send_multiple {copies} {slot_name} {item_name}")
            await asyncio.sleep(0.5)
    finally:
        await context.shutdown()
