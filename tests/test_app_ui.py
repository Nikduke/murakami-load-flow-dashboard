import csv
from hashlib import sha256
import json
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from openpyxl import Workbook
from streamlit.testing.v1 import AppTest


def _uploaded_chart_csv() -> bytes:
    rows = [
        ["Results", *([r"WTG 1\WTG 1"] * 5), "POC1", "POC1", "POC2", "POC2", "Main TR_1", "Exp_Cable_1", "Exp_Cable_1", "Exp_Cable_2"],
        ["Index", "Active Power in MW", "Reactive Power in Mvar", "Voltage, Magnitude in p.u.", "Lower limit of reactive power in Mvar", "Upper limit of reactive power in Mvar", "Active Power Interchange in MW", "Reactive Power Interchange in Mvar", "Active Power Interchange in MW", "Reactive Power Interchange in Mvar", "Maximum Loading in %", "Loading in %", "Power Factor", "Power Factor"],
        [0, 1.0, 0.2, 1.0, -0.5, 0.5, 100, 20, 300, 40, 60, 62, 0.95, 0.96],
        [1, 2.0, 0.3, 1.01, -0.4, 0.6, 200, 30, 400, 50, 65, 66, 0.96, 0.97],
    ]
    content = StringIO(newline="")
    csv.writer(content).writerows(rows)
    return content.getvalue().encode("utf-8")


def _uploaded_violation_csv() -> bytes:
    rows = list(csv.reader(StringIO(_uploaded_chart_csv().decode("utf-8"))))
    rows[2][1:6] = ["10", "-0.6", "0.91", "-0.5", "0.5"]
    rows[3][1:6] = ["20", "0.7", "1.09", "-0.5", "0.5"]
    rows[2][11] = "120"
    rows[3][11] = "105"
    content = StringIO(newline="")
    csv.writer(content).writerows(rows)
    return content.getvalue().encode("utf-8")


def _uploaded_multi_wtg_violation_csv() -> bytes:
    rows = list(csv.reader(StringIO(_uploaded_violation_csv().decode("utf-8"))))
    rows[0].extend([r"WTG 23\WTG 23"] * 5)
    rows[1].extend(
        [
            "Active Power in MW",
            "Reactive Power in Mvar",
            "Voltage, Magnitude in p.u.",
            "Lower limit of reactive power in Mvar",
            "Upper limit of reactive power in Mvar",
        ]
    )
    rows[2].extend(["10", "-0.6", "0.91", "-0.5", "0.5"])
    rows[3].extend(["20", "0.7", "1.09", "-0.5", "0.5"])
    content = StringIO(newline="")
    csv.writer(content).writerows(rows)
    return content.getvalue().encode("utf-8")


def _app_test_script() -> str:
    return """
import streamlit as st
import app

def app_test_equipment_pills(label, options, defaults, *, key):
    st.session_state[f"{key}_options"] = list(options)
    selected = [value for value in options if value in st.session_state.get(key, defaults)]
    st.session_state[key] = selected
    st.caption(f"{label} · click selects one · Ctrl-click adds/removes")
    return selected

app.equipment_pills = app_test_equipment_pills
app._PLOT_WIDTH_SENSOR = lambda **kwargs: None
app.main()
"""


def test_empty_app_keeps_upload_in_sidebar_and_main_area_clear():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    assert (app_path.parent / "assets" / "mpe_app_wordmark.png").is_file()
    assert (app_path.parent / "assets" / "mpe_app_icon.png").is_file()
    app = AppTest.from_file(app_path, default_timeout=45).run()
    assert not app.exception
    assert [title.value for title in app.header] == ["Murakami Load-Flow"]
    assert len(app.sidebar.file_uploader) == 1
    assert not any(button.key in {"reload_local", "clear_uploads"} for button in app.button)
    assert not app.sidebar.multiselect
    assert not app.sidebar.selectbox
    assert not app.sidebar.segmented_control
    assert not app.tabs
    assert any("Upload a CSV or ZIP" in item.value for item in app.info)


def test_uploaded_csv_loads_cases_and_shows_all_five_plot_tabs():
    app = AppTest.from_string(_app_test_script(), default_timeout=45).run()
    app.sidebar.file_uploader[0].set_value(("StudyA__V1.csv", _uploaded_chart_csv(), "text/csv")).run()

    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "WTG P–Q",
        "WTG Terminal Voltage",
        "Equipment Loading",
        "POC P–Q",
        "Power Factor",
    ]
    assert any(item.label == "StudyA" for item in app.sidebar.checkbox)
    assert any(item.label == "V1" for item in app.sidebar.checkbox)
    assert "1 of 1 cases selected" in [item.value for item in app.caption]
    assert app.segmented_control(key="wtg_pq_layout").value == "1 plot"


