# Varun's part: dynamics, epidemic threshold, null models

Aviral built the network. This part examines what happens on it.

There are four pieces of work. Opinion dynamics, an epidemic threshold, three
null models, and a test of how much the results depend on the edge threshold.

No script here builds a graph. Each script reads `data/graphs/`,
`data/cleaned_scores.csv` and `data/metrics.json`, which `src/data_prep.py`,
`src/build_network.py` and `src/analysis.py` produced first.

To calculate every number again, run `python src/run_all.py`. It takes
approximately 80 seconds. All the numbers below come from
`data/dynamics_metrics.json`.

## Method

### 1. Opinion dynamics (`src/degroot.py`)

Each respondent starts at their own mean opinion score. Then each respondent
replaces that score with the average of the scores of their neighbours. All the
respondents do this at the same time. This is the DeGroot model.

The rule in matrix form is `x(t+1) = D⁻¹A x(t)`.

The script runs 300 steps on all 5 networks. A network is converged when every
opinion is within 1e-9 of its limit. The script also calculates the limit with a
formula and compares the 2 results. It runs 4 versions in total: unweighted and
weighted, and for each one the plain map and the lazy map.

### 2. Spectral analysis (`src/degroot.py`)

The matrix `P = D⁻¹A` is not symmetric. But it has the same eigenvalues as the
symmetric matrix `S = D^-1/2 A D^-1/2`. The script uses `S`, because the
eigenvalues of a symmetric matrix are real numbers.

The normalized Laplacian is `I - S`. So the algebraic connectivity is `1 - μ₂`.
The speed of convergence is the second largest eigenvalue modulus of `P`.

### 3. Epidemic threshold (`src/epidemic.py`)

A strong opinion can move through the network like an infection. The threshold
from the course is `(β/γ)_c = 1/λ_max`, where `λ_max` is the largest eigenvalue
of the adjacency matrix. The script calculates this for all 5 networks. It also
calculates `⟨k⟩/⟨k²⟩`, which uses only the degrees.

Then the script simulates SIS. It tests values of `β/γ` from 0.2 times the
threshold to 4 times the threshold. Each value gets 40 independent runs of 400
steps. The result is the mean number of infected people over the last 100 steps.

### 4. Null models (`src/nullmodels.py`)

A null model answers one question. Would we measure the same value on a network
with no opinion structure in it?

The script builds 500 Erdos-Renyi graphs with the same node count and the same
density. It builds 500 degree-preserving rewirings of the real network. It
compares 4 statistics against each set.

The script also does a permutation test on Aviral's Louvain communities. It
shuffles the community labels 10000 times and keeps the community sizes the
same. It does this twice, with 2 different sets of features.

### A note on the missing answers

There are 62 missing answers out of 5220, which is 1.19%. They affect 19 of the
87 respondents. There are 2 correct ways to deal with them, and this part uses a
different one from `AVIRAL.md`.

`AVIRAL.md` removes a missing answer from the average. This gives the mean of
what a respondent actually answered. The population means in that document use
this method. For example, Environment is +1.37.

This part replaces a missing answer with 0 before it takes the average. This is
the same operation that `src/build_network.py` does before it calculates the
similarity. So the opinions and the edges come from the same numbers. Under this
method Environment is +1.35.

The difference is small. For the mean opinion of the full class it is 1.1389
against 1.1284, which is 0.0105. For 1 respondent it is as large as 0.23.

Both methods are correct for their own purpose. Use the `AVIRAL.md` numbers to
describe what the class answered. Use the numbers here for anything that must
agree with the structure of the graph. Do not compare a value from one method
with a value from the other.

### 5. Threshold sensitivity (`src/sensitivity.py`)

`src/build_network.py` keeps the top 10% most similar pairs as edges. This
script applies the same rule to the saved similarity matrices at each quantile
from 0.50 to 0.99. As a check, the graphs at q=0.90 are the same as
`data/graphs/*.graphml`, edge for edge.

## Findings

### There is no consensus for the full class

The overall network has 37 components. So the DeGroot map has 37 fixed points,
not 1.

But 36 of those components are single respondents. A single respondent has no
neighbours. There is no value to take an average of. So that respondent keeps
their first score for ever.

The correct statement is this. 51 respondents move to a consensus of 1.409. The
other 36 respondents do not move at all.

The 51 respondents who converge started at a mean score of 1.309. The 36
respondents who do not move started at a mean score of 0.872. So the process
does not only fail to find a consensus. It also removes the more moderate half
of the class from the process. See `dynamics_degroot_trajectories.png`.

### The speed of convergence follows the algebraic connectivity

