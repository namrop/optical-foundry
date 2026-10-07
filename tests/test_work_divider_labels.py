"""Divider kinds can occupy frontmatter as well as body pages."""
import json

import fitz
import pytest

from engine.work_render import _divider_folios, VolumeError
from engine.work_refs import harvest


def test_work_harvest_preserves_a_frontmatter_divider_label(tmp_path):
    pdf = tmp_path / 'volume.pdf'
    with fitz.open() as doc:
        for _ in range(3):
            doc.new_page()
        doc.set_page_labels([{'startpage': 0, 'style': 'r'}, {'startpage': 2, 'style': 'D'}])
        doc.save(pdf)
    (tmp_path / 'volume.divider_pages.json').write_text(json.dumps({'divider_page_map': {'front': 1, 'body': 3}}))
    manifest = {'section_dividers': [{'uid': 'front', 'title': 'Threshold'}, {'uid': 'body', 'title': 'Body'}]}
    rows = _divider_folios(tmp_path, 'volume', pdf, manifest)
    assert [(row['uid'], row['folio']) for row in rows] == [('front', 'i'), ('body', 1)]
    assert harvest('one', pdf, rows) == {'one:divider:front': 'i', 'one:divider:body': '1'}


def test_work_harvest_still_rejects_a_divider_without_a_page_label(tmp_path):
    pdf = tmp_path / 'volume.pdf'
    with fitz.open() as doc:
        doc.new_page()
        doc.save(pdf)
    (tmp_path / 'volume.divider_pages.json').write_text(json.dumps({'divider_page_map': {'front': 1}}))
    with pytest.raises(VolumeError, match='no page label'):
        _divider_folios(tmp_path, 'volume', pdf, {'section_dividers': [{'uid': 'front'}]})
