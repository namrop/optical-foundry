"""Divider kinds are profile-owned, typed, and usable outside Codex 0."""
from pathlib import Path
import shutil

import pytest
import yaml

from engine.divider_kinds import render_kind
from engine.manifest_compiler import CompositeBundleCompiler
from engine.profile_package import load_package, ProfilePackageError


@pytest.fixture
def probe(tmp_path, monkeypatch):
    repo = tmp_path / 'profiles'
    package = repo / 'garden-notebook'
    package.mkdir(parents=True)
    (package / 'card.tex').write_text(r'\thispagestyle{empty}' + '\n' + r'\begin{center}[[slot:heading]]\end{center}' + '\n' + r'\clearpage' + '\n')
    spec = {'schema_version': 'profile_package_v1', 'id': 'garden-notebook', 'extends': 'document-spine',
            'divider_kinds': {'seed-card': {'slots': {'heading': {'type': 'text'},
                                                   'count': {'type': 'integer', 'minimum': 1, 'maximum': 3, 'default': 1},
                                                   'picture': {'type': 'asset', 'default': ''}},
                                          'pages': [{'latex': 'card.tex', 'repeat': 'count'}]}}}
    (package / 'profile.yaml').write_text(yaml.safe_dump(spec))
    monkeypatch.setenv('OF_PROFILE_PATH', str(repo))
    source = tmp_path / 'chapter.md'
    source.write_text('---\nuid: chapter\n---\n\nA chapter in the garden.\n')
    divider = {'uid': 'seeds', 'before_source_uid': 'chapter', 'kind': 'seed-card', 'slots': {'heading': 'Seeds & soil', 'count': 2}}
    manifest = {'kind': 'composite_bundle', 'schema_version': 'bundle_manifest_v1', 'bundle_id': 'garden',
                'profile': 'garden-notebook', 'presentation': {'title': 'Garden'},
                'render': {'include_toc': False, 'suppress_source_wrapper_headings': True},
                'sources': [{'uid': 'chapter', 'path': str(source), 'role': 'primary_anchor', 'order': 1}],
                'section_dividers': [divider]}
    return package, spec, manifest


def test_non_codex_kind_compiles_and_records_slots(probe):
    package, spec, manifest = probe
    compiler = CompositeBundleCompiler()
    assert compiler.validate(manifest) == []
    plan = compiler.compile(manifest)
    text = plan.render_source.read_text()
    assert text.count(r'Seeds \& soil') == 2
    record = plan.boundary_assertions['section_dividers'][0]
    assert record['kind'] == 'seed-card'
    assert record['slots'] == {'heading': 'Seeds & soil', 'count': 2, 'picture': ''}
    assert record['package'] == str(package)


@pytest.mark.skipif(shutil.which('xelatex') is None, reason='needs xelatex')
@pytest.mark.parametrize('framed', [True, False])
def test_non_codex_kind_renders_a_real_pdf(probe, tmp_path, framed):
    from renderers.pandoc_renderer import PandocRenderer
    import fitz
    package, spec, manifest = probe
    if not framed:
        (package / 'start.tex').write_text(r"\clearpage" + '\n')
        kind = spec['divider_kinds']['seed-card']
        kind['framed'] = False
        kind['pages'].insert(0, {'latex': 'start.tex', 'mark': True})
        (package / 'profile.yaml').write_text(yaml.safe_dump(spec))
    evidence = PandocRenderer().render(CompositeBundleCompiler().compile(manifest), output_dir=str(tmp_path / 'render'))
    assert evidence['status'] == 'ok', evidence.get('error')
    with fitz.open(evidence['output']['pdf_path']) as doc:
        text = '\n'.join(page.get_text() for page in doc)
    assert text.count('Seeds & soil') == 2
    assert 'A chapter in the garden.' in text


