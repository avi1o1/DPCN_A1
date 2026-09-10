"""
Static visualisations for the opinion network(s).

Every plot carries a legend/colorbar and an annotation stating the concrete
takeaway, instead of leaving the reader to guess what the colours mean.

Produces, into figures/:
  - network_<name>.png              spring-layout plot, legend for community
                                     colours + isolates, stats box
  - degree_distribution_overall.png linear + log-log degree distribution,
                                     mean-degree line, isolate fraction
  - centrality_overall.png          top-5 nodes per centrality, value labels,
                                     cross-measure overlap called out
  - topic_correlation_heatmap.png   correlation between mean per-respondent
                                     topic scores, most/least aligned pair named
  - community_topic_heatmap.png     mean opinion per topic, per community,
                                     rows labelled with community size
  - topic_comparison.png            giant-component share & clustering by
                                     topic -> which topic has the most consensus
  - isolates_vs_connected.png       are "outlier" respondents more extreme in
                                     their opinions than well-connected ones?
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import networkx as nx
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parent.parent
GRAPH_DIR = ROOT / "data" / "graphs"
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

METRICS_JSON = ROOT / "data" / "metrics.json"
SCORES_CSV = ROOT / "data" / "cleaned_scores.csv"
META_JSON = ROOT / "data" / "question_meta.json"

sns.set_theme(style="whitegrid")


def load_graph(name: str) -> nx.Graph:
    return nx.read_graphml(GRAPH_DIR / f"network_{name.lower()}.graphml")


# Fixed palette so the same community id gets the same colour across figures.
COMMUNITY_PALETTE = plt.get_cmap("tab10").colors
OTHER_COLOR = "cornflowerblue"
ISOLATE_COLOR = "lightgray"


def major_communities(
    partition: dict[str, int], min_size: int = 3, max_shown: int = 8
) -> dict[int, tuple]:
    """Map the largest communities (size >= min_size) to a fixed colour each."""
    sizes: dict[int, int] = {}
    for comm in partition.values():
        sizes[comm] = sizes.get(comm, 0) + 1
    ranked = sorted(
        (c for c, s in sizes.items() if s >= min_size),
        key=lambda c: sizes[c],
        reverse=True,
    )
    return {
        c: COMMUNITY_PALETTE[i % len(COMMUNITY_PALETTE)]
        for i, c in enumerate(ranked[:max_shown])
    }


def plot_network(name: str, partition: dict[str, int]) -> None:
    g = load_graph(name)
    pos = nx.spring_layout(g, seed=42, weight="weight", k=0.4)

    color_map = major_communities(partition)
    isolated = {n for n in g.nodes() if g.degree(n) == 0}

    def node_color(n: str) -> tuple | str:
        if n in isolated:
            return ISOLATE_COLOR
        return color_map.get(partition.get(n), OTHER_COLOR)

    colors = [node_color(n) for n in g.nodes()]

    sizes_by_comm: dict[int, int] = {}
    for comm in partition.values():
        sizes_by_comm[comm] = sizes_by_comm.get(comm, 0) + 1

    fig, ax = plt.subplots(figsize=(9, 8))
    nx.draw_networkx_edges(g, pos, alpha=0.15, ax=ax)
    nx.draw_networkx_nodes(g, pos, node_size=90, node_color=colors, ax=ax)

    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="",
            color=color_map[c],
            label=f"Community {c} (n={sizes_by_comm[c]})",
            markersize=8,
        )
        for c in color_map
    ]
    legend_handles.append(
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="",
            color=OTHER_COLOR,
            label="Other small groups (n<3)",
            markersize=8,
        )
    )
    legend_handles.append(
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="",
            color=ISOLATE_COLOR,
            label=f"Isolated, no strong-similarity link (n={len(isolated)})",
            markersize=8,
        )
    )
    ax.legend(
        handles=legend_handles,
        loc="upper left",
        bbox_to_anchor=(1.0, 1.0),
        fontsize=8,
        frameon=True,
        title="Node colour",
    )

    giant_frac = len(max(nx.connected_components(g), key=len)) / g.number_of_nodes()
    stats_text = (
        f"N={g.number_of_nodes()}  L={g.number_of_edges()}  "
        f"density={nx.density(g):.2f}\n"
        f"giant component={giant_frac:.0%} of respondents  "
        f"{len(set(partition.values()))} Louvain groups"
    )
    ax.text(
        0.01, -0.02, stats_text, transform=ax.transAxes, fontsize=9, va="top", ha="left"
    )

    ax.set_title(
        f"Opinion similarity network — {name.title()}\n"
        f"edge = respondent pair in the top 10% most similar on {name.lower()} questions"
    )
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"network_{name.lower()}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_degree_distribution(name: str = "overall") -> None:
    g = load_graph(name)
    degrees = np.array([d for _, d in g.degree()])
    mean_deg = degrees.mean()
    isolate_frac = (degrees == 0).mean()

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    axes[0].hist(
        degrees,
        bins=range(0, degrees.max() + 2),
        color="steelblue",
        edgecolor="white",
        label="respondents",
    )
    axes[0].axvline(
        mean_deg,
        color="firebrick",
        linestyle="--",
        label=f"mean degree = {mean_deg:.1f}",
    )
    axes[0].set_xlabel("Degree k (# similar-opinion links)")
    axes[0].set_ylabel("Number of respondents")
    axes[0].set_title(
        f"Linear scale — {isolate_frac:.0%} of respondents are isolated (k=0)"
    )
    axes[0].legend(fontsize=8)

    nonzero = degrees[degrees > 0]
    values, counts = np.unique(nonzero, return_counts=True)
    axes[1].scatter(values, counts / counts.sum(), color="firebrick", label="P(k), k>0")
    axes[1].set_xscale("log")
    axes[1].set_yscale("log")
    axes[1].set_xlabel("Degree k (log)")
    axes[1].set_ylabel("P(k) (log)")
    axes[1].set_title(
        f"Log-log — max degree {degrees.max()} vs. mean {mean_deg:.1f}: heavy tail"
    )
    axes[1].legend(fontsize=8)

    fig.suptitle(
        f"Degree distribution — {name.title()} network\n"
        f"A small 'mainstream opinion' core holds most links; many respondents have none"
    )
    fig.tight_layout()
    fig.savefig(
        FIG_DIR / f"degree_distribution_{name.lower()}.png",
        dpi=150,
        bbox_inches="tight",
    )
    plt.close(fig)


def plot_centrality_bars(name: str = "overall") -> None:
    metrics = json.loads(METRICS_JSON.read_text())
    cent = metrics[name]["centrality"]

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    measures = ["degree_top5", "closeness_top5", "betweenness_top5", "eigenvector_top5"]
    titles = [
        "Degree centrality\n(most direct similar-opinion links)",
        "Closeness centrality\n(shortest avg. distance to others)",
        "Betweenness centrality\n(bridges between opinion groups)",
        "Eigenvector centrality\n(linked to other well-connected people)",
    ]

    appearances: dict[str, int] = {}
    for measure in measures:
        for node, _ in cent[measure]:
            appearances[node] = appearances.get(node, 0) + 1

    for ax, measure, title in zip(axes.flat, measures, titles):
        pairs = cent[measure]
        labels = [p[0] for p in pairs]
        values = [p[1] for p in pairs]
        bars = ax.barh(labels, values, color="teal")
        ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=8)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=10)
        ax.set_xlim(0, max(values) * 1.25)

    repeat = sorted(
        [n for n, c in appearances.items() if c >= 3], key=lambda n: -appearances[n]
    )
    note = (
        f"Respondent(s) {', '.join(repeat)} rank top-5 in 3+ measures — most consistently central."
        if repeat
        else "No single respondent dominates all four centrality measures."
    )
    fig.suptitle(
        f"Top-5 respondents by centrality — {name.title()} network\n{note}", fontsize=11
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(
        FIG_DIR / f"centrality_{name.lower()}.png", dpi=150, bbox_inches="tight"
    )
    plt.close(fig)


def respondent_topic_scores() -> pd.DataFrame:
    scores = pd.read_csv(SCORES_CSV, index_col="respondent_id")
    scores.index = scores.index.astype(str)  # graphml/partition keys are strings
    meta = json.loads(META_JSON.read_text())
    topics = sorted({m["topic"] for m in meta.values()})
    topic_scores = pd.DataFrame(index=scores.index)
    for topic in topics:
        cols = [c for c, m in meta.items() if m["topic"] == topic]
        topic_scores[topic] = scores[cols].mean(axis=1)
    return topic_scores


def plot_topic_correlation() -> None:
    topic_scores = respondent_topic_scores()
    corr = topic_scores.corr()

    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool)).stack()
    most_pair, most_val = upper.idxmax(), upper.max()
    least_pair, least_val = upper.idxmin(), upper.min()

    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    sns.heatmap(
        corr,
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        vmin=-1,
        vmax=1,
        ax=ax,
        cbar_kws={"label": "Pearson correlation"},
    )
    ax.set_title(
        "Correlation between respondents' mean topic scores\n"
        f"Most aligned: {most_pair[0]}-{most_pair[1]} (r={most_val:.2f})  |  "
        f"Least: {least_pair[0]}-{least_pair[1]} (r={least_val:.2f})",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(FIG_DIR / "topic_correlation_heatmap.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_community_topic_heatmap() -> None:
    metrics = json.loads(METRICS_JSON.read_text())
    partition = metrics["overall"]["community"]["partition"]
    topic_scores = respondent_topic_scores()
    topic_scores["community"] = topic_scores.index.map(partition)

    sizes = topic_scores["community"].value_counts()
    keep = sizes[sizes >= 3].index  # ignore singleton/near-singleton communities
    grouped = (
        topic_scores[topic_scores["community"].isin(keep)].groupby("community").mean()
    )
    ordered = sizes[keep].sort_values(ascending=False).index
    grouped = grouped.loc[ordered]
    grouped.index = [f"C{c} (n={sizes[c]})" for c in ordered]

    fig, ax = plt.subplots(figsize=(6.5, max(3, 0.45 * len(grouped))))
    sns.heatmap(
        grouped,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        center=0,
        ax=ax,
        cbar_kws={"label": "mean score (-2 Strongly Disagree .. +2 Strongly Agree)"},
    )
    ax.set_xlabel("Topic")
    ax.set_ylabel("Community (Louvain, overall network, size >= 3)")
    ax.set_title(
        "Do opinion communities actually disagree on anything?\n"
        "Rows = groups of respondents who are mutually similar overall"
    )
    fig.tight_layout()
    fig.savefig(FIG_DIR / "community_topic_heatmap.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_topic_comparison() -> None:
    """Which topic does the class actually agree on? Compare giant-component share
    and clustering across the 4 per-topic networks — both are proxies for consensus."""
    metrics = json.loads(METRICS_JSON.read_text())
    topics = ["technology", "education", "ethics", "environment"]
    giant_frac = [metrics[t]["structure"]["giant_component_fraction"] for t in topics]
    clustering = [metrics[t]["structure"]["avg_clustering"] for t in topics]

    x = np.arange(len(topics))
    width = 0.35
    fig, ax = plt.subplots(figsize=(7, 5))
    bars1 = ax.bar(
        x - width / 2,
        giant_frac,
        width,
        color="darkorange",
        label="Giant component share\n(fraction in one connected opinion cluster)",
    )
    bars2 = ax.bar(
        x + width / 2,
        clustering,
        width,
        color="seagreen",
        label="Avg. clustering coefficient\n(do a person's similar-peers also agree with each other?)",
    )
    ax.bar_label(bars1, fmt="%.2f", fontsize=8)
    ax.bar_label(bars2, fmt="%.2f", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([t.title() for t in topics])
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Score (0-1)")
    best = topics[int(np.argmax(giant_frac))]
    worst = topics[int(np.argmin(giant_frac))]
    ax.set_title(
        f"Consensus by topic — most agreement on {best.title()}, least on {worst.title()}"
    )
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "topic_comparison.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_isolates_vs_connected(name: str = "overall") -> None:
    """Are respondents with no strong-similarity link just extreme/idiosyncratic
    outliers, or are they simply average people who happen to fall just under the
    similarity threshold? Compare mean |score| (opinion extremity) between the two
    groups with a t-test."""
    g = load_graph(name)
    scores = pd.read_csv(SCORES_CSV, index_col="respondent_id")
    scores.index = scores.index.astype(str)
    q_cols = [c for c in scores.columns]
    extremity = scores[q_cols].abs().mean(axis=1)

    isolated_ids = [n for n in g.nodes() if g.degree(n) == 0]
    connected_ids = [n for n in g.nodes() if g.degree(n) > 0]
    iso_vals = extremity.loc[isolated_ids].dropna()
    con_vals = extremity.loc[connected_ids].dropna()

    t_stat, p_val = stats.ttest_ind(iso_vals, con_vals, equal_var=False)

    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    box = ax.boxplot(
        [con_vals, iso_vals],
        tick_labels=[f"Connected (n={len(con_vals)})", f"Isolated (n={len(iso_vals)})"],
        patch_artist=True,
        widths=0.5,
    )
    for patch, color in zip(box["boxes"], ["seagreen", "lightgray"]):
        patch.set_facecolor(color)
    ax.set_ylabel(
        "Mean |score| per respondent\n(0=all Neutral, 2=all Strongly [Dis]Agree)"
    )
    sig = "significant" if p_val < 0.05 else "not significant"
    direction = "more" if iso_vals.mean() > con_vals.mean() else "less"
    ax.set_title(
        f"Isolated respondents hold {direction} extreme opinions than connected ones\n"
        f"mean {con_vals.mean():.2f} (connected) vs {iso_vals.mean():.2f} (isolated), "
        f"Welch t-test p={p_val:.3f} ({sig})",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(
        FIG_DIR / f"isolates_vs_connected_{name.lower()}.png",
        dpi=150,
        bbox_inches="tight",
    )
    plt.close(fig)


if __name__ == "__main__":
    metrics = json.loads(METRICS_JSON.read_text())
    names = ["overall", "technology", "education", "ethics", "environment"]
    for name in names:
        partition = metrics[name]["community"]["partition"]
        plot_network(name, partition)
    plot_degree_distribution("overall")
    plot_centrality_bars("overall")
    plot_topic_correlation()
    plot_community_topic_heatmap()
    plot_topic_comparison()
    plot_isolates_vs_connected("overall")
    print(f"Figures written to {FIG_DIR}")
    print(f"Figures written to {FIG_DIR}")
