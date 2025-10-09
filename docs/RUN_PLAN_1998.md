# Run Plan – 1998 Yangtze Flood (Scheme B)

This document outlines the simulation design for reproducing the 1998 Yangtze flood using Scheme B.

## 1. Objective
Validate the integrated WRF-Hydro → mizuRoute → RRI chain under 1998 climate forcing as the modern benchmark for historical reconstruction.

## 2. Simulation period
June – September 1998 (flood season)

## 3. Domain and resolution
- WRF-Hydro: 0.05° (~5 km) outer domain  
- Routing (mizuRoute / Muskingum-Cunge): 1/16° river network  
- RRI nested floodplain: 100 m DEM sub-domain around Jingjiang reach

## 4. Forcing data
- **Precipitation:** CMA daily stations (interpolated via kriging)  
- **Meteorology:** ERA5 or 20CRv3 downscaled fields (T, P, wind, pressure)  
- **Land use:** MODIS + NLCD (1998 epoch)  
- **Soil:** HWSD v2 / Harmonized World Soil Database

## 5. Calibration & validation
- Gauge stations: Hankou, Datong, Chenglingji  
- Validation variables: discharge Q, inundation extent A, water level H  

## 6. Coupling flow
WRF-Hydro runoff → routed via mizuRoute (or Muskingum-Cunge) → RRI 2D domain boundary forcing.

## 7. Expected outputs
- Q(t) at key stations  
- Maximum inundation maps  
- Time-series of soil moisture & energy fluxes (for process analysis)