def test_wtg_tabs_show_case_limit_violations_below_the_plots():
    app = AppTest.from_string(_app_test_script(), default_timeout=45).run()
    app.sidebar.file_uploader[0].set_value(
        ("StudyA__V1.csv", _uploaded_violation_csv(), "text/csv")
    ).run()

    assert not app.exception
    assert any(item.value == "WTG P–Q limit violations" for item in app.subheader)
    pq_rows = app.dataframe[0].value
    assert set(pq_rows["Limit"]) == {"Qmin", "Qmax"}
    assert "Violating points" not in pq_rows.columns
    assert set(pq_rows["Case"]) == {"StudyA · V1"}

    app.checkbox(key="pq_show_qmax").set_value(False).run()
    assert not app.exception
    assert set(app.dataframe[0].value["Limit"]) == {"Qmin", "Qmax"}

    app.session_state["plot_tabs"] = "WTG Terminal Voltage"
    app.run()

    assert not app.exception
    assert any(item.value == "WTG terminal-voltage limit violations" for item in app.subheader)
    voltage_rows = app.dataframe[0].value
    assert set(voltage_rows["Limit"]) == {"Min voltage", "Max voltage"}
    assert "Violating points" not in voltage_rows.columns
    assert set(voltage_rows["Case"]) == {"StudyA · V1"}

    app.session_state["plot_tabs"] = "Equipment Loading"
    app.run()

    assert not app.exception
    assert any(item.value == "Equipment loading limit violations" for item in app.subheader)
    loading_rows = app.dataframe[0].value
    assert "Violating points" not in loading_rows.columns
    assert loading_rows.iloc[0]["Equipment"] == "Exp_Cable_1"
    assert loading_rows.iloc[0]["X at worst point (MW)"] == -100.0
    assert loading_rows.iloc[0]["Loading (%)"] == 120.0
    assert loading_rows.iloc[0]["Limit (%)"] == 100.0
    assert loading_rows.iloc[0]["Excess (%)"] == 20.0


def test_violation_table_selection_filters_and_restores_plot_traces():
    archive = BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("StudyA__V1.csv", _uploaded_violation_csv())
        zip_file.writestr("StudyB__V2.csv", _uploaded_violation_csv())

    app = AppTest.from_string(_app_test_script(), default_timeout=45).run()
    app.sidebar.file_uploader[0].set_value(("Study.zip", archive.getvalue(), "application/zip")).run()
    app.button(key="all_cases").click().run()

    pq_rows = app.dataframe[0].value
    row_a = next(index for index, row in pq_rows.iterrows() if row["Case"] == "StudyA · V1")
    row_b = next(index for index, row in pq_rows.iterrows() if row["Case"] == "StudyB · V2")
    selection_key = app.dataframe[0].key

    app.session_state[selection_key] = {"selection": {"rows": [int(row_b)]}}
    app.run()
    assert not app.exception
    figure = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert len(figure["data"]) == 3
    assert {trace["legendgroup"] for trace in figure["data"]} == {"StudyB__V2"}

    app.session_state[selection_key] = {"selection": {"rows": [int(row_a), int(row_b)]}}
    app.run()
    assert not app.exception
    figure = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert len(figure["data"]) == 6
    assert {trace["legendgroup"] for trace in figure["data"]} == {"StudyA__V1", "StudyB__V2"}

    app.session_state[selection_key] = {"selection": {"rows": []}}
    app.run()
    assert not app.exception
    figure = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert len(figure["data"]) == 6


def test_violation_selection_clears_when_wtg_scope_changes():
    app = AppTest.from_string(_app_test_script(), default_timeout=45).run()
    app.sidebar.file_uploader[0].set_value(
        ("Study.csv", _uploaded_multi_wtg_violation_csv(), "text/csv")
    ).run()

    first_table_key = app.dataframe[0].key
    app.session_state[first_table_key] = {"selection": {"rows": [0]}}
    app.run()
    figure = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert {trace["meta"][1] for trace in figure["data"]} == {r"WTG 1\WTG 1"}

    app.session_state["pq_objects"] = [r"WTG 23\WTG 23"]
    app.run()
    assert not app.exception
    assert app.dataframe[0].key != first_table_key
    assert app.dataframe[0].value is not None
    assert app.dataframe[0].value.iloc[0]["WTG"] == "WTG 23"
    selection = app.session_state[app.dataframe[0].key]["selection"]["rows"]
    assert selection == []
    figure = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert {trace["meta"][1] for trace in figure["data"]} == {r"WTG 23\WTG 23"}


