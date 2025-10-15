# GHCN-Daily Data Processing Summary

This document summarizes the processing and visualization of GHCN-Daily (GHCNd) station data for the Yangtze River domain and its extended region, along with auxiliary hydrographic and geographic datasets used for spatial reference and validation.

---

## 1. Scope and Purpose

The purpose of this workflow was to identify and analyze daily meteorological stations within and around the Yangtze River Basin for the period 1901–2025, and to prepare spatial–temporal datasets for validation of WRF-Hydro downscaling experiments and subsequent data assimilation studies.

Two station domains were defined:

* **Big window domain** — 90°E–130°E, 18°N–38°N, covering East Asia and Southeast Asia.  
* **China-only subset** — the same spatial window, restricted to stations within mainland China, Hong Kong, Macau, and Taiwan.

---

## 2. Data Sources

### GHCN-Daily

* **Dataset:** Global Historical Climatology Network – Daily (GHCN-Daily), Version 3.  
* **Provider:** NOAA National Centers for Environmental Information (NCEI).  
* **Citation:**  
  Menne, Matthew J., Imke Durre, Bryant Korzeniewski, Shelley McNeill, Kristy Thomas, Xungang Yin, Steven Anthony, Ron Ray, Russell S. Vose, Byron E. Gleason, and Tamara G. Houston (2012): *Global Historical Climatology Network – Daily (GHCN-Daily), Version 3.* NOAA National Climatic Data Center. doi: 10.7289/V5D21VHZ.  
  Publications citing this dataset should also reference: Menne et al., 2012, *J. Atmos. Oceanic Technol.*, 29, 897–910, doi: 10.1175/JTECH-D-11-00103.1.

* **Core variables available:**  
  Daily maximum temperature (TMAX), minimum temperature (TMIN), precipitation (PRCP), snowfall (SNOW), snow depth (SNWD), wind observations (AWND, WSFG, WDFG), and numerous weather-type indicators (WT**xx**).

* **Temporal coverage:** 1901–2025 (variable by station).

* **Local observation day definition:**  
  Each national meteorological agency reports according to its own climatological day. GHCN-Daily does **not** homogenize these to a common UTC standard.  
  For China, the standard observation day is **from 20:00 Beijing Time (previous day) to 20:00 of the current day**, and daily mean temperature is conventionally calculated as the average of the 02:00, 08:00, 14:00, and 20:00 local observations.  
  Therefore, daily values across countries are not strictly time-aligned and should be interpreted within each national system.

---

## 3. Processing Workflow

1. **Station filtering:**  
   The full GHCNd station inventory (`ghcnd-inventory.txt`) was intersected with the defined spatial domains.  
   392 stations were identified in the big-window region; fewer remain in the China-only subset after country-code filtering (`CH`, `HK`, `MC`, `TW`).

2. **Temporal availability:**  
   For each station, start and end years of each element were parsed to determine data availability by year.  
   Yearly station counts were exported as `yearly_counts_big_window.txt` and `yearly_counts_big_window_china_only.txt`.

3. **Visualization:**  
   * Annual maps of active GHCNd stations (1901–2025).  
   * Comparative maps for benchmark flood years 1931, 1935, 1954, and 1998.  
   * Stacked bar charts showing yearly numbers of stations inside vs. outside China.  

4. **Hydrographic overlay:**  
   The spatial context of the Yangtze River system was added using **HydroRIVERS** (river network polylines) and **HydroBASINS** (basin polygons).  
   The scripts automatically classify and render main stem and tributaries using attributes such as `MAIN_RIV`, `ORD_STRAH`, or `UP_CELLS`.

---

## 4. Supporting Geographic Data

### HydroRIVERS and HydroBASINS

Both datasets are developed within the HydroSHEDS framework and provide global hydrographic reference data used to delineate the Yangtze River and its tributaries.

**Citation and acknowledgement (for both):**

Lehner, B., and G. Grill (2013): *Global river hydrography and network routing: baseline data and new approaches to study the world’s large river systems.* *Hydrological Processes,* 27(15): 2171–2186. Data available at [www.hydrosheds.org](https://www.hydrosheds.org).

### Natural Earth base layers

Coastlines, land polygons, and national boundaries were provided by **Natural Earth**.  
50 m-resolution datasets were used:

* **Land:** `ne_50m_land`  
* **Admin 0 – Countries:** `ne_50m_admin_0_countries`

**Citation (long form):**  
*Made with Natural Earth. Free vector and raster map data @ [naturalearthdata.com](https://www.naturalearthdata.com).*

No permission is needed to use Natural Earth data, and attribution is optional.

---

## 5. Outputs

All scripts, intermediate tables, and final figures are stored under:

```
yangtze-1998-wrfhydro-rri/
 ├── data/ghcnd/
 ├── data/geodata/
 │    ├── natural_earth/
 │    ├── hydrorivers/
 │    └── yangtze_basin/
 └── docs/figs/
```

The processed outputs include:
* `yearly_counts_*.txt` — yearly station availability tables.  
* `stations_<year>.png` — annual spatial distributions.  
* `stations_comparison_1931_1935_1954_1998.png` — multi-year comparison map.  
* `stations_stack_in_out_china.png` — stacked bar chart of domestic vs. foreign stations.

---

## 6. Remarks

This phase completes the preprocessing of GHCN-Daily data for the Yangtze River domain.  
The resulting datasets provide a consistent historical station framework for evaluating WRF-Hydro downscaled fields, for assimilation studies, and for hydrologic reconstructions of major historical flood events such as 1931 and 1998.

---

*Document compiled October 2025.*
