from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_empty_app_renders_all_five_tabs_and_source_controls():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(app_path, default_timeout=45).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "WTG P–Q",
        "WTG Terminal Voltage",
        "Equipment Loading",
        "POC P–Q",
        "Power Factor",
    ]
    assert [title.value for title in app.title] == ["PowerFactory Load-Flow Dashboard"]
    assert {button.key for button in app.button} >= {"reload_local", "clear_uploads"}
    assert any("No valid CSV cases" in item.value for item in app.info)

    for tab_name in (
        "WTG Terminal Voltage",
        "Equipment Loading",
        "POC P–Q",
        "Power Factor",
        "WTG P–Q",
    ):
        app.session_state["plot_tabs"] = tab_name
        app.run()
        assert not app.exception

    app.button(key="clear_uploads").click().run()
    assert not app.exception
    app.button(key="reload_local").click().run()
    assert not app.exception
