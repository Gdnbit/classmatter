"""Bounded standing-summary checks; APScheduler wakes, the existing SDK acts."""
import asyncio
import logging

import anyio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from class_os.application.identity import IdentityDenied


class PersonalSummaryService:
    def __init__(self, runtime, *, interval=30):
        self.runtime, self.interval = runtime, interval
        self.scheduler = None
        self.sessions, self.checking, self.tasks = {}, set(), set()

    async def watch(self, credentials):
        # Only a CSRF-protected explicit POST registers a live identity. No
        # credential is persisted and GET/reconnect never redispatches a turn.
        await anyio.to_thread.run_sync(lambda: self.runtime.query.listing(credentials))
        self.sessions[credentials[3]] = credentials
        if self.scheduler is None:
            self.scheduler = AsyncIOScheduler(timezone='UTC')
            self.scheduler.start()
        key = str(credentials[3])
        if self.scheduler.get_job(key) is None:
            self.scheduler.add_job(self.check, 'interval', seconds=self.interval, args=[credentials[3]],
                id=key, coalesce=True, max_instances=1, misfire_grace_time=30)
        task = asyncio.create_task(self.check(credentials[3]))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def check(self, workspace_id):
        if workspace_id in self.checking or workspace_id not in self.sessions:
            return
        self.checking.add(workspace_id)
        task = asyncio.current_task()
        self.tasks.add(task)
        credentials = self.sessions[workspace_id]
        try:
            programs = await anyio.to_thread.run_sync(lambda: self.runtime.query.summary_programs(credentials))
            for program in programs:
                turn = await anyio.to_thread.run_sync(lambda: self.runtime.business.summary_claim(credentials, program['document_id']))
                if turn is not None:
                    async for _ in self.runtime.stream_queued(credentials, program['thread_id'], turn['request_id']):
                        pass  # Only committed QG history is rendered by the UI.
        except asyncio.CancelledError:
            raise
        except IdentityDenied:
            # Expired/revoked sessions stop waking until the original app
            # explicitly registers a newly authorized session again.
            self.sessions.pop(workspace_id, None)
            if self.scheduler is not None and self.scheduler.get_job(str(workspace_id)):
                self.scheduler.remove_job(str(workspace_id))
        except Exception as error:
            # Keep diagnostics useful without copying source text or credentials.
            logging.getLogger(__name__).warning('Personal summary check stopped: %s', type(error).__name__)
        finally:
            self.checking.discard(workspace_id)
            self.tasks.discard(task)

    async def close(self):
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None
        self.sessions.clear()
        for task in tuple(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
