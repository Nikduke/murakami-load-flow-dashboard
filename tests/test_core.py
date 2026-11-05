from __future__ import annotations

import csv
from hashlib import sha256 as real_sha256
from io import BytesIO, StringIO
from pathlib import Path
from typing import Sequence
from zipfile import ZipFile

import pytest
from openpyxl import Workbook

from case_filters import case_labels, filter_cases, token_values, varying_token_positions
from channel_catalogue import (
    discover_loading_objects,
    discover_poc_objects,
    discover_power_factor_objects,
    discover_wtg_objects,
    resolve_channel,
)
import data_loader
from data_loader import InputFile, expand_inputs, parse_cases
from limit_analysis import wtg_pq_limit_violations, wtg_voltage_limit_violations
from mapping import load_mapping, token_heading
from plotting import (
    PlotOptions,
    build_equipment_loading_figures,
    build_poc_pq_figures,
    build_power_factor_figures,
    build_wtg_pq_figures,
    build_wtg_voltage_figures,
    distribute_bundles,
    _legend_column_layout,
    plotted_data_csv,
)


def _csv_bytes(
    case_name: str = "Study__V0__Filter__Q0__C0__Extra.csv",
    *,
    duplicate_q=False,
    extra_wtgs: Sequence[str] = (),
    value_overrides: dict[str, Sequence[float]] | None = None,
) -> bytes:
    headers = [
        ("Results", "Index"),
        ("WTG 1\\WTG 1", "Active Power in MW"),
        ("WTG 1\\WTG 1", "Reactive Power in Mvar"),
        ("WTG 1\\WTG 1", "Voltage, Magnitude in p.u."),
        ("WTG 1\\WTG 1", "Lower limit of reactive power in Mvar"),
        ("WTG 1\\WTG 1", "Upper limit of reactive power in Mvar"),
        ("POC1", "Active Power Interchange in MW"),
        ("POC1", "Reactive Power Interchange in Mvar"),
        ("POC2", "Active Power Interchange in MW"),
        ("POC2", "Reactive Power Interchange in Mvar"),
        ("Main TR_1", "Maximum Loading in %"),
        ("Exp_Cable_1", "Loading in %"),
        ("Exp_Cable_1", "Power Factor"),
        ("Exp_Cable_2", "Power Factor"),
        ("cable from wtg 25 to 0", ""),
        ("Real zero object", "Loading in %"),
    ]
    if duplicate_q:
        headers.insert(3, ("WTG 1\\WTG 1", "Reactive Power in Mvar"))
    for object_name in extra_wtgs:
        headers.extend(
            (object_name, description)
            for description in (
                "Active Power in MW",
                "Reactive Power in Mvar",
                "Voltage, Magnitude in p.u.",
                "Lower limit of reactive power in Mvar",
                "Upper limit of reactive power in Mvar",
            )
        )
    rows = [
        [str(index) for index in range(len(headers))],
        [str(index + 1) for index in range(len(headers))],
        [str(index + 2) for index in range(len(headers))],
    ]
    rows[0][0] = "0"
    rows[1][0] = "1"
    rows[2][0] = "2"
    # Replace the sample values by matching semantic channel columns.
    values = {
        "Index": (0, 1, 2),
        "Active Power in MW": (0, 1, 2),
        "Reactive Power in Mvar": (-2, -1, 0),
        "Voltage, Magnitude in p.u.": (.97, .98, .99),
        "Lower limit of reactive power in Mvar": (-4, -4, -4),
        "Upper limit of reactive power in Mvar": (4, 4, 4),
        "Active Power Interchange in MW": (-1, -2, -3),
        "Reactive Power Interchange in Mvar": (2, 4, 6),
        "Maximum Loading in %": (30, 40, 50),
        "Loading in %": (60, 70, 80),
        "Power Factor": (.9, .8, .7),
    }
    if value_overrides:
        values.update(value_overrides)
    body = []
    for sample in range(3):
        row = [""] * len(headers)
        row[0] = str(sample)
        for position, (object_name, description) in enumerate(headers[1:], start=1):
            if object_name == "Real zero object" or not description:
                value = 0
            else:
                value = values.get(description, (0, 0, 0))[sample]
            row[position] = str(value)
        body.append(row)
    text = StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow([value[0] for value in headers])
    writer.writerow([value[1] for value in headers])
    writer.writerows(body)
    return text.getvalue().encode("utf-8")


def _input(name: str = "Study__V0__Filter__Q0__C0__Extra.csv", content: bytes | None = None) -> InputFile:
    return InputFile(name, f"fixtures/{name}", content or _csv_bytes(name), origin="test")


def _case_options_header(figure):
    return next(
        annotation.text
        for annotation in figure.layout.annotations
        if annotation.text.startswith("Case options")
    )


def test_input_digest_is_computed_once_per_immutable_source(monkeypatch):
    calls = 0

    def counted_sha256(content: bytes):
        nonlocal calls
        calls += 1
        return real_sha256(content)

    monkeypatch.setattr(data_loader, "sha256", counted_sha256)
    source = InputFile("case.csv", "case.csv", b"source bytes")

    assert source.digest == source.digest
    assert calls == 1


