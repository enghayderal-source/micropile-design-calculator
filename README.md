# Micropile ASD Design Calculator

General preliminary micropile axial design/check app based on the FHWA NHI-05-039 workflow.

## New features in this version

- Bond is calculated through **multiple soil/rock layers below the casing end**.
- Each layer is selected from the FHWA Table 5-3 style bond library and has its own grout type, αbond, FS, and allowable compression/tension bond.
- Only the portion of each layer below the casing end and above the pile tip contributes to bond capacity.
- Includes Nucor Skyline fully threaded solid bars from the uploaded bar database.
- Includes SSSI hollow core bars from the hollow bar database.
- Includes Nucor Skyline A252 pipe rows from the uploaded pipe database.
- Supports hollow bars or solid bars.
- Supports multiple full-length bars and up to two additional partial-length bar groups.
- Partial bars are counted only where their length reaches the checked depth.
- Casing and bar databases are cleaned so display names and OD/wall combinations are not duplicated.
- Includes schematic drawing of pile, casing end, full/partial bars, soil layers, and bond interval.

## Deploy on Streamlit Cloud

Use:

- Repository: your GitHub repo
- Branch: `main`
- Main file path: `app.py`
- Python version: choose `3.11` in Advanced settings if available.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Engineering note

This is a preliminary screening and estimating tool only. Final design should be reviewed/sealed by the EOR and should separately address lateral load, bending, buckling, eccentricity, group effects, corrosion classification, threaded joint capacity, pile-cap connection, and project-specific load testing acceptance criteria.
