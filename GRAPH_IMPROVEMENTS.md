# Dashboard Graph Improvements

## Overview
Improved the main dashboard graph with Datadog-inspired controls and enhanced user experience.

## Changes Made

### 1. Display Mode Toggle ($ vs %)
- Added a toggle to switch between absolute dollar values and percentage change
- **Absolute Mode ($)**: Shows actual asset values in dollars
- **Percentage Mode (%)**: Shows percentage change from initial value
- Toggle buttons appear in the control bar at the top of the graph

### 2. Time Range Controls
- Added time range selector with 4 options:
  - **5M**: 5-minute aggregation
  - **1H**: 1-hour aggregation  
  - **1D**: 1-day aggregation
  - **All**: All data points without aggregation
- Time range buttons appear in the control bar alongside display mode toggle
- Backend updated to support "all" timeframe option

### 3. Interactive Legend (AI Trader Asset Ranking)
- Made the AI Trader Asset Ranking blocks clickable
- **Click to hide/show** specific trader series on the graph
- Visual feedback:
  - Hidden traders show "Hidden" overlay with reduced opacity
  - Active traders show ring highlight
  - Hover effects for better interactivity
- Helpful tooltip: "(Click to show/hide • All values in $)"

### 4. Enhanced Visual Design
- Control bar with grouped buttons in pill-style containers
- Active state highlighting for selected options
- Smooth transitions and hover effects
- Clear visual hierarchy inspired by Datadog's design

## Technical Implementation

### Frontend Changes
- **File**: `frontend/app/components/portfolio/AssetCurveWithData.tsx`
  - Added state management for `displayMode`, `timeframe`, and `hiddenAccounts`
  - Implemented percentage calculation logic
  - Updated Y-axis formatting based on display mode
  - Added control bar UI with time range and display mode toggles
  - Made legend blocks clickable with visibility toggle
  - Updated data filtering to respect hidden accounts

### Backend Changes
- **File**: `backend/api/ws.py`
  - Added "all" to valid timeframe options
  
- **File**: `backend/services/asset_curve_calculator.py`
  - Added "all" timeframe support (bucket_minutes = 0)
  - Modified `_get_bucketed_snapshots` to return all snapshots when bucket_minutes is 0

## Usage

### Switching Display Modes
1. Look for the "Display:" label in the control bar
2. Click "$ Absolute" for dollar values
3. Click "% Change" for percentage change from initial value

### Changing Time Range
1. Look for the "Time Range:" label in the control bar
2. Click any of the time range buttons (5M, 1H, 1D, All)
3. Graph will update to show data at the selected aggregation level

### Showing/Hiding Traders
1. Scroll to "AI Trader Asset Ranking" section below the graph
2. Click on any trader block to hide/show that trader's line
3. Hidden traders will show a "Hidden" overlay
4. Click again to show the trader

## Benefits
- **Better data visualization**: Switch between absolute and relative performance
- **Flexible time horizons**: View different time scales without leaving the page
- **Focus on specific traders**: Hide/show traders to reduce visual clutter
- **Datadog-inspired UX**: Professional, familiar interface for power users

## Testing
To test the improvements:
1. Open the application at http://localhost:8802
2. Navigate to the main dashboard
3. Try switching between $ and % display modes
4. Try different time ranges (5M, 1H, 1D, All)
5. Click on the AI Trader Asset Ranking blocks to hide/show traders
6. Observe smooth transitions and visual feedback

