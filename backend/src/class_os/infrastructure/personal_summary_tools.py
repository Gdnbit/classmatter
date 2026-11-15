"""Summary-specific read/draft tools; reuse original document confirmation."""
import re
from typing import Literal
from uuid import uuid4
from pydantic_ai import ModelRetry

from class_os.domain.documents import CreateDocument, ReviseDocument
from class_os.domain.personal_summary import SummaryDelegation, TITLE


def tools(capture, query, credentials, context, execute, missing_class):
    def existing(current):
        rows = [row for row in query.documents(*credentials, current.class_id, current.term_id)
                if row['title'] == TITLE and row['status'] == 'draft']
        if len(rows) > 1:
            raise ValueError('Ambiguous summary delegation')
        return query.document(*credentials, current.class_id, current.term_id, rows[0]['document_id']) if rows else None

    async def prepare_summary_delegation(quote: str, action: Literal['enable', 'update', 'pause'] = 'enable',
            style: Literal['standard', 'three-points'] | None = None, required_material: str | None = None) -> dict:
        """Only for explicit ongoing delegation or long-term feedback about class work summaries. Quote the exact current human request. 'This time' is not a permanent preference. Prepare a readable instruction document for the existing human confirmation; never saves or enables itself. Preserve omitted prior settings. Pause only on an explicit stop request."""
        def prepare():
            request = capture.user_messages[-1] if capture.user_messages else ''
            if capture.summary_context and not re.search(r'以后|今后|持续|长期|暂停|停止|不再|恢复|重新开始', request):
                raise ModelRetry('A confirmed summary delegation already applies. This human answer or retry is not a new delegation. '
                    'Read current facts/tasks and prepare the summary, or use ask_summary_question for its missing required material.')
            if not quote or quote not in request or len(quote) > 1000:
                raise ModelRetry('Quote only the exact current human message, never prior delegation messages or concatenated history. '
                    'If this is a reply/retry, read the confirmed instructions and continue the existing summary instead of asking to enable it again.')
            if action == 'pause':
                valid = bool(re.search(r'暂停|停止|不再|不要|不用|别再', quote)) and not re.search(
                    r'(?:不要|不用|别|不必|无需|不想|不需要)\s*(?:再)?(?:暂停|停止)|这次|仅本次|假设|举例|引用', request)
            else:
                valid = bool(re.search(r'以后|今后|持续|平时|长期|每次|一直', quote)) and not re.search(
                    r'这次|仅本次|不要|不需要|不用|别|假设|举例|引用', quote)
            resume = (action == 'enable' and '小结' in quote and bool(re.search(r'恢复|重新开始', quote))
                and not re.search(r'这次|仅本次|不要|不需要|不用|不想|不必|无需|不再|不恢复|别|假设|举例|引用', request))
            if not valid and not resume:
                return {'status': 'not-long-term-delegation',
                        'instruction': 'Do not change the standing instruction. Handle a one-off request in this turn, or ask whether a lasting change is intended.'}
            current = context()
            if current is None:
                return missing_class
            row = existing(current)
            old = SummaryDelegation.parse(row['body']) if row else SummaryDelegation()
            if not valid and old.state != 'paused':
                return {'status': 'unchanged', 'instruction': 'No paused preference exists. Base preparation is already built in; do not create an enabling instruction.'}
            if required_material and required_material not in quote and required_material != old.required_material:
                return {'status': 'needs-information', 'question': '小结还需要核对什么材料？'}
            value = SummaryDelegation('paused' if action == 'pause' else 'enabled',
                style or old.style, old.required_material if required_material is None else required_material)
            if row and value.body() == row['body']:
                return {'status': 'unchanged', 'instruction': 'The confirmed standing instruction already matches; do not create a duplicate.'}
            command = (ReviseDocument(row['document_id'], current.class_id, current.term_id, row['version'],
                        TITLE, value.body(), 'markdown') if row else
                       CreateDocument(uuid4(), current.class_id, current.term_id, TITLE, value.body(), 'markdown'))
            return capture.propose(command)
        return await execute('prepare_summary_delegation', prepare)

    async def read_summary_delegation() -> dict:
        """Read applicable summary rules: built-in defaults or explicit teacher preferences, never conversation guesses. Base preparation needs no delegation. Does not save anything."""
        def read():
            current = context()
            if current is None:
                return missing_class
            row = existing(current)
            if row is None:
                from class_os.domain.builtin_class_work import identifiers, INSTRUCTION, VERSION
                program_id, _ = identifiers(credentials[3], current.class_id, current.term_id)
                if capture.summary_context is None:
                    capture.summary_context = {'kind': 'builtin', 'program_id': program_id, 'document_id': None,
                        'version': VERSION, 'class_id': current.class_id, 'term_id': current.term_id,
                        'body': INSTRUCTION, 'style': 'standard', 'required_material': '', 'initiative': False, 'resuming': False}
                return {'status': 'builtin', 'style': 'standard', 'required_material': '',
                        'instruction': INSTRUCTION, 'version': VERSION}
            value = SummaryDelegation.parse(row['body'])
            if value.state == 'enabled' and capture.summary_context is None:
                capture.summary_context = {**row, 'class_id': current.class_id, 'term_id': current.term_id,
                    'style': value.style, 'required_material': value.required_material, 'initiative': False,
                    'resuming': bool(capture.user_messages and '小结' in capture.user_messages[-1]
                        and re.search(r'继续|重试|再试', capture.user_messages[-1]))}
            return {'status': value.state, 'style': value.style, 'required_material': value.required_material,
                    'instruction': row['body'], 'version': row['version']}
        return await execute('read_summary_delegation', read)

    return prepare_summary_delegation, read_summary_delegation