| Network | λ₂ = 1 - μ₂ | SLEM | Steps to converge | Giant | Consensus |
| --- | --- | --- | --- | --- | --- |
| overall | 0.627 | 0.397 | 23 | 51 | 1.409 |
| ethics | 0.455 | 0.545 | 31 | 45 | 1.350 |
| technology | 0.318 | 0.682 | 53 | 65 | 1.313 |
| education | 0.264 | 0.736 | 61 | 63 | 1.275 |
| environment | 0.229 | 0.771 | 77 | 44 | 1.349 |

Each SLEM is less than 1. So each of the 5 maps is stable, and each one
converges.

The order of the λ₂ column is the same as the order of the measured steps. There
are no exceptions. This is the stability rule from the course, measured on real
survey data. See `dynamics_degroot_convergence.png`.

### Four networks contain a group that never converges

Technology, Education, Ethics and Environment each contain a small component
that is bipartite. Three of them are a pair of respondents. In Technology it is
the 3-respondent path 19-72-42.

A bipartite component has 2 sides. Each edge goes from one side to the other
side, and no edge stays inside one side. So the respondents on one side take the
values from the other side. No value is ever mixed with a value from its own
side.

On a bipartite component the map has an eigenvalue of exactly -1. An eigenvalue
of -1 does not make the difference smaller. It only changes the sign. So the
difference stays the same size for ever.

All 3 respondents in the Technology group move. Respondents 19 and 42 are on one
side and move together. Respondent 72 is on the other side and moves in the
opposite direction. The values change between 1.200 and 1.092 at each step. The
degree-weighted limit is 1.146. No respondent reaches it.

The correction is the lazy map. Each respondent keeps half of their own value
and takes half of the average of the neighbours. This changes the eigenvalue -1
to 0 and does not change the limit. With the lazy map, all 5 networks converge
everywhere.

This affects only 2 to 4 respondents in each network. But it shows why the
stability rule uses the size of the eigenvalue and not its sign. See
`dynamics_degroot_bipartite.png`.

### The edge weights have almost no effect

The weighted consensus is 1.4099. The unweighted consensus is 1.4085. The
convergence times change by 2 steps at most.

The reason is the range of the weights. Each cosine similarity above the top-10%
cut is between approximately 0.85 and 0.95. The rows of the matrix are then
normalized, and this removes almost all of that small difference.

Put this in the report. It prevents the assumption that the weights do more work
than they do.

### An opinion moves most easily through the networks that are most broken up

This result is the opposite of what you would expect.

| Network | λ_max | 1/λ_max | ⟨k⟩/⟨k²⟩ | Giant size | Density in giant |
| --- | --- | --- | --- | --- | --- |
| environment | 23.92 | 0.0418 | 0.0421 | 44 | 0.395 |
| ethics | 22.45 | 0.0445 | 0.0442 | 45 | 0.378 |
| overall | 22.06 | 0.0453 | 0.0442 | 51 | 0.294 |
| technology | 18.17 | 0.0550 | 0.0569 | 65 | 0.179 |
| education | 17.74 | 0.0564 | 0.0579 | 63 | 0.191 |

Environment has the lowest threshold. So an opinion needs the least
transmissibility to stay in that network. Technology has the highest threshold.

This is the opposite of the connectivity order. Technology has a giant component
of 75%, and Environment has one of 51%.

The cause is the method of construction. Each of the 5 networks has exactly 375
edges, because the rule keeps the top 10% of pairs. Between 373 and 375 of those
edges are inside the giant component. At most 2 edges are in a small side
component.

So a network with a smaller giant component is not a network with fewer edges.
It is almost the same number of edges in fewer people. Environment puts 374
edges into 44 respondents. Technology puts 373 edges into 65 respondents. A
smaller and denser core gives a larger λ_max and a lower threshold.

Fragmentation and ease of spread are not opposites here. Environment is the
topic with the fewest connected respondents. It is also the topic where an
opinion moves most easily between the respondents who are connected.

This is a real property of the network. It is also a warning about the method,
because a fixed edge count is what causes the effect.

### The simulated threshold is higher than the calculated threshold

The transition is sharp. The number of infected people is exactly 0 at each
value below 1.5 times the bound. So the infection dies out. It is not only
difficult to measure.

But the transition does not start at `1/λ_max`. It starts at approximately 1.6
times that value. This is the expected behaviour. The mean-field threshold is a
lower bound on the true threshold. Also, the giant component has only 44 to 65
respondents, so an infection that starts just above the bound usually dies out
by chance.

Treat the value 1.6 as approximate. On a longer run of 1200 steps it is between
1.6 and 1.7, and this depends on the values in the parameter grid. It moves to
1.9 if you use 5% infected instead of 2% as the limit for an endemic infection.

