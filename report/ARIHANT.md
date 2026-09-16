# Arihant's part: the interactive dashboard

## How to open it

Double-click **`dashboard/index.html`**, or open it from a browser's file menu. That is the
whole procedure. No server, no `pip install`, no internet connection, no build step. The data,
the styles and the code all live inside that one file, so it works just as well from a zip of
the repo or a USB stick.

For the report: *"Open `dashboard/index.html` in any modern browser. No server required."*

## How to rebuild it

```bash
python src/build_dashboard.py     # -> dashboard/index.html
```

Run it after anything in `data/` changes. It reads `data/` and writes one file. Unlike the rest
of the pipeline it needs no third-party packages, so it runs on a bare Python with no
virtualenv. It does not recompute a single metric. Every number on the page comes from
`metrics.json`, `dynamics_metrics.json`, or the `dashboard_*` tables that Aviral and Varun
already produced.

The sources live in `src/dashboard_template/` (`index.template.html`, `styles.css`, `app.js`)
and the build inlines all three. Edit those, not `dashboard/index.html`, which is generated and
gets overwritten on every build.

## What is in it

One control scopes the whole page: the network picker in the header. Pick `Overall`,
`Technology`, `Education`, `Ethics` or `Environment` and every number, chart and table
re-renders for that network. Each network keeps the same colour everywhere on the page.

Against the five features in `ARIHANT_tasks.md`:

| Brief | Where it is | Notes |
|---|---|---|
| 1. Network view per topic, community colour, centrality size, hover tooltip | The network | Canvas node-link view. Drag to pan, scroll to zoom, drag a dot to move it, click to select. Hover gives degree, all four centralities with the respondent's rank on each, community, and their DeGroot limit. Colour switches between community and opinion; size switches between the four centralities or uniform. Switching networks tweens the same 87 dots from one layout to the next, so you can watch who moves. |
| 2. Isolate toggle | The network, `Isolates` switch | Hides the roughly 40% with no edge and refits the view. |
| 3. Degree distribution, linear and log-log | Structure | Interactive, with a hover readout per bar and a `Table` twin. The log-log view says outright that k = 0 cannot be plotted on a log axis, rather than silently dropping 36 people. |
| 4. Community by topic heatmap | Communities | Diverging blue to red around the class mean. Hover gives group mean, class mean, difference and group size. Clicking a cell jumps to the network with that community isolated. |
| 5. Respondent lookup | The network inspector, and Respondent profile | Search by id, click a dot, or click a bar in the centrality chart. The inspector gives centralities, ranks, community and opinion-against-class bars. The profile below shows all 60 raw answers as a coloured grid, with the question text on hover. |

Four sections go past the brief, because the data was there and the report needs them.

**The five networks side by side** puts giant component, clustering, modularity and isolate
count across all five networks as small multiples. Clicking a column switches to that network.

**Dynamics** has three panels: a before-and-after view of the DeGroot process, which connects
every respondent's starting opinion to where they settle and turns "the core converges, the
isolates never move" into a picture rather than a sentence; the SIS sweep against the spectral
threshold; and the threshold-sensitivity sweep across quantiles 0.50 to 0.99, with a crosshair.

**Is any of this more than chance?** plots the null-model z-scores on a symmetric-log axis with
the |z| < 2 band drawn, so "ER fails everything, the configuration model matches everything"
reads at a glance.

**What the picture says** carries the four conclusions with their numbers filled in live from
the panels above, so they cannot drift out of sync with the data.

Every chart has a `Table` button that reveals the same numbers as a table. Nothing on the page
is reachable only by hovering.

## Decisions worth defending in the viva

### The data is embedded, not fetched

A page opened over `file://` cannot `fetch()` its own sibling JSON, because the browser treats
every local file as a separate origin. A dashboard that loaded `data/*.json` at runtime would
work perfectly on a web server and show a blank page the moment a teammate double-clicked it.
Embedding costs about 337 KB and removes the whole failure mode.

### No pyvis, no plotly

The brief suggested both. Neither is installed in this environment, both pull in a CDN at
runtime so the page breaks offline, and neither gives control over how the network is drawn.
The charts here are hand-drawn SVG and the network is a canvas, which is why the five networks
can tween into each other and why the whole thing is one file with no dependencies. The cost is
that it is a lot more code than `net.show(...)`.

### Four community colours, not six

The palette was checked with a colour-vision validator rather than by eye. A node-link diagram
is an all-pairs comparison, since any two dots can end up next to each other, and on that test
no five- or six-colour subset of the palette clears the separation floors. The worst pair drops
to a delta-E of 3.2 against a floor of 6. Four colours clear it.

So the four largest communities get a hue, any further group of three or more gets the neutral
tone plus an outline, and singletons get the neutral tone with no outline. The outline is a
second, non-colour channel saying "still a group, just not hued", which stops a 7-person
community from reading as noise. Every community, hued or not, is individually selectable from
the legend, so identity never rests on colour alone. The legend says all of this on the page.

### Opinion is a second colour mode, not decoration

Switching colour to `Opinion` on a topic network paints each dot by that respondent's mean score
on that topic, diverging around the class mean. On Technology it makes the central finding
visible straight away: the enthusiastic answerers sit in the middle and the lukewarm ones sit on
the rim.

### The layout is deliberate

The giant component is laid out in the centre, other multi-node components ring it, and the
isolates sit on an outer rim ordered by their overall opinion, so the rim reads as something
rather than as scatter.

Textbook Fruchterman-Reingold packed these cores into an unreadable blob, because its attraction
grows with the square of the distance and these cores average about 15 edges per node. Raising
its repulsion does nothing, since the model is scale-invariant and only rescales the same shape.
The layout uses linear attraction with degree-weighted repulsion instead. Measured on the overall
giant component, that roughly doubles the median nearest-neighbour spacing. The seed is fixed, so
the picture is identical on every machine and every rebuild.

## Known limits

The SIS sweep only has curves for `overall` and `technology`. That is what
`dynamics_metrics.json` contains, not a dashboard limitation.

Null models were run on the overall network only, so that section does not change with the
network picker. The section says so.

The community-by-topic grid describes the groups, it does not define them. Varun's permutation
test on the four topic means does not separate them (p = 0.108). The note under the grid says
this, and it should stay in whatever goes into the PDF.

Dragging a node moves that dot but does not re-run the layout, so the other dots stay put. It is
for pulling a node out of the crowd to read it, not for re-laying-out the graph.

## For the person assembling the PDF

Four screenshots worth taking, all from the overall network unless stated:

1. The network, colour set to community, isolates on. The core-plus-halo picture makes the "36
   of 87 have no strong-similarity partner" finding in one image, which no table does.
2. The network on Technology, colour set to opinion. Enthusiastic answerers in the middle,
   lukewarm on the rim.
3. Where opinions settle (DeGroot). The funnel of the core collapsing onto 1.41 while the
   isolate lines stay flat.
4. Is any of this more than chance? The z-score chart replaces a paragraph.

The static `figures/*.png` are still the right thing for anything that has to print. The
dashboard is the thing to demo, and the file to hand in alongside the PDF.
