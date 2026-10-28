"""A message the owner sends while the agent waits for the model is heard at once.

The run holds the conversation's lock for a whole step but frees it while the model answers, so
send_message() puts the owner's message into the history right then, before the answer it was
sent during. The model's next request showed the message as already answered (the owner's "stop"
before the agent's next command), and the agent went on as if nothing had been said. Here a
message that arrives while the model answers cancels that answer and the step starts again, with
the message as the newest one. Only while the step has recorded nothing for the model: after
that, the step ends as usual and the message is read at the next one. The stop button (interrupt)
still stops the run.
"""
import asyncio
import contextlib


def patch_conversation(module):
    cls = module.LocalConversation
    cls._nexus_waiting = None  # the run's task while it waits for the model with the lock freed
    cls._nexus_spoke = False  # the current step already recorded an event for the model
    cls._nexus_redo = False  # a new message cancelled the answer: the step starts again
    released = cls._released_state_lock_during_io

    @contextlib.asynccontextmanager
    async def _released_state_lock_during_io(self):
        freed = self._state._lock.owned()
        async with released(self):
            if freed:
                self._nexus_waiting = asyncio.current_task()
            try:
                yield
            finally:
                self._nexus_waiting = None

    cls._released_state_lock_during_io = _released_state_lock_during_io
    send = cls.send_message

    def send_message(self, message, sender=None):
        send(self, message, sender)
        task = self._nexus_waiting
        if task is not None and not task.done():
            task.get_loop().call_soon_threadsafe(hear, self, task)

    cls.send_message = send_message


def hear(conversation, task):
    """Runs on the run's loop, so the step cannot move on between the check and the cancel.
    One redo per answer: a second quick message is already in the history the redone step reads,
    and a second cancel would look like the stop button."""
    if conversation._nexus_waiting is task and not task.done() and not conversation._nexus_spoke \
            and not conversation._nexus_redo:
        conversation._nexus_redo = True
        task.cancel()


def patch_agent(module):
    from openhands.sdk.conversation.state import ConversationExecutionStatus
    from openhands.sdk.event import LLMConvertibleEvent
    astep = module.Agent.astep

    async def astep_hearing(self, conversation, on_event, on_token=None):
        def record(event):
            if isinstance(event, LLMConvertibleEvent):
                conversation._nexus_spoke = True
            on_event(event)

        while True:
            conversation._nexus_spoke = conversation._nexus_redo = False
            try:
                return await astep(self, conversation, record, on_token)
            except asyncio.CancelledError:
                redo, conversation._nexus_redo = getattr(conversation, "_nexus_redo", False), False
                task = asyncio.current_task()
                token = getattr(conversation, "_cancel_token", None)
                # Anything besides our own cancel (the stop button, shutdown) still cancels.
                if not redo or task.cancelling() > 1 or (token is not None and token.is_cancelled):
                    raise
                task.uncancel()
                if conversation._state.execution_status == ConversationExecutionStatus.PAUSED:
                    return

    module.Agent.astep = astep_hearing