Two things are certain. The gap is in the direction that theory gives. Both
networks show the same offset, so the order between networks is still correct.
See `dynamics_sis_sweep.png`.

### The structure of the network is in the degree sequence

| Statistic | Real | ER mean | z | Config mean | z |
| --- | --- | --- | --- | --- | --- |
| Average clustering | 0.408 | 0.098 | +27.2 | 0.391 | +1.6 |
| Giant fraction | 0.586 | 1.000 | -361.7 | 0.586 | 0.0 |
| Average path length | 1.880 | 2.292 | -9.5 | 1.834 | +3.7 |
| Modularity | 0.105 | 0.282 | -13.7 | 0.100 | +0.9 |

The calculated Erdos-Renyi values agree with the 500 simulated graphs. This is a
check on both. `C = p = 0.100`. `L = ln(87)/ln(8.62) = 2.073`. The solution of
`S = 1 - e^(-⟨k⟩S)` at ⟨k⟩ = 8.62 is S = 0.9998. A random graph with this
density is almost 1 single piece. The real network is 58.6%.

The second null model gives the more important result. It keeps the degree of
each respondent and changes only the pairs that are connected. The clustering,
the giant component and the modularity then agree with the real values. Only the
path length is a little different.

So the network is a random graph, if you first fix the degree sequence. The
structural results are all contained in the number of edges that each person
has. Almost nothing is in the specific pattern of who is similar to whom.

This does not make Aviral's work incorrect. It explains it. His result is that
the connected core is the group that agrees with everything. That result is the
same statement as this one. The level of agreement decides the degree. After you
fix the degrees, there is nothing more to explain. See `dynamics_nullmodels.png`.

### The communities are real, but not at the level of the topics

The permutation test shuffles the community labels 10000 times and keeps the
sizes the same. It then asks if the real communities group respondents who are
more alike than chance gives. The answer depends on the features you measure.

| Features tested | Observed | Null mean | z | p |
| --- | --- | --- | --- | --- |
| All 60 question scores | 0.4116 | 0.4592 | -6.57 | < 0.0001 |
| 4 topic means | 0.0791 | 0.0839 | -1.26 | 0.108 |

The graph was built from the 60 individual question scores. On those scores the
communities are strongly significant. On the 4 topic means they are not
different from random.

So Louvain groups respondents by their detailed pattern of answers. It does not
group them by their general position on the 4 topics. Two respondents in the
same community can have different topic means and still answer the individual
questions in a similar way.

This corrects the community table in `AVIRAL.md`. The per-topic values in that
table are correct as a description of each group. But they are not what makes
the groups different from each other. Do not write them as if they are. See
`dynamics_community_permutation.png`.

### The topic order is correct at each threshold

Technology stays above Environment at each cut from 0.50 to 0.99. Education
stays above Ethics at each cut. There are no exceptions. So this result is a
property of the data and not of the 90th percentile. Aviral's topic result is
correct.

The isolated respondents are a different case.

| Quantile kept | Edges | Isolated | Giant fraction | Clustering |
| --- | --- | --- | --- | --- |
| 0.90 | 375 | 36 | 0.586 | 0.408 |
| 0.80 | 749 | 21 | 0.736 | 0.579 |
| 0.70 | 1123 | 15 | 0.828 | 0.643 |
| 0.60 | 1497 | 13 | 0.851 | 0.674 |
| 0.50 | 1871 | 8 | 0.908 | 0.751 |

Aviral wrote that a lower threshold would connect more of the 36 respondents.
That is correct. The number decreases to 15 at q=0.70.

But it does not decrease to 0. At q=0.50 the rule keeps half of all the possible
pairs as edges, and 8 respondents still have no edge. The answer pattern of
those 8 respondents is below the median similarity against every other person in
the class. They are different from everybody, and the threshold is not the cause.

A lower threshold also has a cost. The same table shows it. The clustering
increases to 0.75 and the graph is half complete. Community detection and
centrality have little meaning on a graph like that. So q=0.90 is a good choice.
It is now a tested choice and not an assumption. See
`dynamics_threshold_sensitivity.png` and `dynamics_threshold_ordering.png`.

## For the Results and Discussion section

Two paragraphs. Use them as they are.

