"""One readable, versioned standing instruction; not a generic memory store."""
from dataclasses import dataclass
from hashlib import sha256
import re

import rfc8785


TITLE = '班级小结委托'
SUMMARY_TITLE = '班级工作小结'
INITIATIVE_REQUEST = '依据已确认的班级小结委托，检查最新材料；有值得整理的新内容才准备“班级工作小结”，没有新价值保持安静。'
STYLES = {'standard': '按已完成、进行中、待核对整理', 'three-points': '三条要点'}
STATES = {'enabled': '持续整理', 'paused': '暂停整理'}


@dataclass(frozen=True)
class SummaryDelegation:
    state: str = 'enabled'
    style: str = 'standard'
    required_material: str = ''

    def __post_init__(self):
        if self.state not in STATES or self.style not in STYLES:
            raise ValueError('Unsupported summary delegation')
        if (type(self.required_material) is not str or len(self.required_material) > 160
                or self.required_material != self.required_material.strip()
                or any(ord(char) < 32 for char in self.required_material)):
            raise ValueError('Invalid summary requirement')

    def body(self):
        return ('# 班级小结委托\n\n- 目的：持续根据已登记的普通事实与任务准备小结草稿\n'
                f'- 状态：{STATES[self.state]}\n- 格式：{STYLES[self.style]}\n'
                f'- 需要核对：{self.required_material or "无额外材料"}\n'
                '- 保存：核对后确认，不自动提交或对外发送')

    @classmethod
    def parse(cls, body):
        if type(body) is not str:
            raise ValueError('Invalid summary delegation')
        match = re.fullmatch(r'# 班级小结委托\n\n- 目的：持续根据已登记的普通事实与任务准备小结草稿\n'
            r'- 状态：(持续整理|暂停整理)\n- 格式：(按已完成、进行中、待核对整理|三条要点)\n'
            r'- 需要核对：([^\n]{1,160})\n- 保存：核对后确认，不自动提交或对外发送', body)
        if match is None:
            raise ValueError('Unknown standing instruction format')
        state, style, required = match.groups()
        return cls(next(key for key, value in STATES.items() if value == state),
                   next(key for key, value in STYLES.items() if value == style),
                   '' if required == '无额外材料' else required)


def source_basis(document, activity):
    """Hash stored content/versions only; wall-clock and overdue do not wake AI."""
    latest = {}
    for row in activity['records']:
        if row['kind'] == 'ordinary_fact' and (row['record_id'] not in latest
                or latest[row['record_id']]['version'] < row['version']):
            latest[row['record_id']] = row
    records = [{'id': str(row['record_id']), 'version': row['version'],
                'fact': row['fact_text'], 'observation': row['observation_text']}
               for row in sorted(latest.values(), key=lambda value: str(value['record_id']))]
    tasks = [{'id': str(row['task_id']), 'version': row['version'], 'title': row['title'],
              'status': row['status'], 'evidence': row.get('evidence', ''),
              'due_at': row['due_at'].isoformat() if row.get('due_at') is not None else None}
             for row in sorted(activity['tasks'], key=lambda value: str(value['task_id']))]
    if len(records) + len(tasks) > 100:
        raise ValueError('Summary source limit exceeded')
    payload = {'mandate': str(document['document_id']), 'version': document['version'],
               'context': document.get('context_basis', ''),
               'body': document['body'], 'records': records, 'tasks': tasks}
    return sha256(rfc8785.dumps(payload)).hexdigest(), bool(records or tasks)