def _mapping_bytes(rows: list[tuple[object, object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Headers"
    sheet.append(["Token N", "Header"])
    for row in rows:
        sheet.append(list(row))
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _find(case, object_name: str, description: str):
    return next(
        channel
        for channel in case.channels
        if channel.object_name == object_name and channel.metric_description == description
    )


def test_parser_excludes_unheaded_zeros_but_keeps_labelled_zero():
    parsed = parse_cases([_input()])
    assert len(parsed.cases) == 1
    case = parsed.cases[0]
    assert not any(channel.object_name == "cable from wtg 25 to 0" for channel in case.channels)
    zero = _find(case, "Real zero object", "Loading in %")
    assert zero.numeric_values == (0.0, 0.0, 0.0)
    assert any(issue.code == "blank_channel_headings" for issue in parsed.issues)


def test_zip_and_loose_csv_have_equivalent_parsed_channels():
    filename = "Study__V0__Filter__Q0__C0__Extra.csv"
    content = _csv_bytes(filename)
    archive = BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr(filename, content)
    loose = expand_inputs([InputFile(filename, filename, content, "test")])
    zipped = expand_inputs([InputFile("results.zip", "results.zip", archive.getvalue(), "test")])
    loose_case = parse_cases(loose.csv_files).cases[0]
    zip_case = parse_cases(zipped.csv_files).cases[0]
    assert loose_case.tokens == zip_case.tokens
    assert loose_case.sweep_index == zip_case.sweep_index
    assert [(c.object_name, c.metric_description, c.numeric_values) for c in loose_case.channels] == [
        (c.object_name, c.metric_description, c.numeric_values) for c in zip_case.channels
    ]


def test_duplicate_case_stems_are_excluded_with_an_error():
    first = _input()
    duplicate = InputFile(first.name, "another/" + first.name, first.content, "test")
    parsed = parse_cases([first, duplicate])
    assert parsed.cases == ()
    assert any(issue.code == "duplicate_case_id" for issue in parsed.issues)


def test_bad_csv_isolated_and_unsafe_zip_member_is_ignored():
    valid = _input()
    invalid = InputFile("broken.csv", "broken.csv", b"\xff", "test")
    parsed = parse_cases([valid, invalid])
    assert len(parsed.cases) == 1
    assert any(issue.code == "csv_encoding" for issue in parsed.issues)

    archive = BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("../outside.csv", valid.content)
        zip_file.writestr(valid.name, valid.content)
    expanded = expand_inputs([InputFile("unsafe.zip", "unsafe.zip", archive.getvalue(), "test")])
    assert [source.name for source in expanded.csv_files] == [valid.name]
    assert any(issue.code == "unsafe_zip_member" for issue in expanded.issues)


def test_cascading_token_options_and_sixth_position():
    names = [
        "A__V1__F1__Q1__C1__X.csv",
        "A__V1__F1__Q2__C1__Y.csv",
        "B__V2__F1__Q1__C2__X.csv",
    ]
    cases = parse_cases([_input(name) for name in names]).cases
    assert token_values(cases, 0) == ["A", "B"]
    assert token_values(cases, 1, [{"A"}]) == ["V1"]
    assert token_values(cases, 5, [{"A"}, {"V1"}, {"F1"}, {"Q1"}, {"C1"}]) == ["X"]
    assert len(filter_cases(cases, [{"A"}, {"V1"}, {"F1"}, {"Q1"}, {"C1"}, {"X"}])) == 1
    assert cases[0].tokens[-1] == "X"
    assert case_labels([cases[0]], []) == {
        cases[0].case_id: "A · V1 · F1 · Q1 · C1 · X"
    }


def test_mapping_changes_headings_only_and_reports_invalid_rows():
    source = InputFile("Mapping_Murakami.xlsx", "upload:/Mapping_Murakami.xlsx", _mapping_bytes([(1, "Study"), (6, "Variant"), (0, "Bad")]), "upload")
    result = load_mapping(source)
    assert result.headers == {1: "Study", 6: "Variant"}
    assert token_heading(6, result.headers) == "Variant"
    assert token_heading(2, result.headers) == "Case parameter 2"
    assert token_heading(7, result.headers) == "Case parameter 7"
    assert any(issue.code == "mapping_position" for issue in result.issues)


def test_mapping_duplicate_position_and_missing_sheet_are_actionable():
    duplicate = load_mapping(InputFile("Mapping.xlsx", "Mapping.xlsx", _mapping_bytes([(1, "One"), (1, "Two")]), "test"))
    assert any(issue.code == "mapping_duplicate_position" for issue in duplicate.issues)
    workbook = Workbook()
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    missing = load_mapping(InputFile("Mapping.xlsx", "Mapping.xlsx", output.getvalue(), "test"))
    assert any(issue.code == "mapping_sheet" for issue in missing.issues)
    empty = load_mapping(InputFile("Mapping.xlsx", "Mapping.xlsx", _mapping_bytes([(2, "  ")]), "test"))
    assert any(issue.code == "mapping_empty_heading" for issue in empty.issues)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Headers"
    sheet.append(["Token N", "Header", "Case values"])
    sheet.append([1, "Study", "A / B"])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    extra_column = load_mapping(InputFile("Mapping.xlsx", "Mapping.xlsx", output.getvalue(), "test"))
    assert any(issue.code == "mapping_columns" for issue in extra_column.issues)


def test_real_mapping_workbook_headers_when_example_is_available():
    path = Path(__file__).resolve().parents[2] / "Example_export" / "Mapping.xlsx"
    if not path.is_file():
        pytest.skip("Murakami example mapping workbook is not available in this checkout.")
    result = load_mapping(InputFile(path.name, str(path), path.read_bytes(), "test"))
    assert result.headers == {
        1: "Study configuration",
        2: "Initial voltage",
        3: "Filter configuration",
        4: "Reactive-power condition",
        5: "C condition",
    }
    assert result.issues == ()


def test_catalogue_discovery_excludes_cables_from_wtg_and_flags_duplicate_metrics():
    parsed = parse_cases([_input(content=_csv_bytes(duplicate_q=True))])
    case = parsed.cases[0]
    assert discover_wtg_objects([case]) == ["WTG 1\\WTG 1"]
    assert "cable from wtg 25 to 0" not in discover_wtg_objects([case])
    assert resolve_channel(case, "WTG 1\\WTG 1", "reactive_power").status == "ambiguous"
    assert "Exp_Cable_1" in discover_loading_objects([case])
    assert "POC1" in discover_poc_objects([case])
    assert "Exp_Cable_1" in discover_power_factor_objects([case])


def test_missing_and_conflicting_metrics_have_actionable_resolution_status():
    conflict_csv = _csv_bytes().decode("utf-8").replace("Active Power in MW", "Active Power in kW", 1).encode("utf-8")
    conflict_case = parse_cases([_input(content=conflict_csv)]).cases[0]
    assert resolve_channel(conflict_case, "WTG 1\\WTG 1", "active_power").status == "unit_conflict"

    missing_csv = _csv_bytes().decode("utf-8").replace("Reactive Power in Mvar", "Reactive output in Mvar", 1).encode("utf-8")
    missing_case = parse_cases([_input(content=missing_csv)]).cases[0]
    resolution = resolve_channel(missing_case, "WTG 1\\WTG 1", "reactive_power")
    assert resolution.status == "missing"
    result = build_wtg_pq_figures(
        [missing_case], ["WTG 1\\WTG 1"], {missing_case.case_id: "case-A"}, options=PlotOptions()
    )
    assert any("no channel" in issue.message for issue in result.issues)


def test_wtg_pq_limit_violations_use_same_sweep_point_and_include_only_breaches():
    overrides = {
        "Active Power in MW": (10, 20, 30),
        "Reactive Power in Mvar": (-4, 2, 5),
        "Lower limit of reactive power in Mvar": (-3, -1, -2),
        "Upper limit of reactive power in Mvar": (-2, 2, 4),
    }
    case = parse_cases([_input(content=_csv_bytes(value_overrides=overrides))]).cases[0]
    rows = wtg_pq_limit_violations([case], ["WTG 1\\WTG 1"], {case.case_id: "Case A"})

    assert len(rows) == 2
    by_limit = {row["Limit"]: row for row in rows}
    assert by_limit["Qmin"] == {
        "WTG": "WTG 1",
        "Case": "Case A",
        "Limit": "Qmin",
        "Violating points": 1,
        "P at worst point (MW)": 10.0,
        "Q (Mvar)": -4.0,
        "Limit (Mvar)": -3.0,
        "Excess (Mvar)": 1.0,
    }
    assert by_limit["Qmax"]["Violating points"] == 1
    assert by_limit["Qmax"]["P at worst point (MW)"] == 30
    assert by_limit["Qmax"]["Q (Mvar)"] == 5
    assert by_limit["Qmax"]["Limit (Mvar)"] == 4
    assert by_limit["Qmax"]["Excess (Mvar)"] == 1

    at_limits = {
        "Reactive Power in Mvar": (-3, 2, 4),
        "Lower limit of reactive power in Mvar": (-3, -1, -2),
        "Upper limit of reactive power in Mvar": (-2, 2, 4),
    }
    equal_case = parse_cases([_input(content=_csv_bytes(value_overrides=at_limits))]).cases[0]
    assert wtg_pq_limit_violations([equal_case], ["WTG 1\\WTG 1"], {}) == []


def test_wtg_voltage_limit_violations_use_manual_limits_and_exclude_equality():
    overrides = {
        "Active Power in MW": (10, 20, 30),
        "Voltage, Magnitude in p.u.": (.91, .92, 1.09),
    }
    case = parse_cases([_input(content=_csv_bytes(value_overrides=overrides))]).cases[0]
    rows = wtg_voltage_limit_violations(
        [case], ["WTG 1\\WTG 1"], {case.case_id: "Case A"}, .92, 1.08
    )

    assert len(rows) == 2
    by_limit = {row["Limit"]: row for row in rows}
    assert by_limit["Min voltage"]["Violating points"] == 1
    assert by_limit["Min voltage"]["P at worst point (MW)"] == 10
    assert by_limit["Min voltage"]["Voltage (p.u.)"] == .91
    assert by_limit["Min voltage"]["Limit (p.u.)"] == .92
    assert by_limit["Min voltage"]["Excess (p.u.)"] == pytest.approx(.01)
    assert by_limit["Max voltage"]["Violating points"] == 1
    assert by_limit["Max voltage"]["P at worst point (MW)"] == 30
    assert by_limit["Max voltage"]["Voltage (p.u.)"] == 1.09
    assert by_limit["Max voltage"]["Limit (p.u.)"] == 1.08
    assert by_limit["Max voltage"]["Excess (p.u.)"] == pytest.approx(.01)
    assert wtg_voltage_limit_violations([case], ["WTG 1\\WTG 1"], {}, .92, .92) == []


def test_plot_signs_and_capability_curves_are_numeric_and_grouped():
    case = parse_cases([_input()]).cases[0]
    labels = {case.case_id: "case-A"}
    options = PlotOptions(layout="1×2")

    pq = build_wtg_pq_figures([case], ["WTG 1\\WTG 1"], labels, options=options)
    assert pq.bundles[0].curves[0].x_values == (-2.0, -1.0, 0.0)
    assert pq.bundles[0].curves[0].y_values == (0.0, 1.0, 2.0)
    assert [curve.series_name for curve in pq.bundles[0].curves] == [
        "operating curve",
        "Qmin capability boundary",
        "Qmax capability boundary",
    ]
    assert len(pq.figures) == 1
    assert pq.figures[0].layout.title.text == "WTG P–Q · WTG 1"
    case_traces = [trace for trace in pq.figures[0].data if trace.legendgroup == case.case_id]
    assert [trace.showlegend for trace in case_traces] == [True, False, False]
    assert {trace.name for trace in case_traces} == {"Selected case"}
    assert [trace.name for trace in pq.figures[0].data if trace.showlegend] == ["Selected case"]
    assert {trace.legendgroup for trace in pq.figures[0].data} == {case.case_id}
    assert case_traces[0].line.color != "#555555"
    assert [trace.line.color for trace in case_traces[1:]] == ["#555555", "#555555"]
    assert [trace.line.width for trace in case_traces[1:]] == [1.4, 1.4]
    assert [trace.line.dash for trace in case_traces] == ["dash", "dash", "dash"]
    assert _case_options_header(pq.figures[0]).startswith("Case options: <b>")
    assert "(" not in _case_options_header(pq.figures[0])
    assert pq.figures[0].layout.legend.font.size == 12
    assert pq.figures[0].layout.legend.orientation == "h"
    assert pq.figures[0].layout.legend.entrywidthmode == "pixels"
    assert pq.figures[0].layout.legend.xref == "paper"
    assert pq.figures[0].layout.legend.x == 0
    assert pq.figures[0].layout.legend.tracegroupgap == 0
    assert pq.figures[0].layout.legend.y == pytest.approx(-78 / 352)
    assert pq.figures[0].layout.margin.b == 110
    assert "Case options: <b>%{meta[0]}</b>" in pq.figures[0].data[0].hovertemplate
    assert "Boundary: %{meta[2]}" in pq.figures[0].data[1].hovertemplate
    assert "Filename" not in pq.figures[0].data[0].hovertemplate

    split_cases = parse_cases(
        [_input("Study__V0__Filter__Q0__C0__Extra.csv"), _input("Study__V0__Filter__Q1__C0__Extra.csv")]
    ).cases
    split = build_wtg_pq_figures(
        split_cases,
        ["WTG 1\\WTG 1"],
        {item.case_id: item.case_id for item in split_cases},
        options=PlotOptions(layout="1×2"),
    )
    assert [figure.layout.title.text for figure in split.figures] == [
        "WTG P–Q · WTG 1 · Panel 1 of 2",
        "WTG P–Q · WTG 1 · Panel 2 of 2",
    ]

    voltage = build_wtg_voltage_figures([case], ["WTG 1\\WTG 1"], labels, options=options)
    assert voltage.bundles[0].curves[0].x_values == (0.0, 1.0, 2.0)
    assert voltage.bundles[0].curves[0].y_values == (.97, .98, .99)
    assert len(voltage.figures[0].layout.shapes) == 2
    voltage_reference_labels = [annotation.text for annotation in voltage.figures[0].layout.annotations]
    assert "Min = 0.92 p.u." in voltage_reference_labels
    assert "Max = 1.08 p.u." in voltage_reference_labels
    assert all(
        annotation.xshift == 48
        for annotation in voltage.figures[0].layout.annotations
        if annotation.text.startswith(("Min =", "Max ="))
    )

    loading = build_equipment_loading_figures([case], ["Main TR_1"], "POC1", labels, options=options)
    assert loading.bundles[0].curves[0].x_values == (1.0, 2.0, 3.0)
    assert loading.bundles[0].curves[0].y_values == (30.0, 40.0, 50.0)
    assert loading.figures[0].layout.shapes[0].y0 == 100.0
    assert loading.figures[0].layout.shapes[0].line.dash == "dash"
    assert loading.figures[0].layout.shapes[0].line.color == "#c33b35"
    peak_annotation = next(
        annotation for annotation in loading.figures[0].layout.annotations if "3.0 MW" in annotation.text
    )
    assert "50.0 %" in peak_annotation.text
    limited = build_equipment_loading_figures(
        [case], ["Main TR_1"], "POC1", labels, options=options, loading_reference=75.0
    )
    assert limited.figures[0].layout.shapes[0].y0 == 75.0

    poc = build_poc_pq_figures([case], ["POC1", "POC2"], labels, options=options)
    by_object = {bundle.element_name: bundle.curves[0] for bundle in poc.bundles}
    assert by_object["POC1"].x_values == (-2.0, -4.0, -6.0)
    assert by_object["POC1"].y_values == (1.0, 2.0, 3.0)
    assert by_object["POC2"].x_values == (-2.0, -4.0, -6.0)

    pf = build_power_factor_figures([case], ["Exp_Cable_1", "Exp_Cable_2"], labels, options=options)
    pf_values = {bundle.element_name: bundle.curves[0].y_values for bundle in pf.bundles}
    assert pf_values["Exp_Cable_1"] == (-.9, -.8, -.7)
    assert pf_values["Exp_Cable_2"] == (-.9, -.8, -.7)


def test_plot_legend_and_hover_use_compact_case_options():
    cases = parse_cases(
        [
            _input("No_Qlim_HTRT__00 Vini 1pu__Filter_Out__Qmax__Cmax.csv"),
            _input("No_Qlim_noHTRT__01 Vini 0.95pu__Filter_Out__Q0__Cnom.csv"),
        ]
    ).cases
    labels = case_labels(cases, varying_token_positions(cases))
    result = build_wtg_pq_figures(cases, ["WTG 1\\WTG 1"], labels, options=PlotOptions())
    case_ids = {case.case_id for case in cases}
    legend_traces = [
        trace for trace in result.figures[0].data if trace.showlegend and trace.legendgroup in case_ids
    ]

    assert [trace.name for trace in legend_traces] == [
        "HTRT · Vini 1pu · Qmax · Cmax",
        "noHTRT · Vini 0.95pu · Q0 · Cnom",
    ]
    assert [trace.meta[0] for trace in legend_traces] == [labels[case.case_id] for case in cases]
    assert result.figures[0].layout.margin.b == 110
    case_line_styles = {
        case_id: {trace.line.dash for trace in result.figures[0].data if trace.legendgroup == case_id}
        for case_id in case_ids
    }
    assert all(len(styles) == 1 for styles in case_line_styles.values())
    assert len({next(iter(styles)) for styles in case_line_styles.values()}) == len(case_ids)
    assert [trace.name for trace in result.figures[0].data if trace.showlegend] == [
        trace.name for trace in legend_traces
    ]
    assert _case_options_header(result.figures[0]) == "Case options: <b>Filter_Out</b>"
    assert all("Filename" not in trace.hovertemplate for trace in result.figures[0].data)

    single = build_wtg_pq_figures(
        [cases[0]], ["WTG 1\\WTG 1"], labels, options=PlotOptions()
    )
    single_trace = next(trace for trace in single.figures[0].data if trace.showlegend)
    assert single_trace.name == "Selected case"
    assert single_trace.meta[0] == labels[cases[0].case_id]
    assert _case_options_header(single.figures[0]).startswith("Case options: <b>")


def test_distribution_preserves_every_element_case_bundle_without_duplicates():
    cases = parse_cases([_input(f"Study__V0__Filter__Q{n}__C0__Extra.csv") for n in range(8)]).cases
    label_map = {case.case_id: f"case-{index}" for index, case in enumerate(cases)}
    built = build_wtg_pq_figures(cases, ["WTG 1\\WTG 1"], label_map, options=PlotOptions())
    panels = distribute_bundles(built.bundles, 4)
    assert [len(panel) for panel in panels] == [2, 2, 2, 2]
    expected = [(bundle.element_name, bundle.case.case_id) for bundle in built.bundles]
    actual = [(bundle.element_name, bundle.case.case_id) for panel in panels for bundle in panel]
    assert sorted(actual) == sorted(expected)
    assert len(actual) == len(set(actual))


def test_plot_trace_metadata_is_stored_once_and_dense_panels_use_webgl(monkeypatch):
    case = parse_cases([_input()]).cases[0]
    result = build_wtg_pq_figures([case], ["WTG 1\\WTG 1"], {case.case_id: "case-A"}, options=PlotOptions())
    trace = result.figures[0].data[0]
    assert trace.type == "scatter"
    assert trace.mode == "lines"
    assert trace.customdata is None
    assert trace.meta == ("case-A", "WTG 1\\WTG 1", "")
    assert "Case options: <b>%{meta[0]}</b>" in trace.hovertemplate
    assert "WTG 1\\WTG 1" not in trace.hovertemplate
    assert "Filename" not in trace.hovertemplate
    assert "Source" not in trace.hovertemplate
    assert "Transform" not in trace.hovertemplate
    assert "Case ID:" not in trace.hovertemplate
    assert "All filename tokens:" not in trace.hovertemplate

    monkeypatch.setattr("plotting.WEBGL_POINT_THRESHOLD", 0)
    dense = build_wtg_pq_figures([case], ["WTG 1\\WTG 1"], {case.case_id: "case-A"}, options=PlotOptions())
    assert dense.figures[0].data[0].type == "scattergl"


def test_synthetic_fourth_wtg_is_discovered_and_three_wtgs_split_across_panels():
    source = _input(content=_csv_bytes(extra_wtgs=("WTG 23\\WTG 23", "WTG 45\\WTG 45", "WTG 67\\WTG 67")))
    case = parse_cases([source]).cases[0]
    names = discover_wtg_objects([case])
    assert names == ["WTG 1\\WTG 1", "WTG 23\\WTG 23", "WTG 45\\WTG 45", "WTG 67\\WTG 67"]
    result = build_wtg_pq_figures(
        [case], names[:3], {case.case_id: "one-case"}, options=PlotOptions(layout="1×2")
    )
    assert [len(panel) for panel in result.panels] == [2, 1]
    assigned = [bundle.element_name for panel in result.panels for bundle in panel]
    assert sorted(assigned) == sorted(names[:3])
    assert len(assigned) == len(set(assigned))


def test_automatic_distribution_stays_balanced_when_panels_outnumber_elements():
    object_names = ("WTG 1\\WTG 1", "WTG 23\\WTG 23", "WTG 45\\WTG 45")
    cases = parse_cases(
        [
            _input(
                name,
                _csv_bytes(name, extra_wtgs=object_names[1:]),
            )
            for name in (
                f"Study__V0__Filter__Q{number}__C0__Extra.csv" for number in range(8)
            )
        ]
    ).cases
    labels = {case.case_id: case.case_id for case in cases}
    result = build_wtg_pq_figures(cases, object_names, labels, options=PlotOptions())

    panels = distribute_bundles(result.bundles, 4)

    assert [len(panel) for panel in panels] == [6, 6, 6, 6]
    actual = [(bundle.element_name, bundle.case.case_id) for panel in panels for bundle in panel]
    expected = [(bundle.element_name, bundle.case.case_id) for bundle in result.bundles]
    assert sorted(actual) == sorted(expected)
    assert len(actual) == len(set(actual))


def test_all_five_plot_builders_support_all_layouts_without_lost_bundles():
    cases = parse_cases([_input(f"Study__V0__Filter__Q{number}__C0__Extra.csv") for number in range(4)]).cases
    labels = {case.case_id: f"case-{index}" for index, case in enumerate(cases)}
    builders = (
        lambda options: build_wtg_pq_figures(cases, ["WTG 1\\WTG 1"], labels, options=options),
        lambda options: build_wtg_voltage_figures(cases, ["WTG 1\\WTG 1"], labels, options=options),
        lambda options: build_equipment_loading_figures(cases, ["Main TR_1", "Exp_Cable_1"], "POC1", labels, options=options),
        lambda options: build_poc_pq_figures(cases, ["POC1", "POC2"], labels, options=options),
        lambda options: build_power_factor_figures(cases, ["Exp_Cable_1", "Exp_Cable_2"], labels, options=options),
    )
    for builder in builders:
        for layout, expected_panels in (("1 plot", 1), ("1×2", 2), ("2×2", 4)):
            result = builder(PlotOptions(layout=layout))
            expected = [(bundle.element_name, bundle.case.case_id) for bundle in result.bundles]
            actual = [(bundle.element_name, bundle.case.case_id) for panel in result.panels for bundle in panel]
            assert len(result.figures) == expected_panels
            assert all(panel for panel in result.panels)
            assert sorted(actual) == sorted(expected)
            assert len(actual) == len(set(actual))
            assert all(_case_options_header(figure).startswith("Case options") for figure in result.figures)
            assert all(
                "Filename" not in trace.hovertemplate and "Source" not in trace.hovertemplate
                for figure in result.figures
                for trace in figure.data
            )

    multi_case_legend = build_wtg_pq_figures(
        cases, ["WTG 1\\WTG 1"], labels, options=PlotOptions()
    ).figures[0]
    assert multi_case_legend.layout.legend.orientation == "h"
    assert {trace.legend for trace in multi_case_legend.data if trace.showlegend} == {None}
    assert multi_case_legend.layout.legend.entrywidthmode == "pixels"
    assert multi_case_legend.layout.legend.entrywidth == pytest.approx((1066 - 110) / 4 - 45)
    assert multi_case_legend.layout.margin.b == 110
    assert multi_case_legend.layout.height == 700


def test_case_legend_column_count_uses_longest_label_and_panel_width():
    assert _legend_column_layout("Vini 0.95pu", 72, 1)[0] == 4
    assert _legend_column_layout("Vini 0.95pu", 72, 4)[0] == 2
    assert _legend_column_layout("Vini 0.95pu", 72, 4)[1] < _legend_column_layout("Vini 0.95pu", 72, 1)[1]
    assert _legend_column_layout("Vini 0.95pu", 72, 1)[1] == pytest.approx((1066 - 110) / 4 - 45)
    assert _legend_column_layout("Vini 0.95pu", 72, 4)[1] == pytest.approx((520 - 110) / 2 - 45)
    long_label = "A very long case label with several tokens"
    assert _legend_column_layout(long_label, 72, 1)[0] == 3
    assert _legend_column_layout(long_label, 72, 4)[0] == 1
    assert _legend_column_layout(long_label, 72, 1, panel_width=1800)[0] == 4
    assert _legend_column_layout(long_label, 72, 4, panel_width=750)[0] == 2
    assert _legend_column_layout(long_label, 72, 4, panel_width=620)[0] == 1


def test_real_case_labels_use_four_columns_full_width_and_two_in_2x2(murakami_cases):
    cases = [
        case
        for case in murakami_cases.cases
        if case.tokens[0] == "No_Qlim_HTRT" and case.tokens[2] == "Filter_Out"
    ]
    assert len(cases) == 36
    labels = case_labels(cases, varying_token_positions(cases))
    builders = (
        lambda options: build_wtg_pq_figures(cases, ["WTG 1\\WTG 1"], labels, options=options),
        lambda options: build_wtg_voltage_figures(cases, ["WTG 1\\WTG 1"], labels, options=options),
        lambda options: build_equipment_loading_figures(
            cases, ["Main TR_1"], "POC1", labels, options=options
        ),
        lambda options: build_poc_pq_figures(cases, ["POC1"], labels, options=options),
        lambda options: build_power_factor_figures(cases, ["Exp_Cable_1"], labels, options=options),
    )
    for builder in builders:
        for layout, panel_count, expected_columns, panel_width in (
            ("1 plot", 1, 4, 1800),
            ("2×2", 4, 2, 750),
        ):
            result = builder(PlotOptions(layout=layout, panel_width=panel_width))
            assert len(result.figures) == panel_count
            for figure in result.figures:
                panel_names = [trace.name for trace in figure.data if trace.showlegend]
                columns, entry_width = _legend_column_layout(
                    max(panel_names, key=len), len(panel_names), panel_count, panel_width
                )
                assert columns == expected_columns
                assert figure.layout.legend.entrywidth == pytest.approx(entry_width)


def test_plotted_csv_includes_axis_provenance_and_sign_transforms():
    case = parse_cases([_input()]).cases[0]
    result = build_poc_pq_figures([case], ["POC1"], {case.case_id: "case-A"}, options=PlotOptions())
    rows = list(csv.DictReader(StringIO(plotted_data_csv(result.bundles).decode("utf-8-sig"))))
    assert rows[1]["original_x_metric_description"] == "Reactive Power Interchange in Mvar"
    assert rows[1]["case_tokens"] == "Study | V0 | Filter | Q0 | C0 | Extra"
    assert rows[1]["original_metric_description"] == "Active Power Interchange in MW"
    assert rows[1]["x_transform"].startswith("−1")
    assert float(rows[1]["plotted_x_value"]) == -4.0
    assert float(rows[1]["plotted_y_value"]) == 2.0


@pytest.fixture(scope="module")
def murakami_cases():
    example_dir = Path(__file__).resolve().parents[2] / "Example_export"
    csv_paths = sorted(example_dir.glob("*.csv"))
    if not csv_paths:
        pytest.skip("Murakami Example_export CSV files are not available in this checkout.")
    sources = [InputFile(path.name, path.name, path.read_bytes(), "test") for path in csv_paths]
    return parse_cases(sources)


def test_real_murakami_regression_counts_and_token_cardinalities(murakami_cases):
    assert len(murakami_cases.cases) == 72
    token_count = max(len(case.tokens) for case in murakami_cases.cases)
    assert token_count == 5
    assert [len({case.tokens[i] for case in murakami_cases.cases}) for i in range(token_count)] == [2, 3, 1, 4, 3]
    assert all(len(case.sweep_index) == 151 for case in murakami_cases.cases)
    example_path = Path(__file__).resolve().parents[2] / "Example_export" / "No_Qlim_HTRT__00 Vini 1pu__Filter_Out__Qmax__Cmax.csv"
    with example_path.open(encoding="utf-8-sig", newline="") as handle:
        header_row = next(csv.reader(handle))
    assert len(header_row) == 317
    case = next(case for case in murakami_cases.cases if case.filename == example_path.name)
    assert len([issue for issue in murakami_cases.issues if issue.case_id == case.case_id and issue.code == "blank_channel_headings"]) == 1
    blank_issue = next(issue for issue in murakami_cases.issues if issue.case_id == case.case_id and issue.code == "blank_channel_headings")
    assert blank_issue.message.startswith("Excluded 22 column(s)")


def test_real_murakami_objects_columns_and_curve_values(murakami_cases):
    cases = murakami_cases.cases
    assert discover_wtg_objects(cases) == ["WTG 1\\WTG 1", "WTG 23\\WTG 23", "WTG 45\\WTG 45"]
    assert len(discover_loading_objects(cases)) == 64
    assert discover_poc_objects(cases) == ["POC1", "POC2"]
    assert {"Exp_Cable_1", "Exp_Cable_2"}.issubset(discover_power_factor_objects(cases))

    case = next(case for case in cases if case.filename == "No_Qlim_HTRT__00 Vini 1pu__Filter_Out__Qmax__Cmax.csv")
    wtg = "WTG 1\\WTG 1"
    assert _find(case, wtg, "Reactive Power in Mvar").column_position == 84
    assert _find(case, wtg, "Active Power in MW").column_position == 85
    assert _find(case, wtg, "Lower limit of reactive power in Mvar").column_position == 87
    assert _find(case, wtg, "Upper limit of reactive power in Mvar").column_position == 88
    assert _find(case, wtg, "Voltage, Magnitude in p.u.").column_position == 86
    labels = {case.case_id: "Qmax · Cmax"}
    options = PlotOptions()
    pq = build_wtg_pq_figures([case], [wtg], labels, options=options)
    assert pq.bundles[0].curves[0].x_values[1] == _find(case, wtg, "Reactive Power in Mvar").numeric_values[1]
    assert pq.bundles[0].curves[0].y_values[1] == _find(case, wtg, "Active Power in MW").numeric_values[1]
    assert pq.bundles[0].curves[1].x_values[1] == _find(case, wtg, "Lower limit of reactive power in Mvar").numeric_values[1]
    assert pq.bundles[0].curves[2].x_values[1] == _find(case, wtg, "Upper limit of reactive power in Mvar").numeric_values[1]
    assert pq.bundles[0].curves[0].x_values[1] == pytest.approx(-2.760408)
    assert pq.bundles[0].curves[0].y_values[1] == pytest.approx(0.103330)

    voltage = build_wtg_voltage_figures([case], [wtg], labels, options=options)
    assert voltage.bundles[0].curves[0].y_values[1] == pytest.approx(.976772)

    pq_violations = wtg_pq_limit_violations([case], [wtg], labels)
    assert len(pq_violations) == 1
    assert pq_violations[0]["Limit"] == "Qmax"
    assert pq_violations[0]["Violating points"] == 41
    assert pq_violations[0]["P at worst point (MW)"] == pytest.approx(14.983335)
    assert pq_violations[0]["Excess (Mvar)"] == pytest.approx(3.546701)

    voltage_violations = wtg_voltage_limit_violations([case], [wtg], labels, .92, 1.08)
    assert len(voltage_violations) == 1
    assert voltage_violations[0]["Limit"] == "Max voltage"
    assert voltage_violations[0]["Violating points"] == 9
    assert voltage_violations[0]["Voltage (p.u.)"] == pytest.approx(1.088737)
    assert voltage_violations[0]["Excess (p.u.)"] == pytest.approx(.008737)

    all_case_labels = case_labels(cases, varying_token_positions(cases))
    one_plot = build_wtg_pq_figures(cases, [wtg], all_case_labels, options=PlotOptions())
    assert {
        trace.legend for trace in one_plot.figures[0].data if trace.showlegend
    } == {None}
    split = build_wtg_pq_figures(
        cases, [wtg], all_case_labels, options=PlotOptions(layout="2×2")
    )
    assert all(
        {trace.legend for trace in figure.data if trace.showlegend} == {None}
        for figure in split.figures
    )

    twelve_cases = [
        item for item in cases
        if item.tokens[0] == "No_Qlim_HTRT"
        and item.tokens[2] == "Filter_Out"
        and item.tokens[4] == "Cmax"
    ]
    compact_split = build_wtg_pq_figures(
        twelve_cases,
        [wtg],
        case_labels(twelve_cases, varying_token_positions(twelve_cases)),
        options=PlotOptions(layout="2×2"),
    )
    assert len(twelve_cases) == 12
    assert all(figure.layout.margin.b == 122 for figure in compact_split.figures)
    assert all(figure.layout.height == 462 for figure in compact_split.figures)
    assert all(figure.layout.xaxis.title.standoff == 6 for figure in compact_split.figures)
    assert all(figure.layout.legend.y == pytest.approx(-78 / 282) for figure in compact_split.figures)
    assert all(figure.layout.legend.yref == "paper" for figure in compact_split.figures)
    assert all(figure.layout.annotations[0].y == pytest.approx(-46 / 282) for figure in compact_split.figures)
    assert all(figure.layout.annotations[0].yref == "paper" for figure in compact_split.figures)

    assert _find(case, "Main TR_1", "Maximum Loading in %").column_position == 65
    assert _find(case, "Exp_Cable_1", "Loading in %").column_position == 1
    assert _find(case, "POC1", "Active Power Interchange in MW").column_position == 306
    assert _find(case, "POC1", "Reactive Power Interchange in Mvar").column_position == 307
    assert _find(case, "POC2", "Active Power Interchange in MW").column_position == 308
    assert _find(case, "POC2", "Reactive Power Interchange in Mvar").column_position == 309
    loading = build_equipment_loading_figures([case], ["Main TR_1"], "POC1", labels, options=options)
    p_interchange = _find(case, "POC1", "Active Power Interchange in MW").numeric_values[1]
    assert loading.bundles[0].curves[0].x_values[1] == pytest.approx(-p_interchange)
    assert p_interchange != 0

    poc = build_poc_pq_figures([case], ["POC1", "POC2"], labels, options=options)
    by_object = {bundle.element_name: bundle.curves[0] for bundle in poc.bundles}
    for object_name, p_position, q_position in (("POC1", 306, 307), ("POC2", 308, 309)):
        p_channel = next(channel for channel in case.channels_for(object_name) if channel.column_position == p_position)
        q_channel = next(channel for channel in case.channels_for(object_name) if channel.column_position == q_position)
        assert by_object[object_name].x_values[1] == pytest.approx(-q_channel.numeric_values[1])
        assert by_object[object_name].y_values[1] == pytest.approx(-p_channel.numeric_values[1])

    pf = build_power_factor_figures([case], ["Exp_Cable_1", "Exp_Cable_2"], labels, options=options)
    assert _find(case, "Exp_Cable_1", "Power Factor").column_position == 4
    assert _find(case, "Exp_Cable_2", "Power Factor").column_position == 16
    by_object = {bundle.element_name: bundle.curves[0] for bundle in pf.bundles}
    for object_name in ("Exp_Cable_1", "Exp_Cable_2"):
        channel = _find(case, object_name, "Power Factor")
        assert by_object[object_name].x_values[:2] == (0.0, 1.0)
        assert by_object[object_name].y_values[0] == pytest.approx(-channel.numeric_values[0])
        assert by_object[object_name].y_values[1] == pytest.approx(-channel.numeric_values[1])
    assert _find(case, "Exp_Cable_1", "Power Factor").numeric_values[0] == pytest.approx(.95)
    assert _find(case, "Exp_Cable_1", "Power Factor").numeric_values[1] == pytest.approx(-.95)
