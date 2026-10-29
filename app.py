"""Streamlit interface for PowerFactory load-flow CSV sweeps."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import streamlit as st

from case_filters import case_labels, filter_cases, natural_key, token_values, varying_token_positions
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
TAB_NAMES = ("WTG P–Q", "WTG Terminal Voltage", "Equipment Loading", "POC P–Q", "Power Factor")
LAYOUTS = ("1 plot", "1×2", "2×2")
DISTRIBUTIONS = ("Auto", "By element", "By case")


@st.cache_data(show_spinner=False, max_entries=4)
def _cached_local_inputs(_input_dir: Path, signature: tuple[tuple[str, int, int], ...]) -> tuple[InputFile, ...]:
    # The stat signature invalidates this read when a local file changes; the path is excluded from cache hashing.
    del signature
    return discover_local_inputs(_input_dir)


@st.cache_data(show_spinner="Reading CSV results…", max_entries=4)
def _cached_parse(signature: tuple[tuple[str, str, str], ...], _files: tuple[InputFile, ...]) -> tuple[ExpandedInputs, ParseResult]:
    del signature
    expanded = expand_inputs(_files)
    parsed = parse_cases(expanded.csv_files)
    return expanded, parsed


@st.cache_data(show_spinner=False, max_entries=16)
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


def _select_mapping(candidates: Sequence[InputFile]) -> tuple[InputFile | None, tuple[ValidationIssue, ...]]:
    if not candidates:
        st.session_state.pop("mapping_choice", None)
        return None, ()

    keys = {
        f"{source.origin}|{source.source_path}|{source.digest}": source
        for source in candidates
    }
    labels = {
        key: f"{source.source_path} · {source.origin}"
        for key, source in keys.items()
    }
    options: list[str | None] = [None, *keys]
    choice_key = "mapping_choice"
    if choice_key not in st.session_state:
        st.session_state[choice_key] = next(iter(keys)) if len(keys) == 1 else None
    elif st.session_state[choice_key] not in options:
        st.session_state[choice_key] = None

    selected_key = st.selectbox(
        "Token heading mapping",
        options,
        key=choice_key,
        format_func=lambda key: "Use fallback headings" if key is None else labels[key],
        help="A selected workbook changes token headings only. Token values still come from filenames.",
    )
    if len(keys) > 1 and selected_key is None:
        return None, (
            _issue_for_mapping(
                candidates[0],
                "Several mapping workbooks are available. Choose one explicitly or select fallback headings.",
                "mapping_choice_required",
            ),
        )
    if selected_key is None:
        return None, ()
    source = keys[selected_key]
    result = _cached_mapping(source.digest, source)
    return source, result.issues


def _initial_selection(key: str, options: Sequence[str], defaults: Sequence[str]) -> list[str]:
    available = list(options)
    if key not in st.session_state:
        st.session_state[key] = [value for value in defaults if value in available]
    else:
        old = list(st.session_state[key] or [])
        valid = [value for value in old if value in available]
        if valid != old:
            st.session_state[key] = valid
            removed = [value for value in old if value not in available]
            st.info(f"Removed unavailable selection(s) from {key.removeprefix('select_')}: {', '.join(removed)}")
    return st.multiselect("Selected objects", available, key=key, label_visibility="collapsed", select_all=1000)


def _case_filter_controls(cases: Sequence[CaseData], headings: dict[int, str]) -> list[CaseData]:
    token_count = max((len(case.tokens) for case in cases), default=0)
    if not token_count:
        st.info("No valid CSV cases are available for filtering.")
        return []

    selected_sets: list[set[str]] = []
    removed_by_position: dict[int, list[str]] = {}
    options_by_position: list[list[str]] = []
    for position in range(token_count):
        options = token_values(cases, position, selected_sets)
        options_by_position.append(options)
        key = f"case_filter_{position}"
        if key not in st.session_state:
            selection = options[:1]
            st.session_state[key] = selection
        else:
            old = list(st.session_state[key] or [])
            selection = [value for value in old if value in options]
            if selection != old:
                removed_by_position[position] = [value for value in old if value not in options]
                st.session_state[key] = selection
        selected_sets.append(set(selection))

    for position, options in enumerate(options_by_position):
        key = f"case_filter_{position}"
        label = token_heading(position + 1, headings)
        eligible_count = len(filter_cases(cases, selected_sets[:position]))
        current_count = len(filter_cases(cases, selected_sets[: position + 1]))
        columns = st.columns([3, 1, 1])
        with columns[0]:
            st.multiselect(
                f"{position + 1}. {label} · {len(options)} values · {eligible_count} cases before filter",
                options,
                key=key,
                select_all=1000,
                help="Options are limited to cases matching all earlier token selections.",
            )
        with columns[1]:
            st.button(
                "Select all",
                key=f"all_{position}",
                disabled=not options,
                on_click=lambda state_key=key, values=options: st.session_state.__setitem__(state_key, list(values)),
                width="stretch",
            )
        with columns[2]:
            st.button(
                "Clear",
                key=f"clear_{position}",
                disabled=not options,
                on_click=lambda state_key=key: st.session_state.__setitem__(state_key, []),
                width="stretch",
            )
        if position in removed_by_position:
            removed = ", ".join(removed_by_position[position])
            st.info(f"{label}: removed values no longer available after an earlier filter change: {removed}")
        st.caption(f"{label}: {current_count} case(s) remain after this filter.")
        selected_sets[position] = set(st.session_state.get(key, []))

    selected = filter_cases(cases, selected_sets)
    st.write(f"**{len(selected)} case(s) selected**")
    return selected


def _label_controls(cases: Sequence[CaseData], headings: dict[int, str]) -> dict[str, str]:
    width = max((len(case.tokens) for case in cases), default=0)
    options = list(range(width))
    defaults = varying_token_positions(cases)
    key = "legend_token_positions"
    if key not in st.session_state:
        st.session_state[key] = defaults
    else:
        st.session_state[key] = [position for position in st.session_state[key] if position in options]
    selected = st.multiselect(
        "Legend labels use token positions",
        options,
        key=key,
        format_func=lambda position: f"{position + 1}: {token_heading(position + 1, headings)}",
        help="The default includes token positions that vary among the selected cases. Collisions receive a case ID suffix.",
    )
    return case_labels(cases, selected)


def _tab_plot_options(tab_id: str) -> PlotOptions:
    first, second, third = st.columns([1, 1, 2])
    with first:
        layout = st.selectbox("Layout", LAYOUTS, key=f"{tab_id}_layout")
    with second:
        distribution = st.selectbox("Bundle distribution", DISTRIBUTIONS, key=f"{tab_id}_distribution")
    with third:
        independent = st.checkbox(
            "Independent axis ranges per panel",
            key=f"{tab_id}_independent_ranges",
            help="When enabled, each subplot chooses its own visible range.",
        )

    x_range = y_range = None
    with st.expander("Axis limits", expanded=False):
        x_enabled, y_enabled = st.columns(2)
        x_on = x_enabled.checkbox("Set X-axis limits", key=f"{tab_id}_x_on")
        y_on = y_enabled.checkbox("Set Y-axis limits", key=f"{tab_id}_y_on")
        cols = st.columns(4)
        x_min = cols[0].number_input("X minimum", key=f"{tab_id}_x_min", value=0.0, format="%.6g", disabled=not x_on)
        x_max = cols[1].number_input("X maximum", key=f"{tab_id}_x_max", value=1.0, format="%.6g", disabled=not x_on)
        y_min = cols[2].number_input("Y minimum", key=f"{tab_id}_y_min", value=0.0, format="%.6g", disabled=not y_on)
        y_max = cols[3].number_input("Y maximum", key=f"{tab_id}_y_max", value=1.0, format="%.6g", disabled=not y_on)
        if x_on:
            if x_min >= x_max:
                st.warning("X minimum must be less than X maximum; automatic limits are in use.")
            else:
                x_range = (float(x_min), float(x_max))
        if y_on:
            if y_min >= y_max:
                st.warning("Y minimum must be less than Y maximum; automatic limits are in use.")
            else:
                y_range = (float(y_min), float(y_max))
    return PlotOptions(
        layout=layout,
        distribution=distribution,
        independent_ranges=independent,
        x_range=x_range,
        y_range=y_range,
    )


def _render_plotset(tab_id: str, plot_set: PlotSet, cases: Sequence[CaseData], object_selection: Sequence[str]) -> None:
    if not plot_set.bundles or not plot_set.figures:
        st.info("No curves are available for the current case and source selections. Check the validation details and axis source.")
        return

    trace_count = sum(len(bundle.curves) for bundle in plot_set.bundles)
    if trace_count > 30:
        st.info(f"{trace_count} traces are plotted. Use the Plotly legend to hide or isolate traces; the source list below identifies every selection.")
    st.caption(
        f"{len(plot_set.bundles)} element × case bundle(s) · {trace_count} trace(s) · "
        f"distribution: {plot_set.distribution_used}"
    )

    figures = plot_set.figures
    for start in range(0, len(figures), 2):
        row_figures = figures[start : start + 2]
        cols = st.columns(len(row_figures))
        for column, figure_index in zip(cols, range(start, start + len(row_figures))):
            with column:
                st.plotly_chart(
                    figures[figure_index],
                    key=f"{tab_id}_figure_{figure_index}",
                    width="stretch",
                    config={"displayModeBar": True, "responsive": True, "scrollZoom": True},
                )

    st.download_button(
        "Download plotted data (CSV)",
        data=plotted_data_csv(plot_set.bundles),
        file_name=f"{tab_id}_plotted_data.csv",
        mime="text/csv",
        key=f"{tab_id}_download",
    )
    with st.expander("Plotted sources and cases", expanded=False):
        st.write("**Sources:** " + (", ".join(object_selection) if object_selection else "none"))
        st.write("**Cases:**")
        st.dataframe(
            [
                {
                    "Case label": bundle.curves[0].case_label,
                    "Filename": bundle.case.filename,
                    "Source path": bundle.case.source_path,
                    "Source object": bundle.element_name,
                    "Curves in bundle": len(bundle.curves),
                }
                for bundle in plot_set.bundles
            ],
            hide_index=True,
            width="stretch",
        )


def _eligible_objects(cases: Sequence[CaseData], role_pair: tuple[str, str] | None = None) -> list[str]:
    names = discover_wtg_objects(cases)
    if role_pair is None:
        return names
    return [
        name
        for name in names
        if any(
            resolve_channel(case, name, role_pair[0]).status == "found"
            and resolve_channel(case, name, role_pair[1]).status == "found"
            for case in cases
        )
    ]


def _render_tabs(cases: Sequence[CaseData], all_cases: Sequence[CaseData], headings: dict[int, str]) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    labels = _label_controls(cases, headings)
    tabs = st.tabs(TAB_NAMES, on_change="rerun", key="plot_tabs")

    if tabs[0].open:
        with tabs[0]:
            source_options = _eligible_objects(all_cases, ("active_power", "reactive_power"))
            selected = _initial_selection("pq_objects", source_options, source_options[:3])
            options = _tab_plot_options("pq")
            show_qmin = st.checkbox("Show Qmin capability boundaries", value=True, key="pq_show_qmin")
            show_qmax = st.checkbox("Show Qmax capability boundaries", value=True, key="pq_show_qmax")
            result = build_wtg_pq_figures(cases, selected, labels, options=options, show_qmin=show_qmin, show_qmax=show_qmax)
            issues.extend(result.issues)
            _render_plotset("wtg_pq", result, cases, selected)

    if tabs[1].open:
        with tabs[1]:
            source_options = _eligible_objects(all_cases, ("active_power", "voltage"))
            default = st.session_state.get("voltage_objects", st.session_state.get("pq_objects", source_options[:3]))
            selected = _initial_selection("voltage_objects", source_options, default)
            options = _tab_plot_options("voltage")
            show_references = st.checkbox("Show optional voltage display references", value=True, key="voltage_references")
            refs = st.columns(2)
            low = refs[0].number_input("Lower display reference (p.u.)", value=0.92, key="voltage_reference_low", disabled=not show_references)
            high = refs[1].number_input("Upper display reference (p.u.)", value=1.08, key="voltage_reference_high", disabled=not show_references)
            if show_references and low >= high:
                st.warning("The lower display reference must be below the upper reference.")
            result = build_wtg_voltage_figures(
                cases,
                selected,
                labels,
                options=options,
                show_references=show_references and low < high,
                low_reference=float(low),
                high_reference=float(high),
            )
            issues.extend(result.issues)
            _render_plotset("wtg_voltage", result, cases, selected)
            st.caption("These editable lines are visual references only; they are not universal limits or a compliance assessment.")

    if tabs[2].open:
        with tabs[2]:
            source_options = discover_loading_objects(all_cases)
            selected = _initial_selection("loading_objects", source_options, source_options[:3])
            poc_options = discover_poc_objects(all_cases)
            x_default = "POC1" if "POC1" in poc_options else (poc_options[0] if poc_options else "")
            if poc_options:
                x_source = st.selectbox(
                    "Active interchange X-axis source",
                    poc_options,
                    key="loading_x_source",
                    index=poc_options.index(x_default),
                )
            else:
                x_source = ""
                st.info("No POC active-interchange source is available for the X-axis.")
            options = _tab_plot_options("loading")
            show_reference = st.checkbox("Show loading display reference", value=True, key="loading_reference_on")
            reference = st.number_input("Loading reference (%)", value=100.0, key="loading_reference_value", disabled=not show_reference)
            result = build_equipment_loading_figures(
                cases,
                selected,
                x_source,
                labels,
                options=options,
                show_reference=show_reference,
                loading_reference=float(reference),
            ) if x_source else PlotSet((), (), (), (), "Auto", None, None)
            issues.extend(result.issues)
            _render_plotset("equipment_loading", result, cases, selected)

    if tabs[3].open:
        with tabs[3]:
            source_options = discover_poc_objects(all_cases)
            selected = _initial_selection("poc_objects", source_options, source_options[:3])
            options = _tab_plot_options("poc")
            result = build_poc_pq_figures(cases, selected, labels, options=options)
            issues.extend(result.issues)
            _render_plotset("poc_pq", result, cases, selected)

    if tabs[4].open:
        with tabs[4]:
            source_options = discover_power_factor_objects(all_cases)
            defaults = [name for name in ("Exp_Cable_1", "Exp_Cable_2") if name in source_options]
            selected = _initial_selection("pf_objects", source_options, defaults or source_options[:3])
            options = _tab_plot_options("pf")
            x_mode = st.selectbox("X-axis", ("Sweep index", "Active power interchange"), key="pf_x_mode")
            x_source = "Sweep index"
            if x_mode != "Sweep index":
                poc_options = discover_poc_objects(all_cases)
                default_source = "POC1" if "POC1" in poc_options else (poc_options[0] if poc_options else "")
                if poc_options:
                    x_source = st.selectbox(
                        "Active interchange source",
                        poc_options,
                        key="pf_x_source",
                        index=poc_options.index(default_source),
                    )
                else:
                    x_source = ""
                    st.info("No POC active-interchange source is available for the X-axis.")
            sign_mode = st.selectbox(
                "Power-factor sign",
                ("Original PowerFactory plot", "Raw exported values", "Invert selected channels"),
                key="pf_sign_mode",
                help="The original plot sign is verified for Exp_Cable_1 and Exp_Cable_2. Other channels remain raw by default.",
            )
            result = build_power_factor_figures(cases, selected, labels, options=options, x_source=x_source, pf_sign_mode=sign_mode) if x_source else PlotSet((), (), (), (), "Auto", None, None)
            issues.extend(result.issues)
            _render_plotset("power_factor", result, cases, selected)

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


def _clear_uploads() -> None:
    st.session_state["upload_generation"] = st.session_state.get("upload_generation", 0) + 1


def _reload_local() -> None:
    st.cache_data.clear()
    st.session_state["local_reload_count"] = st.session_state.get("local_reload_count", 0) + 1


def main() -> None:
    st.set_page_config(page_title="Murakami Load-Flow Dashboard", page_icon="⚡", layout="wide")
    st.title("PowerFactory Load-Flow Dashboard")
    st.caption("Explore load-flow sweep results from two-header-row PowerFactory CSV exports.")

    upload_key = f"source_uploads_{st.session_state.get('upload_generation', 0)}"
    with st.sidebar:
        st.header("Data sources")
        left, right = st.columns(2)
        left.button("Reload local files", key="reload_local", on_click=_reload_local, width="stretch")
        right.button("Clear uploads", key="clear_uploads", on_click=_clear_uploads, width="stretch")
        st.file_uploader(
            "Upload CSV, ZIP or Mapping workbook",
            type=("csv", "zip", "xlsx"),
            accept_multiple_files=True,
            key=upload_key,
            help="Files stay in this browser session and are not written to disk.",
        )
        st.caption(f"Local inputs are read recursively from `{INPUT_DIR.relative_to(APP_DIR).as_posix()}/`.")

    stat_signature = _local_stat_signature(INPUT_DIR)
    local_files = _cached_local_inputs(INPUT_DIR, stat_signature)
    uploaded_values = st.session_state.get(upload_key) or []
    uploaded_files = tuple(
        InputFile(
            name=uploaded.name,
            source_path=f"upload:/{uploaded.name}",
            content=uploaded.getvalue(),
            origin="upload",
        )
        for uploaded in uploaded_values
    )
    source_files = tuple(local_files) + uploaded_files
    with st.spinner("Indexing result sources…"):
        expanded, parsed = _cached_parse(_source_signature(source_files), source_files)

    mapping_source, mapping_issues = _select_mapping(expanded.mapping_files)
    mapping_headers: dict[int, str] = {}
    if mapping_source is not None:
        mapping_result = _cached_mapping(mapping_source.digest, mapping_source)
        mapping_headers = mapping_result.headers
        mapping_issues = (*mapping_issues, *mapping_result.issues)

    top = st.columns(4)
    top[0].metric("Valid cases", f"{len(parsed.cases):,}")
    top[1].metric("WTG objects", f"{len(discover_wtg_objects(parsed.cases)):,}")
    top[2].metric("Loading objects", f"{len(discover_loading_objects(parsed.cases)):,}")
    top[3].metric("POC objects", f"{len(discover_poc_objects(parsed.cases)):,}")
    st.caption(f"Power-factor objects discovered: {len(discover_power_factor_objects(parsed.cases)):,} · Source files: {len(expanded.csv_files):,} CSV, {len(expanded.mapping_files):,} mapping workbook(s)")

    for issue in (*expanded.issues, *parsed.issues):
        if issue.severity == "error":
            st.error(issue.message)
    if not parsed.cases:
        st.info("Add CSV exports to `Input_files/` or upload CSV/ZIP files to begin.")

    st.subheader("Global case filters")
    selected_cases = _case_filter_controls(parsed.cases, mapping_headers)
    st.divider()
    plot_issues = _render_tabs(selected_cases, parsed.cases, mapping_headers)

    all_issues = [*expanded.issues, *parsed.issues, *mapping_issues, *_header_variation_issues(parsed.cases), *plot_issues]
    with st.expander("Data validation and sources", expanded=False):
        st.write(f"Local CSV/ZIP/workbook sources: {len(local_files)} · Uploaded sources: {len(uploaded_files)}")
        st.write(f"Expanded CSV cases: {len(expanded.csv_files)} · Valid cases: {len(parsed.cases)} · Selected cases: {len(selected_cases)}")
        st.write(f"Selected mapping: {mapping_source.source_path if mapping_source else 'fallback headings'}")
        if all_issues:
            st.write(f"{sum(issue.severity == 'error' for issue in all_issues)} error(s) · {sum(issue.severity == 'warning' for issue in all_issues)} warning(s) · {sum(issue.severity == 'info' for issue in all_issues)} note(s)")
            st.dataframe(
                [
                    {
                        "Severity": issue.severity,
                        "Code": issue.code,
                        "Message": issue.message,
                        "Source": issue.source_path,
                        "Case": issue.case_id,
                        "Object": issue.object_name,
                        "Column": issue.column_position,
                    }
                    for issue in all_issues
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.success("No data or mapping issues detected.")
        st.caption("This dashboard displays existing CSV results; it does not run PowerFactory calculations or make compliance assessments.")


if __name__ == "__main__":
    main()