@pytest.mark.parametrize('slots,message', [
    ({'heading': 'Hello', 'extra': 'bad'}, 'unknown divider slots'),
    ({}, 'missing divider slot'),
    ({'heading': r'\input{secrets}'}, 'unsafe text'),
    ({'heading': '{bad}'}, 'unsafe text'),
    ({'heading': 'Hello', 'picture': '../bad.png'}, 'unsafe relative'),
    ({'heading': 'Hello', 'picture': '/etc/bad.png'}, 'unsafe relative'),
    ({'heading': 'Hello', 'picture': 'https://example.com/a.png'}, 'unsafe relative'),
    ({'heading': 'Hello', 'picture': 'a.png\\input{bad}'}, 'unsafe relative'),
    ({'heading': 'Hello', 'picture': 'a.tex'}, 'unsafe relative'),
    ({'heading': 'Hello', 'count': True}, 'integer outside bounds'),
    ({'heading': 'Hello', 'count': 4}, 'integer outside bounds'),
    ({'heading': 'Hello', 'count': 0}, 'integer outside bounds'),
])
def test_invalid_manifest_slots_fail_before_render(probe, slots, message):
    manifest = probe[2]
    manifest['section_dividers'][0]['slots'] = slots
    errors = CompositeBundleCompiler().validate(manifest)
    assert any(message in error for error in errors), errors
    with pytest.raises(ValueError, match='manifest validation failed'):
        CompositeBundleCompiler().compile(manifest)


def test_unknown_kind_and_slots_without_kind(probe):
    manifest = probe[2]
    manifest['section_dividers'][0]['kind'] = 'not-a-kind'
    assert any('unknown divider kind' in e for e in CompositeBundleCompiler().validate(manifest))
    del manifest['section_dividers'][0]['kind']
    assert any('slots require kind' in e for e in CompositeBundleCompiler().validate(manifest))


def test_source_and_kind_are_exclusive(probe):
    manifest = probe[2]
    manifest['section_dividers'][0]['source'] = {'path': manifest['sources'][0]['path']}
    assert any('mutually exclusive' in e for e in CompositeBundleCompiler().validate(manifest))


@pytest.mark.parametrize('change', ['unknown-key', 'missing-template', 'outside-template', 'undeclared-token', 'glued-token', 'unknown-slot-type', 'bad-repeat'])
def test_invalid_package_declarations_fail_when_loaded(probe, change):
    package, spec, manifest = probe
    kind = spec['divider_kinds']['seed-card']
    if change == 'unknown-key':
        kind['surprise'] = True
    elif change == 'missing-template':
        kind['pages'][0]['latex'] = 'missing.tex'
    elif change == 'outside-template':
        kind['pages'][0]['latex'] = '../outside.tex'
    elif change == 'undeclared-token':
        (package / 'card.tex').write_text('[[slot:undeclared]]')
    elif change == 'glued-token':  # \else[[slot:x]] fills to \elseX: a different command
        (package / 'card.tex').write_text(r'\ifx\a\b\else[[slot:heading]]\fi')
    elif change == 'unknown-slot-type':
        kind['slots']['heading']['type'] = 'latex'
    else:
        kind['pages'][0]['repeat'] = 'heading'
    (package / 'profile.yaml').write_text(yaml.safe_dump(spec))
    with pytest.raises(ProfilePackageError):
        load_package(package / 'profile.yaml')


def test_markdown_slot_is_bounded_to_its_resource_root(probe, tmp_path):
    package, spec, manifest = probe
    kind = spec['divider_kinds']['seed-card']
    kind['slots']['verse'] = {'type': 'markdown'}
    kind['pages'] = [{'markdown': 'verse'}]
    (package / 'profile.yaml').write_text(yaml.safe_dump(spec))
    root = tmp_path / 'resources'
    root.mkdir()
    (root / 'poem.md').write_text('---\nuid: poem\n---\n\n| One seed\n| One garden\n')
    divider = {'kind': 'seed-card', 'slots': {'heading': 'unused', 'verse': 'poem.md'}}
    text = '\n'.join(render_kind('garden-notebook', divider, [root])[0])
    assert '| One seed' in text and 'uid: poem' not in text
    outside = tmp_path / 'outside.md'
    outside.write_text('outside')
    (root / 'escape.md').symlink_to(outside)
    divider['slots']['verse'] = 'escape.md'
    with pytest.raises(ValueError, match='not found inside resource roots'):
        render_kind('garden-notebook', divider, [root])
