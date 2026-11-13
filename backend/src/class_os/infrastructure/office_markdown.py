"""CommonMark presentation only; never HTML execution, resource I/O or facts."""
from dataclasses import dataclass, replace
from textwrap import wrap

from class_os.application.document_artifacts import ArtifactTooLarge


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


@dataclass(frozen=True)
class Block:
    runs: tuple[Run, ...]
    heading: int = 0
    depth: int = 0
    quoted: bool = False

    @property
    def text(self):
        return ''.join(run.text for run in self.runs)


def inline(tokens):
    result, links = [], []
    bold = italic = 0
    for token in tokens:
        if token.type in ('strong_open', 'strong_close'):
            bold += token.nesting
        elif token.type in ('em_open', 'em_close'):
            italic += token.nesting
        elif token.type == 'link_open':
            links.append((len(result), token.attrGet('href') or ''))
        elif token.type == 'link_close':
            start, destination = links.pop()
            label = ''.join(run.text for run in result[start:])
            if destination and label != destination:
                result.append(Run(' (' + destination + ')'))
        elif token.type == 'image':
            # Text-only export retains the alt text and source as text. Never
            # dereference a URL, local path or attachment through the renderer.
            result.append(Run('[' + (token.content or '图片') + '] (' + (token.attrGet('src') or '') + ')'))
        elif token.type in ('softbreak', 'hardbreak'):
            result.append(Run('\n'))
        elif token.content:
            result.append(Run(token.content, bool(bold), bool(italic), token.type == 'code_inline'))
    return tuple(result)


def line_runs(runs):
    current = []
    for span in runs:
        for index, value in enumerate(span.text.split('\n')):
            if index:
                yield tuple(current)
                current = []
            if value:
                current.append(replace(span, text=value))
    yield tuple(current)


def blocks(body, format):
    if format == 'plain-text':
        result = [Block((Run(line),)) for line in body.split('\n')]
    else:
        from markdown_it import MarkdownIt
        tokens = MarkdownIt('commonmark', {'html': False, 'linkify': False, 'maxNesting': 20}).parse(body)
        if len(tokens) > 30000:
            raise ArtifactTooLarge()
        result, lists = [], []
        heading = quoted = 0
        def emit(runs, level=0):
            if lists and lists[-1]['pending']:
                item = lists[-1]
                marker = str(item['next']) + '.' if item['ordered'] else '•'
                runs = (Run(marker + ' '),) + runs
                item['next'] += 1
                item['pending'] = False
            result.extend(Block(line, level, len(lists), bool(quoted)) for line in line_runs(runs))
        for token in tokens:
            if token.type == 'heading_open':
                heading = int(token.tag[1:])
            elif token.type == 'heading_close':
                heading = 0
            elif token.type in ('bullet_list_open', 'ordered_list_open'):
                if lists and lists[-1]['pending']:
                    emit(())
                lists.append({'ordered': token.type == 'ordered_list_open', 'next': int(token.attrGet('start') or 1), 'pending': False})
            elif token.type in ('bullet_list_close', 'ordered_list_close'):
                lists.pop()
            elif token.type == 'list_item_open':
                lists[-1]['pending'] = True
            elif token.type == 'list_item_close' and lists[-1]['pending']:
                # A teacher's blank placeholder still consumes its list number.
                emit(())
            elif token.type == 'blockquote_open':
                quoted += 1
            elif token.type == 'blockquote_close':
                quoted -= 1
            elif token.type == 'inline':
                emit(inline(token.children or ()), heading)
            elif token.type in ('fence', 'code_block'):
                emit((Run(token.content.removesuffix('\n'), code=True),))
            elif token.type == 'hr':
                result.append(Block((Run('—'),)))
    if len(result) > 10000:
        raise ArtifactTooLarge()
    return result


def wrapped_runs(block, width=32):
    """Wrap visible text while carrying styles and consuming every character."""
    index = offset = 0

    def consume(length, keep=True):
        nonlocal index, offset
        result = []
        while length:
            run = block.runs[index]
            size = min(length, len(run.text) - offset)
            if keep and size:
                result.append(replace(run, text=run.text[offset:offset + size]))
            offset += size
            length -= size
            if offset == len(run.text):
                index += 1
                offset = 0
        return tuple(result)

    values = block.text.split('\n')
    for line_index, value in enumerate(values):
        parts = wrap(value, width=width, expand_tabs=False, replace_whitespace=False,
                     drop_whitespace=False, break_on_hyphens=False) or ['']
        # Preserve data even for whitespace edge cases in textwrap.
        if ''.join(parts) != value:
            parts = [value[start:start + width] for start in range(0, len(value), width)] or ['']
        for part in parts:
            yield consume(len(part))
        if line_index + 1 < len(values):
            consume(1, keep=False)
