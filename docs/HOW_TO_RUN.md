# How to Run: Functional Guide

This guide explains how to operate the Datalogger, manage its data, and run the analysis pipeline.

---

## 1. Device Operation (On the Bike)

The system is designed to be headless and controlled via physical buttons.

### **Startup**

- **Power On:** Turn on the bike/battery. The **Red LED** (Power) will light up.
- **Ready State:** The OLED Display will show "WAITING". The **Blue LED** stays OFF while waiting.

### **Logging**

- **Start Logging:** Press the **Toggle Button** (Grey).
  - **Indicator:** The **Blue LED** will turn **Solid ON**.
  - **Data:** Data is now being written to `output/log_*.csv`.
- **Stop Logging:** Press the **Toggle Button** again.
  - **Indicator:** The **Blue LED** turns **OFF**. Result is saved.

### **Shutdown**

- **Safe Shutdown:** Press the **Shutdown Button** (Brown). The system will halt safely to prevent data corruption.

---

## 2. Data Management

Data is stored in a structured directory layout.

### **Directories**

| Directory   | Role                 | Content Type                                                                                     |
| :---------- | :------------------- | :----------------------------------------------------------------------------------------------- |
| `output/`   | **Raw Data**         | CSV files containing raw GPS/IMU telemetry from each session.                                    |
| `tracks/`   | **Track Database**   | `.json` files defining track geometry and record sectors.<br>`.png` files showing the track map. |
| `sessions/` | **Analysis Results** | `.json` files summarizing processed sessions (Laps, Sectors, Deltas).                            |

### **Retrieving Data**

Connect to the Pi via SFTP or synced folder to copy `output/*.csv` files to your local machine for analysis.

---

## 3. Running Analysis (Offline/Local)

The analysis engine runs on your local computer (Windows/Mac/Linux). It takes a raw CSV and produces meaningful insights.

### **Command**

From the project root:

```bash
python src/analysis/run_analysis.py path/to/your_log.csv
```

### **What Happens?**

1.  **Auto-Detection:** The system checks GPS coordinates against `tracks/`.
    - **Known Track:** It loads the existing sectors and records.
    - **Unknown Track:** It **automatically generates** a new Track JSON and Map PNG.
2.  **Processing:** Detects laps and calculates sector times.
3.  **Persistence:** Updates the **Theoretical Best Lap** (TBL) in `tracks/*_tbl.json`.
4.  **Export:** Creates a full summary in `sessions/session_<uuid>.json`.

---

## 4. Understanding the Results

### **Track Artifacts (`tracks/`)**

- `my_track.json`: The "Map". Contains the fixed start line and 7 sector divisions.
- `my_track_tbl.json`: The "Ghost". Stores the fastest-ever time for _each_ sector recorded by you on this track.
- `my_track_layout.png`: Visual map of the circuit geometry.

### **Session Summary (`sessions/`)**

A generated JSON file containing:

- **Lap List:** Every lap with sector splits.
- **Validity:** Automatic invalidation of laps (e.g., short cuts - _in progress_).
- **Ideal Lap:** Gap between your Actual Best vs. Theoretical Best.

This file is the "Report Card" for the session.
