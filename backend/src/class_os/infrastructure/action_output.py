"""Narrow false-preview checks; never infer a command or grant authority."""
import re

from .seating_input import unbacked_seating_promise

_META = re.compile(r'翻译|仅讨论|不执行|不要|不用|不必|先不|暂不|如果|假设|举例|引用|原话|这句话|translate|quote|do not|don\x27t', re.I)
_ACTION = re.compile(r'创建|建立|新建|修改|改为|改名|更正|录入|记录|安排|交换|调换|添加|更新|编辑|生成|追加|放在|放到|移到|等待|结束|完成|取消|create|rename|update|edit|record|assign|swap', re.I)
_DOMAIN = re.compile(r'班[级名]|学期|学生|任务|跟进|文档|小结|考试|月考|周测|期中|期末|测验|成绩|分数|座位|名单|class|term|student|task|document|exam|score|seat', re.I)
_FOLLOWUP = re.compile(r'^(?:是|是的|好|好的|可以|确认|生成预览|继续|yes|ok)[，。！!\s]*$', re.I)
_DETAIL = re.compile(r'^(?:满分|科目|考试名称|名字|名称|姓名|班名|学期|原因|标题|正文)[:：\s]*\S|^\d+(?:\.\d+)?[。！!\s]*$')
_READY = re.compile(r'(?:已[\s\S]{0,24}(?:准备|生成|整理|做好|就绪|创建|建立|修改|更新|录入|记录|完成|结束|取消|安排|交换)|(?:方案|预览|草稿|文档|座位表|任务)准备好了|prepared|ready)[\s\S]{0,160}(?:确认|应用|提交|保存|核对|预览|confirm|apply|review|preview)', re.I)
_WRITE = re.compile(r'^(?:我)?(?:已|已经)(?:为[你您])?(?:成功)?(?:创建|建立|保存|修改|更新|录入|记录|完成|结束|取消|安排|交换|添加)(?![的过])', re.I)
_PRIOR = re.compile(r'上次|之前|已有|上一|原有|待确认|上方|先前|previous|existing', re.I)


def unbacked_action_promise(text, user_text, user_messages=(), *, attempted=False, pending=False):
    # Quoting, planning and hypothetical discussion must remain normal chat.
    # Withholding commit is the normal preview flow, not a refusal to prepare.
    intent_text = re.sub(r'(?:不要|不用|不必|先不|暂不)(?:自动)?(?:保存|提交|落库)|(?:do not|don\x27t)\s+(?:save|submit)', '', user_text, flags=re.I)
    if _META.search(intent_text):
        return False
    if pending and _PRIOR.search(user_text) and _PRIOR.search(text) and not _ACTION.search(user_text):
        return False  # Only a freshly verified, actually displayed earlier card.
    action = bool(_ACTION.search(user_text) or re.search(r'预览|preview', user_text, re.I)) or bool((_FOLLOWUP.fullmatch(user_text) or _DETAIL.search(user_text)) and any(_ACTION.search(message) for message in user_messages[:-1]))
    if not attempted and not action:
        return unbacked_seating_promise(text, intent_text, user_messages)
    if not attempted and not (_DOMAIN.search(text) or any(_DOMAIN.search(message) for message in user_messages)):
        return False  # A joke/poem response is not a business candidate.
    return bool(_READY.search(text) or _WRITE.search(text))