def test_violation_selection_clears_when_case_options_change_but_rows_do_not():
    archive = BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("StudyA__V1.csv", _uploaded_violation_csv())
        zip_file.writestr("StudyB__V2.csv", _uploaded_chart_csv())

    app = AppTest.from_string(_app_test_script(), default_timeout=45).run()
    app.sidebar.file_uploader[0].set_value(("Study.zip", archive.getvalue(), "application/zip")).run()
    assert "1 of 2 cases selected" in [item.value for item in app.caption]
    assert set(app.dataframe[0].value["Case"]) == {"StudyA · V1"}

    first_table_key = app.dataframe[0].key
    app.session_state[first_table_key] = {"selection": {"rows": [0]}}
    app.run()
    figure = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert {trace["legendgroup"] for trace in figure["data"]} == {"StudyA__V1"}

    app.button(key="all_cases").click().run()
    assert app.dataframe[0].key != first_table_key
    assert set(app.dataframe[0].value["Case"]) == {"StudyA · V1"}
    assert app.session_state[app.dataframe[0].key]["selection"]["rows"] == []
    figure = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert {trace["legendgroup"] for trace in figure["data"]} == {"StudyA__V1", "StudyB__V2"}


def test_uploaded_csv_values_are_rendered_correctly_on_all_five_tabs():
    app = AppTest.from_string(_app_test_script(), default_timeout=45).run()
    app.sidebar.file_uploader[0].set_value(("StudyA__V1.csv", _uploaded_chart_csv(), "text/csv")).run()
    assert not app.exception

    expected = {
        "WTG P–Q": (
            [([0.2, 0.3], [1.0, 2.0]), ([-0.5, -0.4], [1.0, 2.0]), ([0.5, 0.6], [1.0, 2.0])],
            "Reactive power, Q (Mvar)",
            "Active power, P (MW)",
        ),
        "WTG Terminal Voltage": (
            [([1.0, 2.0], [1.0, 1.01])],
            "Active power, P (MW)",
            "Terminal voltage, U (p.u.)",
        ),
        "Equipment Loading": (
            [([-100.0, -200.0], [62.0, 66.0])],
            "−POC1 active power interchange (MW)",
            "Equipment loading (%)",
        ),
        "POC P–Q": (
            [([-20.0, -30.0], [-100.0, -200.0])],
            "−Reactive power interchange (Mvar)",
            "−Active power interchange (MW)",
        ),
        "Power Factor": (
            [([None, 1.0], [None, -0.96])],
            "Sweep index (index)",
            "Power factor (unitless)",
        ),
    }

    for tab_name, (expected_traces, expected_x_title, expected_y_title) in expected.items():
        app.session_state["plot_tabs"] = tab_name
        app.run()
        assert not app.exception
        rendered = json.loads(app.get("plotly_chart")[0].proto.spec)
        actual_traces = [(trace["x"], trace["y"]) for trace in rendered["data"]]
        assert actual_traces == expected_traces, tab_name
        assert rendered["layout"]["xaxis"]["title"]["text"] == expected_x_title, tab_name
        assert rendered["layout"]["yaxis"]["title"]["text"] == expected_y_title, tab_name
        assert rendered["data"][0]["meta"][0] == "StudyA · V1", tab_name

        if tab_name == "WTG Terminal Voltage":
            assert [shape["y0"] for shape in rendered["layout"]["shapes"]] == [0.92, 1.08]
            reference_labels = [annotation["text"] for annotation in rendered["layout"]["annotations"]]
            assert "Min = 0.92 p.u." in reference_labels
            assert "Max = 1.08 p.u." in reference_labels
        elif tab_name == "Equipment Loading":
            assert rendered["layout"]["shapes"][0]["y0"] == 100.0
            peak = next(
                annotation["text"]
                for annotation in rendered["layout"]["annotations"]
                if annotation.get("showarrow")
            )
            assert peak == "-200.0 MW<br>66.0 %"
            app.session_state["plot_tabs"] = tab_name
            app.selectbox(key="loading_x_source").set_value("POC2").run()
            assert not app.exception
            changed_source = json.loads(app.get("plotly_chart")[0].proto.spec)
            assert [(trace["x"], trace["y"]) for trace in changed_source["data"]] == [
                ([-300.0, -400.0], [62.0, 66.0])
            ]
            assert changed_source["layout"]["xaxis"]["title"]["text"] == (
                "−POC2 active power interchange (MW)"
            )


def test_uploaded_zip_renders_the_same_case_data_as_loose_csv():
    archive = BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("StudyA__V1.csv", _uploaded_chart_csv())

    app = AppTest.from_string(_app_test_script(), default_timeout=45).run()
    app.sidebar.file_uploader[0].set_value(("Study.zip", archive.getvalue(), "application/zip")).run()

    assert not app.exception
    rendered = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert [(trace["x"], trace["y"]) for trace in rendered["data"]] == [
        ([0.2, 0.3], [1.0, 2.0]),
        ([-0.5, -0.4], [1.0, 2.0]),
        ([0.5, 0.6], [1.0, 2.0]),
    ]
    assert rendered["data"][0]["meta"][0] == "StudyA · V1"


