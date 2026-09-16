"""
Builds the interactive dashboard.

Reads everything that `src/` already produced in `data/` and writes one
self-contained page, `dashboard/index.html`, with the data embedded in it. The
page opens straight from the filesystem: no server, no build step, no network
access at runtime.

Embedding rather than fetching is deliberate. A page opened over `file://`
cannot `fetch()` its own sibling JSON (the browser treats every local file as a
separate origin), so a dashboard that loaded `data/*.json` at runtime would work
from a web server and silently show nothing when a teammate double-clicked it.

Standard library only, so this runs with a bare Python and no virtualenv, unlike
the rest of the pipeline. Nothing here recomputes a metric; the one thing it
derives is the graph layout, which is a drawing decision and not a result.

    python src/build_dashboard.py        # -> dashboard/index.html

Inputs (all must already exist):
    data/graphs/network_<name>.graphml   edges + weights
    data/metrics.json                    structure, centralities, communities
    data/dashboard_nodes.csv             per-respondent flat table
    data/dashboard_networks.csv          per-network flat table
    data/dashboard_curves.json           the two swept curves
    data/dynamics_metrics.json           DeGroot / epidemic / null models
    data/cleaned_scores.csv              raw answers, for the respondent panel
    data/question_meta.json              question code -> topic + text
"""

from __future__ import annotations

import csv
import json
import math
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
ROOT = SRC_DIR.parent
DATA_DIR = ROOT / "data"
GRAPH_DIR = DATA_DIR / "graphs"
TEMPLATE_DIR = SRC_DIR / "dashboard_template"
OUT_DIR = ROOT / "dashboard"

NETWORKS = ["overall", "technology", "education", "ethics", "environment"]
TOPICS = ["Technology", "Education", "Ethics", "Environment"]
TOPIC_PREFIX = {"Technology": "T", "Education": "E", "Ethics": "S", "Environment": "V"}
CENTRALITIES = [
    "degree_centrality",
    "closeness_centrality",
    "betweenness_centrality",
    "eigenvector_centrality",
]

# Seeded so the layout is identical on every machine and every rebuild —
# a dashboard that reshuffles itself between runs is impossible to talk about.
SEED = 20260920

GRAPHML_NS = "{http://graphml.graphdrawing.org/xmlns}"


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #


def read_graphml(path: Path) -> tuple[list[str], list[tuple[str, str, float]]]:
    """Node ids in file order and (source, target, weight) triples.

    Hand-rolled rather than `nx.read_graphml` so this script keeps its
    stdlib-only promise. The files `build_network.py` writes are flat:
    one `<key>` for the edge weight, undirected `<edge>` elements, no
    node attributes.
    """
    root = ET.parse(path).getroot()

    weight_keys = {
        key.get("id")
        for key in root.findall(f"{GRAPHML_NS}key")
        if key.get("attr.name") == "weight" and key.get("for") == "edge"
    }

    graph = root.find(f"{GRAPHML_NS}graph")
    nodes = [n.get("id") for n in graph.findall(f"{GRAPHML_NS}node")]

    edges = []
    for edge in graph.findall(f"{GRAPHML_NS}edge"):
        weight = 1.0
        for datum in edge.findall(f"{GRAPHML_NS}data"):
            if datum.get("key") in weight_keys:
                weight = float(datum.text)
        edges.append((edge.get("source"), edge.get("target"), weight))

    return nodes, edges


def read_csv_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_float(value: str | None) -> float | None:
    """CSV cell -> float, with the empty string and `NaN` both meaning missing."""
    if value is None or value == "":
        return None
    number = float(value)
    return None if math.isnan(number) else number


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


# --------------------------------------------------------------------------- #
# layout
# --------------------------------------------------------------------------- #


