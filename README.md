# Micropile ASD Design Calculator

A general Streamlit software app for preliminary micropile axial design checks.

## What it does

The app checks:

- Hollow bar only / bar only micropiles
- Casing only micropiles
- Casing + hollow/core bar micropiles
- Required allowable compression load per pile
- Required allowable uplift/tension load per pile
- Selected hollow bar or rebar size
- Selected casing size, no casing, or custom casing
- Casing corrosion wall deduction
- Grout strength
- Bond/socket diameter and length
- FHWA Table 5-3 ultimate grout-to-ground bond values with FS
- User-specified allowable bond values when provided by geotechnical criteria
- Required bond/socket length
- Provided vs required capacity checks

## Calculation basis

Primary preliminary design logic is based on FHWA NHI-05-039 Chapter 5:

- Eq. 5-1: cased compression structural capacity
- Eq. 5-2: cased tension structural capacity
- Eq. 5-7: uncased compression structural capacity
- Eq. 5-8: uncased tension structural capacity
- Eq. 5-9 / 5-10: grout-to-ground bond capacity and required bond length
- Table 5-3: typical ultimate grout-to-ground bond values by soil/rock type and grout type

The app is intentionally generic. It does not reference any specific job, owner, or site. All loads, material properties, bond values, and socket dimensions must be entered by the user based on applicable design criteria.

## Install and run

1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

On Windows you can double-click `launch_windows.bat` after Python is installed.
On Mac/Linux you can run:

```bash
chmod +x launch_mac_linux.sh
./launch_mac_linux.sh
```

## Important limitations

This is a preliminary design/check and estimating tool. It is not a sealed design and does not replace final engineering review.

Not included in this version:

- Lateral load and bending analysis
- Buckling check
- Group effects and settlement
- Pile cap connection design
- Detailed eccentricity design
- Downdrag, seismic, scour, or lateral load cases
- Full corrosion classification
- Load test procedure/acceptance criteria
- Threaded casing joint capacity testing

Final design should be reviewed and sealed by the EOR/geotechnical engineer based on applicable specifications, actual loads, installation method, site conditions, and load testing.


## Drawing feature

The app includes a schematic drawing section that updates from the user inputs. It shows:

- Micropile pile cap, grout/drill hole, casing, center bar, and bond/socket zone
- Soil/rock layers with user-entered top and bottom depths
- Optional groundwater line
- Total pile length, cased length, bond length, selected casing, selected bar, and bond diameter

The drawing is conceptual and intended for calculation review and communication only. It is not a sealed engineering/shop drawing.
