# 🌳 Fruit Tree Analysis

**Explore vegetation around a location of your choice using satellite imagery.** This desktop app analyzes Sentinel-2 imagery through Google Earth Engine and displays estimated vegetation classes on an interactive map. Its default center is the selected analysis area; you can enter coordinates for another location.

The app offers a hands-on introduction to remote sensing, satellite data, and vegetation indices.

## 🛰️ What does the app do?

The app retrieves Sentinel-2 imagery for a selected season and analysis area, calculates vegetation indices such as NDVI, EVI, and SAVI, then displays classified detections and summary counts. You can adjust the analysis center, radius, season, and detection detail.

| Map marker | Estimated class |
| --- | --- |
| 🟢 Green | Olive trees |
| 🟠 Orange | Citrus trees |
| 🔴 Red | Other fruit trees |
| 🌲 Dark green | Pine groups |
| 🌿 Light green | Shrub and ornamental groups |
| 📍 Red marker | Selected analysis center |
| 🔵 Blue circle | Analysis boundary |

Individual detections and groups are shown separately where available. The map also includes seasonal harvest highlighting and an on-screen count summary.

> **Please note:** Satellite classifications are estimates, not a verified inventory or field survey. Results depend on image resolution, cloud cover, and classification thresholds. The thresholds were tuned for the the selected region area and may not generalize to other regions.

## 🚀 Get started

### Requirements

- Python 3.8 or newer
- Internet access
- A Google Earth Engine account
- Access to an Earth Engine project (the app currently uses project ID `your-earth-engine-project-id`)

### 1. Install dependencies

Open a terminal in the project directory and run:

```bash
python -m pip install -r requirements.txt
```

### 2. Authenticate with Earth Engine

```bash
earthengine authenticate
```

Sign in with your Google account in the browser and approve access. Earth Engine credentials are stored locally in your user profile.

### 3. Launch the app

```bash
python app.py
```

## 🗺️ Choose a location and run an analysis

1. Enter the location's **latitude** and **longitude** in the Analysis Center fields. To find coordinates in Google Maps, right-click the location and copy the displayed coordinates. The first value is latitude and the second is longitude.
2. Set the analysis radius from **1 to 5 km**. The default is **2 km**.
3. Select a season. Summer is selected by default.
4. Choose **Fast**, **Balanced**, or **Precise** detection detail. Balanced is the default.
5. Click **Start Analysis**. Progress messages appear in the activity log.
6. Review the selected center, vegetation classes, and estimated counts on the map and in the summary panel.

The current version uses fixed date ranges: spring, summer, and autumn 2024; winter covers December 2023 through February 2024. Update the date ranges in `app.py` to analyze another year.

## 🧰 Built with

- [Google Earth Engine](https://earthengine.google.com/) and Sentinel-2
- [PyQt5](https://riverbankcomputing.com/software/pyqt/intro) desktop interface
- [Folium](https://python-visualization.github.io/folium/) interactive map
- NDVI, EVI, NDRE, NDWI, and SAVI vegetation indices


## 🛠️ Troubleshooting

- **Cannot connect to Earth Engine:** Run `earthengine authenticate` and check that you are signed into the correct account. If you do not have access to `your-earth-engine-project-id`, replace the project ID in `app.py` with one you can use.
- **`ModuleNotFoundError`:** Run `python -m pip install -r requirements.txt` from the project directory.
- **The map does not appear:** Check your internet connection and confirm that `PyQtWebEngine` is installed.
- **Few or no detections:** Try a different season or a larger analysis radius. Cloud cover can affect results.

## 📄 License and permitted use

This project is **not open source**. It is governed by the custom [Restricted Use License](LICENSE). Private, non-commercial inspection and evaluation are permitted under its terms. Use in any competition, official or organized project, or profit-seeking activity requires advance written permission from the rights holder at **alectoaa@proton.me**. The license explains the request process and other restrictions.

**Public GitHub repositories can be viewed and forked under GitHub's Terms of Service.** The license does not override those platform terms and cannot prevent copies or rights already allowed by GitHub. If that does not match your sharing preferences, use a private repository. See [GitHub's repository licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository) and [Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service).

## 💬 Feedback

Please share issues, suggestions, and ideas in the GitHub Issues section.
