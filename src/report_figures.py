"""
Publication-style figures for report/report.tex.

These are deliberately separate from `visualize.py`. That module writes the
exploratory figure set (seaborn defaults, in-figure titles, annotation boxes).
The report needs the opposite: a serif face that matches the document, no
in-figure titles because the caption carries them, no decorative colour, and a
vector output so the text stays sharp at print size.

Every number is read from the pipeline outputs in data/. Nothing here recomputes
the networks; the only derived quantity is the DeGroot trajectory, which is a
replay of the saved graph and the saved initial opinions.

Writes into figures/report/:
  overview.pdf    component split per network + core-vs-isolate opinion ECDF
  structure.pdf   degree CCDF (log-log) + top-10 degree centrality
  networks.pdf    node-link views: overall by community, technology by opinion
  dynamics.pdf    DeGroot trajectories + SIS sweep + threshold sensitivity
  nullmodels.pdf  z-scores against the two null ensembles
  heatmap.pdf     mean opinion per community per topic
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
GRAPH_DIR = DATA / "graphs"
OUT_DIR = ROOT / "figures" / "report"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NETWORKS = ["overall", "technology", "education", "ethics", "environment"]
LABEL = {n: n.capitalize() for n in NETWORKS}

# ---------------------------------------------------------------- style ----
# One column of the report is 17 cm wide. Sizes below are in inches so that a
# figure drawn at width=\linewidth is reproduced at 1:1 and the 8 pt tick text
# lands at 8 pt on the page.
TEXT_WIDTH_IN = 6.7

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["CMU Serif", "Latin Modern Roman", "DejaVu Serif"],
    "mathtext.fontset": "cm",
    "font.size": 8.5,
    "axes.titlesize": 9,
    "axes.labelsize": 8.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5,
    "axes.linewidth": 0.6,
    "axes.edgecolor": "#333333",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#cccccc",
    "grid.linewidth": 0.4,
    "grid.alpha": 0.8,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "lines.linewidth": 1.1,
    "lines.markersize": 3.0,
    "legend.frameon": False,
    "figure.dpi": 200,
    "savefig.dpi": 400,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
    "pdf.fonttype": 42,
})

# Print-safe, ordered so that the greys read as the neutral category and the
# five series stay separable in greyscale.
INK = "#1b1f24"
GREY = "#8a8f98"
LIGHT = "#d8dade"
SERIES = ["#1f3b73", "#b3452a", "#3f7d4e", "#8a6d1f", "#6b3a70"]
NET_COLOR = dict(zip(NETWORKS, SERIES))


def panel_tag(ax, text: str, dx: float = -0.10, dy: float = 1.06) -> None:
    """(a), (b), ... in the corner. The LaTeX caption carries the wording."""
    ax.text(dx, dy, text, transform=ax.transAxes, fontsize=9,
            fontweight="bold", va="top", ha="left", color=INK)


def save(fig, name: str) -> None:
    path = OUT_DIR / name
    fig.savefig(path)
    plt.close(fig)
    print(f"wrote {path.relative_to(ROOT)}")


# ----------------------------------------------------------------- data ----
def load_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


METRICS = load_json(DATA / "metrics.json")
DYNAMICS = load_json(DATA / "dynamics_metrics.json")
CURVES = load_json(DATA / "dashboard_curves.json")
NODES = pd.read_csv(DATA / "dashboard_nodes.csv")
NETS = pd.read_csv(DATA / "dashboard_networks.csv").set_index("network")


def load_graph(name: str) -> nx.Graph:
    return nx.read_graphml(GRAPH_DIR / f"network_{name}.graphml")


# ------------------------------------------------------------ figure 1 -----
def fig_overview() -> None:
    """Where the 87 respondents sit, and who the disconnected ones are."""
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(TEXT_WIDTH_IN, 2.1),
        gridspec_kw={"width_ratios": [1.15, 1.0], "wspace": 0.34},
    )

    # (a) giant component / other components / isolates, per network.
    giant, middle, isolated = [], [], []
    for net in NETWORKS:
        n = METRICS[net]["structure"]["n_nodes"]
        g = round(METRICS[net]["structure"]["giant_component_fraction"] * n)
        iso = int(NETS.loc[net, "n_isolated"])
        giant.append(100 * g / n)
        isolated.append(100 * iso / n)
        middle.append(100 * (n - g - iso) / n)

    y = np.arange(len(NETWORKS))[::-1]
    h = 0.62
    ax1.barh(y, giant, h, color=SERIES[0], edgecolor="white", linewidth=0.5,
             label="Giant component")
    ax1.barh(y, middle, h, left=giant, color=GREY, edgecolor="white",
             linewidth=0.5, label="Other components")
    ax1.barh(y, isolated, h, left=np.add(giant, middle), color=LIGHT,
             edgecolor="white", linewidth=0.5, label="Isolates")
    ax1.set_yticks(y, [LABEL[n] for n in NETWORKS])
    ax1.set_xlim(0, 100)
    ax1.set_xlabel("Share of the 87 respondents (%)")
    ax1.xaxis.grid(True)
    ax1.yaxis.grid(False)
    ax1.set_axisbelow(True)
    ax1.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=3,
               handlelength=1.1, columnspacing=1.2, borderpad=0.0)
    panel_tag(ax1, "(a)", dx=-0.22, dy=1.22)

    # (b) do the disconnected respondents hold different opinions?
    core = NODES.loc[~NODES["overall__is_isolate"], "opinion_overall"].to_numpy()
    iso = NODES.loc[NODES["overall__is_isolate"], "opinion_overall"].to_numpy()
    for values, color, style, name in (
        (core, SERIES[0], "-", f"Connected core ($n={core.size}$)"),
        (iso, SERIES[1], "--", f"Isolates ($n={iso.size}$)"),
    ):
        xs = np.sort(values)
        ys = np.arange(1, xs.size + 1) / xs.size
        ax2.step(xs, ys, where="post", color=color, linestyle=style, label=name)
        ax2.axvline(xs.mean(), linestyle=":", linewidth=0.7, color=color)
    ax2.set_xlabel("Mean opinion score ($-2$ disagree to $+2$ agree)")
    ax2.set_ylabel("Cumulative share")
    ax2.set_ylim(0, 1.02)
    handles, _ = ax2.get_legend_handles_labels()
    handles.append(Line2D([], [], color=GREY, linestyle=":", linewidth=0.7,
                          label="Group mean"))
    ax2.legend(handles=handles, loc="upper left", handlelength=1.3,
               borderpad=0.0, labelspacing=0.25, fontsize=6.8,
               handletextpad=0.5, borderaxespad=0.3)
    panel_tag(ax2, "(b)", dx=-0.19, dy=1.22)

    save(fig, "overview.pdf")


# ------------------------------------------------------------ figure 2 -----
def fig_structure() -> None:
    """Degree distribution and the top of the degree-centrality ranking."""
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(TEXT_WIDTH_IN, 2.0),
        gridspec_kw={"width_ratios": [1.0, 1.0], "wspace": 0.28},
    )

    degrees = np.asarray(METRICS["overall"]["structure"]["degree_sequence"])
    n = degrees.size
    n_iso = int((degrees == 0).sum())
    ks = np.unique(degrees[degrees > 0])
    ccdf = np.array([(degrees >= k).sum() / n for k in ks])

    ax1.loglog(ks, ccdf, marker="o", color=SERIES[0], markerfacecolor="white",
               markeredgewidth=0.8, linewidth=0.9,
               label=f"{n - n_iso} connected respondents")
    ax1.set_xlabel("Degree $k$")
    ax1.set_ylabel(r"$P(K \geq k)$")
    ax1.axvline(degrees.mean(), color=GREY, linestyle="--", linewidth=0.7,
                label=rf"$\langle k \rangle = {degrees.mean():.1f}$")
    ax1.grid(True, which="both")
    ax1.legend(loc="lower left", handlelength=1.6, labelspacing=0.2,
               borderaxespad=0.3)
    panel_tag(ax1, "(a)", dx=-0.19)

    # metrics.json stores only the top 5, so take the top 10 from the exported
    # per-node table. Ties are broken by respondent id, as in the dashboard.
    top = (NODES[["respondent_id", "overall__degree_centrality"]]
           .sort_values(["overall__degree_centrality", "respondent_id"],
                        ascending=[False, True])
           .head(10))
    names = [str(v) for v in top["respondent_id"]][::-1]
    vals = list(top["overall__degree_centrality"])[::-1]
    pos = np.arange(len(names))
    ax2.barh(pos, vals, 0.68, color=SERIES[0], edgecolor="none")
    ax2.set_yticks(pos, names)
    ax2.set_ylabel("Respondent id")
    ax2.set_xlabel("Degree centrality")
    ax2.set_xlim(0, max(vals) * 1.05)
    ax2.xaxis.grid(True)
    ax2.yaxis.grid(False)
    ax2.set_axisbelow(True)
    panel_tag(ax2, "(b)", dx=-0.19)

    save(fig, "structure.pdf")


# ------------------------------------------------------------ figure 3 -----
def _unit(pos: dict, pct: float = 100.0) -> dict:
    """Centre a layout on the origin and scale it to roughly unit radius.

    Scaling by the furthest node lets one long spoke shrink the whole core, so
    the caller can scale by a percentile of the radii instead and let the few
    outliers sit slightly beyond 1.
    """
    if not pos:
        return pos
    arr = np.array(list(pos.values()))
    arr = arr - arr.mean(axis=0)
    span = max(float(np.percentile(np.linalg.norm(arr, axis=1), pct)), 1e-9)
    return {v: p / span for v, p in zip(pos, arr)}


def _layout(g: nx.Graph, seed: int = 7) -> dict:
    """Giant component in the centre, small components and isolates on rings.

    A single spring layout over the whole graph pushes the detached pieces far
    apart, and once the drawing is scaled to fit them the giant component
    shrinks to a blob. Laying each component out on its own and then placing
    the pieces keeps the core at a readable size and still shows how many
    respondents sit outside it.
    """
    comps = sorted(nx.connected_components(g), key=len, reverse=True)
    giant = g.subgraph(comps[0]) if comps else g
    pos = _unit(nx.spring_layout(
        giant, seed=seed, k=3.0 / np.sqrt(max(giant.number_of_nodes(), 1)),
        iterations=800), pct=94.0)

    small = [c for c in comps[1:] if len(c) > 1]
    for i, comp in enumerate(small):
        theta = 2 * np.pi * (i + 0.5) / max(len(small), 1)
        centre = np.array([1.26 * np.cos(theta), 1.26 * np.sin(theta)])
        sub = _unit(nx.spring_layout(g.subgraph(comp), seed=seed, iterations=200))
        for v, p in sub.items():
            pos[v] = centre + 0.09 * p

    isolates = [v for v in g.nodes if g.degree(v) == 0]
    for i, v in enumerate(isolates):
        theta = 2 * np.pi * i / max(len(isolates), 1)
        pos[v] = np.array([1.48 * np.cos(theta), 1.48 * np.sin(theta)])
    return pos


def _draw(ax, g: nx.Graph, pos: dict, colors, sizes) -> None:
    nx.draw_networkx_edges(ax=ax, G=g, pos=pos, width=0.28, edge_color="#b6bac0",
                           alpha=0.8)
    nx.draw_networkx_nodes(ax=ax, G=g, pos=pos, node_color=colors,
                           node_size=sizes, linewidths=0.3, edgecolors="white")
    ax.set_axis_off()
    ax.set_aspect("equal")
    ax.set_xlim(-1.62, 1.62)
    ax.set_ylim(-1.62, 1.62)


def fig_networks() -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(TEXT_WIDTH_IN, 2.95))

    # (a) overall, coloured by Louvain community.
    g = load_graph("overall")
    partition = {k: int(v) for k, v in METRICS["overall"]["community"]["partition"].items()}
    sizes_by_comm: dict[int, int] = {}
    for c in partition.values():
        sizes_by_comm[c] = sizes_by_comm.get(c, 0) + 1
    top_comms = sorted((c for c, s in sizes_by_comm.items() if s >= 3),
                       key=lambda c: -sizes_by_comm[c])[:4]
    comm_color = {c: SERIES[i] for i, c in enumerate(top_comms)}

    pos = _layout(g)
    degs = dict(g.degree())
    colors = [comm_color.get(partition.get(v, -1), LIGHT if degs[v] == 0 else GREY)
              for v in g.nodes]
    sizes = [5 + 5.0 * degs[v] for v in g.nodes]
    _draw(ax1, g, pos, colors, sizes)
    handles = [Line2D([], [], marker="o", linestyle="", markersize=4,
                      markerfacecolor=comm_color[c], markeredgecolor="none",
                      label=f"C{c} ($n={sizes_by_comm[c]}$)") for c in top_comms]
    handles += [
        Line2D([], [], marker="o", linestyle="", markersize=4,
               markerfacecolor=GREY, markeredgecolor="none",
               label="Smaller groups"),
        Line2D([], [], marker="o", linestyle="", markersize=4,
               markerfacecolor=LIGHT, markeredgecolor="none", label="Isolates"),
    ]
    ax1.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.11),
               ncol=3, handletextpad=0.3, columnspacing=1.0, borderpad=0.0)
    panel_tag(ax1, "(a)", dx=0.0, dy=1.0)

    # (b) technology, coloured by mean opinion on that topic.
    g2 = load_graph("technology")
    opinion = NODES.set_index(NODES["respondent_id"].astype(str))["opinion_technology"]
    pos2 = _layout(g2, seed=11)
    degs2 = dict(g2.degree())
    vals = np.array([opinion.get(v, np.nan) for v in g2.nodes], dtype=float)
    cmap = plt.get_cmap("RdBu_r")
    vmin, vmax = np.nanmin(vals), np.nanmax(vals)
    norm = plt.Normalize(vmin=vmin, vmax=vmax)
    colors2 = cmap(norm(vals))
    sizes2 = [5 + 5.0 * degs2[v] for v in g2.nodes]
    _draw(ax2, g2, pos2, colors2, sizes2)
    cax = ax2.inset_axes([0.14, -0.05, 0.72, 0.035])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax,
                      orientation="horizontal")
    cb.set_label("Mean Technology score", labelpad=1.5)
    cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(width=0.4, length=2, pad=1.5)
    panel_tag(ax2, "(b)", dx=0.0, dy=1.0)

    fig.subplots_adjust(wspace=0.02)
    save(fig, "networks.pdf")


# ------------------------------------------------------------ figure 4 -----
def _degroot_trajectory(name: str, steps: int = 30) -> tuple[np.ndarray, np.ndarray]:
    """Replay x(t+1) = D^-1 A x(t) on the saved graph and saved start values."""
    g = load_graph(name)
    order = list(g.nodes)
    a = nx.to_numpy_array(g, nodelist=order, weight=None)
    deg = a.sum(axis=1)
    w = np.divide(a, deg[:, None], out=np.zeros_like(a), where=deg[:, None] > 0)
    w[deg == 0, :] = 0.0
    start = NODES.set_index(NODES["respondent_id"].astype(str))[f"opinion_{name}"]
    x = np.array([start[v] for v in order], dtype=float)
    traj = [x.copy()]
    for _ in range(steps):
        x = np.where(deg > 0, w @ x, x)
        traj.append(x.copy())
    return np.vstack(traj), deg


def fig_dynamics() -> None:
    fig, axes = plt.subplots(
        1, 3, figsize=(TEXT_WIDTH_IN, 2.0),
        gridspec_kw={"wspace": 0.46},
    )
    ax1, ax2, ax3 = axes

    # (a) DeGroot trajectories on the overall network. The core collapses onto
    # the consensus within a handful of rounds, so a short horizon shows the
    # shape; Table 4 carries the tolerance-based step count.
    horizon = 12
    traj, deg = _degroot_trajectory("overall", steps=horizon)
    t = np.arange(traj.shape[0])
    moving = deg > 0
    for i in np.flatnonzero(~moving):
        ax1.plot(t, traj[:, i], color=LIGHT, linewidth=0.5, zorder=1)
    for i in np.flatnonzero(moving):
        ax1.plot(t, traj[:, i], color=SERIES[0], linewidth=0.45, alpha=0.5,
                 zorder=2)
    consensus = DYNAMICS["degroot"]["unweighted"]["overall"]["consensus_giant"]
    ax1.axhline(consensus, color=INK, linestyle="--", linewidth=0.7, zorder=3)
    ax1.set_xlabel("DeGroot step $t$")
    ax1.set_ylabel("Opinion $x_i(t)$")
    ax1.set_xlim(0, horizon)
    ax1.set_ylim(-0.55, 2.35)
    ax1.legend(handles=[
        Line2D([], [], color=SERIES[0], linewidth=1.0,
               label=f"Core ($n={int(moving.sum())}$)"),
        Line2D([], [], color=LIGHT, linewidth=1.0,
               label=f"Isolates ($n={int((~moving).sum())}$)"),
        Line2D([], [], color=INK, linestyle="--", linewidth=0.7,
               label=f"Consensus {consensus:.2f}"),
    ], loc="upper right", handlelength=1.4, labelspacing=0.2, fontsize=6.8,
        borderaxespad=0.2)
    panel_tag(ax1, "(a)", dx=-0.30)

    # (b) SIS prevalence against the mean-field threshold.
    for net in ("overall", "technology"):
        c = CURVES["sis_sweep"][net]
        ax2.plot(c["x_ratio_over_threshold"], 100 * np.asarray(c["y_prevalence"]),
                 color=NET_COLOR[net], label=LABEL[net],
                 linestyle="-" if net == "overall" else "--")
    ax2.axvline(1.0, color=INK, linestyle=":", linewidth=0.8,
                label=r"predicted $\lambda_c$")
    ax2.set_xlabel(r"$\lambda / \lambda_c$")
    ax2.set_ylabel("Endemic prevalence (%)")
    ax2.set_xlim(0, 4)
    ax2.set_ylim(0, 55)
    ax2.legend(loc="upper left", handlelength=1.6, labelspacing=0.2,
               fontsize=6.8, borderaxespad=0.2)
    panel_tag(ax2, "(b)", dx=-0.30)

    # (c) the similarity cut-off sweep.
    sweep = CURVES["threshold_sweep"]
    baseline = sweep.get("baseline_quantile", 0.90)
    for net in NETWORKS:
        c = sweep[net]
        ax3.plot(c["x_quantile"], 100 * np.asarray(c["y_giant_fraction"]),
                 color=NET_COLOR[net], label=LABEL[net],
                 linewidth=1.2 if net == "overall" else 0.9,
                 linestyle="-" if net == "overall" else "--")
    ax3.axvline(baseline, color=INK, linestyle=":", linewidth=0.8,
                label=f"$q = {baseline:.2f}$ (used)")
    ax3.set_xlabel("Similarity quantile $q$ kept as edges")
    ax3.set_ylabel("Giant component (%)")
    ax3.set_ylim(0, 105)
    ax3.legend(loc="lower left", handlelength=1.3, ncol=1, labelspacing=0.15,
               fontsize=6.8, handletextpad=0.4, borderaxespad=0.2)
    panel_tag(ax3, "(c)", dx=-0.30)

    save(fig, "dynamics.pdf")


# ------------------------------------------------------------ figure 5 -----
def fig_nullmodels() -> None:
    nm = DYNAMICS["nullmodels"]
    stats = [
        ("avg_clustering", "Average clustering"),
        ("giant_fraction", "Giant fraction"),
        ("avg_path_length", "Average path length"),
        ("modularity", "Modularity"),
    ]
    er = [nm["vs_erdos_renyi"][k]["z_score"] for k, _ in stats]
    cm = [nm["vs_configuration_model"][k]["z_score"] for k, _ in stats]

    fig, ax = plt.subplots(figsize=(TEXT_WIDTH_IN * 0.82, 1.7))
    y = np.arange(len(stats))[::-1]
    off = 0.18
    ax.axvspan(-2, 2, color="#eceef1", zorder=0)
    for yi, v in zip(y + off, er):
        ax.plot([0, v], [yi, yi], color=SERIES[1], linewidth=1.0, zorder=2)
        ax.plot([v], [yi], "o", color=SERIES[1], markersize=3.6, zorder=3)
    for yi, v in zip(y - off, cm):
        ax.plot([0, v], [yi, yi], color=SERIES[2], linewidth=1.0, zorder=2)
        ax.plot([v], [yi], "s", color=SERIES[2], markersize=3.2, zorder=3)

    ax.set_xscale("symlog", linthresh=2, linscale=0.7)
    ax.set_xlim(-900, 300)
    ax.axvline(0, color=INK, linewidth=0.7, zorder=1)
    ax.set_xticks([-100, -10, -2, 0, 2, 10, 100])
    ax.set_xticklabels(["$-100$", "$-10$", "$-2$", "0", "2", "10", "100"])
    ax.set_yticks(y, [name for _, name in stats])
    ax.set_ylim(y.min() - 0.6, y.max() + 0.6)
    ax.set_xlabel(r"$z$-score against %d null graphs (symmetric-log axis)"
                  % nm["n_null_graphs"])
    ax.xaxis.grid(True)
    ax.yaxis.grid(False)
    ax.legend(handles=[
        Line2D([], [], color=SERIES[1], marker="o", markersize=3.6,
               label="vs. Erdős–Rényi"),
        Line2D([], [], color=SERIES[2], marker="s", markersize=3.2,
               label="vs. configuration model"),
        Patch(facecolor="#eceef1", edgecolor="none", label=r"$|z| < 2$"),
    ], loc="upper left", ncol=1, handlelength=1.6, borderpad=0.0,
        labelspacing=0.2, fontsize=7)
    ax.set_axisbelow(False)

    save(fig, "nullmodels.pdf")


# ------------------------------------------------------------ figure 6 -----
def fig_heatmap() -> None:
    partition = {k: int(v) for k, v in METRICS["overall"]["community"]["partition"].items()}
    nodes = NODES.copy()
    nodes["community"] = nodes["respondent_id"].astype(str).map(partition)
    topics = ["technology", "education", "ethics", "environment"]

    counts = nodes["community"].value_counts()
    keep = [c for c in counts.index if counts[c] >= 3]
    keep = sorted(keep, key=lambda c: -counts[c])
    grid = np.array([[nodes.loc[nodes["community"] == c, f"opinion_{t}"].mean()
                      for t in topics] for c in keep])

    # A dot plot rather than a heat map: the reader takes each value off the
    # shared x axis instead of from a number printed in a coloured cell.
    fig, ax = plt.subplots(figsize=(TEXT_WIDTH_IN * 0.72, 1.45))
    rows = np.arange(len(topics))[::-1]
    markers = ["o", "s", "^", "D", "v"]
    spread = np.linspace(0.26, -0.26, len(keep))
    for ci, c in enumerate(keep):
        ax.plot(grid[ci], rows + spread[ci], linestyle="none",
                marker=markers[ci % len(markers)],
                color=SERIES[ci % len(SERIES)], markersize=3.6,
                label=f"C{c} ($n={counts[c]}$)")
    class_mean = [nodes[f"opinion_{t}"].mean() for t in topics]
    ax.plot(class_mean, rows, linestyle="none", marker="|", color=INK,
            markersize=9, markeredgewidth=1.0, label="Class mean")

    ax.set_yticks(rows, [t.capitalize() for t in topics])
    ax.set_ylim(rows.min() - 0.55, rows.max() + 0.55)
    ax.set_xlabel("Mean opinion score ($-2$ disagree to $+2$ agree)")
    ax.set_ylabel("Topic")
    ax.xaxis.grid(True)
    ax.yaxis.grid(False)
    ax.set_axisbelow(True)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), handlelength=1.0,
              labelspacing=0.35, borderpad=0.0, fontsize=7)

    save(fig, "heatmap.pdf")


def main() -> None:
    fig_overview()
    fig_structure()
    fig_networks()
    fig_dynamics()
    fig_nullmodels()
    fig_heatmap()


if __name__ == "__main__":
    main()