# ForceAtlas2-style constants. Textbook Fruchterman-Reingold packs these
# components into a blob: its attraction grows with the square of the distance,
# so a core averaging ~15 edges per node collapses to a point while its few
# loosely attached nodes are flung out, and rescaling then leaves the
# structure-carrying part microscopic. (Raising FR's repulsion does not help —
# the model is scale-invariant, so it only rescales the same shape.) Linear
# attraction plus degree-weighted repulsion pushes the hubs apart instead:
# measured on the overall giant component it roughly doubles the median
# nearest-neighbour spacing and drops the share of nodes crowded into the
# middle 40% of the radius from 0.65 to 0.35.
REPULSION = 0.02      # scaled by (degree + 1) on each side
ATTRACTION = 1.0      # along edges, linear in distance
GRAVITY = 0.05        # weak pull to the centre, so nothing drifts off


def spring_layout(
    index: dict[str, int],
    edges: list[tuple[str, str, float]],
    rng: random.Random,
    iterations: int = 600,
) -> list[list[float]]:
    """Lay one connected component out into a unit-ish disc.

    Plain O(n^2) repulsion. The biggest component here is 51 nodes, so the
    naive version costs nothing and avoids a quadtree's approximation.
    """
    n = len(index)
    if n == 1:
        return [[0.0, 0.0]]

    # start on a circle rather than uniformly at random: no coincident points,
    # so the first repulsion step cannot divide by zero
    pos = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        jitter = 0.08
        pos.append(
            [
                math.cos(angle) + rng.uniform(-jitter, jitter),
                math.sin(angle) + rng.uniform(-jitter, jitter),
            ]
        )

    adjacency = [[] for _ in range(n)]
    degree = [0] * n
    for source, target, weight in edges:
        u, v = index[source], index[target]
        adjacency[u].append((v, weight))
        adjacency[v].append((u, weight))
        degree[u] += 1
        degree[v] += 1

    speed = 0.1

    for _ in range(iterations):
        disp = [[0.0, 0.0] for _ in range(n)]

        # repulsion: a hub pushes harder, which is what opens the core up
        for i in range(n):
            for j in range(i + 1, n):
                dx = pos[i][0] - pos[j][0]
                dy = pos[i][1] - pos[j][1]
                dist2 = dx * dx + dy * dy
                if dist2 < 1e-9:
                    dx, dy, dist2 = rng.uniform(-1e-3, 1e-3), rng.uniform(-1e-3, 1e-3), 1e-6
                dist = math.sqrt(dist2)
                force = REPULSION * (degree[i] + 1) * (degree[j] + 1) / dist
                ux, uy = dx / dist, dy / dist
                disp[i][0] += ux * force
                disp[i][1] += uy * force
                disp[j][0] -= ux * force
                disp[j][1] -= uy * force

        for i in range(n):
            for j, weight in adjacency[i]:
                if j <= i:
                    continue
                dx = pos[i][0] - pos[j][0]
                dy = pos[i][1] - pos[j][1]
                dist = math.hypot(dx, dy) or 1e-6
                # similarity weights sit in a narrow band just above the cut, so
                # they are softened rather than used raw
                force = ATTRACTION * dist * (0.6 + 0.4 * weight)
                ux, uy = dx / dist, dy / dist
                disp[i][0] -= ux * force
                disp[i][1] -= uy * force
                disp[j][0] += ux * force
                disp[j][1] += uy * force

            radius = math.hypot(*pos[i]) or 1e-6
            pull = GRAVITY * (degree[i] + 1)
            disp[i][0] -= pos[i][0] / radius * pull
            disp[i][1] -= pos[i][1] / radius * pull

        for i in range(n):
            length = math.hypot(*disp[i]) or 1e-9
            step = min(length, speed)
            pos[i][0] += disp[i][0] / length * step
            pos[i][1] += disp[i][1] / length * step

        speed *= 0.997

    return pos


def normalise(points: list[list[float]]) -> tuple[list[list[float]], float]:
    """Centre on the centroid and report the radius that encloses the points."""
    if not points:
        return points, 0.0
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    centred = [[p[0] - cx, p[1] - cy] for p in points]
    radius = max((math.hypot(*p) for p in centred), default=0.0)
    return centred, radius


