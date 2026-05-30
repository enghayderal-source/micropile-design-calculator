# Cloud Deployment Instructions

This package contains a generic Streamlit app for preliminary micropile ASD axial design checks.

## Files to upload to GitHub

Upload the unzipped contents of this folder to your GitHub repository:

```text
app.py
micropile_calc_engine.py
requirements.txt
runtime.txt
README.md
README_CLOUD_DEPLOY.md
data/
.streamlit/
```

## Streamlit Community Cloud

1. Go to Streamlit Community Cloud.
2. Choose **Deploy a public app from GitHub**.
3. Select your GitHub repository.
4. Use branch: `main`.
5. Use main file path: `app.py`.
6. Click **Deploy**.

## Optional password protection

Set an environment variable in Streamlit Cloud secrets or hosting settings:

```text
APP_PASSWORD=your-password
```

If `APP_PASSWORD` is not set, the app is public.

## Notes

This app is generic and does not include any specific project name, owner name, or site name. The user must enter the applicable design values.
