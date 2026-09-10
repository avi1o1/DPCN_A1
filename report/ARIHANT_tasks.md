# Arihant's part — interactive dashboard

Everything you need already exists in `data/` — don't recompute metrics, just load and visualize them interactively. Goal: one self-contained HTML page (or small local web app) where you can explore the opinion network(s) instead of only looking at static PNGs.

## Data available to load

| File | Contents |
|---|---|
| `data/graphs/network_<name>.graphml` | 5 graphs: `overall`, `technology`, `education`, `ethics`, `environment` — nodes = respondents, weighted edges = opinion similarity |
| `data/metrics.json` | per network: degree/centrality values for every node, Louvain community assignment per node, structural summary (density, clustering, components, etc.) |
| `data/cleaned_scores.csv` | raw per-question numeric scores per respondent, if you want tooltips showing someone's actual answers |
| `data/question_meta.json` | question code → {topic, text}, for labeling |
| (later) `data/dynamics_metrics.json` | Varun's dynamics results — not ready yet, check before you need it |

## Suggested approach

**Recommended stack:** Python + [`pyvis`](https://pyvis.readthedocs.io/) for the network view (renders an interactive vis.js graph to a single HTML file — easiest path to "drag nodes around, hover for info") plus [`plotly`](https://plotly.com/python/) for the charts (degree distribution, centrality bars) so they're interactive too, not static PNGs. Both are pure client-side HTML+JS output, no server needed — good for embedding in the report repo and opening directly in a browser.

```python
from pyvis.network import Network
import networkx as nx, json

g = nx.read_graphml("data/graphs/network_overall.graphml")
metrics = json.load(open("data/metrics.json"))
partition = metrics["overall"]["community"]["partition"]  # node_id -> community int

net = Network(height="800px", width="100%", notebook=False)
for node in g.nodes():
    net.add_node(node, label=node, group=partition.get(node, -1),
                 title=f"degree centrality: {metrics['overall']['centrality']['degree_centrality'][node]:.3f}")
for u, v, data in g.edges(data=True):
    net.add_edge(u, v, value=data.get("weight", 1))
net.show("dashboard/network_overall.html")
```

## Features worth building (roughly in priority order)

1. **Network view per topic**: a dropdown/tabs to switch between the 5 networks (`overall`/`technology`/`education`/`ethics`/`environment`), nodes coloured by community, node size scaled by degree centrality, hover tooltip showing all 4 centrality values for that respondent.
2. **Isolate toggle**: since ~40% of nodes are isolated in most networks (no strong-similarity edge), let the user show/hide isolated nodes — otherwise the view gets cluttered (see `figures/network_overall.png` for what it looks like static).
3. **Degree distribution chart** (plotly): linear + log-log, same data as `figures/degree_distribution_overall.png` but interactive/zoomable.
4. **Community × topic heatmap** (plotly): interactive version of `figures/community_topic_heatmap.png` — hover to see exact mean score per cell.
5. **Respondent lookup**: type/select a respondent id, show their raw answers (`data/cleaned_scores.csv`) next to their centrality ranks and which community they're in.

## Output

Put everything under `dashboard/` (already created, empty). A single `dashboard/index.html` that links out to (or embeds via iframe) the per-network pyvis views and plotly charts is fine — it doesn't need a build step or framework. Note in the report which URL/file to open and how (e.g. "open `dashboard/index.html` directly in a browser, no server required").

Ping me if you need a different data shape out of `metrics.json` (e.g. flattened tables) — easier to adjust the export than to have you re-derive things from the graphml by hand.