The opinion network does not reach a consensus for the full class under any of
the dynamics that we ran. The overall network divides into 37 components. The
DeGroot averaging map moves 51 respondents to an agreement at 1.409, and the
other 36 respondents do not move at all. The 51 respondents converge at the
speed that the spectral analysis gives. The order of the measured convergence
times is the same as the order of the algebraic connectivity for all 5 networks.
The failure to reach a consensus is not random. The 36 respondents who are
removed from the process started at a mean opinion of 0.872, against 1.309 for
the connected group. So the process leaves out the more moderate half of the
class. The epidemic analysis gives a second result that is against expectation.
Environment and Ethics have the lowest epidemic thresholds, although they are
the most fragmented topics. The construction fixes the edge count at 375, so
fewer connected people gives a denser core and a larger λ_max.

Two null models show where the structure of the network is. Against Erdos-Renyi
graphs of the same size and density, the network is very unusual on each
measure. The clustering is 4 times higher, and the giant component is 58.6%
against a calculated 99.98%. Against degree-preserving rewirings of itself, the
network is ordinary. It agrees with the null model on clustering, on the giant
component and on modularity. So the structure is almost all in the degree
sequence. Given the method of construction, this is the same statement as the
result that respondents who agree with everything collect more edges. The
Louvain communities do contain a real signal. But the signal is at the level of
the individual question responses (p < 0.0001). It is not at the level of the 4
topic averages (p = 0.108). So describe them as groups with similar answer
patterns, and not as groups with different topic positions. A sweep of the edge
threshold confirms the per-topic connectivity order at each cut between 0.50 and
0.99. The same sweep shows that the number of isolated respondents is partly an
artifact. It decreases from 36 to 8 as the cut becomes looser, and it does not
reach 0.

## The nine figures

| Figure | What it shows |
|---|---|
| `dynamics_degroot_trajectories.png` | opinions converging, isolated respondents flat, bipartite pairs oscillating |
| `dynamics_degroot_bipartite.png` | why a bipartite component never settles, and the lazy map that corrects it |
| `dynamics_degroot_convergence.png` | convergence speed against algebraic connectivity, and the stability of all 5 maps |
| `dynamics_sis_threshold.png` | largest adjacency eigenvalue and epidemic threshold, per network |
| `dynamics_sis_sweep.png` | the simulated SIS transition against the mean-field bound |
| `dynamics_nullmodels.png` | the real network against the Erdos-Renyi and configuration-model sets |
| `dynamics_community_permutation.png` | whether the Louvain communities are more homogeneous than chance |
| `dynamics_threshold_sensitivity.png` | how the giant component, the isolates and the clustering respond to the edge cut |
| `dynamics_threshold_ordering.png` | whether the topic order survives a different cut |

## Data for the dashboard

`python src/export_dashboard.py` writes three flat tables into `data/`. They
hold the same numbers as `data/dynamics_metrics.json`, in a shape that a
plotting library can load directly.

| File | Shape | Contents |
|---|---|---|
| `dashboard_nodes.csv` | 87 x 51 | one row per respondent |
| `dashboard_networks.csv` | 5 x 17 | one row per network |
| `dashboard_curves.json` | | the 2 swept curves, as x and y lists |

In `dashboard_nodes.csv`, 6 columns apply to the respondent in general. They are
`respondent_id`, `opinion_overall`, and `opinion_<topic>` for the 4 topics. The
other columns are named `<network>__<field>` for each of the 5 networks.

| Field | Use it for |
|---|---|
| `degree` | the size of the node |
| `degree_centrality`, `closeness_centrality`, `betweenness_centrality`, `eigenvector_centrality` | tooltips and rankings |
| `community` | the colour of the node |
| `is_isolate` | a control to show or hide the isolated respondents |
| `in_giant` | the same idea, but it also removes the small components |
| `degroot_limit` | the opinion that respondent moves to |

`degree` is the number of edges. `degree_centrality` is the same value divided
by 86. They are 2 different columns.

Respondent ids are strings in the GraphML files and in `data/metrics.json`. They
are integers in the CSV files. Change one of the 2 types before you join them.
If you do not, the result is empty and there is no error message.

## Notes for the person who assembles the PDF

Use `dynamics_degroot_trajectories.png` for Analysis and Visualizations. Use
`dynamics_nullmodels.png` for Results and Discussion. If there is not enough
space, remove `dynamics_degroot_bipartite.png` first. It affects only 2 to 4
respondents in each network.

My results change 3 statements that are already in `AVIRAL.md`. Agree on one
version of each before you submit the report.

- His community table describes each community by its topic deviation. The
  permutation test shows that the topic means do not separate the communities.
  The table is correct as a description. Do not write it as the definition of
  the groups.
- His caveat says that a lower threshold would connect more of the 36 isolated
  respondents. This is confirmed. The number is 8 at q=0.50.
- My task brief predicted that Technology would have the highest λ_max. It has
  the lowest. The brief assumed that the density is different in each of the 5
  networks. The density is the same in all 5.
