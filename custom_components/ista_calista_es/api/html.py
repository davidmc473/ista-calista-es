"""Árbol HTML mínimo sobre ``html.parser`` de la librería estándar (constitución IV).

Las páginas del portal son tablas *displaytag* con HTML algo descuidado (``</br>``,
celdas sin cerrar…). Este árbol aplica los cierres implícitos habituales de los
navegadores en tablas, listas y ``<option>``, que es todo lo que hace falta aquí.
"""

from __future__ import annotations

import codecs
from collections.abc import Iterator
from html.parser import HTMLParser
import re

_VOID = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr",
    }
)  # fmt: skip
_TABLE_SCOPE = ("table", "thead", "tbody", "tfoot")
_WS_RE = re.compile(r"\s+")


def _cp1252_fallback(err: UnicodeError) -> tuple[str, int]:
    assert isinstance(err, UnicodeDecodeError)
    bad = err.object[err.start : err.end]
    return bytes(bad).decode("cp1252", errors="replace"), err.end


codecs.register_error("ista_cp1252_fallback", _cp1252_fallback)


def decode_html(raw: bytes) -> str:
    """UTF-8 con respaldo cp1252 por fragmento (el portal mezcla codificaciones)."""
    return raw.decode("utf-8", errors="ista_cp1252_fallback")


def normalize_space(text: str) -> str:
    return _WS_RE.sub(" ", text.replace("\xa0", " ")).strip()


class Element:
    """Nodo del árbol: etiqueta, atributos e hijos (elementos o texto)."""

    __slots__ = ("attrs", "children", "parent", "tag")

    def __init__(self, tag: str, attrs: dict[str, str], parent: Element | None) -> None:
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children: list[Element | str] = []

    def __repr__(self) -> str:
        return f"<{self.tag} {self.attrs}>"

    def get(self, name: str, default: str | None = None) -> str | None:
        return self.attrs.get(name, default)

    @property
    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    def iter(self, tag: str | None = None) -> Iterator[Element]:
        """Descendientes en orden de documento (sin incluir el propio nodo)."""
        for child in self.children:
            if isinstance(child, Element):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.iter(tag)

    def find_all(
        self, tag: str | None = None, *, class_: str | None = None, **attrs: str
    ) -> list[Element]:
        return [
            el
            for el in self.iter(tag)
            if (class_ is None or class_ in el.classes)
            and all(el.attrs.get(name) == value for name, value in attrs.items())
        ]

    def find(
        self, tag: str | None = None, *, class_: str | None = None, **attrs: str
    ) -> Element | None:
        for el in self.iter(tag):
            if (class_ is None or class_ in el.classes) and all(
                el.attrs.get(name) == value for name, value in attrs.items()
            ):
                return el
        return None

    def raw_text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            parts.append(child if isinstance(child, str) else child.raw_text())
        return "".join(parts)

    def text(self) -> str:
        """Texto de todos los descendientes con los espacios normalizados."""
        return normalize_space(self.raw_text())

    def rows(self) -> list[Element]:
        """Filas ``<tr>`` de una tabla (sin entrar en tablas anidadas)."""
        return [tr for tr in self.iter("tr") if tr.closest("table") is self]

    def cells(self) -> list[Element]:
        """Celdas ``<td>``/``<th>`` directas de una fila."""
        return [c for c in self.children if isinstance(c, Element) and c.tag in ("td", "th")]

    def closest(self, tag: str) -> Element | None:
        node = self.parent
        while node is not None and node.tag != tag:
            node = node.parent
        return node


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#document", {}, None)
        self._stack: list[Element] = [self.root]

    def _close_until(self, tags: tuple[str, ...], scope: tuple[str, ...]) -> None:
        """Cierra el elemento abierto más cercano de ``tags`` sin salir de ``scope``."""
        for index in range(len(self._stack) - 1, 0, -1):
            tag = self._stack[index].tag
            if tag in tags:
                del self._stack[index:]
                return
            if tag in scope:
                return

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("td", "th"):
            self._close_until(("td", "th"), ("tr", *_TABLE_SCOPE))
        elif tag == "tr":
            self._close_until(("tr",), _TABLE_SCOPE)
        elif tag in ("thead", "tbody", "tfoot"):
            self._close_until(("thead", "tbody", "tfoot"), ("table",))
        elif tag == "option":
            self._close_until(("option",), ("select",))
        elif tag == "li":
            self._close_until(("li",), ("ul", "ol"))
        parent = self._stack[-1]
        element = Element(tag, {k: v or "" for k, v in attrs}, parent)
        parent.children.append(element)
        if tag not in _VOID:
            self._stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent = self._stack[-1]
        parent.children.append(Element(tag, {k: v or "" for k, v in attrs}, parent))

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)


def parse_html(html: str) -> Element:
    """Devuelve la raíz (``#document``) del árbol."""
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root
