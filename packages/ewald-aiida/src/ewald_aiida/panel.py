"""The AiiDA side bar of EWALD: EWALD's workflow side bar over
:class:`ewald_aiida.source.AiidaWorkflows` (a profile's workflows, the processes they called and
their outputs; a double click opens a whole workflow as one notebook)."""
from __future__ import annotations

from ewald.plugin_api import workflow_panel

#: a small provenance graph, drawn with currentColor so it takes the UI theme's colors
ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><rect x="9.5" y="15.5" width="5" '
        'height="5" rx="1"/><path d="M7.8 7.8l3.4 7.2M16.2 7.8l-3.4 7.2M8.5 6h7"/></svg>')

aiida = workflow_panel("aiida", title="AiiDA", icon=ICON, tooltip="AiiDA: a profile's workflows and their outputs")
