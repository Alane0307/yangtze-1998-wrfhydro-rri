# Research Plan – Reconstruction of the 1931 and 1954 Yangtze Floods

## 1. Background and Motivation

The 1931 Yangtze flood remains one of the most catastrophic hydrological events in modern human history, causing unprecedented loss of life and reshaping flood-control policies across China.  
Despite its historical importance, the 1931 flood has never been dynamically reconstructed with modern coupled land–atmosphere–hydrology models, largely due to the scarcity of reliable meteorological observations before the mid-20th century.

The overarching goal of this project is to **reproduce the spatial–temporal evolution of the 1931 and 1954 Yangtze floods** using physically based hydrometeorological modeling and modern data-assimilation techniques.  
To achieve this, we will first build a validated modeling chain under the well-observed **1998 flood** as a reference benchmark.

---

## 2. Conceptual Framework

Three alternative modeling pathways (Scheme A, B, and C) were considered to simulate basin-scale runoff generation and floodplain inundation.

### **Scheme A — Traditional Semi-distributed Approach**
- **Core idea:** Use SWAT or VIC-type models for rainfall–runoff computation at sub-basin scale, with Muskingum routing.  
- **Advantages:** Computationally cheap, easily calibrated.  
- **Limitations:**  
  - Relies heavily on empirical parameters.  
  - Simplified representation of surface–subsurface exchanges.  
  - Inadequate for physically consistent reconstruction under historical climate forcing.

### **Scheme B — Fully Integrated Physically Based System (Selected)**
- **Core modules:**
  1. **WRF-Hydro (Noah-MP)** for land-atmosphere coupled runoff generation.  
  2. **Muskingum-Cunge or mizuRoute** for 1-D river routing.  
  3. **RRI / LISFLOOD-FP** nested 2-D floodplain simulation.

- **Rationale for selection:**
  - Provides physically consistent surface energy and water balance.  
  - Allows explicit downscaling from reanalysis (ERA5, 20CRv3).  
  - Enables process-level interpretation of the flood evolution (soil moisture, infiltration excess, energy fluxes).  
  - Modular design: routing and floodplain components can be replaced or nested at higher resolution without disturbing land-surface processes.  
  - Proven applicability in large-basin flood reconstruction (e.g., Yamazaki et al. 2022, Toyoshima et al. 2021).

- **Disadvantages:**  
  - Computationally expensive.  
  - Requires high-quality boundary forcing and calibration.

### **Scheme C — Statistical / Hybrid ML Downscaling Approach**
- **Core idea:** Combine reanalysis data with machine-learning-based rainfall downscaling (e.g., cGAN / diffusion models) to generate synthetic high-resolution precipitation sequences.  
- **Advantages:** Useful when meteorological data are severely limited.  
- **Limitations:**  
  - Lacks physical closure; difficult to ensure energy and mass conservation.  
  - Poor interpretability for process studies.

### **Decision:**
> Scheme B is adopted as the baseline framework due to its physical consistency and scalability for long-term reconstruction experiments.

---

## 3. Stepwise Experimental Design

| Phase | Target Year | Purpose | Expected Output |
|-------|--------------|----------|-----------------|
| Phase 1 | **1998 Flood** | Modern benchmark; calibration and validation of full modeling chain | Validated discharge and inundation maps |
| Phase 2 | **1954 Flood** | Historical reproduction with post-WWII reanalysis data and limited observations | Quantitative comparison to 1998 and 1931 |
| Phase 3 | **1931 Flood** | Pre-instrumental reconstruction using 20CRv3 and assimilated station datasets | Physically consistent dynamic reconstruction |

---

## 4. Methodology Overview

### 4.1 Meteorological Forcing and Downscaling
- **Primary source:** ERA5 (post-1950), 20CRv3 (before 1950).  
- **Spatial downscaling:** WRF (with Noah-MP LSM) forced by reanalysis fields.  
- **Temporal resolution:** 3-hourly outputs aggregated to daily for hydrological forcing.  
- **Bias correction:** Station data assimilation and kriging interpolation where available.

### 4.2 Runoff and Routing
- **WRF-Hydro** computes surface and subsurface runoff.  
- Outputs routed through **mizuRoute** or Muskingum-Cunge network.  
- River geometries derived from HydroSHEDS and local survey data.

### 4.3 Floodplain Inundation (2-D Nesting)
- Selected critical reaches (Jingjiang, Poyang, Dongting) simulated with **RRI** or **LISFLOOD-FP**.  
- Boundary conditions driven by 1-D routed discharges.  
- High-resolution DEM (SRTM-30m / ALOS-AW3D) and landcover applied.

### 4.4 Validation Metrics
- Hydrograph comparison (R², NSE) at key gauges (Hankou, Datong).  
- Inundation area overlap (F-score) with satellite or historical maps.  
- Energy and water flux balance diagnostics for physical consistency.

---

## 5. Sensitivity Experiments

| Experiment | Purpose | Method |
|-------------|----------|--------|
| Parameter perturbation | Assess uncertainty in infiltration & soil parameters | Ensemble runs varying soil/landcover parameters |
| Boundary forcing | Compare 20CRv3 vs ERA-20C vs ERA5-backward extensions | WRF re-runs with different lateral BCs |
| Routing schemes | Evaluate Muskingum-Cunge vs mizuRoute | Coupled reruns under identical runoff inputs |
| Inundation nesting | Test sensitivity to DEM and resolution | RRI vs LISFLOOD-FP comparison |

---

## 6. Expected Contributions
1. **First physically based dynamic reconstruction** of the 1931 Yangtze flood.  
2. Quantitative assessment of long-term changes in flood generation processes (1931 → 1954 → 1998).  
3. Methodological framework transferable to other major historical floods in Asia.  
4. Open and reproducible hydrometeorological workflow for future reanalysis–hydrology coupling studies.

---

## 7. Implementation Plan

| Stage | Task | Timeline (tentative) |
|-------|------|---------------------|
| Stage 1 | Repository setup, 1998 WRF-Hydro calibration | 2025Q4 |
| Stage 2 | 1954 simulation & data preparation | 2026Q2 |
| Stage 3 | 1931 reconstruction with 20CRv3 | 2026Q4 |
| Stage 4 | Sensitivity analysis & publication | 2027 |

---

## 8. References (Key)
- Yamazaki et al., *Hydrological Research Letters*, 2022.  
- Toyoshima et al., *J. Hydrometeorology*, 2021.  
- ECMWF (2023): ERA5 Reanalysis documentation.  
- NOAA PSL (2020): 20th Century Reanalysis v3.  
- Gochis et al., *WRF-Hydro Technical Description*, NCAR.

---

*Prepared by Chang Liu & Wei Wei, 2025*  
