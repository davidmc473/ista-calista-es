"""HTML del portal → modelos. Funciones puras (ver contracts/calista-http.md)."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
import io
import re
import unicodedata

from .exceptions import ParseError
from .html import Element, normalize_space
from .models import Bill, Meter, MeterKind, Reading

_SHORT_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
_LOCATION_RE = re.compile(r"^\(?\s*(?:(\d+)\s*-\s*)?(.*?)\s*\)?$")
_TRAILING_NUMBER_RE = re.compile(r"(?<=[^\W\d_])(\d+)$")


# --- utilidades ---------------------------------------------------------------------


def fold(text: str) -> str:
    """Minúsculas sin tildes ni espacios sobrantes (para comparar textos del portal)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return normalize_space("".join(c for c in decomposed if not unicodedata.combining(c))).lower()


def parse_number(text: str) -> float | None:
    """``2.236`` / ``17,11`` / ``1.234,56`` → float. Vacío → ``None``."""
    value = text.strip().replace(" ", "")
    if not value:
        return None
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return float(value)
    except ValueError as err:
        raise ParseError(f"Número no válido: {text!r}") from err


def parse_date(text: str) -> date:
    """``dd/mm/aaaa`` o ``dd/mm/aa`` (con hora opcional) → date."""
    value = text.strip().split(" ")[0]
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"Fecha no válida: {text!r}")


def normalize_unit(unit: str) -> str:
    key = fold(unit).replace(" ", "")
    return {
        "m3": "m³",
        "m³": "m³",
        "kwh": "kWh",
        "mwh": "MWh",
        "gj": "GJ",
        "un": "UN",
        "ud": "UN",
        "uds": "UN",
        "unidades": "UN",
        "l": "L",
        "litros": "L",
    }.get(key, unit.strip())


def classify(type_label: str, unit: str = "") -> MeterKind:
    """Tipo de equipo (o de recibo) a partir del texto del portal y la unidad."""
    text = fold(type_label)
    unit_key = normalize_unit(unit)
    if any(word in text for word in ("coste", "repartidor", "distribuidor")):
        return MeterKind.HEAT_COST_ALLOCATOR
    if "agua" in text:
        if "caliente" in text or "acs" in text.split():
            return MeterKind.HOT_WATER
        if "fria" in text:
            return MeterKind.COLD_WATER
        return MeterKind.WATER
    if any(w in text for w in ("energia", "calor", "frigor", "termic", "calefac")):
        return MeterKind.HEAT
    if unit_key in ("kWh", "MWh", "GJ"):
        return MeterKind.HEAT
    if unit_key == "UN":
        return MeterKind.HEAT_COST_ALLOCATOR
    if unit_key in ("m³", "L"):
        return MeterKind.WATER
    return MeterKind.UNKNOWN


def parse_location(text: str) -> tuple[str | None, str | None]:
    """``(1-Dormitorio1)`` → (``"1"``, ``"Dormitorio 1"``)."""
    match = _LOCATION_RE.match(normalize_space(text))
    if not match:
        return None, None
    code, name = match.group(1), match.group(2).strip()
    if not name:
        return code, None
    return code, _TRAILING_NUMBER_RE.sub(r" \1", name)


# --- login (Keycloak) ---------------------------------------------------------------


def login_form_action(doc: Element) -> str | None:
    form = doc.find("form", id="loginForm")
    return form.get("action") if form is not None else None


def login_error_message(doc: Element) -> str | None:
    """Mensaje de error que muestra Keycloak junto al formulario (si lo hay)."""
    area = doc.find(id="content-area")
    if area is not None and area.text():
        return area.text()
    dialog = doc.find("dialog")
    return dialog.text() if dialog is not None and dialog.text() else None


def is_portal_page(doc: Element) -> bool:
    """Página autenticada de GesCon (tiene el enlace «Salir»)."""
    return any("logOutAbonado" in (a.get("href") or "") for a in doc.iter("a"))


# --- cabecera y abonados ------------------------------------------------------------


@dataclass(slots=True)
class Header:
    number: str | None = None
    email: str | None = None
    #: dirección del abonado activo (primera opción del selector)
    address: str | None = None
    #: (idAbonado, dirección) de cada abonado de la cuenta
    dwellings: list[tuple[str, str]] = field(default_factory=list)

    @property
    def active_id(self) -> str | None:
        """``idAbonado`` del abonado activo (por su dirección); ``None`` si es ambiguo."""
        matches = [i for i, label in self.dwellings if label == self.address]
        if len(matches) == 1:
            return matches[0]
        if len(self.dwellings) == 1:
            return self.dwellings[0][0]
        return None


def parse_header(doc: Element) -> Header:
    header = Header()
    for table in doc.find_all("table", class_="no-borde"):
        for row in table.rows():
            cells = row.cells()
            for label_cell, value_cell in zip(cells[::2], cells[1::2], strict=False):
                label, value = fold(label_cell.text()), value_cell.text() or None
                # «Nº abonado» (NFKD: «no abonado»), «N° abonado», «Num. abonado»…
                if label.startswith("n") and label.endswith(" abonado"):
                    header.number = value
                elif label in ("email", "e-mail", "correo electronico"):
                    header.email = value
    select = next(
        (s for s in doc.find_all("select") if "cambiaAbonado" in (s.get("onchange") or "")),
        None,
    )
    if select is not None:
        for index, option in enumerate(select.iter("option")):
            value, label = (option.get("value") or "").strip(), option.text()
            if index == 0 and not value:
                header.address = label or None
            elif value:
                header.dwellings.append((value, label))
    return header


