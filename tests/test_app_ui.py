import csv
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
    assert pq_rows["Violating points"].tolist() == [1, 1]
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
    assert voltage_rows["Violating points"].tolist() == [1, 1]
    assert set(voltage_rows["Case"]) == {"StudyA · V1"}


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