def test_multiple_mapping_workbooks_apply_the_explicitly_selected_headers():
    with TemporaryDirectory() as temporary_directory:
        app_dir = Path(temporary_directory)
        input_dir = app_dir / "Input_files"
        input_dir.mkdir()
        (input_dir / "StudyA__V1.csv").write_bytes(_uploaded_chart_csv())

        for filename, headings in (
            ("Mapping_A.xlsx", ("Site", "Operating condition")),
            ("Mapping_B.xlsx", ("Network case", "Initial voltage")),
        ):
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Headers"
            sheet.append(["Token N", "Header"])
            sheet.append([1, headings[0]])
            sheet.append([2, headings[1]])
            workbook.save(input_dir / filename)
            workbook.close()

        script = _app_test_script().replace(
            "app.main()",
            f"from pathlib import Path\napp.APP_DIR = Path({str(app_dir)!r})\n"
            f"app.INPUT_DIR = Path({str(input_dir)!r})\napp.main()",
        )
        app = AppTest.from_string(script, default_timeout=45).run()

        assert not app.exception
        assert len(app.selectbox) == 1
        mapping_picker = app.selectbox[0]
        assert mapping_picker.label == "Mapping workbook"
        assert mapping_picker.value is None
        selected_mapping = next(option for option in mapping_picker.options if "Mapping_B.xlsx" in option)
        mapping_picker.set_value(selected_mapping).run()

        assert not app.exception
        assert any("Network case" in item.value for item in app.markdown)
        assert any("Initial voltage" in item.value for item in app.markdown)


