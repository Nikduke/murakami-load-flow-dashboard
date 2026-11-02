"""Compact equipment chips with single-click and modifier-click selection."""

from collections.abc import Sequence

import streamlit as st


_HTML = '<div id="equipment-pills" role="group"></div>'
_CSS = """
#equipment-pills {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
}

.equipment-pill {
  appearance: none;
  flex: 0 0 auto;
  width: auto;
  max-width: 100%;
  border: 1px solid #bfd5bb;
  border-radius: 999px;
  padding: 0.35rem 0.8rem;
  background: #eaf4e8;
  color: #263329;
  font: inherit;
  line-height: 1.2;
  text-align: center;
  cursor: pointer;
}

.equipment-pill[aria-pressed="true"] {
  border-color: #d39b35;
  background: #fff0d2;
  box-shadow: inset 0 0 0 1px #d39b35;
}

.equipment-pill:hover {
  border-color: #78936f;
}

.equipment-pill[aria-pressed="true"]:hover {
  border-color: #b67818;
}

.equipment-pill:focus-visible {
  outline: 2px solid var(--st-primary-color);
  outline-offset: 2px;
}
"""
_JS = """
export default function (component) {
  const { data, parentElement, setStateValue } = component
  const root = parentElement.querySelector("#equipment-pills")
  if (!root) return

  const options = Array.isArray(data?.options) ? data.options : []
  const selected = new Set(data?.selected ?? [])
  root.setAttribute("aria-label", data?.label ?? "Equipment")
  root.replaceChildren()

  for (const option of options) {
    const button = document.createElement("button")
    button.type = "button"
    button.className = "equipment-pill"
    button.textContent = option
    button.setAttribute("aria-pressed", String(selected.has(option)))
    button.addEventListener("click", (event) => {
      const additive = event.ctrlKey || event.metaKey
      const next = additive ? new Set(selected) : new Set()
      if (additive && selected.has(option)) next.delete(option)
      else next.add(option)
      setStateValue("selected", options.filter((value) => next.has(value)))
    })
    root.append(button)
  }
}
"""

_PILL_SELECTOR = st.components.v2.component(
    "murakami_equipment_pills",
    html=_HTML,
    css=_CSS,
    js=_JS,
)


def _store_selection(component_key: str, selection_key: str) -> None:
    state = st.session_state.get(component_key, {})
    st.session_state[selection_key] = list(state.get("selected", []))


def equipment_pills(
    label: str,
    options: Sequence[str],
    defaults: Sequence[str],
    *,
    key: str,
) -> list[str]:
    available = list(options)
    if not available:
        st.caption(f"No {label.casefold()} available.")
        return []

    current = st.session_state.get(key, list(defaults))
    selected = [option for option in available if option in current]
    st.session_state[key] = selected
    st.caption(f"{label} · click selects one · Ctrl-click adds/removes")

    component_key = f"{key}_selector"
    _PILL_SELECTOR(
        key=component_key,
        data={"label": label, "options": available, "selected": selected},
        default={"selected": selected},
        width="stretch",
        height="content",
        on_selected_change=lambda: _store_selection(component_key, key),
    )
    return selected
