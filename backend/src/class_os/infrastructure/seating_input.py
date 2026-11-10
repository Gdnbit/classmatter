"""Bounded explicit seating dimensions, not inferred numbers or authorization."""
import re

_DIGITS = '一二三四五六七八九'
_NUMBERS = {str(n): n for n in range(1, 21)} | {word: n for n, word in enumerate(_DIGITS, 1)}
_NUMBERS |= {'两': 2, '十': 10, '二十': 20} | {'十' + word: n + 10 for n, word in enumerate(_DIGITS, 1)}
_NUMBER = r'[0-9一二三四五六七八九十两]+'
_PAIR = re.compile(rf'(?<![0-9.\-+一二三四五六七八九十两])({_NUMBER})\s*(?:排|行|rows?)\s*[,，、]?\s*(?:每[排行]|各|and)?\s*({_NUMBER})\s*(?:列|座|columns?)(?![0-9.])', re.I)
_PRODUCT = re.compile(rf'(?<![0-9.\-+一二三四五六七八九十两])({_NUMBER})\s*[x×*]\s*({_NUMBER})(?![0-9.一二三四五六七八九十两])', re.I)


def explicit_layout_dimensions(messages):
    for message in reversed(messages):
        matches = list(_PAIR.finditer(message)) + list(_PRODUCT.finditer(message))
        pairs = [match.groups() for match in matches
                 if not re.search(r'(?:第|到|在|放|坐|至)\s*$', message[:match.start()])]
        if pairs:
            decoded = {(_NUMBERS.get(row), _NUMBERS.get(column)) for row, column in pairs}
            return next(iter(decoded)) if len(decoded) == 1 and all(value is not None for value in next(iter(decoded))) else None
    return None


def unbacked_seating_promise(text, user_text, user_messages=()):
    # A narrow false-success guard for a dimension-bearing action reply. It
    # does not classify ordinary chat, prove arbitrary prose, or execute tools.
    if re.search(r'翻译|仅讨论|不执行|不要|不用|不必|先不|暂不|如果|假设|举例|引用|原话|这句话|translate|quote|do not|don\x27t', user_text, re.I):
        return False
    explicit = explicit_layout_dimensions((user_text,)) is not None
    followup = (explicit_layout_dimensions(user_messages) is not None
                and (re.search(r'预览|创建|建立|继续|准备|生成|安排|应用', user_text)
                     or re.fullmatch(r'(?:是|是的|好|好的|可以|确认|yes|ok)[，。！!\s]*', user_text, re.I)))
    if not explicit and not followup:
        return False
    return bool(re.search(r'座位|seating|seat layout', text, re.I)
                and re.search(r'(?:已[\s\S]{0,16}(?:准备|生成|建好)|(?:prepared|ready))[\s\S]{0,160}(?:确认|应用|confirm|apply)', text, re.I))