def test_mapping_groups_filter_equipment_and_power_factor_chips(monkeypatch):
    import app as application

    build_calls = 0
    build_loading = application.build_equipment_loading_figures

    def counted_build(*args, **kwargs):
        nonlocal build_calls
        build_calls += 1
        return build_loading(*args, **kwargs)

    monkeypatch.setattr(application, "build_equipment_loading_figures", counted_build)

    rows = list(csv.reader(StringIO(_uploaded_chart_csv().decode("utf-8"))))
    rows[0].extend(["Unmapped Device", "Unmapped Device"])
    rows[1].extend(["Loading in %", "Power Factor"])
    rows[2].extend(["70", "0.98"])
    rows[3].extend(["75", "0.99"])
    content = StringIO(newline="")
    csv.writer(content).writerows(rows)

    workbook = Workbook()
    headers = workbook.active
    headers.title = "Headers"
    headers.append(["Token N", "Header"])
    headers.append([1, "Study"])
    headers.append([2, "Initial voltage"])
    grouping = workbook.create_sheet("Grouping")
    grouping.append(["HEADER", "Group"])
    grouping.append(["Exp_Cable_1", "Export Cables "])
    grouping.append(["Main TR_1", "Transformers"])
    grouping.append(["Exp_Cable_2", "Export Cables"])
    mapping_bytes = BytesIO()
    workbook.save(mapping_bytes)
    workbook.close()

    archive = BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("StudyA__V1.csv", content.getvalue())
        zip_file.writestr("Mapping_V2.xlsx", mapping_bytes.getvalue())

    script = _app_test_script().replace(
        "app._PLOT_WIDTH_SENSOR = lambda **kwargs: None",
        "def app_test_width_sensor(**kwargs):\n"
        "    st.session_state.setdefault('_plot_width_keys', []).append(kwargs['key'])\n"
        "    st.session_state.setdefault(kwargs['key'], {'width': 1200})\n"
        "app._PLOT_WIDTH_SENSOR = app_test_width_sensor",
    )
    app = AppTest.from_string(script, default_timeout=45).run()
    app.sidebar.file_uploader[0].set_value(("Study.zip", archive.getvalue(), "application/zip")).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "WTG P–Q",
        "WTG Terminal Voltage",
        "Equipment Loading",
        "POC P–Q",
        "Power Factor",
    ]

    def plotted_objects():
        figure = json.loads(app.get("plotly_chart")[0].proto.spec)
        return {trace["meta"][1] for trace in figure["data"]}

    app.session_state["plot_tabs"] = "Equipment Loading"
    app.run()
    assert not app.exception
    assert build_calls == 1
    width_key = "plot_panel_width_1_column"
    assert app.session_state[width_key] == {"width": 1200}
    app.session_state["plot_tabs"] = "Equipment Loading"
    app.session_state["equipment_loading_groups"] = "Export Cables"
    app.run()
    assert build_calls == 1
    app.session_state["plot_tabs"] = "Equipment Loading"
    app.session_state["equipment_loading_groups"] = "Export Cables"
    app.run()
    assert build_calls == 1
    assert {tab.label for tab in app.tabs} >= {"Export Cables", "Transformers", "All cases"}
    export_key = f"export_cables_{sha256(b'Export Cables').hexdigest()[:6]}"
    transformer_key = f"transformers_{sha256(b'Transformers').hexdigest()[:6]}"
    all_key = f"all_cases_{sha256(b'All cases').hexdigest()[:6]}"
    assert app.session_state[f"loading_objects_group_{export_key}_options"] == ["Exp_Cable_1"]
    assert app.session_state[f"loading_objects_group_{export_key}"] == ["Exp_Cable_1"]
    assert plotted_objects() == {"Exp_Cable_1"}
    assert "1 of 1 cases selected" in [item.value for item in app.caption]

    app.session_state["plot_tabs"] = "Equipment Loading"
    app.session_state["equipment_loading_groups"] = "Transformers"
    app.run()
    assert not app.exception
    assert build_calls == 2
    assert app.session_state[f"loading_objects_group_{transformer_key}_options"] == ["Main TR_1"]
    assert app.session_state[f"loading_objects_group_{transformer_key}"] == ["Main TR_1"]
    assert plotted_objects() == {"Main TR_1"}
    app.session_state["plot_tabs"] = "Equipment Loading"
    app.session_state["equipment_loading_groups"] = "Transformers"
    app.run()
    assert build_calls == 2
    assert {
        key for key in app.session_state["_plot_width_keys"] if key.startswith("plot_panel_width")
    } == {width_key}

    app.session_state["plot_tabs"] = "Equipment Loading"
    app.session_state["equipment_loading_groups"] = "All cases"
    app.run()
    assert not app.exception
    assert app.session_state[f"loading_objects_group_{all_key}_options"] == [
        "Exp_Cable_1",
        "Main TR_1",
        "Unmapped Device",
    ]
    assert app.session_state[f"loading_objects_group_{all_key}"] == ["Exp_Cable_1"]
    assert plotted_objects() == {"Exp_Cable_1"}
    app.session_state["plot_tabs"] = "Equipment Loading"
    app.session_state["equipment_loading_groups"] = "All cases"
    app.session_state[f"loading_objects_group_{all_key}"] = [
        "Exp_Cable_1",
        "Main TR_1",
        "Unmapped Device",
    ]
    app.run()
    assert plotted_objects() == {"Exp_Cable_1", "Main TR_1", "Unmapped Device"}

    app.session_state["plot_tabs"] = "Equipment Loading"
    app.session_state["equipment_loading_groups"] = "Export Cables"
    app.run()
    assert app.session_state[f"loading_objects_group_{export_key}"] == ["Exp_Cable_1"]
    assert plotted_objects() == {"Exp_Cable_1"}
    app.session_state["plot_tabs"] = "Equipment Loading"
    app.session_state["equipment_loading_groups"] = "All cases"
    app.run()
    assert app.session_state[f"loading_objects_group_{all_key}"] == [
        "Exp_Cable_1",
        "Main TR_1",
        "Unmapped Device",
    ]
    assert plotted_objects() == {"Exp_Cable_1", "Main TR_1", "Unmapped Device"}

    app.session_state["plot_tabs"] = "Power Factor"
    app.run()
    assert not app.exception
    assert app.session_state[f"pf_objects_group_{export_key}_options"] == [
        "Exp_Cable_1",
        "Exp_Cable_2",
    ]
    assert app.session_state[f"pf_objects_group_{export_key}"] == ["Exp_Cable_1"]
    assert "Transformers" not in {tab.label for tab in app.tabs}
    assert plotted_objects() == {"Exp_Cable_1"}

    app.session_state["plot_tabs"] = "Power Factor"
    app.session_state["power_factor_groups"] = "All cases"
    app.run()
    assert not app.exception
    assert app.session_state[f"pf_objects_group_{all_key}_options"] == [
        "Exp_Cable_1",
        "Exp_Cable_2",
        "Unmapped Device",
    ]
    app.session_state["plot_tabs"] = "Power Factor"
    app.session_state["power_factor_groups"] = "All cases"
    app.session_state[f"pf_objects_group_{all_key}"] = [
        "Exp_Cable_1",
        "Exp_Cable_2",
        "Unmapped Device",
    ]
    app.run()
    assert plotted_objects() == {"Exp_Cable_1", "Exp_Cable_2", "Unmapped Device"}
    assert {
        key for key in app.session_state["_plot_width_keys"] if key.startswith("plot_panel_width")
    } == {width_key}