def components(nodes: list[str], edges: list[tuple[str, str, float]]) -> list[list[str]]:
    """Connected components, largest first."""
    adjacency = {n: set() for n in nodes}
    for source, target, _ in edges:
        adjacency[source].add(target)
        adjacency[target].add(source)

    seen: set[str] = set()
    found = []
    for node in nodes:
        if node in seen:
            continue
        stack, group = [node], []
        seen.add(node)
        while stack:
            current = stack.pop()
            group.append(current)
            for neighbour in adjacency[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        found.append(group)

    return sorted(found, key=len, reverse=True)


def layout_network(
    nodes: list[str],
    edges: list[tuple[str, str, float]],
    opinion: dict[str, float],
) -> dict[str, tuple[float, float]]:
    """Positions for every respondent: core in the middle, isolates on a rim.

    Around 40% of respondents have no edge at all. Letting a force layout
    scatter them turns the picture into confetti, so the components are placed
    deliberately instead: the giant component takes the centre, the other
    multi-node components ring it, and the isolates go on an outer rim ordered
    by their overall opinion — which makes the rim itself readable rather than
    arbitrary.
    """
    rng = random.Random(SEED)
    groups = components(nodes, edges)

    multi = [g for g in groups if len(g) > 1]
    isolates = [g[0] for g in groups if len(g) == 1]

    placed: dict[str, tuple[float, float]] = {}

    laid_out = []
    for group in multi:
        index = {node: i for i, node in enumerate(group)}
        member = set(group)
        sub_edges = [e for e in edges if e[0] in member and e[1] in member]
        points, radius = normalise(spring_layout(index, sub_edges, rng))
        # a component's drawn size should track its node count, not the
        # accident of how far its force layout happened to spread
        target = 0.46 * math.sqrt(len(group))
        scale = (target / radius) if radius > 1e-6 else 1.0
        laid_out.append((group, [[p[0] * scale, p[1] * scale] for p in points], target))

    # giant component centred, the rest packed around it
    if laid_out:
        group, points, radius = laid_out[0]
        for node, point in zip(group, points):
            placed[node] = (point[0], point[1])
        core_radius = radius

        satellites = laid_out[1:]
        if satellites:
            ring = core_radius + max(r for _, _, r in satellites) + 0.45
            for i, (group, points, _) in enumerate(satellites):
                angle = 2 * math.pi * i / len(satellites) - math.pi / 2
                cx, cy = ring * math.cos(angle), ring * math.sin(angle)
                for node, point in zip(group, points):
                    placed[node] = (cx + point[0], cy + point[1])
    else:
        core_radius = 0.3

    if isolates:
        extent = max((math.hypot(x, y) for x, y in placed.values()), default=core_radius)
        rim = extent + 0.5
        ordered = sorted(isolates, key=lambda n: opinion.get(n, 0.0))
        for i, node in enumerate(ordered):
            angle = 2 * math.pi * i / len(ordered) - math.pi / 2
            placed[node] = (rim * math.cos(angle), rim * math.sin(angle))

    return placed


# --------------------------------------------------------------------------- #
# payload
# --------------------------------------------------------------------------- #


def round_to(value, digits=4):
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, digits)
    return value


def degree_histogram(degrees: list[int]) -> dict:
    """Linear counts per degree, plus the non-empty points for the log-log view."""
    largest = max(degrees) if degrees else 0
    counts = [0] * (largest + 1)
    for degree in degrees:
        counts[degree] += 1

    loglog = [
        {"k": k, "count": count}
        for k, count in enumerate(counts)
        if k > 0 and count > 0
    ]
    return {"counts": counts, "loglog": loglog}


