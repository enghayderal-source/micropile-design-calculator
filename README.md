# Micropile ASD Design Calculator

General preliminary micropile axial design/check software based on the FHWA NHI-05-039 workflow.

## Main features

- Select pile configuration: hollow/core bar only, casing only, or casing + hollow/core bar.
- Select bar/reinforcement and casing size from built-in libraries or use custom values.
- Enter required allowable compression and uplift/tension load per pile.
- Enter grout strength, bond/socket diameter, casing-end depth, proposed bond length, and proof/test factors.
- Define soil/rock layers by top and bottom depth.
- Each layer is pulled from the FHWA Table 5-3 bond library with soil/rock type, grout type, αbond low/mid/high, and FS.
- The bond layer is automatically selected based on the layer where the casing ends.
- The bond calculation uses only the selected bond layer. If the proposed bond length extends beyond that layer, the used length is capped at the available thickness in that layer and a warning is shown.
- Generates a schematic drawing of the pile, casing end, selected bond layer, soil profile, and used/required bond length.
- Provides pass/fail checks for structural compression, structural tension, compression bond, tension bond, and provided bond length.
- Allows JSON/text report download.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Community Cloud

Main file path:

```text
app.py
```

Recommended Python version: 3.11 or 3.12.

## Important limitation

This app is for preliminary estimating/design checks only. Final design must be reviewed by the EOR/geotechnical engineer and must address lateral load, bending, buckling, eccentricity, group effects, settlement, corrosion classification, pile-cap connection, casing-thread tension capacity, and project-specific load testing/acceptance criteria.