def test_plot_width_keys_follow_panel_geometry():
    from app import _plot_width_key

    assert _plot_width_key("1 plot") == _plot_width_key("1×2")
    assert _plot_width_key("2×2") != _plot_width_key("1 plot")


def test_header_variations_are_computed_once_per_parsed_source_set(monkeypatch):
    import app as application

    header_issue_calls = 0
    compute_header_issues = application._header_variation_issues

    def counted_header_issues(cases):
        nonlocal header_issue_calls
        if len(cases) > 1:
            header_issue_calls += 1
        return compute_header_issues(cases)

    monkeypatch.setattr(application, "_header_variation_issues", counted_header_issues)
    first_case = list(csv.reader(StringIO(_uploaded_chart_csv().decode("utf-8"))))
    second_case = [row[:-2] for row in first_case]
    first_csv = StringIO(newline="")
    second_csv = StringIO(newline="")
    csv.writer(first_csv).writerows(first_case)
    csv.writer(second_csv).writerows(second_case)
    archive = BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("StudyA__V1.csv", first_csv.getvalue())
        zip_file.writestr("StudyA__V2.csv", second_csv.getvalue())

    app = AppTest.from_string(_app_test_script(), default_timeout=45).run()
    app.sidebar.file_uploader[0].set_value(("Study.zip", archive.getvalue(), "application/zip")).run()
    assert not app.exception
    assert header_issue_calls == 1
    app.session_state["plot_tabs"] = "WTG Terminal Voltage"
    app.run()
    assert not app.exception
    assert header_issue_calls == 1


def test_case_option_description_table_appears_below_every_chart_section():
    workbook = Workbook()
    headers = workbook.active
    headers.title = "Headers"
    headers.append(["Token N", "Header"])
    headers.append([1, "Study configuration"])
    headers.append([2, "Initial voltage"])
    descriptions = workbook.create_sheet("Description")
    descriptions.append(["ID", "Description"])
    descriptions.append(["StudyA", "Study A description"])
    descriptions.append(["StudyB", "Study B description"])
    descriptions.append(["V1", "Version one"])
    mapping_bytes = BytesIO()
    workbook.save(mapping_bytes)
    workbook.close()

    archive = BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("StudyA__V1.csv", _uploaded_violation_csv())
        zip_file.writestr("StudyB__V1.csv", _uploaded_violation_csv())
        zip_file.writestr("Mapping_V2.xlsx", mapping_bytes.getvalue())

    app = AppTest.from_string(_app_test_script(), default_timeout=45).run()
    app.sidebar.file_uploader[0].set_value(("Study.zip", archive.getvalue(), "application/zip")).run()
    assert not app.exception

    expected_rows = [
        {"Case filter": "Study configuration", "Option": "StudyA", "Description": "Study A description"},
        {"Case filter": "", "Option": "StudyB", "Description": "Study B description"},
        {"Case filter": "Initial voltage", "Option": "V1", "Description": "Version one"},
    ]
    chart_sections = (
        "WTG P–Q",
        "WTG Terminal Voltage",
        "Equipment Loading",
        "POC P–Q",
        "Power Factor",
    )
    for section in chart_sections:
        app.session_state["plot_tabs"] = section
        app.run()
        assert not app.exception
        tables = [
            element.value
            for element in app.dataframe
            if list(element.value.columns) == ["Case filter", "Option", "Description"]
        ]
        assert len(tables) == 1
        assert [dict(row) for row in tables[0].to_dict(orient="records")] == expected_rows
        section_headers = [element.value for element in app.subheader]
        assert "Case option descriptions" in section_headers
        dataframe_columns = [list(element.value.columns) for element in app.dataframe]
        if section in {"WTG P–Q", "WTG Terminal Voltage", "Equipment Loading"}:
            violation_table_index = next(
                index
                for index, columns in enumerate(dataframe_columns)
                if "Case" in columns and any(column.startswith("Excess") for column in columns)
            )
            description_table_index = dataframe_columns.index(
                ["Case filter", "Option", "Description"]
            )
            assert description_table_index < violation_table_index
            violation_header = next(header for header in section_headers if header.endswith("limit violations"))
            assert section_headers.index("Case option descriptions") < section_headers.index(violation_header)