def build_respondents(scores_rows: list[dict], questions: list[str], meta: dict) -> dict:
    """Per-respondent answers and topic means, keyed by id as a string."""
    topic_questions = {
        topic: [q for q in questions if meta[q]["topic"] == topic] for topic in TOPICS
    }

    respondents = {}
    for row in scores_rows:
        rid = str(row["respondent_id"])
        answers = {q: as_float(row.get(q)) for q in questions}

        means = {}
        for topic, codes in topic_questions.items():
            # matches `common.topic_means`: a missing answer counts as 0, the
            # same imputation the similarity matrix was built on
            values = [answers[c] if answers[c] is not None else 0.0 for c in codes]
            means[topic.lower()] = sum(values) / len(values)

        all_values = [v if v is not None else 0.0 for v in answers.values()]
        respondents[rid] = {
            "id": rid,
            "answers": [round_to(answers[q], 2) for q in questions],
            "n_missing": sum(1 for v in answers.values() if v is None),
            "topicMeans": {k: round_to(v, 4) for k, v in means.items()},
            "overall": round_to(sum(all_values) / len(all_values), 4),
        }

    return respondents


def build_network(
    name: str,
    node_rows: dict[str, dict],
    metrics: dict,
    respondents: dict,
) -> dict:
    """Everything the page needs to draw and interrogate one network."""
    graph_nodes, edges = read_graphml(GRAPH_DIR / f"network_{name}.graphml")
    order = {node: i for i, node in enumerate(graph_nodes)}

    opinion = {node: respondents[node]["overall"] for node in graph_nodes}
    positions = layout_network(graph_nodes, edges, opinion)

    centrality = metrics[name]["centrality"]
    partition = metrics[name]["community"]["partition"]

    nodes = []
    for node in graph_nodes:
        row = node_rows[node]
        nodes.append(
            {
                "id": node,
                "x": round_to(positions[node][0], 4),
                "y": round_to(positions[node][1], 4),
                "degree": int(float(row[f"{name}__degree"])),
                "community": int(float(row[f"{name}__community"])),
                "isolate": as_bool(row[f"{name}__is_isolate"]),
                "inGiant": as_bool(row[f"{name}__in_giant"]),
                "degroot": round_to(as_float(row[f"{name}__degroot_limit"]), 4),
                "c": [round_to(centrality[c][node], 6) for c in CENTRALITIES],
            }
        )

    edge_list = [
        [order[source], order[target], round_to(weight, 4)]
        for source, target, weight in edges
    ]

    # ranks are 1-based and computed once here so the page never has to sort 87
    # nodes four times on every hover
    ranks = {}
    for slot, measure in enumerate(CENTRALITIES):
        ordered = sorted(nodes, key=lambda n: -n["c"][slot])
        ranks[measure] = {n["id"]: i + 1 for i, n in enumerate(ordered)}

    sizes: dict[int, int] = {}
    for node in nodes:
        sizes[node["community"]] = sizes.get(node["community"], 0) + 1

    communities = []
    for community_id, size in sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0])):
        members = [n["id"] for n in nodes if n["community"] == community_id]
        means = {
            topic.lower(): sum(respondents[m]["topicMeans"][topic.lower()] for m in members)
            / len(members)
            for topic in TOPICS
        }
        communities.append(
            {
                "id": community_id,
                "size": size,
                "members": members,
                "topicMeans": {k: round_to(v, 4) for k, v in means.items()},
            }
        )

    return {
        "nodes": nodes,
        "edges": edge_list,
        "communities": communities,
        "ranks": ranks,
        "degreeHistogram": degree_histogram([n["degree"] for n in nodes]),
        "structure": metrics[name]["structure"],
        "community": {
            "n_communities": metrics[name]["community"]["n_communities"],
            "modularity": round_to(metrics[name]["community"]["modularity"], 4),
        },
    }


