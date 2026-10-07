"""Profile-owned divider page sequences, with typed manifest slots.

Templates are trusted package LaTeX. Slot values are not LaTeX: text is escaped,
paths are relative resources, and integers are bounded by the package declaration.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

TOKEN = re.compile(r"\[\[slot:([a-z][a-z0-9_]*)\]\]")
NAME = re.compile(r"[a-z][a-z0-9_-]*\Z")
SLOT_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")


def _relative(value: Any, extensions: set[str]) -> bool:
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        return False
    if any(c in value for c in '\\{}%#$`') or '://' in value:
        return False
    p = Path(value)
    return not p.is_absolute() and '..' not in p.parts and p.suffix.lower() in extensions


def validate_kinds(kinds: Any, directory: Path) -> None:
    if not isinstance(kinds, dict):
        raise ValueError('divider_kinds must be a mapping')
    for name, kind in kinds.items():
        if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(kind, dict):
            raise ValueError('divider kind must have a simple name and mapping')
        if set(kind) - {'slots', 'pages', 'framed'}:
            raise ValueError(f'divider kind {name}: unknown keys')
        if not isinstance(kind.get('framed', True), bool):
            raise ValueError(f'divider kind {name}: framed must be boolean')
        slots = kind.get('slots', {})
        if not isinstance(slots, dict):
            raise ValueError(f'divider kind {name}: slots must be a mapping')
        for slot, spec in slots.items():
            if not isinstance(slot, str) or not SLOT_NAME.fullmatch(slot) or not isinstance(spec, dict):
                raise ValueError(f'divider kind {name}: invalid slot declaration')
            if set(spec) - {'type', 'default', 'minimum', 'maximum'} or spec.get('type') not in {'text', 'asset', 'markdown', 'integer'}:
                raise ValueError(f'divider kind {name}: invalid slot {slot}')
            for bound in ('minimum', 'maximum'):
                if bound in spec and (type(spec[bound]) is not int or spec['type'] != 'integer'):
                    raise ValueError(f'divider kind {name}: invalid {bound} for {slot}')
            if 'minimum' in spec and 'maximum' in spec and spec['minimum'] > spec['maximum']:
                raise ValueError(f'divider kind {name}: reversed bounds for {slot}')
            if 'default' in spec:
                _value(slot, spec, spec['default'])
        pages = kind.get('pages')
        if not isinstance(pages, list) or not pages:
            raise ValueError(f'divider kind {name}: pages must be a nonempty sequence')
        for page in pages:
            if not isinstance(page, dict) or set(page) - {'latex', 'markdown', 'when', 'unless', 'repeat', 'offset', 'mark'}:
                raise ValueError(f'divider kind {name}: invalid page')
            if ('latex' in page) == ('markdown' in page):
                raise ValueError(f'divider kind {name}: page must name latex or markdown')
            if 'latex' in page:
                rel = page['latex']
                if not _relative(rel, {'.tex'}):
                    raise ValueError(f'divider kind {name}: unsafe template path')
                path = (directory / rel).resolve()
                if not path.is_relative_to(directory.resolve()) or not path.is_file():
                    raise ValueError(f'divider kind {name}: template is missing or outside package')
                template_text = path.read_text()
                missing = set(TOKEN.findall(template_text)) - set(slots)
                if missing:
                    raise ValueError(f'divider kind {name}: undeclared template slots {sorted(missing)}')
                # A slot written straight after a control word (\else[[slot:x]]) fuses with it
                # once filled (\elsePercival); TeX then reads a different command, silently.
                glued = re.findall(r'\\[A-Za-z@]+\[\[slot:([a-z][a-z0-9_]*)\]\]', template_text)
                if glued:
                    raise ValueError(f'divider kind {name}: slots {sorted(set(glued))} follow a control word '
                                     'directly; put a space or {} between them')
            elif page['markdown'] not in slots or slots[page['markdown']]['type'] != 'markdown':
                raise ValueError(f'divider kind {name}: markdown must name a markdown slot')
            for key in ('when', 'unless', 'repeat'):
                if key in page and page[key] not in slots:
                    raise ValueError(f'divider kind {name}: {key} names unknown slot')
            if 'mark' in page and (type(page['mark']) is not bool or kind.get('framed', True) or any(k in page for k in ('repeat', 'when', 'unless'))):
                raise ValueError(f'divider kind {name}: mark must be an unconditional unframed boundary')
            if 'repeat' in page and slots[page['repeat']]['type'] != 'integer':
                raise ValueError(f'divider kind {name}: repeat requires integer slot')
            if 'offset' in page and ('repeat' not in page or type(page['offset']) is not int):
                raise ValueError(f'divider kind {name}: invalid repeat offset')

        if not kind.get('framed', True) and sum(p.get('mark') is True for p in pages) != 1:
            raise ValueError(f'divider kind {name}: unframed sequence needs one page mark')


def _value(name: str, spec: dict, value: Any) -> Any:
    typ = spec['type']
    if typ == 'integer':
        if type(value) is not int or ('minimum' in spec and value < spec['minimum']) or ('maximum' in spec and value > spec['maximum']):
            raise ValueError(f'divider slot {name}: integer outside bounds')
    elif typ == 'text':
        if not isinstance(value, str) or any(c in value for c in '\\{}') or any(ord(c) < 32 and c != '\n' for c in value):
            raise ValueError(f'divider slot {name}: unsafe text (LaTeX is not allowed)')
    elif not (value == '' and spec.get('default') == ''):
        if not _relative(value, {'.md'} if typ == 'markdown' else {'.png', '.jpg', '.jpeg', '.pdf'}):
            raise ValueError(f'divider slot {name}: unsafe relative {typ} path')
    return value


def resolve_kind(profile: str, divider: dict, roots: list[Path]) -> tuple[Any, dict, dict]:
    from engine.profile_package import find_package
    package = find_package(profile)
    name = divider.get('kind')
    if package is None or name not in package.spec.get('divider_kinds', {}):
        raise ValueError(f'profile {profile}: unknown divider kind {name!r}')
    kind = package.spec['divider_kinds'][name]
    supplied = divider.get('slots', {})
    if not isinstance(supplied, dict):
        raise ValueError('divider slots must be a mapping')
    declarations = kind.get('slots', {})
    unknown = set(supplied) - set(declarations)
    if unknown:
        raise ValueError(f'unknown divider slots: {sorted(unknown)}')
    values = {}
    for name, spec in declarations.items():
        if name not in supplied and 'default' not in spec:
            raise ValueError(f'missing divider slot: {name}')
        value = _value(name, spec, supplied.get(name, spec.get('default')))
        values[name] = value
    return package, kind, values


def _resource(value: str, roots: list[Path]) -> Path:
    for root in roots:
        path = (root / value).resolve()
        if path.is_relative_to(root.resolve()) and path.is_file():
            return path
    raise ValueError(f'divider Markdown resource not found inside resource roots: {value}')


def render_kind(profile: str, divider: dict, roots: list[Path]) -> tuple[list[str], dict]:
    from engine.manifest_compiler import _latex_escape_text, _split_frontmatter_and_body
    package, kind, values = resolve_kind(profile, divider, roots)
    rendered = []
    for page in kind['pages']:
        if 'when' in page and not values[page['when']]:
            continue
        if 'unless' in page and values[page['unless']]:
            continue
        count = max(0, values[page['repeat']] + page.get('offset', 0)) if 'repeat' in page else 1
        if 'markdown' in page:
            value = values[page['markdown']]
            body = _split_frontmatter_and_body(_resource(value, roots).read_text())[1]
            chunk = body.strip()
        else:
            text = (package.directory / page['latex']).read_text().rstrip()
            def replace(match):
                name = match[1]
                value = values[name]
                return _latex_escape_text(value).replace('\n', r'\\ ') if kind['slots'][name]['type'] == 'text' else str(value)
            chunk = '```{=latex}\n' + TOKEN.sub(replace, text) + '\n```'
        rendered.extend([chunk, ''] * count)
        if page.get('mark') and divider.get('uid'):
            uid = divider['uid']
            # An unframed sequence owns its page breaks. Mark the first page
            # after its initialization step without adding a line to its body.
            marker = (r"\AddToShipoutPictureFG*{\AtPageLowerLeft{\begingroup\fontsize{1}{1}\selectfont\OFDivMarkerHideBegin"
                      + r"\hbox{\detokenize{[[OFDIV:" + uid + r"]]}}\OFDivMarkerHideEnd\endgroup}}")
            rendered.extend(['```{=latex}', marker, '```', ''])
    return rendered, {'kind': divider['kind'], 'slots': values, 'package': str(package.directory), 'pages': kind['pages']}