def test_single_mapping_workbook_is_used_without_a_picker(monkeypatch):
    import app as application

    build_calls = 0
    build_plot = application.build_wtg_pq_figures

    def counted_build(*args, **kwargs):
        nonlocal build_calls
        build_calls += 1
        return build_plot(*args, **kwargs)

    monkeypatch.setattr(application, "build_wtg_pq_figures", counted_build)

    with TemporaryDirectory() as temporary_directory:
        app_dir = Path(temporary_directory)
        input_dir = app_dir / "Input_files"
        input_dir.mkdir()
        first_case = input_dir / "StudyA__V1.csv"
        with first_case.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "Results",
                    *([r"WTG 1\WTG 1"] * 5),
                    "POC1",
                    "POC1",
                    "Main TR_1",
                    "Exp_Cable_1",
                    "Exp_Cable_1",
                    "Exp_Cable_2",
                ]
            )
            writer.writerow(
                [
                    "Index",
                    "Active Power in MW",
                    "Reactive Power in Mvar",
                    "Voltage, Magnitude in p.u.",
                    "Lower limit of reactive power in Mvar",
                    "Upper limit of reactive power in Mvar",
                    "Active Power Interchange in MW",
                    "Reactive Power Interchange in Mvar",
                    "Maximum Loading in %",
                    "Loading in %",
                    "Power Factor",
                    "Power Factor",
                ]
            )
            writer.writerow([0, 1.0, 0.2, 1.0, -0.5, 0.5, 100, 20, 60, 62, 0.95, 0.96])
            writer.writerow([1, 2.0, 0.3, 1.01, -0.4, 0.6, 200, 30, 65, 66, 0.96, 0.97])
        (input_dir / "StudyB__V2.csv").write_bytes(first_case.read_bytes())

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Headers"
        sheet.append(["Token N", "Header"])
        sheet.append([1, "Study config"])
        sheet.append([2, "Initial voltage"])
        workbook.save(input_dir / "Mapping.xlsx")

        script = (
            "import app\n"
            "import streamlit as st\n"
            "def app_test_equipment_pills(label, options, defaults, *, key):\n"
            "    st.session_state[f'{key}_options'] = list(options)\n"
            "    selected = [value for value in options if value in st.session_state.get(key, defaults)]\n"
            "    st.session_state[key] = selected\n"
            "    st.caption(f'{label} · click selects one · Ctrl-click adds/removes')\n"
            "    return selected\n"
            "app.equipment_pills = app_test_equipment_pills\n"
            "app._PLOT_WIDTH_SENSOR = lambda **kwargs: None\n"
            "from pathlib import Path\n"
            f"app.APP_DIR = Path({str(app_dir)!r})\n"
            f"app.INPUT_DIR = Path({str(input_dir)!r})\n"
            "app.main()\n"
        )
        app = AppTest.from_string(script, default_timeout=45).run()

        assert not app.exception
        assert any(item.label == "StudyA" for item in app.checkbox)
        assert any(item.label == "StudyB" for item in app.checkbox)
        assert any(item.label == "V1" for item in app.checkbox)
        assert any("Study config" in item.value for item in app.markdown)
        assert any("Initial voltage" in item.value for item in app.markdown)
        assert app.button(key="case_filter_0_select_all")
        assert app.button(key="case_filter_0_clear_all")
        assert app.button(key="case_filter_0_select_all").label == "Select all"
        assert app.button(key="case_filter_0_clear_all").label == "Clear all"
        assert app.button(key="all_cases").label == "All cases"
        assert not app.sidebar.multiselect
        assert not app.sidebar.selectbox
        assert not app.sidebar.segmented_control
        assert app.segmented_control(key="wtg_pq_layout").value == "1 plot"
        app.segmented_control(key="wtg_pq_layout").set_value(None).run()
        assert not app.exception
        assert app.segmented_control(key="wtg_pq_layout").value == "1 plot"
        assert app.session_state["case_filter_0"] == ["StudyA"]
        assert app.session_state["case_filter_1"] == ["V1"]
        assert app.session_state["pq_objects"] == ["WTG 1\\WTG 1"]
        assert app.session_state["pq_objects"] == app.session_state["pq_objects_options"][:1]
        assert any("Ctrl-click adds/removes" in item.value for item in app.caption)
        assert not app.multiselect
        assert not any(item.label == "Curve label token positions" for item in app.expander)
        assert not any(item.label == "Axis limits" for item in app.expander)
        assert not any(item.label == "Mapping workbook" for item in app.selectbox)
        assert len(app.get("plotly_chart")) == 1
        assert build_calls == 1

        app.run()
        assert not app.exception
        assert build_calls == 1
        app.segmented_control(key="wtg_pq_layout").set_value("1×2").run()
        assert not app.exception
        assert build_calls == 2
        app.segmented_control(key="wtg_pq_layout").set_value("2×2").run()
        assert not app.exception
        assert build_calls == 3

        app.button(key="case_filter_0_clear_all").click().run()
        assert not app.exception
        assert app.session_state["case_filter_0"] == []
        assert build_calls == 3
        app.button(key="case_filter_0_select_all").click().run()
        assert not app.exception
        assert app.session_state["case_filter_0"] == ["StudyA", "StudyB"]
        assert app.session_state["case_filter_1"] == []
        assert build_calls == 3
        assert any(item.label == "V2" for item in app.checkbox)
        app.button(key="case_filter_1_select_all").click().run()
        assert not app.exception
        assert app.session_state["case_filter_1"] == ["V1", "V2"]
        assert build_calls == 4
        app.segmented_control(key="wtg_pq_layout").set_value("1×2").run()
        assert not app.exception
        assert build_calls == 5
        assert len(app.get("plotly_chart")) == 2
        app.button(key="all_cases").click().run()
        assert not app.exception
        assert app.session_state["case_filter_0"] == ["StudyA", "StudyB"]
        assert app.session_state["case_filter_1"] == ["V1", "V2"]
        assert build_calls == 5

        (input_dir / "StudyC__V3.csv").write_bytes(first_case.read_bytes())
        app.run()
        assert not app.exception
        assert any(item.label == "StudyC" for item in app.checkbox)
        assert not any(item.label == "V3" for item in app.checkbox)
        assert app.session_state["case_filter_0"] == ["StudyA"]
        assert app.session_state["case_filter_1"] == ["V1"]
        next(item for item in app.checkbox if item.label == "StudyC").set_value(True).run()
        assert app.session_state["case_filter_0"] == ["StudyA", "StudyC"]
        assert any(item.label == "V3" for item in app.checkbox)
        next(item for item in app.checkbox if item.label == "StudyC").set_value(False).run()
        assert app.session_state["case_filter_0"] == ["StudyA"]
        for tab_name in ("WTG Terminal Voltage", "Equipment Loading", "POC P–Q", "Power Factor"):
            app.session_state["plot_tabs"] = tab_name
            app.run()
            assert not app.exception
            assert not app.sidebar.multiselect
            assert app.segmented_control[0].value == "1 plot"
            selection_key = {
                "WTG Terminal Voltage": "voltage_objects",
                "Equipment Loading": "loading_objects",
                "POC P–Q": "poc_objects",
                "Power Factor": "pf_objects",
            }[tab_name]
            assert app.session_state[selection_key] == app.session_state[f"{selection_key}_options"][:1]
            assert len(app.get("plotly_chart")) >= 1


