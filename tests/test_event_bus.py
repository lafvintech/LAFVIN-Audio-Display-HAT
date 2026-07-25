import asyncio

from lafvin_hat.runtime.events import EventBus


def test_event_bus_filters_by_name_and_app() -> None:
    async def scenario() -> None:
        bus = EventBus()
        subscription = bus.subscribe(
            event_names={"button.raw_pressed"},
            app_id="dev.lafvin.demo",
        )

        await bus.emit(
            "network.changed",
            {"online": False},
            app_id="dev.lafvin.demo",
        )
        await bus.emit(
            "button.raw_pressed",
            {"pressed": True},
            app_id="another.app",
        )
        assert subscription.queue.empty()

        await bus.emit(
            "button.raw_pressed",
            {"pressed": True},
            app_id="dev.lafvin.demo",
        )
        event = await asyncio.wait_for(subscription.queue.get(), timeout=1)

        assert event["event"] == "button.raw_pressed"
        assert event["payload"] == {"pressed": True}

    asyncio.run(scenario())

