# Experiment setup (3 slides)

Values match the research stage matrices:  
`fault_matrix_research_stage1_paper_geometry.yaml`,  
`fault_matrix_research_stage2_memleak_boundary.yaml`,  
`fault_matrix_research_stage3_extended_transfer.yaml`.

---

## Slide 1 — Intensity (single table, all stages)

**Title:** Fault intensity ladders (all stages)

**Fault** — A **named injected failure mode** we turn on during a run (memory leak, CPU stress, network delay, lock contention, or disk pressure); each **row** is one such mode.

**Intensity** — The **severity setting** for that mode: one number per ladder level, passed when the fault is switched **on**; interpret **only within the same row** (units differ by fault type). **—** = that fault or level is not used in that stage.

**Units (row):** Memory leak **MB/s** · CPU hog **workers** · Net latency **ms** · Lock **threads** · Disk **MB**.


| Fault (unit)          | Stage 1 · Low | Stage 1 · High | Stage 2 · Very low | Stage 2 · Low | Stage 2 · Medium | Stage 2 · High | Stage 3 · Low | Stage 3 · High |
| --------------------- | ------------- | -------------- | ------------------ | ------------- | ---------------- | -------------- | ------------- | -------------- |
| Memory leak (MB/s)    | 20            | 80             | 10                 | 20            | 40               | —              | —             | —              |
| CPU hog (workers)     | 2             | 8              | —                  | 2             | 4                | 8              | —             | —              |
| Net latency (ms)      | 150           | 700            | —                  | 150           | 400              | 700            | —             | —              |
| Lock convoy (threads) | —             | —              | —                  | 20            | 40               | 60             | 20            | 60             |
| Disk fill (MB)        | —             | —              | —                  | 500           | 2000             | 5000           | 500           | 5000           |


---

## Slide 2 — Duration (single table, all stages)

**Title:** Fault hold duration (all stages)

**Duration** — How **long** the fault stays **on** after the **14 s** post-onset delay, for the **short** vs **long** cell (seconds per column); longer holds test whether the effect **lasts long enough** for the detector to respond. **—** = that fault is not part of that stage.

**Context:** Warmup **60 s**, bootstrap **240 s**, cooldown **90 s** elsewhere in the runbook (this table is only the **injection hold**).


| Fault       | Stage 1 · Short (s) | Stage 1 · Long (s) | Stage 2 · Short (s) | Stage 2 · Long (s) | Stage 3 · Short (s) | Stage 3 · Long (s) |
| ----------- | ------------------- | ------------------ | ------------------- | ------------------ | ------------------- | ------------------ |
| Memory leak | 60                  | 300                | 60                  | 300                | —                   | —                  |
| CPU hog     | 60                  | 300                | 60                  | 300                | —                   | —                  |
| Net latency | 60                  | 300                | 60                  | 300                | —                   | —                  |
| Lock convoy | —                   | —                  | 30                  | 90                 | 30                  | 90                 |
| Disk fill   | —                   | —                  | 60                  | 300                | 60                  | 300                |


---

## Slide 3 — What varies: stages, seeds, grids, run counts

**Title:** Stage design: geometry, seeds, and planned runs

**What varies**  
**Intensity** and **duration** ladders are defined **per fault**; **stage** changes the **fault set** and the **ladder size** (2 vs 3 intensity levels). The **detector and training recipe stay fixed** across stages.

**Seeds / repeats**  

- **Repeats:** **1** per cell.  
- **Stage 1:** seeds **41** and **42** (each geometry cell runs under both seeds).  
- **Stages 2–3:** seed **42** only.

**Stage 1**  

- **Faults:** 3 (memory leak, CPU hog, network latency proxy).  
- **Grid:** **2 × 2** (intensity × duration).  
- **Durations:** **60 s** / **300 s**.  
- **Intensities:** mem **20 / 80**, CPU **2 / 8**, net **150 / 700**.  
- **Planned runs:** **24**.

**Stage 2**  

- **Faults:** 5 (same three paper-aligned + lock convoy + disk fill).  
- **Grid:** **3 × 2** (memory adds **very_low = 10**).  
- **Lock durations:** **30 s** / **90 s**; other faults **60 s** / **300 s** where applicable.  
- **Intensities:** mem **10 / 20 / 40**; CPU **2 / 4 / 8**; net **150 / 400 / 700**; lock **20 / 40 / 60**; disk **500 / 2000 / 5000**.  
- **Planned runs:** **30**.

**Stage 3**  

- **Faults:** lock convoy + disk fill only.  
- **Grid:** **2 × 2**.  
- **Lock:** intensity **20 / 60**, duration **30 / 90 s**.  
- **Disk:** intensity **500 / 5000**, duration **60 / 300 s**.  
- **Planned runs:** **8**.

---

## Optional visual hints

- **Slides 1–2:** Widen deck or use landscape—the master tables are wide; in PowerPoint, shrink font or split header row.  
- **Slide 2:** Optional timeline glyph: fault-on → **hold = duration** → fault-off.  
- **Slide 3:** Three rows (Stage 1 / 2 / 3) with grid icon **2×2**, **3×2**, **2×2** and seed callout.

