#!/usr/bin/env python3
"""
convert_to_json.py
==================
Reads race_master_v9.1.xlsx and outputs JSON files for the Aup Dashboard.

Usage (from inside your aup-dashboard folder):
    python convert_to_json.py

Outputs into ./racing/ by default:
    racing/races.json         — All 53 races, cleaned and typed
    racing/bsr.json           — Broad Street Run series history
    racing/boston.json        — Boston Marathon history
    racing/ultras.json        — All Tier A ultra races
    racing/strava_annual.json — Year-in-review Strava data
    racing/splits.json        — Race splits keyed by race_id
    racing/garmin.json        — Garmin enrichment keyed by race_id
    racing/meta.json          — Generation metadata (timestamp, counts)
"""

import pandas as pd
import json
import os
from datetime import datetime, date
from pathlib import Path


def clean_val(v):
    """Convert numpy/pandas types to JSON-safe Python types."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip()
        return s if s and s.lower() not in ('nan', 'none', 'nat', 'n/a') else None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if hasattr(v, 'item'):
        v = v.item()
    if isinstance(v, (datetime, date)):
        return str(v)[:10]
    if isinstance(v, float):
        return int(v) if v == int(v) else round(v, 4)
    return v


def row_to_dict(row):
    return {k: clean_val(v) for k, v in row.items()}


def compute_percentile(place, field):
    try:
        place = float(place)
        field = float(field)
        if field > 0:
            return f"Top {(1 - place / field) * 100:.1f}%"
    except Exception:
        pass
    return None


def enrich_race(row):
    d = row_to_dict(row)

    # Computed percentiles
    d['oa_percentile']     = compute_percentile(d.get('OA\nPlace'), d.get('OA\nField'))
    d['gender_percentile'] = compute_percentile(d.get('Gender\nPlace'), d.get('Gender\nField'))
    d['ag_percentile']     = compute_percentile(d.get('AG\nPlace'), d.get('AG\nField'))

    # Data source badges
    badges = ['OFFICIAL']
    if str(d.get('Strava', '')).strip() in ('True', 'true', '1', '\u2713'):
        badges.append('STRAVA')
    if str(d.get('Garmin', '')).strip() in ('True', 'true', '1', '\u2713'):
        badges.append('GARMIN')
    d['data_badges'] = badges

    # Tier label
    tier_labels = {
        'A': 'Major Ultra', 'B': 'Marathon', 'C': 'Half Marathon',
        'D': 'Road Race',   'E': 'Charity/Fun Run', 'F': 'Challenge'
    }
    d['tier_label'] = tier_labels.get(str(d.get('Tier', '')), 'Unknown')

    return d


def load_races_sheet(path):
    """Load the RACES sheet, handling the two-row header."""
    try:
        df = pd.read_excel(path, sheet_name="\U0001f3c1 RACES", header=1)
    except Exception:
        # Fallback: try by index
        df = pd.read_excel(path, sheet_name=1, header=1)

    # Drop rows that aren't actual race data (Race ID must start with RACE_)
    df = df[df.iloc[:, 0].astype(str).str.startswith('RACE_')].copy()
    df['_date_str'] = pd.to_datetime(df['Date'], errors='coerce').dt.strftime('%Y-%m-%d')
    return df


def main():
    # Locate the Excel file
    excel_candidates = list(Path('.').glob('race_master*.xlsx'))
    if not excel_candidates:
        print("ERROR: No race_master*.xlsx file found in the current folder.")
        print("Make sure race_master_v9.1.xlsx is in the same folder as this script.")
        return
    excel_path = sorted(excel_candidates)[-1]
    print(f"Reading: {excel_path}")

    out_dir = Path('racing')
    out_dir.mkdir(exist_ok=True)

    # ── Load races ────────────────────────────────────────────────────────────
    df = load_races_sheet(excel_path)
    print(f"Loaded {len(df)} races from RACES sheet.")

    # ── races.json ────────────────────────────────────────────────────────────
    all_races = [enrich_race(row) for _, row in df.sort_values('_date_str').iterrows()]
    with open(out_dir / 'races.json', 'w') as f:
        json.dump({'count': len(all_races), 'races': all_races}, f, indent=2, default=str)
    print(f"  races.json        → {len(all_races)} races")

    # ── bsr.json ──────────────────────────────────────────────────────────────
    bsr = df[df['Series'].astype(str).str.contains('Broad Street', na=False)]
    bsr_list = [enrich_race(r) for _, r in bsr.sort_values('_date_str').iterrows()]
    with open(out_dir / 'bsr.json', 'w') as f:
        json.dump({'count': len(bsr_list), 'races': bsr_list}, f, indent=2, default=str)
    print(f"  bsr.json          → {len(bsr_list)} races")

    # ── boston.json ───────────────────────────────────────────────────────────
    boston = df[df['Race Name'].astype(str).str.contains('Boston', na=False, case=False)]
    boston_editions = {
        '2020-09-14': '2020 Virtual', '2021-10-11': '125th',
        '2023-04-17': '127th',        '2025-04-21': '129th',
        '2026-04-20': '130th'
    }
    boston_list = []
    for _, row in boston.sort_values('_date_str').iterrows():
        d = enrich_race(row)
        d['edition'] = boston_editions.get(d.get('_date_str', ''), '—')
        boston_list.append(d)
    with open(out_dir / 'boston.json', 'w') as f:
        json.dump({'count': len(boston_list), 'races': boston_list}, f, indent=2, default=str)
    print(f"  boston.json       → {len(boston_list)} races")

    # ── ultras.json ───────────────────────────────────────────────────────────
    ultras = df[df['Tier'].astype(str).str.strip() == 'A']
    ultras_list = [enrich_race(r) for _, r in ultras.sort_values('_date_str').iterrows()]
    with open(out_dir / 'ultras.json', 'w') as f:
        json.dump({'count': len(ultras_list), 'races': ultras_list}, f, indent=2, default=str)
    print(f"  ultras.json       → {len(ultras_list)} races")

    # ── strava_annual.json ────────────────────────────────────────────────────
    try:
        strava_df = pd.read_excel(excel_path, sheet_name="\U0001f49a STRAVA", header=1)
        strava_df = strava_df[pd.to_numeric(strava_df['Year'], errors='coerce').notna()]
        strava_list = [row_to_dict(r) for _, r in strava_df.iterrows()]
    except Exception as e:
        strava_list = []
        print(f"  Warning: could not load STRAVA sheet ({e})")
    with open(out_dir / 'strava_annual.json', 'w') as f:
        json.dump({'count': len(strava_list), 'years': strava_list}, f, indent=2, default=str)
    print(f"  strava_annual.json→ {len(strava_list)} years")

    # ── splits.json ───────────────────────────────────────────────────────────
    try:
        splits_df = pd.read_excel(excel_path, sheet_name="\U0001f4ca SPLITS", header=1)
        splits_df = splits_df[splits_df['Race ID'].astype(str).str.startswith('RACE_')]
        splits_list = [row_to_dict(r) for _, r in splits_df.iterrows()]
    except Exception as e:
        splits_list = []
        print(f"  Warning: could not load SPLITS sheet ({e})")
    with open(out_dir / 'splits.json', 'w') as f:
        json.dump({'count': len(splits_list), 'splits': splits_list}, f, indent=2, default=str)
    print(f"  splits.json       → {len(splits_list)} entries")

    # ── garmin.json ───────────────────────────────────────────────────────────
    try:
        garmin_df = pd.read_excel(excel_path, sheet_name="\u231a GARMIN", header=1)
        garmin_df = garmin_df[garmin_df['Race ID'].astype(str).str.startswith('RACE_')]
        garmin_list = [row_to_dict(r) for _, r in garmin_df.iterrows()]
    except Exception as e:
        garmin_list = []
        print(f"  Warning: could not load GARMIN sheet ({e})")
    with open(out_dir / 'garmin.json', 'w') as f:
        json.dump({'count': len(garmin_list), 'activities': garmin_list}, f, indent=2, default=str)
    print(f"  garmin.json       → {len(garmin_list)} entries")

    # ── meta.json ─────────────────────────────────────────────────────────────
    tiers = {}
    for t in ['A', 'B', 'C', 'D', 'E', 'F']:
        tiers[t] = int((df['Tier'].astype(str).str.strip() == t).sum())

    meta = {
        'generated_at':   datetime.now().isoformat(),
        'source_file':    str(excel_path),
        'version':        'v9.1',
        'race_count':     len(all_races),
        'bsr_count':      len(bsr_list),
        'boston_count':   len(boston_list),
        'ultra_count':    len(ultras_list),
        'strava_years':   len(strava_list),
        'garmin_matched': len(garmin_list),
        'tiers':          tiers,
        'pr': {
            '5k_competitive':  '19:21',
            '8k':              '33:41',
            '10_mile_bsr':     '1:06:54',
            'half_marathon':   '1:28:16',
            'marathon':        '2:53:35',
            'marathon_boston': '2:54:10',
            '50k':             '3:58:13',
            '50_mile':         '8:03:54',
            '100_mile':        '21:08:43',
        }
    }
    with open(out_dir / 'meta.json', 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"  meta.json         → generated")

    print(f"\n✅ All JSON files written to {out_dir}/")
    print("\nNext steps:")
    print("  1. Check the racing/ folder — you should see 8 .json files")
    print("  2. Run: git add .")
    print("  3. Run: git commit -m \"Add racing JSON data\"")
    print("  4. Run: git push")
    print("  5. Your data will be live at:")
    print("     https://raw.githubusercontent.com/AJDar808/aup-dashboard/main/racing/races.json")


if __name__ == '__main__':
    main()
