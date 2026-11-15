"""One built-in preparation task, not a generic planner or a human mandate."""
from uuid import UUID, uuid5

KIND = 'class-work-summary'
VERSION = 1
TITLE = '班级工作小结'
REQUEST = '根据系统内置的班级小结任务，核对已有普通事实和任务，准备可核对的小结草稿；没有新材料保持安静。不要求老师先委托，不预设班会主题或其他缺项。'
INSTRUCTION = '根据已登记的普通事实和任务，按已完成、进行中、待核对整理小结草稿。只准备，不自动保存或发送；没有额外必填材料。'


def identifiers(workspace_id, class_id, term_id):
    if any(type(value) is not UUID for value in (workspace_id, class_id, term_id)):
        raise ValueError('Exact built-in work scope required')
    program = uuid5(workspace_id, f'{KIND}:{class_id}:{term_id}:v{VERSION}')
    return program, uuid5(program, 'conversation')
