"""Streamlit interface for PowerFactory load-flow CSV sweeps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Sequence

import streamlit as st

from case_filters import case_labels, filter_cases, token_values, varying_token_positions
from equipment_pills import equipment_pills
from channel_catalogue import (
    discover_loading_objects,
    discover_poc_objects,
    discover_power_factor_objects,
    discover_wtg_objects,
    resolve_channel,
)
from data_loader import (
    CaseData,
    ExpandedInputs,
    InputFile,
    ParseResult,
    discover_local_inputs,
    expand_inputs,
    parse_cases,
)
from mapping import MappingResult, load_mapping, token_heading
from plotting import (
    PlotOptions,
    PlotSet,
    build_equipment_loading_figures,
    build_poc_pq_figures,
    build_power_factor_figures,
    build_wtg_pq_figures,
    build_wtg_voltage_figures,
    plotted_data_csv,
)
from validation import ValidationIssue


APP_DIR = Path(__file__).resolve().parent
INPUT_DIR = APP_DIR / "Input_files"
APP_ICON_PATH = APP_DIR / "assets" / "mpe_app_icon.png"
APP_LOGO_PATH = APP_DIR / "assets" / "mpe_app_wordmark.png"
TAB_NAMES = ("WTG P–Q", "WTG Terminal Voltage", "Equipment Loading", "POC P–Q", "Power Factor")
LAYOUTS = ("1 plot", "1×2", "2×2")
CASE_FILTER_DEFAULTS_VERSION = 2
PLOT_CACHE_VERSION = 21
_PLOT_WIDTH_SENSOR = st.components.v2.component(
    "murakami_plot_width_sensor",
    html='<div id="plot-width-sensor" aria-hidden="true"></div>',
    css="#plot-width-sensor { width: 100%; height: 0; overflow: hidden; }",
    js="""
const sensors = new WeakMap()

