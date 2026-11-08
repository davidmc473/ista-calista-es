"""Tests del árbol HTML y de la decodificación (T021, FR-007, FR-008)."""

from __future__ import annotations

from custom_components.ista_calista_es.api.html import decode_html, parse_html


def test_decode_mixed_encoding() -> None:
    raw = "Calefacción ".encode() + "¿Cuánto pagar?".encode("cp1252")
    assert decode_html(raw) == "Calefacción ¿Cuánto pagar?"


def test_implicit_cell_and_row_closing() -> None:
    doc = parse_html("<table id=t><tr><th>A<th>B<tr><td>1<td>2</table><p>fuera</p>")
    table = doc.find("table", id="t")
    assert table is not None
    rows = table.rows()
    assert [[c.text() for c in r.cells()] for r in rows] == [["A", "B"], ["1", "2"]]
    assert doc.find("p").text() == "fuera"


def test_nested_tables_and_stray_end_tags() -> None:
    doc = parse_html(
        "<table id=outer><tr><td>x<table id=inner><tr><td>y</td></tr></table></td></tr>"
        "</table></br><div class='a b'>z</div>"
    )
    outer = doc.find("table", id="outer")
    assert len(outer.rows()) == 1
    # como textContent del navegador: los nodos de texto se concatenan sin separador
    assert outer.rows()[0].cells()[0].text() == "xy"
    assert outer.find("table", id="inner").rows()[0].cells()[0].text() == "y"
    assert doc.find(class_="b").text() == "z"


def test_options_and_attributes_unescaped() -> None:
    doc = parse_html(
        '<select name=s><option value="">Uno<option value="a&amp;b" disabled>Dos</select>'
        '<form id="f" action="https://x/y?a=1&amp;b=2"></form>'
    )
    options = doc.find("select").find_all("option")
    assert [(o.get("value"), o.text()) for o in options] == [("", "Uno"), ("a&b", "Dos")]
    assert doc.find("form", id="f").get("action") == "https://x/y?a=1&b=2"


def test_script_content_is_not_markup() -> None:
    doc = parse_html("<script>if (a < b) { x = '<td>' }</script><td>real</td>")
    assert [td.text() for td in doc.find_all("td")] == ["real"]
