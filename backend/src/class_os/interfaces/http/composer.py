"""Explicit capture of user-selected input, never business persistence."""
import asyncio
from contextlib import suppress
from typing import Literal
import anyio
from uuid import UUID
from fastapi import APIRouter, Request
from pydantic import Field
from starlette.responses import JSONResponse
from .contracts import WireModel
from .roster import credentials
from class_os.infrastructure.composer_capture import capture_text, CaptureRejected
from class_os.application.audit import AuditUnavailable
from class_os.application.roster import CommandRejected
from class_os.application.identity import IdentityDenied


class CaptureInput(WireModel):
    name: str = Field(min_length=1, max_length=120)
    data: str = Field(min_length=1, max_length=2796204)
    capacity: int = Field(strict=True, ge=1, le=2000)


class CaptureOutput(WireModel):
    schema_version: Literal['classmatter.composer-capture.v1'] = 'classmatter.composer-capture.v1'
    text: str = Field(min_length=1, max_length=2000)


def router(query, controller):
    routes = APIRouter(prefix='/api/workspaces/{workspace_id}/composer')
    @routes.post('/capture', response_model=CaptureOutput)
    async def capture(workspace_id: UUID, request: Request, body: CaptureInput):
        auth = credentials(request, workspace_id, write=True)
        await anyio.to_thread.run_sync(lambda: query.agent_workspace_context(*auth))
        task = asyncio.create_task(capture_text(query, controller, auth, body.name, body.data, body.capacity))
        try:
            while not task.done():
                if await request.is_disconnected():
                    task.cancel()
                    break
                await asyncio.sleep(.1)
            return CaptureOutput(text=await task)
        except CaptureRejected as error:
            return JSONResponse({'error': error.code}, status_code=422)
        except asyncio.CancelledError:
            raise
        except (AuditUnavailable, CommandRejected, IdentityDenied):
            raise
        except Exception:
            return JSONResponse({'error': 'capture_failed'}, status_code=422)
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
    return routes
