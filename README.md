# Yangtze 1998 – WRF-Hydro → mizuRoute → RRI

Baseline reproduction of the 1998 Yangtze flood using **Scheme B**:
WRF-Hydro (Noah-MP) → Muskingum-Cunge / mizuRoute → RRI (2D).

## Goals
- Validate Scheme B on the 1998 event.
- Provide reproducible workflow for 1954 and 1931 experiments.

## Repo layout
models/ – model wrappers  
config/ – namelists & runtime configs  
scripts/ – pre- & post-processing tools  
notebooks/ – analysis & figures  
docs/ – method notes  
env/ – conda environment  
ci/ – automation / tests  

## Data policy
This repo is **code-only**.  
Large/restricted datasets are excluded.  
See `docs/DATA_SOURCES.md` for acquisition instructions.

## License
MIT © 2025 Chang Liu / Wei Wei