# --- lecturas radio -----------------------------------------------------------------


@dataclass(slots=True)
class RadioPage:
    header: Header
    id_finca: str | None
    window_start: date | None
    window_end: date | None
    meters: list[Meter]


def _input_value(doc: Element, name: str) -> str | None:
    element = doc.find("input", name=name)
    value = element.get("value") if element is not None else None
    return value.strip() if value else None


def _header_index(names: list[str], *candidates: str) -> int | None:
    for index, name in enumerate(names):
        if name in candidates:
            return index
    return None


def parse_radio_page(doc: Element) -> RadioPage:
    """«Mis lecturas Radio» (``preCargaLecturasRadio`` / ``listadoLecturasRadio``)."""
    if not is_portal_page(doc) or doc.find("form", name="fincasForm") is None:
        raise ParseError("La página de lecturas radio no tiene el formato esperado")
    start = _input_value(doc, "fechaDesdeRadio")
    end = _input_value(doc, "fechaHastaRadio")
    page = RadioPage(
        header=parse_header(doc),
        id_finca=_input_value(doc, "idFinca"),
        window_start=parse_date(start) if start else None,
        window_end=parse_date(end) if end else None,
        meters=[],
    )
    table = doc.find("table", id="listaLecturasRadio")
    if table is None:
        return page  # sin equipos de radio
    rows = table.rows()
    if not rows:
        return page
    names = [fold(cell.text()) for cell in rows[0].cells()]
    serial_col = _header_index(names, "n serie", "no serie", "nº serie", "n° serie", "numero serie")
    if serial_col is None:
        serial_col = next((i for i, n in enumerate(names) if "serie" in n), None)
    type_col = _header_index(names, "tipo", "tipo equipo")
    unit_col = next((i for i, n in enumerate(names) if n.startswith("unidad")), None)
    loc_col = next((i for i, n in enumerate(names) if n.startswith("ubicaci")), None)
    if serial_col is None or type_col is None:
        raise ParseError("Tabla de lecturas radio sin columnas de serie/tipo")
    date_cols = [
        (index, parse_date(rows[0].cells()[index].text()))
        for index, name in enumerate(names)
        if _SHORT_DATE_RE.match(name)
    ]
    for row in rows[1:]:
        cells = row.cells()
        if len(cells) <= max(serial_col, type_col):
            continue
        serial = cells[serial_col].text()
        if not serial:
            continue
        type_label = cells[type_col].text()
        unit = cells[unit_col].text() if unit_col is not None and unit_col < len(cells) else ""
        code, location = (
            parse_location(cells[loc_col].text())
            if loc_col is not None and loc_col < len(cells)
            else (None, None)
        )
        readings = [
            Reading(day, value)
            for index, day in date_cols
            if index < len(cells) and (value := parse_number(cells[index].text())) is not None
        ]
        readings.sort(key=lambda r: r.date)
        page.meters.append(
            Meter(
                serial=serial,
                kind=classify(type_label, unit),
                type_label=type_label,
                unit=normalize_unit(unit) if unit else "",
                location=location,
                location_code=code,
                readings=readings,
            )
        )
    return page


# --- recibos ------------------------------------------------------------------------


def parse_bills(doc: Element) -> list[Bill]:
    """Primera página de «Mis recibos» (tabla con columna *Importe*)."""
    for table in doc.find_all("table"):
        rows = table.rows()
        if not rows:
            continue
        names = [fold(cell.text()) for cell in rows[0].cells()]
        amount_col = _header_index(names, "importe")
        date_col = next((i for i, n in enumerate(names) if n.startswith("fecha")), None)
        type_col = next((i for i, n in enumerate(names) if n.startswith("tipo")), None)
        if amount_col is None or date_col is None or type_col is None:
            continue
        bills: list[Bill] = []
        for row in rows[1:]:
            cells = row.cells()
            if len(cells) <= max(amount_col, date_col, type_col):
                continue
            date_text, amount_text = cells[date_col].text(), cells[amount_col].text()
            if not date_text or not amount_text:
                continue
            amount = parse_number(amount_text)
            if amount is None:
                continue
            type_label = cells[type_col].text()
            bills.append(
                Bill(
                    date=parse_date(date_text),
                    type_label=type_label,
                    kind=classify(type_label),
                    amount=amount,
                )
            )
        return bills
    return []


def parse_bills_csv(text: str) -> list[Bill]:
    """Exportación CSV de «Mis recibos» (todo el historial; spec 004).

    ``Fecha lectura,Tipo equipo,Importe`` con el importe entre comillas y coma decimal.
    """
    rows = [row for row in csv.reader(io.StringIO(text.lstrip("\ufeff"))) if any(row)]
    if not rows:
        return []
    names = [fold(name) for name in rows[0]]
    date_col = next((i for i, n in enumerate(names) if n.startswith("fecha")), None)
    type_col = next((i for i, n in enumerate(names) if n.startswith("tipo")), None)
    amount_col = _header_index(names, "importe")
    if date_col is None or type_col is None or amount_col is None:
        raise ParseError("El CSV de recibos no tiene las columnas esperadas")
    bills: list[Bill] = []
    for row in rows[1:]:
        if len(row) <= max(date_col, type_col, amount_col):
            continue
        amount = parse_number(row[amount_col])
        if amount is None or not row[date_col].strip():
            continue
        type_label = normalize_space(row[type_col])
        bills.append(
            Bill(
                date=parse_date(row[date_col]),
                type_label=type_label,
                kind=classify(type_label),
                amount=amount,
            )
        )
    return bills