def test_validation_summary_groups_repeated_messages_by_source():
    from app import _group_validation_issues
    from validation import ValidationIssue

    issue = ValidationIssue("warning", "blank_channel_headings", "Blank columns ignored")
    grouped = _group_validation_issues(
        (
            ValidationIssue(issue.severity, issue.code, issue.message, "case-1.csv"),
            ValidationIssue(issue.severity, issue.code, issue.message, "case-2.csv"),
        )
    )
    assert len(grouped) == 1
    assert grouped[0][0].message == "Blank columns ignored"
    assert grouped[0][1] == 2


def test_cached_violation_rows_reuses_same_scope_summary():
    app = AppTest.from_string(
        """
import streamlit as st
import app

calls = []
def build_rows(cases, selected_objects, labels, threshold):
    calls.append(1)
    return [{"Case": str(threshold)}]

first = app._cached_violation_rows(("cache-test", 42), build_rows, (), (), {}, (42,))
second = app._cached_violation_rows(("cache-test", 42), build_rows, (), (), {}, (42,))
st.session_state["cache_test_result"] = (first == second, len(calls))
"""
    ).run()

    assert not app.exception
    assert app.session_state["cache_test_result"] == (True, 1)


def test_mapping_cache_identity_includes_source_path():
    app = AppTest.from_string(
        """
import streamlit as st
import app
from data_loader import InputFile

first_source = InputFile("Mapping.xlsx", "first/Mapping.xlsx", b"not a workbook", "test")
second_source = InputFile("Mapping.xlsx", "second/Mapping.xlsx", b"not a workbook", "test")
first = app._cached_mapping(app._mapping_signature(first_source), first_source)
second = app._cached_mapping(app._mapping_signature(second_source), second_source)
st.session_state["mapping_source_paths"] = (
    first.issues[0].source_path,
    second.issues[0].source_path,
)
"""
    ).run()

    assert not app.exception
    assert app.session_state["mapping_source_paths"] == (
        "first/Mapping.xlsx",
        "second/Mapping.xlsx",
    )


def test_violation_selection_key_changes_when_summary_values_change():
    from app import _violation_table_key

    row = {
        "_case_id": "Study",
        "_object_name": "WTG 1",
        "Case": "Study",
        "Limit": "Qmax",
        "Excess (Mvar)": 0.2,
    }

    first_key = _violation_table_key("wtg_pq", [row], (), ["WTG 1"])
    changed_key = _violation_table_key(
        "wtg_pq", [{**row, "Excess (Mvar)": 0.3}], (), ["WTG 1"]
    )

    assert first_key != changed_key
