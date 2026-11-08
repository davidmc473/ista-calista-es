"""Tests del parser del portal y de los modelos (T020, T022, FR-011)."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.ista_calista_es.api import (
    CalistaData,
    Dwelling,
    Meter,
    MeterKind,
    ParseError,
    Reading,
    consumption_delta,
)
from custom_components.ista_calista_es.api.html import parse_html
from custom_components.ista_calista_es.api.parser import (
    classify,
    is_portal_page,
    login_error_message,
    login_form_action,
    normalize_unit,
    parse_bills,
    parse_bills_csv,
    parse_date,
    parse_header,
    parse_location,
    parse_number,
    parse_radio_page,
)
from custom_components.ista_calista_es.api.redact import REDACTED, anonymized_data

from .conftest import fixture_bytes, fixture_doc

ADDRESS = "CL-Calle FALSA 1 2 B MADRID (Madrid)"
DWELLING_ID = "AbonadoTest0000000000A"


# --- utilidades ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [("2.236", 2.236), ("0.0", 0.0), (" 19.875\n", 19.875), ("17,11", 17.11),
     ("1.234,56", 1234.56), ("", None), ("  ", None)],
)  # fmt: skip
def test_parse_number(text: str, expected: float | None) -> None:
    assert parse_number(text) == expected


def test_parse_number_invalid() -> None:
    with pytest.raises(ParseError):
        parse_number("n/d")


def test_parse_date() -> None:
    assert parse_date("05/11/26") == date(2026, 11, 5)
    assert parse_date("30/05/2026") == date(2026, 5, 30)
    assert parse_date("05/11/2026 00:00:00") == date(2026, 11, 5)
    with pytest.raises(ParseError):
        parse_date("2026-11-05")


@pytest.mark.parametrize(
    ("label", "unit", "kind"),
    [
        ("Radio Distribuidor de Costes de Calefacción", "UN", MeterKind.HEAT_COST_ALLOCATOR),
        ("Repartidor de costes", "", MeterKind.HEAT_COST_ALLOCATOR),
        ("Radio agua caliente", "m3", MeterKind.HOT_WATER),
        ("Agua caliente", "", MeterKind.HOT_WATER),
        ("Radio Agua Fría", "m3", MeterKind.COLD_WATER),
        ("Contador de agua", "m3", MeterKind.WATER),
        ("Contador de energía", "kWh", MeterKind.HEAT),
        ("Calefacción", "", MeterKind.HEAT),
        ("Equipo raro", "MWh", MeterKind.HEAT),
        ("Equipo raro", "UN", MeterKind.HEAT_COST_ALLOCATOR),
        ("Equipo raro", "m3", MeterKind.WATER),
        ("Equipo raro", "", MeterKind.UNKNOWN),
    ],
)
def test_classify(label: str, unit: str, kind: MeterKind) -> None:
    assert classify(label, unit) is kind


def test_normalize_unit() -> None:
    assert normalize_unit("m3") == "m³"
    assert normalize_unit("KWH") == "kWh"
    assert normalize_unit(" UN ") == "UN"
    assert normalize_unit("raro") == "raro"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("(1-Dormitorio1)", ("1", "Dormitorio 1")),
        (" (4-Baño1) ", ("4", "Baño 1")),
        ("(12-Salón)", ("12", "Salón")),
        ("Cocina", (None, "Cocina")),
        ("", (None, None)),
    ],
)
def test_parse_location(text: str, expected: tuple) -> None:
    assert parse_location(text) == expected


def test_consumption_delta() -> None:
    hca, water = MeterKind.HEAT_COST_ALLOCATOR, MeterKind.HOT_WATER
    assert consumption_delta(water, None, 5.0) == 0.0
    assert consumption_delta(water, 1.0, 1.5) == 0.5
    # reinicio de temporada del repartidor: cuenta el valor nuevo
    assert consumption_delta(hca, 46.4, 0.3) == 0.3
    # bajada en el agua: corrección, no consumo
    assert consumption_delta(water, 19.9, 19.8) == 0.0


# --- Keycloak -----------------------------------------------------------------------


def test_login_pages() -> None:
    login = fixture_doc("keycloak_login.html")
    assert login_form_action(login) == "__ACTION__"
    assert login_error_message(login) is None
    assert not is_portal_page(login)

    error = fixture_doc("keycloak_login_error.html")
    assert login_form_action(error) == "__ACTION__"
    assert "contraseña son incorrectas" in (login_error_message(error) or "")


# --- cabecera -----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["landing.html", "radio.html", "bills.html"])
def test_header(name: str) -> None:
    header = parse_header(fixture_doc(name))
    assert header.number == "12345678"
    assert header.email == "abonado@example.com"
    assert header.address == ADDRESS
    assert header.dwellings == [(DWELLING_ID, ADDRESS)]
    assert header.active_id == DWELLING_ID


def test_header_several_dwellings() -> None:
    doc = parse_html(
        '<select name="idAbonado" onchange="javascript:cambiaAbonado(this);">'
        '<option value="" disabled selected>Calle B</option>'
        '<option value="" disabled>-----</option>'
        '<option value="A1">Calle A</option><option value="B2">Calle B</option></select>'
    )
    header = parse_header(doc)
    assert header.dwellings == [("A1", "Calle A"), ("B2", "Calle B")]
    assert header.active_id == "B2"


# --- lecturas radio -----------------------------------------------------------------


def test_radio_default_window() -> None:
    page = parse_radio_page(fixture_doc("radio.html"))
    assert page.id_finca == "1000"
    assert (page.window_start, page.window_end) == (date(2026, 10, 24), date(2026, 11, 8))
    assert [m.serial for m in page.meters] == [f"90000000{i}" for i in range(1, 10)]
    hca = page.meters[0]
    assert hca.kind is MeterKind.HEAT_COST_ALLOCATOR
    assert hca.type_label == "Radio Distribuidor de Costes de Calefacción"
    assert (hca.unit, hca.location, hca.location_code) == ("UN", "Dormitorio 1", "1")
    assert len(hca.readings) == 12
    assert hca.readings[0] == Reading(date(2026, 10, 25), 2.236)
    assert hca.last_reading == Reading(date(2026, 11, 5), 2.236)

    hall = page.meters[7]
    assert hall.location == "Hall 1"
    consumption = hall.last_consumption()
    assert consumption is not None
    assert (consumption.start, consumption.end, consumption.value) == (
        date(2026, 11, 4),
        date(2026, 11, 5),
        0.314,
    )

    water = page.meters[8]
    assert water.kind is MeterKind.HOT_WATER
    assert (water.unit, water.location) == ("m³", None)
    assert water.last_reading == Reading(date(2026, 11, 5), 19.875)
    assert water.last_consumption().value == pytest.approx(0.039)


def test_radio_range_with_gaps_and_season_reset() -> None:
    page = parse_radio_page(fixture_doc("radio_range.html"))
    assert (page.window_start, page.window_end) == (date(2026, 9, 2), date(2026, 11, 8))
    water = page.meters[8]
    # días vacíos ignorados: 64 columnas con fecha, 57 con dato
    assert len(water.readings) == 57
    assert all(a.date < b.date for a, b in zip(water.readings, water.readings[1:], strict=False))
    bath = page.meters[3]
    assert bath.location == "Baño 1"
    resets = [
        (b.date, a.value, b.value)
        for a, b in zip(bath.readings, bath.readings[1:], strict=False)
        if b.value < a.value
    ]
    assert resets == [(date(2026, 10, 1), 46.407, 0.0)]


def test_radio_page_without_meters() -> None:
    page = parse_radio_page(
        parse_html(
            '<a href="/GesCon/GestionOficinaVirtual.do?metodo=logOutAbonado">Salir</a>'
            '<form name="fincasForm"><input name="idFinca" value="7"></form>'
            "<p>No hay lecturas</p>"
        )
    )
    assert page.meters == []
    assert page.id_finca == "7"


def test_radio_page_unexpected() -> None:
    with pytest.raises(ParseError):
        parse_radio_page(fixture_doc("keycloak_login.html"))


# --- recibos ------------------------------------------------------------------------


def test_bills() -> None:
    bills = parse_bills(fixture_doc("landing.html"))
    assert len(bills) == 15
    assert bills[0].date == date(2026, 5, 30)
    assert bills[0].kind is MeterKind.HOT_WATER
    latest = Dwelling(None, None, None, bills=bills).latest_bills()
    assert latest[MeterKind.HEAT_COST_ALLOCATOR].amount == 17.11
    assert latest[MeterKind.HEAT_COST_ALLOCATOR].date == date(2026, 5, 31)
    assert latest[MeterKind.HOT_WATER].amount == 0.0
    assert parse_bills(fixture_doc("radio.html")) == []


def test_bills_csv() -> None:
    from custom_components.ista_calista_es.api.html import decode_html

    bills = parse_bills_csv(decode_html(fixture_bytes("bills.csv")))
    assert len(bills) == 34
    assert bills[0].date == date(2026, 5, 31)
    assert bills[0].type_label == "Radio Distribuidor de Costes de Calefacción"
    assert bills[0].kind is MeterKind.HEAT_COST_ALLOCATOR
    assert bills[0].amount == 17.11
    assert bills[-1].date == date(2023, 3, 31)
    heating = [b for b in bills if b.kind is MeterKind.HEAT_COST_ALLOCATOR]
    assert round(sum(b.amount for b in heating), 2) == 337.83
    assert {b.kind for b in bills} == {MeterKind.HEAT_COST_ALLOCATOR, MeterKind.HOT_WATER}


def test_bills_csv_edge_cases() -> None:
    # BOM, CRLF, filas vacías e importe con punto de miles
    text = '﻿Fecha lectura,Tipo equipo,Importe\r\n01/02/2026,Agua fría,"1.234,50"\r\n\r\n,,\r\n'
    bills = parse_bills_csv(text)
    assert len(bills) == 1
    assert (bills[0].date, bills[0].kind, bills[0].amount) == (
        date(2026, 2, 1),
        MeterKind.COLD_WATER,
        1234.5,
    )
    assert parse_bills_csv("") == []
    with pytest.raises(ParseError):
        parse_bills_csv("a,b\n1,2")


# --- modelos y anonimización --------------------------------------------------------


def test_dwelling_key_and_lookup() -> None:
    meter = Meter("1", MeterKind.HOT_WATER, "Agua", "m³")
    data = CalistaData(dwellings=[Dwelling("X", "123", "Calle", meters=[meter])])
    assert data.dwellings[0].key == "123"
    assert Dwelling("X", None, None).key == "X"
    assert data.find_meter("1") == (data.dwellings[0], meter)
    assert data.find_meter("2") is None
    assert data.find_dwelling("123") is data.dwellings[0]
    assert meter.last_consumption() is None


def test_anonymized_data_has_no_personal_data() -> None:
    page = parse_radio_page(fixture_doc("radio.html"))
    data = CalistaData(
        dwellings=[
            Dwelling(DWELLING_ID, "12345678", ADDRESS, page.meters,
                     parse_bills(fixture_doc("landing.html")))
        ],
        window_start=page.window_start,
        window_end=page.window_end,
    )  # fmt: skip
    dump = repr(anonymized_data(data))
    for secret in ("12345678", ADDRESS, DWELLING_ID, "900000001"):
        assert secret not in dump
    assert REDACTED in dump
    assert "Dormitorio 1" in dump  # las ubicaciones sí se mantienen