export default function (component) {
  const { data, parentElement, setStateValue } = component
  const host = parentElement.host
  const previous = sensors.get(parentElement)
  if (previous) {
    clearTimeout(previous.timer)
    previous.observer.disconnect()
  }

  const sensor = { observer: null, timer: null }
  let lastWidth = Number(data?.width ?? 0)
  const reportWidth = () => {
    const width = Math.round(host.getBoundingClientRect().width / 24) * 24
    if (width > 0 && width !== lastWidth) {
      lastWidth = width
      setStateValue("width", width)
    }
  }
  const observer = new ResizeObserver(() => {
    clearTimeout(sensor.timer)
    sensor.timer = setTimeout(reportWidth, 120)
  })
  sensor.observer = observer
  sensors.set(parentElement, sensor)
  observer.observe(host)
  reportWidth()

  return () => {
    clearTimeout(sensor.timer)
    observer.disconnect()
    if (sensors.get(parentElement) === sensor) sensors.delete(parentElement)
  }
}
""",
)


@dataclass(frozen=True)
class ObjectCatalogue:
    wtg_pq: tuple[str, ...]
    wtg_voltage: tuple[str, ...]
    loading: tuple[str, ...]
    poc: tuple[str, ...]
    power_factor: tuple[str, ...]


@st.cache_resource(show_spinner=False, max_entries=4, scope="session")
def _cached_local_inputs(input_dir: Path, signature: tuple[tuple[str, int, int], ...]) -> tuple[InputFile, ...]:
    del signature
    return discover_local_inputs(input_dir)


@st.cache_resource(show_spinner=False, max_entries=2, scope="session")
def _cached_upload_inputs(
    signature: tuple[tuple[str, str, int], ...], _uploads: tuple
) -> tuple[InputFile, ...]:
    del signature
    return tuple(
        InputFile(
            name=uploaded.name,
            source_path=f"upload:/{uploaded.name}",
            content=uploaded.getvalue(),
            origin="upload",
        )
        for uploaded in _uploads
    )


@st.cache_resource(show_spinner="Reading CSV results…", max_entries=4, scope="session")
def _cached_parse(signature: tuple[tuple[str, str, str], ...], _files: tuple[InputFile, ...]) -> tuple[ExpandedInputs, ParseResult]:
    del signature
    expanded = expand_inputs(_files)
    parsed = parse_cases(expanded.csv_files)
    return expanded, parsed


@st.cache_resource(show_spinner=False, max_entries=4, scope="session")
def _cached_object_catalogue(signature: tuple[tuple[str, str, str], ...], _cases: tuple[CaseData, ...]) -> ObjectCatalogue:
    del signature
    wtg = discover_wtg_objects(_cases)

    def eligible_wtg(first_role: str, second_role: str) -> tuple[str, ...]:
        return tuple(
            name
            for name in wtg
            if any(
                resolve_channel(case, name, first_role).status == "found"
                and resolve_channel(case, name, second_role).status == "found"
                for case in _cases
            )
        )

    return ObjectCatalogue(
        wtg_pq=eligible_wtg("active_power", "reactive_power"),
        wtg_voltage=eligible_wtg("active_power", "voltage"),
        loading=tuple(discover_loading_objects(_cases)),
        poc=tuple(discover_poc_objects(_cases)),
        power_factor=tuple(discover_power_factor_objects(_cases)),
    )


@st.cache_resource(show_spinner=False, max_entries=8, scope="session")
def _cached_plot_set(
    signature: tuple[object, ...],
    _builder: Callable[..., PlotSet],
    _args: tuple,
    _kwargs: dict,
) -> PlotSet:
    return _builder(*_args, **_kwargs)


@st.cache_data(show_spinner=False, max_entries=16, scope="session")
def _cached_mapping(signature: str, _source: InputFile) -> MappingResult:
    del signature
    return load_mapping(_source)


def _local_stat_signature(input_dir: Path) -> tuple[tuple[str, int, int], ...]:
    if not input_dir.is_dir():
        return ()
    result = []
    for path in sorted(input_dir.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file() or "__macosx" in {part.casefold() for part in path.parts}:
            continue
        if path.suffix.casefold() not in {".csv", ".zip", ".xlsx"}:
            continue
        stat = path.stat()
        result.append((path.relative_to(input_dir).as_posix(), stat.st_size, stat.st_mtime_ns))
    return tuple(result)


def _source_signature(files: Sequence[InputFile]) -> tuple[tuple[str, str, str], ...]:
    return tuple(sorted((source.origin, source.source_path, source.digest) for source in files))


def _issue_for_mapping(source: InputFile, message: str, code: str) -> ValidationIssue:
    return ValidationIssue("error", code, message, source.source_path)


def _select_mapping(
    candidates: Sequence[InputFile],
) -> tuple[InputFile | None, MappingResult, tuple[ValidationIssue, ...]]:
    if not candidates:
        st.session_state.pop("mapping_choice", None)
        return None, MappingResult({}, ()), ()

    if len(candidates) == 1:
        st.session_state.pop("mapping_choice", None)
        source = candidates[0]
        return source, _cached_mapping(source.digest, source), ()

    keys = {
        f"{source.origin}|{source.source_path}|{source.digest}": source
        for source in sorted(candidates, key=lambda item: (item.source_path.casefold(), item.origin))
    }
    labels = {
        key: f"{source.source_path} · {source.origin}"
        for key, source in keys.items()
    }
    options: list[str | None] = [None, *keys]
    choice_key = "mapping_choice"
    if choice_key not in st.session_state:
        st.session_state[choice_key] = None
    elif st.session_state[choice_key] not in options:
        st.session_state[choice_key] = None

    selected_key = st.selectbox(
        "Mapping workbook",
        options,
        key=choice_key,
        format_func=lambda key: "Use fallback headings" if key is None else labels[key],
        help="The workbook names the case filters; available values come from filenames.",
    )
    if selected_key is None:
        return None, MappingResult({}, ()), (
            _issue_for_mapping(
                candidates[0],
                "Several mapping workbooks are available. Choose one explicitly or select fallback headings.",
                "mapping_choice_required",
            ),
        )
    source = keys[selected_key]
    result = _cached_mapping(source.digest, source)
    return source, result, ()


def _initial_selection(key: str, label: str, options: Sequence[str], defaults: Sequence[str]) -> list[str]:
    available = list(options)
    if not available:
        st.caption(f"No {label.casefold()} available.")
        return []
    return equipment_pills(label, available, defaults, key=key)


def _set_case_filter_values(key: str, values: tuple[str, ...], selected: bool) -> None:
    st.session_state["case_filters_all"] = False
    for value in values:
        st.session_state[_case_checkbox_key(key, value)] = selected


def _select_all_cases() -> None:
    st.session_state["case_filters_all"] = True


def _case_filter_changed() -> None:
    st.session_state["case_filters_all"] = False


def _case_checkbox_key(key: str, value: str) -> str:
    return f"{key}::v{CASE_FILTER_DEFAULTS_VERSION}::{value}"


def _reset_case_filters() -> None:
    for key in tuple(st.session_state):
        if key.startswith("case_filter_"):
            del st.session_state[key]
    st.session_state["case_filters_all"] = False


def _case_filter_controls(cases: Sequence[CaseData], headings: dict[int, str]) -> list[CaseData]:
    dataset_signature = tuple((case.case_id, case.source_path, case.sha256) for case in cases)
    if (
        st.session_state.get("cases_dataset_signature") != dataset_signature
        or st.session_state.get("case_filter_defaults_version") != CASE_FILTER_DEFAULTS_VERSION
    ):
        _reset_case_filters()
        st.session_state["cases_dataset_signature"] = dataset_signature
        st.session_state["case_filter_defaults_version"] = CASE_FILTER_DEFAULTS_VERSION

    token_count = max((len(case.tokens) for case in cases), default=0)
    if not token_count:
        st.info("No valid CSV cases are available for filtering.")
        return []

    selected_sets: list[set[str]] = []
    for position in range(token_count):
        options = token_values(cases, position, selected_sets)
        key = f"case_filter_{position}"
        label = token_heading(position + 1, headings)
        all_selected = st.session_state.get("case_filters_all", False)
        previous = st.session_state.get(key)
        selection = (
            list(options)
            if all_selected
            else list(options[:1])
            if previous is None
            else [value for value in previous if value in options]
        )
        removed = [] if all_selected or previous is None else [value for value in previous if value not in options]
        if removed:
            st.session_state[key] = selection
            for value in removed:
                checkbox_key = _case_checkbox_key(key, value)
                if checkbox_key in st.session_state:
                    st.session_state[checkbox_key] = False

        for value in options:
            checkbox_key = _case_checkbox_key(key, value)
            if all_selected:
                st.session_state[checkbox_key] = True
            elif checkbox_key not in st.session_state:
                st.session_state[checkbox_key] = value in selection

        selected_count = sum(st.session_state[_case_checkbox_key(key, value)] for value in options)
        with st.container(border=True, gap="small"):
            st.markdown(f"**{position + 1}. {label}** · {selected_count}/{len(options)} selected")
            option_columns = st.columns(2)
            for option_index, value in enumerate(options):
                checkbox_key = _case_checkbox_key(key, value)
                option_columns[option_index % 2].checkbox(
                    value, key=checkbox_key, on_change=_case_filter_changed
                )
            action_columns = st.columns(2)
            action_columns[0].button(
                "Select all",
                key=f"{key}_select_all",
                on_click=_set_case_filter_values,
                args=(key, tuple(options), True),
                disabled=not options,
                width="stretch",
            )
            action_columns[1].button(
                "Clear all",
                key=f"{key}_clear_all",
                on_click=_set_case_filter_values,
                args=(key, tuple(options), False),
                disabled=not options,
                width="stretch",
            )

        selected = [
            value for value in options if st.session_state.get(_case_checkbox_key(key, value), False)
        ]
        st.session_state[key] = selected
        selected_sets.append(set(selected))
        if removed:
            st.caption(f"Removed after earlier filter change: {', '.join(removed)}")

    selected = filter_cases(cases, selected_sets)
    st.caption(f"{len(selected):,} of {len(cases):,} cases selected")
    return selected


def _case_label_map(cases: Sequence[CaseData]) -> dict[str, str]:
    return case_labels(cases, varying_token_positions(cases))


def _plot_layout_control(tab_id: str) -> str:
    layout_key = f"{tab_id}_layout"
    if st.session_state.get(layout_key) is None:
        st.session_state[layout_key] = LAYOUTS[0]
    with st.container(horizontal=True, vertical_alignment="center", gap="small", width="content"):
        st.caption("Plot layout:", width="content")
        return st.segmented_control(
            "Plot layout",
            LAYOUTS,
            key=layout_key,
            width="content",
            label_visibility="collapsed",
        )


def _inline_control_label(label: str) -> None:
    st.caption(f"{label}:", width="content")


def _plot_cache_signature(
    tab_id: str,
    cases: Sequence[CaseData],
    selected_objects: Sequence[str],
    labels: dict[str, str],
    options: PlotOptions,
    settings: dict[str, object],
) -> tuple[object, ...]:
    return (
        PLOT_CACHE_VERSION,
        tab_id,
        tuple((case.case_id, case.source_path, case.sha256) for case in cases),
        tuple(selected_objects),
        tuple(sorted(labels.items())),
        options,
        tuple(sorted(settings.items())),
    )


def _plot_width_key(tab_id: str, layout: str) -> str:
    layout_key = layout.replace(" ", "_").replace("×", "x")
    return f"{tab_id}_plot_width_{layout_key}"


def _plot_panel_width(tab_id: str, layout: str) -> int | None:
    width = st.session_state.get(_plot_width_key(tab_id, layout), {}).get("width")
    return int(width) if width else None


def _measure_plot_panel(tab_id: str, layout: str) -> None:
    key = _plot_width_key(tab_id, layout)
    width = st.session_state.get(key, {}).get("width", 0)
    _PLOT_WIDTH_SENSOR(
        key=key,
        data={"width": width},
        default={"width": 0},
        on_width_change=lambda: None,
        width="stretch",
        height="content",
    )


def _render_plotset(tab_id: str, plot_set: PlotSet, cases: Sequence[CaseData], layout: str) -> None:
    if not cases:
        st.info("No cases match the current filters. Select more values or click All cases in the sidebar.")
        return
    if not plot_set.bundles or not plot_set.figures:
        st.info("No curves are available for the current case and source selections. Check the validation details and axis source.")
        return

    case_count = len({bundle.case.case_id for bundle in plot_set.bundles})
    object_count = len({bundle.element_name for bundle in plot_set.bundles})
    trace_count = sum(len(bundle.curves) for bundle in plot_set.bundles)
    st.caption(f"{case_count:,} cases · {object_count:,} elements · {trace_count:,} curves · {len(plot_set.figures)} panels")

    figures = plot_set.figures
    columns_per_row = 2 if layout == "2×2" else 1
    with st.container(gap="xxsmall" if layout == "2×2" else "small"):
        for start in range(0, len(figures), columns_per_row):
            row_figures = figures[start : start + columns_per_row]
            cols = st.columns(len(row_figures))
            for column, figure_index in zip(cols, range(start, start + len(row_figures))):
                with column:
                    if figure_index == 0:
                        _measure_plot_panel(tab_id, layout)
                    st.plotly_chart(
                        figures[figure_index],
                        key=f"{tab_id}_figure_{figure_index}",
                        width="stretch",
                        config={"displayModeBar": "hover", "responsive": True, "scrollZoom": True},
                    )

    st.download_button(
        "Download plotted data (CSV)",
        data=lambda: plotted_data_csv(plot_set.bundles),
        file_name=f"{tab_id}_plotted_data.csv",
        mime="text/csv",
        key=f"{tab_id}_download",
        on_click="ignore",
    )


def _render_tabs(
    cases: Sequence[CaseData],
    catalogue: ObjectCatalogue,
    label_cases: Sequence[CaseData],
) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    tabs = st.tabs(TAB_NAMES, on_change="rerun", key="plot_tabs")
    active_index = next((index for index, tab in enumerate(tabs) if tab.open), 0)

    with tabs[active_index]:
        if active_index == 0:
            tab_id, source_options, source_key, label = "wtg_pq", catalogue.wtg_pq, "pq_objects", "WTG objects"
            defaults = source_options[:1]
        elif active_index == 1:
            tab_id, source_options, source_key, label = "wtg_voltage", catalogue.wtg_voltage, "voltage_objects", "WTG objects"
            defaults = source_options[:1]
        elif active_index == 2:
            tab_id, source_options, source_key, label = "equipment_loading", catalogue.loading, "loading_objects", "Equipment channels"
            defaults = source_options[:1]
        elif active_index == 3:
            tab_id, source_options, source_key, label = "poc_pq", catalogue.poc, "poc_objects", "POC objects"
            defaults = source_options[:1]
        else:
            tab_id, source_options, source_key, label = "power_factor", catalogue.power_factor, "pf_objects", "Power-factor channels"
            defaults = source_options[:1]

        selected = _initial_selection(source_key, label, source_options, defaults)

        controls_col, layout_col = st.columns([3, 1], vertical_alignment="center")
        with controls_col:
            if active_index == 0:
                with st.container(
                    horizontal=True,
                    horizontal_alignment="left",
                    vertical_alignment="center",
                    gap="small",
                    width="content",
                ):
                    show_qmin = st.checkbox(
                        "Show Qmin", value=True, key="pq_show_qmin", width="content"
                    )
                    show_qmax = st.checkbox(
                        "Show Qmax", value=True, key="pq_show_qmax", width="content"
                    )
            elif active_index == 1:
                min_col, max_col = st.columns([1, 1], vertical_alignment="bottom")
                with min_col.container(horizontal=True, vertical_alignment="center", gap="small"):
                    _inline_control_label("Min voltage (p.u.)")
                    low = st.number_input(
                        "Min voltage (p.u.)",
                        value=0.92,
                        step=0.01,
                        format="%.2f",
                        key="voltage_reference_low",
                        label_visibility="collapsed",
                    )
                with max_col.container(horizontal=True, vertical_alignment="center", gap="small"):
                    _inline_control_label("Max voltage (p.u.)")
                    high = st.number_input(
                        "Max voltage (p.u.)",
                        value=1.08,
                        step=0.01,
                        format="%.2f",
                        key="voltage_reference_high",
                        label_visibility="collapsed",
                    )
            elif active_index == 2:
                source_col, limit_col = st.columns([2, 1], vertical_alignment="bottom")
                x_default = "POC1" if "POC1" in catalogue.poc else (catalogue.poc[0] if catalogue.poc else "")
                if catalogue.poc:
                    with source_col.container(horizontal=True, vertical_alignment="center", gap="small"):
                        _inline_control_label("X-axis source")
                        x_source = st.selectbox(
                            "X-axis source",
                            catalogue.poc,
                            key="loading_x_source",
                            index=catalogue.poc.index(x_default),
                            label_visibility="collapsed",
                        )
                else:
                    x_source = ""
                with limit_col.container(horizontal=True, vertical_alignment="center", gap="small"):
                    _inline_control_label("Loading limit (%)")
                    reference = st.number_input(
                        "Loading limit (%)",
                        min_value=0.0,
                        value=100.0,
                        step=1.0,
                        key="loading_reference_value",
                        label_visibility="collapsed",
                    )
            elif active_index == 4:
                x_col, sign_col = st.columns([1.2, 1.4], vertical_alignment="bottom")
                with x_col.container(horizontal=True, vertical_alignment="center", gap="small"):
                    _inline_control_label("X-axis")
                    x_mode = st.selectbox(
                        "X-axis",
                        ("Sweep index", "Active power interchange"),
                        key="pf_x_mode",
                        label_visibility="collapsed",
                    )
                x_source = "Sweep index"
                if x_mode != "Sweep index":
                    x_default = "POC1" if "POC1" in catalogue.poc else (catalogue.poc[0] if catalogue.poc else "")
                    if catalogue.poc:
                        with x_col.container(horizontal=True, vertical_alignment="center", gap="small"):
                            _inline_control_label("Active interchange source")
                            x_source = st.selectbox(
                                "Active interchange source",
                                catalogue.poc,
                                key="pf_x_source",
                                index=catalogue.poc.index(x_default),
                                label_visibility="collapsed",
                            )
                    else:
                        x_source = ""
                with sign_col.container(horizontal=True, vertical_alignment="center", gap="small"):
                    _inline_control_label("Power-factor sign")
                    sign_mode = st.selectbox(
                        "Power-factor sign",
                        ("Original PowerFactory plot", "Raw exported values", "Invert selected channels"),
                        key="pf_sign_mode",
                        label_visibility="collapsed",
                    )
        with layout_col.container(horizontal_alignment="right", vertical_alignment="center"):
            layout = _plot_layout_control(tab_id)

        if active_index == 1 and low >= high:
            st.warning("Min voltage must be lower than max voltage.")

        options = PlotOptions(layout=layout, panel_width=_plot_panel_width(tab_id, layout))

        labels = _case_label_map(label_cases)

        if not cases:
            result = PlotSet((), (), (), ())
        else:
            build_kwargs: dict[str, object] = {"options": options}
            build_args: tuple = (cases, selected, labels)
            if active_index == 0:
                builder = build_wtg_pq_figures
                build_kwargs.update(show_qmin=show_qmin, show_qmax=show_qmax)
            elif active_index == 1:
                builder = build_wtg_voltage_figures
                build_kwargs.update(
                    show_references=low < high,
                    low_reference=float(low),
                    high_reference=float(high),
                )
            elif active_index == 2:
                builder = build_equipment_loading_figures
                build_args = (cases, selected, x_source, labels)
                build_kwargs.update(loading_reference=float(reference))
            elif active_index == 3:
                builder = build_poc_pq_figures
            else:
                builder = build_power_factor_figures
                build_kwargs.update(x_source=x_source, pf_sign_mode=sign_mode)

            if active_index == 2 and not x_source:
                result = PlotSet((), (), (), ())
            elif active_index == 4 and x_mode != "Sweep index" and not x_source:
                result = PlotSet((), (), (), ())
            else:
                settings = dict(build_kwargs)
                if active_index == 2:
                    settings["x_source"] = x_source
                result = _cached_plot_set(
                    _plot_cache_signature(tab_id, cases, selected, labels, options, settings),
                    builder,
                    build_args,
                    build_kwargs,
                )
        issues.extend(result.issues)
        _render_plotset(tab_id, result, cases, layout)

    return tuple(issues)


def _header_variation_issues(cases: Sequence[CaseData]) -> tuple[ValidationIssue, ...]:
    if len(cases) < 2:
        return ()
    channel_sets = {
        case.case_id: {(channel.object_name, channel.metric_description) for channel in case.channels}
        for case in cases
    }
    union = set().union(*channel_sets.values())
    result = []
    for case in cases:
        missing = union - channel_sets[case.case_id]
        if missing:
            result.append(
                ValidationIssue(
                    "warning",
                    "header_channel_variation",
                    f"{case.filename}: {len(missing)} channel(s) found in other cases are absent here; plotting uses semantic object and metric matches.",
                    case.source_path,
                    case.case_id,
                )
            )
    return tuple(result)


def _group_validation_issues(
    issues: Sequence[ValidationIssue],
) -> tuple[tuple[ValidationIssue, int], ...]:
    groups: dict[tuple[str, str, str, str], list[ValidationIssue]] = {}
    for issue in issues:
        key = (issue.severity, issue.code, issue.message, issue.object_name)
        groups.setdefault(key, []).append(issue)
    return tuple(
        (
            group[0],
            len({issue.source_path for issue in group if issue.source_path}) or len(group),
        )
        for group in groups.values()
    )


def _source_label(source_path: str) -> str:
    normalized = source_path.replace("\\", "/")
    if "!/" in normalized:
        archive, member = normalized.split("!/", 1)
        return f"{PurePosixPath(archive).name} → {member}"
    return PurePosixPath(normalized).name or "—"


def main() -> None:
    st.set_page_config(page_title="Murakami Load-Flow Dashboard", page_icon=str(APP_ICON_PATH), layout="wide")

    with st.sidebar:
        st.image(str(APP_LOGO_PATH), width=210)
        uploaded_values = st.file_uploader(
            "Upload CSV, ZIP or Mapping workbook",
            type=("csv", "zip", "xlsx"),
            accept_multiple_files=True,
            key="source_uploads",
            help="Uploads stay in this browser session and are not written to disk.",
        )

    stat_signature = _local_stat_signature(INPUT_DIR)
    local_files = _cached_local_inputs(INPUT_DIR, stat_signature)
    uploaded_values = uploaded_values or []
    upload_signature = tuple(
        (uploaded.file_id, uploaded.name, uploaded.size)
        for uploaded in uploaded_values
    )
    uploaded_files = _cached_upload_inputs(upload_signature, tuple(uploaded_values))
    source_files = tuple(local_files) + uploaded_files
    source_signature = _source_signature(source_files)
    with st.spinner("Indexing result sources…"):
        expanded, parsed = _cached_parse(source_signature, source_files)
    catalogue = _cached_object_catalogue(source_signature, parsed.cases)

    with st.sidebar:
        _, mapping_result, mapping_selection_issues = _select_mapping(expanded.mapping_files)
        if parsed.cases:
            st.markdown("**Cases**")
            st.button("All cases", key="all_cases", on_click=_select_all_cases, width="stretch")
            selected_cases = _case_filter_controls(parsed.cases, mapping_result.headers)
        else:
            selected_cases = []

    st.header("Murakami Load-Flow")
    if not parsed.cases:
        st.info("Upload a CSV or ZIP in the sidebar to display plots.")
        plot_issues = ()
    else:
        plot_issues = _render_tabs(selected_cases, catalogue, parsed.cases)

    all_issues = [
        *expanded.issues,
        *parsed.issues,
        *mapping_selection_issues,
        *mapping_result.issues,
        *_header_variation_issues(parsed.cases),
        *plot_issues,
    ]
    grouped_issues = _group_validation_issues(all_issues)
    errors = sum(issue.severity == "error" for issue, _ in grouped_issues)
    warnings = sum(issue.severity == "warning" for issue, _ in grouped_issues)
    notes = sum(issue.severity == "info" for issue, _ in grouped_issues)
    error_label = "error" if errors == 1 else "errors"
    warning_label = "warning" if warnings == 1 else "warnings"
    validation_title = (
        "Data validation"
        if not all_issues
        else f"Data validation · {errors} {error_label} · {warnings} {warning_label}"
    )
    with st.expander(validation_title, expanded=errors > 0):
        st.caption(
            f"{len(parsed.cases):,} valid cases from {len(expanded.csv_files):,} CSVs · "
            f"{len(local_files):,} local inputs · {len(uploaded_files):,} uploaded inputs"
        )
        if grouped_issues:
            filenames = {case.case_id: case.filename for case in parsed.cases}
            rows = []
            for issue, affected_files in grouped_issues:
                message = issue.message
                filename = filenames.get(issue.case_id, "")
                if filename and message.startswith(f"{filename}: "):
                    message = message[len(filename) + 2 :]
                row = {
                    "Severity": issue.severity,
                    "Issue": message,
                    "Affected files": affected_files,
                    "File": _source_label(issue.source_path),
                }
                if issue.object_name:
                    row["Object"] = issue.object_name
                rows.append(row)
            st.dataframe(rows, hide_index=True, width="stretch")
            if any(count > 1 for _, count in grouped_issues):
                st.caption("Identical issues are grouped; File shows one example.")
        else:
            st.caption("No data issues.")
        if notes:
            st.caption(f"{notes} informational note(s)")
        st.caption("This dashboard displays existing results; it does not run PowerFactory or assess compliance.")


if __name__ == "__main__":
    main()