def build_payload() -> dict:
    meta = json.loads((DATA_DIR / "question_meta.json").read_text(encoding="utf-8"))
    metrics = json.loads((DATA_DIR / "metrics.json").read_text(encoding="utf-8"))
    curves = json.loads((DATA_DIR / "dashboard_curves.json").read_text(encoding="utf-8"))
    dynamics = json.loads((DATA_DIR / "dynamics_metrics.json").read_text(encoding="utf-8"))

    scores_rows = read_csv_rows(DATA_DIR / "cleaned_scores.csv")
    questions = [c for c in scores_rows[0] if c != "respondent_id"]
    respondents = build_respondents(scores_rows, questions, meta)

    # the flat node table keys on integers, the graphs on strings; joining the
    # two without this cast quietly yields nothing (see report/VARUN.md)
    node_rows = {str(r["respondent_id"]): r for r in read_csv_rows(DATA_DIR / "dashboard_nodes.csv")}

    network_rows = {r["network"]: r for r in read_csv_rows(DATA_DIR / "dashboard_networks.csv")}
    network_stats = {
        name: {
            key: (value if key == "network" else as_float(value))
            for key, value in row.items()
        }
        for name, row in network_rows.items()
    }

    ids = list(respondents)
    population = {
        topic.lower(): round_to(
            sum(respondents[i]["topicMeans"][topic.lower()] for i in ids) / len(ids), 4
        )
        for topic in TOPICS
    }
    population["overall"] = round_to(
        sum(respondents[i]["overall"] for i in ids) / len(ids), 4
    )

    networks = {
        name: build_network(name, node_rows, metrics, respondents) for name in NETWORKS
    }

    return {
        "meta": {
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "n_respondents": len(ids),
            "n_questions": len(questions),
            "similarity_quantile": curves["baseline_quantile"],
            "networks": NETWORKS,
            "topics": TOPICS,
            "centralities": CENTRALITIES,
        },
        "questions": {
            "order": questions,
            "meta": meta,
            "prefix": TOPIC_PREFIX,
        },
        "population": population,
        "respondents": respondents,
        "networks": networks,
        "networkStats": network_stats,
        "curves": curves,
        "dynamics": {
            "degroot": dynamics["degroot"]["unweighted"],
            "degrootWeighted": dynamics["degroot"]["weighted"],
            "epidemic": dynamics["epidemic"],
            "nullmodels": dynamics["nullmodels"],
            "thresholdSensitivity": {
                "baseline_quantile": dynamics["threshold_sensitivity"]["baseline_quantile"],
                "topic_ordering_holds_at_every_cut": dynamics["threshold_sensitivity"][
                    "topic_ordering_holds_at_every_cut"
                ],
            },
        },
    }


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #


def render(payload: dict) -> str:
    template = (TEMPLATE_DIR / "index.template.html").read_text(encoding="utf-8")
    styles = (TEMPLATE_DIR / "styles.css").read_text(encoding="utf-8")
    script = (TEMPLATE_DIR / "app.js").read_text(encoding="utf-8")

    # `</script>` inside the JSON would close the tag it lives in; escaping the
    # slash keeps the payload valid JSON and inert to the HTML parser
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")

    for placeholder, value in (
        ("/*__STYLES__*/", styles),
        ("/*__DATA__*/", blob),
        ("/*__APP__*/", script),
    ):
        if placeholder not in template:
            raise SystemExit(f"template is missing {placeholder}")
        template = template.replace(placeholder, value)

    return template


def main() -> None:
    print("Building the dashboard")

    missing = [
        path.name
        for path in (
            DATA_DIR / "metrics.json",
            DATA_DIR / "dashboard_nodes.csv",
            DATA_DIR / "dashboard_networks.csv",
            DATA_DIR / "dashboard_curves.json",
            DATA_DIR / "dynamics_metrics.json",
        )
        if not path.exists()
    ]
    if missing:
        raise SystemExit(
            "missing inputs: " + ", ".join(missing) + " — run the pipeline in README.md first"
        )

    payload = build_payload()
    html = render(payload)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "index.html"
    out.write_text(html, encoding="utf-8")

    total_nodes = sum(len(n["nodes"]) for n in payload["networks"].values())
    total_edges = sum(len(n["edges"]) for n in payload["networks"].values())
    print(f"  {len(payload['networks'])} networks, {total_nodes} node records, {total_edges} edges")
    print(f"  wrote dashboard/{out.name}  ({out.stat().st_size / 1024:.0f} KB, self-contained)")
    print("  open it by double-clicking the file — no server needed")


if __name__ == "__main__":
    main()
