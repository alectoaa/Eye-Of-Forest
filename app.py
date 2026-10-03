import sys
import os
import ee
import folium
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QPushButton, QLabel, QProgressBar, QTextEdit,
                             QSpinBox, QDoubleSpinBox, QGroupBox, QMessageBox, QComboBox)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QFont

HASAT_TAKVIMI = {
    "Spring": {"olive": False, "citrus": True, "other": False},
    "Summer": {"olive": False, "citrus": False, "other": True},
    "Autumn": {"olive": True, "citrus": False, "other": True},
    "Winter": {"olive": False, "citrus": True, "other": False},
}

class EarthEngineWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str, int, int, int, int, int)
    error = pyqtSignal(str)

    def __init__(self, lat, lon, buffer_km, start_date, end_date, scale, season):
        super().__init__()
        self.lat = lat
        self.lon = lon
        self.buffer_km = buffer_km
        self.start_date = start_date
        self.end_date = end_date
        self.scale = scale
        self.season = season

    def run(self):
        try:
            self.progress.emit("Checking the Earth Engine connection...")

            connected = False
            try:
                ee.Initialize(project='your-earth-engine-project-id')
                self.progress.emit("✓ Connected to Earth Engine!")
                connected = True
            except:
                pass

            if not connected:
                try:
                    self.progress.emit("Authenticating...")
                    ee.Authenticate()
                    ee.Initialize(project='your-earth-engine-project-id')
                    self.progress.emit("✓ Authentication complete!")
                    connected = True
                except:
                    pass

            if not connected:
                try:
                    ee.Initialize()
                    self.progress.emit("✓ Connected to Earth Engine!")
                    connected = True
                except:
                    pass

            if not connected:
                self.error.emit("Could not connect to Google Earth Engine!\n\nTo fix this:\n1. Open a terminal or Command Prompt\n2. Run 'earthengine authenticate'\n3. Sign in with your Google account\n4. Restart the application")
                return
            
            self.progress.emit("Defining the analysis area...")
            roi = ee.Geometry.Point([self.lon, self.lat]).buffer(self.buffer_km * 1000)

            self.progress.emit("Searching for Sentinel-2 imagery...")
            sentinel_collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(roi)
                .filterDate(self.start_date, self.end_date)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50))
            )

            collection_size = sentinel_collection.size().getInfo()
            self.progress.emit(f"✓ {collection_size} satellite images found")

            if collection_size == 0:
                raise Exception("No suitable imagery was found for the selected date range")

            sentinel = sentinel_collection.median().select(['B2', 'B3', 'B4', 'B5', 'B8', 'B8A', 'B11'])

            self.progress.emit("Calculating NDVI...")
            ndvi = sentinel.normalizedDifference(['B8', 'B4']).rename('NDVI')

            self.progress.emit("Calculating EVI...")
            evi = sentinel.expression(
                '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))',
                {'NIR': sentinel.select('B8'), 'RED': sentinel.select('B4'), 'BLUE': sentinel.select('B2')}
            ).rename('EVI')

            self.progress.emit("Calculating NDRE...")
            ndre = sentinel.normalizedDifference(['B8A', 'B5']).rename('NDRE')

            self.progress.emit("Calculating NDWI...")
            ndwi = sentinel.normalizedDifference(['B3', 'B8']).rename('NDWI')

            actual_scale = max(self.scale, 20)

            self.progress.emit("🌳 Running spectral analysis...")
            vegetation_clean = ndvi.gt(0.25).focal_median(radius=1, kernelType='square', units='pixels')

            olive_mask = (vegetation_clean
                .And(ndvi.gte(0.25)).And(ndvi.lt(0.44))
                .And(ndwi.lt(0.0))
                .And(ndre.gte(0.05))
            )
            citrus_mask = (vegetation_clean
                .And(ndvi.gte(0.38)).And(ndvi.lt(0.60))
                .And(ndwi.gte(0.0))
                .And(ndre.gte(0.15))
            )
            other_mask = (vegetation_clean
                .And(ndvi.gte(0.50)).And(ndvi.lt(0.74))
                .And(ndwi.gte(-0.1))
                .And(ndre.gte(0.10))
            )
            pine_mask = (vegetation_clean
                .And(ndvi.gte(0.65)).And(ndvi.lt(0.86))
                .And(ndwi.lt(0.05))
                .And(ndre.gte(0.20))
            )
            shrub_mask = vegetation_clean.And(ndvi.gte(0.82))
            
            
            self.progress.emit("🌳 Converting vegetation detections to map features...")

            self.progress.emit("🫒 Processing olive trees...")
            try:
                olive_connected = olive_mask.connectedPixelCount(100, False)
                olive_single = olive_mask.updateMask(olive_connected.lte(4))
                olive_groups = olive_mask.updateMask(olive_connected.gt(4))
                olive_single_vectors = olive_single.reduceToVectors(geometry=roi, scale=actual_scale, maxPixels=1e9, geometryType='centroid', bestEffort=True)
                olive_single_count = olive_single_vectors.size().getInfo()
                olive_group_vectors = olive_groups.reduceToVectors(geometry=roi, scale=actual_scale, maxPixels=1e9, geometryType='centroid', bestEffort=True)
                olive_group_count = olive_group_vectors.size().getInfo()
                self.progress.emit(f"  ✓ {olive_single_count} individual, {olive_group_count} groups")
            except Exception as e:
                self.progress.emit(f"  ⚠ Olive processing error: {str(e)}")
                olive_single_vectors = olive_group_vectors = ee.FeatureCollection([])
                olive_single_count = olive_group_count = 0

            self.progress.emit("🍊 Processing citrus trees...")
            try:
                citrus_connected = citrus_mask.connectedPixelCount(100, False)
                citrus_single = citrus_mask.updateMask(citrus_connected.lte(4))
                citrus_groups = citrus_mask.updateMask(citrus_connected.gt(4))
                citrus_single_vectors = citrus_single.reduceToVectors(geometry=roi, scale=actual_scale, maxPixels=1e9, geometryType='centroid', bestEffort=True)
                citrus_single_count = citrus_single_vectors.size().getInfo()
                citrus_group_vectors = citrus_groups.reduceToVectors(geometry=roi, scale=actual_scale, maxPixels=1e9, geometryType='centroid', bestEffort=True)
                citrus_group_count = citrus_group_vectors.size().getInfo()
                self.progress.emit(f"  ✓ {citrus_single_count} individual, {citrus_group_count} groups")
            except Exception as e:
                self.progress.emit(f"  ⚠ Citrus processing error: {str(e)}")
                citrus_single_vectors = citrus_group_vectors = ee.FeatureCollection([])
                citrus_single_count = citrus_group_count = 0

            self.progress.emit("🍎 Processing other fruit trees...")
            try:
                other_connected = other_mask.connectedPixelCount(100, False)
                other_single = other_mask.updateMask(other_connected.lte(4))
                other_groups = other_mask.updateMask(other_connected.gt(4))
                other_single_vectors = other_single.reduceToVectors(geometry=roi, scale=actual_scale, maxPixels=1e9, geometryType='centroid', bestEffort=True)
                other_single_count = other_single_vectors.size().getInfo()
                other_group_vectors = other_groups.reduceToVectors(geometry=roi, scale=actual_scale, maxPixels=1e9, geometryType='centroid', bestEffort=True)
                other_group_count = other_group_vectors.size().getInfo()
                self.progress.emit(f"  ✓ {other_single_count} individual, {other_group_count} groups")
            except Exception as e:
                self.progress.emit(f"  ⚠ Other fruit tree processing error: {str(e)}")
                other_single_vectors = other_group_vectors = ee.FeatureCollection([])
                other_single_count = other_group_count = 0

            self.progress.emit("🌲 Processing pine groups...")
            try:
                pine_connected = pine_mask.connectedPixelCount(100, False)
                pine_groups = pine_mask.updateMask(pine_connected.gt(5))
                pine_group_vectors = pine_groups.reduceToVectors(geometry=roi, scale=actual_scale, maxPixels=1e9, geometryType='centroid', bestEffort=True)
                pine_group_count = pine_group_vectors.size().getInfo()
                self.progress.emit(f"  ✓ {pine_group_count} groups")
            except Exception as e:
                self.progress.emit(f"  ⚠ Pine processing error: {str(e)}")
                pine_group_vectors = ee.FeatureCollection([])
                pine_group_count = 0

            self.progress.emit("🌿 Processing shrub and ornamental groups...")
            try:
                shrub_connected = shrub_mask.connectedPixelCount(100, False)
                shrub_groups = shrub_mask.updateMask(shrub_connected.gt(5))
                shrub_group_vectors = shrub_groups.reduceToVectors(geometry=roi, scale=actual_scale, maxPixels=1e9, geometryType='centroid', bestEffort=True)
                shrub_group_count = shrub_group_vectors.size().getInfo()
                self.progress.emit(f"  ✓ {shrub_group_count} groups")
            except Exception as e:
                self.progress.emit(f"  ⚠ Shrub processing error: {str(e)}")
                shrub_group_vectors = ee.FeatureCollection([])
                shrub_group_count = 0
            
            olive_count  = olive_single_count  + olive_group_count
            citrus_count = citrus_single_count + citrus_group_count
            other_count  = other_single_count  + other_group_count
            tree_count   = olive_count + citrus_count + other_count + pine_group_count + shrub_group_count

            self.progress.emit(f"✓ Total {tree_count} trees/groups detected")
            self.progress.emit(f"  🫒 Olives: {olive_count} ({olive_single_count} individual, {olive_group_count} groups)")
            self.progress.emit(f"  🍊 Citrus: {citrus_count} ({citrus_single_count} individual, {citrus_group_count} groups)")
            self.progress.emit(f"  🍎 Other fruit: {other_count} ({other_single_count} individual, {other_group_count} groups)")
            self.progress.emit(f"  🌲 Pine: {pine_group_count} groups")
            self.progress.emit(f"  🌿 Shrubs/Ornamental: {shrub_group_count} groups")

            self.progress.emit("Creating the map...")
            m = folium.Map(
                location=[self.lat, self.lon],
                zoom_start=15,
                tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                attr='Google Satellite'
            )

            self.progress.emit("🎨 Adding detections to the map...")

            for i, f in enumerate(olive_single_vectors.getInfo()['features']):
                c = f['geometry']['coordinates']
                folium.CircleMarker(location=[c[1],c[0]], radius=6, color='#4a6b23', fill=True, fillColor='#6B8E23', fillOpacity=0.9, weight=2, popup=f'🫒 Olive #{i+1}').add_to(m)
            for i, f in enumerate(olive_group_vectors.getInfo()['features']):
                c = f['geometry']['coordinates']
                folium.Circle(location=[c[1],c[0]], radius=25, color='#4a6b23', fill=True, fillColor='#6B8E23', fillOpacity=0.6, weight=3, popup=f'🫒 Olive Group #{i+1}').add_to(m)

            for i, f in enumerate(citrus_single_vectors.getInfo()['features']):
                c = f['geometry']['coordinates']
                folium.CircleMarker(location=[c[1],c[0]], radius=6, color='#cc7000', fill=True, fillColor='#FFA500', fillOpacity=0.9, weight=2, popup=f'🍊 Citrus #{i+1}').add_to(m)
            for i, f in enumerate(citrus_group_vectors.getInfo()['features']):
                c = f['geometry']['coordinates']
                folium.Circle(location=[c[1],c[0]], radius=25, color='#cc7000', fill=True, fillColor='#FFA500', fillOpacity=0.6, weight=3, popup=f'🍊 Citrus Group #{i+1}').add_to(m)

            for i, f in enumerate(other_single_vectors.getInfo()['features']):
                c = f['geometry']['coordinates']
                folium.CircleMarker(location=[c[1],c[0]], radius=6, color='#b31a1a', fill=True, fillColor='#FF6347', fillOpacity=0.9, weight=2, popup=f'🍎 Tree #{i+1}').add_to(m)
            for i, f in enumerate(other_group_vectors.getInfo()['features']):
                c = f['geometry']['coordinates']
                folium.Circle(location=[c[1],c[0]], radius=25, color='#b31a1a', fill=True, fillColor='#FF6347', fillOpacity=0.6, weight=3, popup=f'🍎 Tree Group #{i+1}').add_to(m)

            for i, f in enumerate(pine_group_vectors.getInfo()['features']):
                c = f['geometry']['coordinates']
                folium.Circle(location=[c[1],c[0]], radius=30, color='#1a4d2e', fill=True, fillColor='#2d5f3f', fillOpacity=0.6, weight=3, popup=f'🌲 Pine Group #{i+1}').add_to(m)

            for i, f in enumerate(shrub_group_vectors.getInfo()['features']):
                c = f['geometry']['coordinates']
                folium.Circle(location=[c[1],c[0]], radius=30, color='#4a7c59', fill=True, fillColor='#5f9ea0', fillOpacity=0.6, weight=3, popup=f'🌿 Shrub/Ornamental Group #{i+1}').add_to(m)
            

            folium.Marker(
                location=[self.lat, self.lon],
                popup='📍 Selected analysis center',
                icon=folium.Icon(color='red', icon='map-marker', prefix='fa')
            ).add_to(m)
            

            folium.Circle(
                location=[self.lat, self.lon],
                radius=self.buffer_km * 1000,
                color='blue',
                fill=False,
                weight=2,
                popup=f'Analysis Area ({self.buffer_km} km)'
            ).add_to(m)
            

            legend_html = f'''
            <style>
                .legend-container {{
                    position: fixed;
                    top: 10px;
                    right: 10px;
                    background: rgba(0, 0, 0, 0.3);
                    color: white;
                    padding: 15px;
                    border-radius: 15px;
                    z-index: 1000;
                    border: 2px solid rgba(0, 217, 255, 0.3);
                    min-width: 300px;
                    box-shadow: 0 8px 32px rgba(0, 217, 255, 0.2);
                    transition: all 0.3s ease;
                    backdrop-filter: blur(5px);
                }}
                
                .legend-container:hover {{
                    background: rgba(0, 0, 0, 0.95);
                    border-color: #00d9ff;
                    box-shadow: 0 12px 48px rgba(0, 217, 255, 0.4);
                    transform: scale(1.02);
                }}
                
                .legend-title {{
                    margin: 0 0 15px 0;
                    color: #00d9ff;
                    border-bottom: 2px solid #00d9ff;
                    padding-bottom: 10px;
                    font-size: 16px;
                    font-weight: bold;
                    opacity: 0.8;
                    transition: opacity 0.3s ease;
                }}
                
                .legend-container:hover .legend-title {{
                    opacity: 1;
                }}
                
                .stats-box {{
                    margin: 12px 0;
                    padding: 12px;
                    background: linear-gradient(135deg, rgba(0, 217, 255, 0.1), rgba(0, 160, 200, 0.1));
                    border-radius: 8px;
                    border-left: 3px solid #00d9ff;
                    opacity: 0.7;
                    transition: opacity 0.3s ease;
                }}
                
                .legend-container:hover .stats-box {{
                    opacity: 1;
                }}
                
                .tree-item {{
                    padding: 6px 0;
                    font-size: 13px;
                    opacity: 0.8;
                    transition: opacity 0.3s ease;
                }}
                
                .legend-container:hover .tree-item {{
                    opacity: 1;
                }}
                
                .tree-subitem {{
                    padding: 3px 0 3px 15px;
                    font-size: 11px;
                    opacity: 0.7;
                    transition: opacity 0.3s ease;
                }}
                
                .legend-container:hover .tree-subitem {{
                    opacity: 1;
                }}
                
                .map-legend-item {{
                    margin: 8px 0;
                    padding: 6px;
                    border-left: 3px solid;
                    border-radius: 4px;
                    font-size: 12px;
                    opacity: 0.7;
                    transition: all 0.3s ease;
                }}
                
                .legend-container:hover .map-legend-item {{
                    opacity: 1;
                    padding-left: 10px;
                }}
                
                .tip-box {{
                    margin-top: 12px;
                    padding: 8px;
                    background: rgba(255, 255, 255, 0.05);
                    border-radius: 6px;
                    font-size: 10px;
                    border: 1px solid rgba(0, 217, 255, 0.2);
                    opacity: 0.6;
                    transition: opacity 0.3s ease;
                }}
                
                .legend-container:hover .tip-box {{
                    opacity: 1;
                }}
            </style>
            
            <div class="legend-container">
                <h3 class="legend-title">🌳 Tree Analysis</h3>
                
                <div class="stats-box">
                    <strong style="color: #00d9ff; font-size: 13px;">📊 Detected</strong><br>
                    <div style="margin-top: 10px;">
                        <div class="tree-item">🫒 Olives: <strong style="color: #6B8E23;">{olive_count}</strong></div>
                        <div class="tree-subitem">• Individual: {olive_single_count}</div>
                        <div class="tree-subitem">• Groups: {olive_group_count}</div>
                        
                        <div class="tree-item" style="margin-top: 5px;">🍊 Citrus: <strong style="color: #FFA500;">{citrus_count}</strong></div>
                        <div class="tree-subitem">• Individual: {citrus_single_count}</div>
                        <div class="tree-subitem">• Groups: {citrus_group_count}</div>
                        
                        <div class="tree-item" style="margin-top: 5px;">🍎 Other Fruit: <strong style="color: #FF6347;">{other_count}</strong></div>
                        <div class="tree-subitem">• Individual: {other_single_count}</div>
                        <div class="tree-subitem">• Groups: {other_group_count}</div>
                        
                        <div class="tree-item" style="margin-top: 5px;">🌲 Pine: <strong style="color: #2d5f3f;">{pine_group_count}</strong></div>
                        <div class="tree-subitem">• Groups only</div>
                        
                        <div class="tree-item" style="margin-top: 5px;">🌿 Shrubs/Ornamental: <strong style="color: #5f9ea0;">{shrub_group_count}</strong></div>
                        <div class="tree-subitem">• Groups only</div>
                        
                        <div class="tree-item" style="margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(0,217,255,0.3);">
                            📍 Total: <strong style="color: #00d9ff; font-size: 15px;">{tree_count}</strong>
                        </div>
                    </div>
                </div>
                
                <div style="margin: 15px 0 10px 0; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.2);">
                    <strong style="color: #00d9ff; font-size: 12px;">🗺️ Map Legend</strong>
                </div>
                
                <div class="map-legend-item" style="background: rgba(107,142,35,0.2); border-color: #6B8E23;">
                    🫒 <strong style="color: #6B8E23;">Green</strong> = Olives<br>
                    <span style="font-size: 10px; opacity: 0.8;">• Marker = Individual | ○ Circle = Group</span>
                </div>
                <div class="map-legend-item" style="background: rgba(255,165,0,0.2); border-color: #FFA500;">
                    🍊 <strong style="color: #FFA500;">Orange</strong> = Citrus<br>
                    <span style="font-size: 10px; opacity: 0.8;">• Marker = Individual | ○ Circle = Group</span>
                </div>
                <div class="map-legend-item" style="background: rgba(255,99,71,0.2); border-color: #FF6347;">
                    🍎 <strong style="color: #FF6347;">Red</strong> = Other Fruit<br>
                    <span style="font-size: 10px; opacity: 0.8;">• Marker = Individual | ○ Circle = Group</span>
                </div>
                <div class="map-legend-item" style="background: rgba(45,95,63,0.2); border-color: #2d5f3f;">
                    🌲 <strong style="color: #2d5f3f;">Dark Green</strong> = Pine<br>
                    <span style="font-size: 10px; opacity: 0.8;">○ Groups only</span>
                </div>
                <div class="map-legend-item" style="background: rgba(95,158,160,0.2); border-color: #5f9ea0;">
                    🌿 <strong style="color: #5f9ea0;">Light Green</strong> = Shrubs/Ornamental<br>
                    <span style="font-size: 10px; opacity: 0.8;">○ Groups only</span>
                </div>
                <div class="map-legend-item" style="background: rgba(255,0,0,0.2); border-color: #FF0000;">
                    📍 <strong style="color: #FF0000;">Marker</strong> = Selected location
                </div>
                
                <div class="tip-box">
                    💡 Zoom in to see more detail<br>
                    🛰️ Sentinel-2 · NDVI + NDRE + NDWI analysis<br>
                    📏 Analysis radius: {self.buffer_km} km<br>
                    🌟 Blinking markers = Harvest season!
                </div>
            </div>
            '''
            m.get_root().html.add_child(folium.Element(legend_html))
            
            
            hasat_durumu = HASAT_TAKVIMI.get(self.season, {})
            
            
            blink_style = '''
            <style>
            @keyframes blink {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.2; }
            }
            .harvest-blink {
                animation: blink 1.5s ease-in-out infinite !important;
            }
            </style>
            '''
            m.get_root().html.add_child(folium.Element(blink_style))
            

            blink_script = '''
            <script>
            function blinkHarvestTrees() {
                // Tüm path ve circle elementlerini bul
                var allElements = document.querySelectorAll('path.leaflet-interactive, circle.leaflet-interactive');
                
                allElements.forEach(function(element) {
                    var fillColor = element.getAttribute('fill') || '';
                    var stroke = element.getAttribute('stroke') || '';
                    
                    // Renklere göre hasat zamanını kontrol et
            '''
            

            if hasat_durumu.get('olive', False):
                blink_script += '''
                    if (fillColor.toLowerCase().includes('6b8e23') || stroke.toLowerCase().includes('6b8e23')) {
                        element.classList.add('harvest-blink');
                    }
                '''
            if hasat_durumu.get('citrus', False):
                blink_script += '''
                    if (fillColor.toLowerCase().includes('ffa500') || stroke.toLowerCase().includes('ffa500')) {
                        element.classList.add('harvest-blink');
                    }
                '''
            if hasat_durumu.get('other', False):
                blink_script += '''
                    if (fillColor.toLowerCase().includes('ff6347') || stroke.toLowerCase().includes('ff6347')) {
                        element.classList.add('harvest-blink');
                    }
                '''
            
            blink_script += '''
                });
            }
            
            // Harita yüklendiğinde çalıştır
            setTimeout(blinkHarvestTrees, 2000);
            
            // MutationObserver ile yeni eklenen elementleri izle
            var observer = new MutationObserver(function(mutations) {
                blinkHarvestTrees();
            });
            
            setTimeout(function() {
                var mapPane = document.querySelector('.leaflet-map-pane');
                if (mapPane) {
                    observer.observe(mapPane, { childList: true, subtree: true });
                }
            }, 1000);
            </script>
            '''
            m.get_root().html.add_child(folium.Element(blink_script))
            
            self.progress.emit("Saving the map...")
            html_path = os.path.abspath("fruit_tree_analysis.html")
            m.save(html_path)
            
            self.finished.emit(html_path, olive_count, citrus_count, other_count, pine_group_count, shrub_group_count)
            
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🍊 Fruit Tree Analysis")
        self.setGeometry(50, 50, 1600, 900)
        

        self.setStyleSheet("""
            QMainWindow {
                background-color: #0a1f1f;
                color: #ffffff;
            }
            QWidget {
                background-color: #0a1f1f;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #1a4d4d;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 15px;
                background-color: #0d2d2d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #00d9ff;
                font-size: 14px;
            }
            QLabel {
                color: #ffffff;
                font-size: 12px;
                padding: 2px;
            }
            QPushButton {
                background-color: #0d5959;
                border: 2px solid: #14a0a0;
                border-radius: 8px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #14a0a0;
                border-color: #00d9ff;
            }
            QPushButton:pressed {
                background-color: #0a4545;
            }
            QPushButton:disabled {
                background-color: #1a3333;
                border-color: #2a4444;
                color: #5a7777;
            }
            QSpinBox, QDoubleSpinBox, QLineEdit, QDateEdit {
                background-color: #1a3d3d;
                border: 2px solid #2a5555;
                border-radius: 6px;
                padding: 8px;
                color: #ffffff;
                font-size: 12px;
            }
            QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QDateEdit:focus {
                border-color: #00d9ff;
            }
            QTextEdit {
                background-color: #0d2d2d;
                border: 2px solid #1a4d4d;
                border-radius: 6px;
                color: #ffffff;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                padding: 8px;
            }
            QProgressBar {
                border: 2px solid #1a4d4d;
                border-radius: 6px;
                background-color: #0d2d2d;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #00d9ff;
                border-radius: 4px;
            }
            QComboBox {
                background-color: #1a3d3d;
                border: 2px solid #2a5555;
                border-radius: 6px;
                padding: 8px;
                color: #ffffff;
                font-size: 12px;
            }
            QComboBox:focus {
                border-color: #00d9ff;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #0d2d2d;
                color: #ffffff;
                selection-background-color: #00d9ff;
                selection-color: #000000;
            }
        """)
        

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        

        main_layout = QHBoxLayout(main_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        

        self.create_control_panel()
        main_layout.addWidget(self.control_panel, 1)
        

        self.create_map_panel()
        main_layout.addWidget(self.map_panel, 4)
        

        self.worker = None
        

        self.load_default_map()
        
    def create_control_panel(self):
        """Kontrol panelini oluştur"""
        self.control_panel = QGroupBox("🎛️ Kontrol Paneli")
        self.control_panel.setMaximumWidth(380)
        layout = QVBoxLayout(self.control_panel)
        layout.setSpacing(15)
        

        title = QLabel("🍊 Fruit Tree Analysis")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("""
            color: #00d9ff; 
            font-size: 16px; 
            padding: 12px; 
            text-align: center;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0d4d5d, stop:1 #0a3d4d);
            border-radius: 10px;
            border: 2px solid #00d9ff;
        """)
        layout.addWidget(title)
        

        location_group = QGroupBox("📍 Analysis Center")
        location_layout = QVBoxLayout(location_group)
        location_layout.setSpacing(8)

        location_help = QLabel("Enter latitude and longitude. In Google Maps, right-click a location to copy its coordinates.")
        location_help.setWordWrap(True)
        location_layout.addWidget(location_help)

        coordinates_layout = QHBoxLayout()
        self.latitude_spin = QDoubleSpinBox()
        self.latitude_spin.setRange(-90.0, 90.0)
        self.latitude_spin.setDecimals(6)
        self.latitude_spin.setSingleStep(0.001)
        self.latitude_spin.setValue(0.0)
        self.latitude_spin.setPrefix("Lat ")
        self.latitude_spin.setToolTip("Latitude: -90 to 90")
        coordinates_layout.addWidget(self.latitude_spin)

        self.longitude_spin = QDoubleSpinBox()
        self.longitude_spin.setRange(-180.0, 180.0)
        self.longitude_spin.setDecimals(6)
        self.longitude_spin.setSingleStep(0.001)
        self.longitude_spin.setValue(0.0)
        self.longitude_spin.setPrefix("Lon ")
        self.longitude_spin.setToolTip("Longitude: -180 to 180")
        coordinates_layout.addWidget(self.longitude_spin)

        location_layout.addLayout(coordinates_layout)

        default_location = QLabel("Default: the selected area")
        default_location.setStyleSheet("""
            color: #00d9ff; 
            font-weight: bold; 
            font-size: 11px;
            padding: 4px;
        """)
        location_layout.addWidget(default_location)

        layout.addWidget(location_group)
        

        analysis_group = QGroupBox("⚙️ Analysis Settings")
        analysis_layout = QVBoxLayout(analysis_group)
        analysis_layout.setSpacing(12)
        

        analysis_layout.addWidget(QLabel("📏 Analysis Radius:"))
        self.buffer_spin = QSpinBox()
        self.buffer_spin.setRange(1, 5)
        self.buffer_spin.setValue(2)
        self.buffer_spin.setSuffix(" km")
        analysis_layout.addWidget(self.buffer_spin)
        

        analysis_layout.addWidget(QLabel("🌤️ Season:"))
        self.season_combo = QComboBox()
        self.season_combo.addItems([
            "🌸 Spring (March–May)",
            "☀️ Summer (June–August)", 
            "🍂 Autumn (September–November)",
            "❄️ Winter (December–February)"
        ])
        self.season_combo.setCurrentIndex(1)
        self.season_combo.setStyleSheet("""
            QComboBox {
                background-color: #3d3d3d;
                border: 2px solid #555555;
                border-radius: 6px;
                padding: 8px;
                color: #ffffff;
                font-size: 12px;
            }
            QComboBox:focus {
                border-color: #00ff88;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #ffffff;
                selection-background-color: #00ff88;
                selection-color: #000000;
            }
        """)
        analysis_layout.addWidget(self.season_combo)
        

        analysis_layout.addWidget(QLabel("🎯 Detection Detail:"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            "⚡ Fast (Low detail)",
            "⚖️ Balanced (Recommended)",
            "🔍 Precise (High detail)"
        ])
        self.quality_combo.setCurrentIndex(1)
        self.quality_combo.setStyleSheet("""
            QComboBox {
                background-color: #3d3d3d;
                border: 2px solid #555555;
                border-radius: 6px;
                padding: 8px;
                color: #ffffff;
                font-size: 12px;
            }
            QComboBox:focus {
                border-color: #00ff88;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #ffffff;
                selection-background-color: #00ff88;
                selection-color: #000000;
            }
        """)
        analysis_layout.addWidget(self.quality_combo)
        
        layout.addWidget(analysis_group)
        

        food_group = QGroupBox("🍽️ Recipe Ideas")
        food_layout = QVBoxLayout(food_group)
        food_layout.setSpacing(10)
        

        food_info = QLabel("""
<b style="color: #6B8E23;">🫒 Olives</b><br>
<span style="font-size: 10px;">→ Olive oil, cracked olives</span><br><br>

<b style="color: #FFA500;">🍊 Citrus</b><br>
<span style="font-size: 10px;">→ Orange juice, marmalade</span><br><br>

<b style="color: #FF6347;">🍎 Other Fruit</b><br>
<span style="font-size: 10px;">→ Jam, fruit tart, compote</span><br><br>

<span style="color: #00d9ff; font-size: 9px;">🛰️ NDVI + NDRE + NDWI analysis</span>
        """)
        food_info.setStyleSheet("""
            color: #ffffff; 
            font-size: 11px; 
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0d3d3d, stop:1 #0a2d2d);
            padding: 12px; 
            border-radius: 8px;
            border: 2px solid #00d9ff;
            line-height: 1.5;
        """)
        food_layout.addWidget(food_info)
        
        layout.addWidget(food_group)
        

        stats_group = QGroupBox("📊 Latest Analysis")
        stats_layout = QVBoxLayout(stats_group)
        stats_layout.setSpacing(8)
        
        self.stats_label = QLabel("""
<div style="text-align: center; padding: 10px;">
<span style="color: #888; font-size: 11px;">
No analysis yet.<br>
Click the button to start an analysis.
</span>
</div>
        """)
        self.stats_label.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0d2d2d, stop:1 #0a1d1d);
            border: 2px solid #00d9ff;
            border-radius: 8px;
            padding: 10px;
            min-height: 80px;
        """)
        stats_layout.addWidget(self.stats_label)
        
        layout.addWidget(stats_group)
        

        self.analyze_btn = QPushButton("🚀 START ANALYSIS")
        self.analyze_btn.clicked.connect(self.start_analysis)
        self.analyze_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00d9ff, stop:1 #00a0cc);
                font-size: 18px;
                font-weight: bold;
                padding: 18px;
                margin: 15px 0;
                border-radius: 12px;
                border: 3px solid #00d9ff;
                color: #000000;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00ffff, stop:1 #00bbdd);
                border-color: #00ffff;
                transform: scale(1.05);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00a0cc, stop:1 #007799);
            }
            QPushButton:disabled {
                background-color: #1a3333;
                border-color: #2a4444;
                color: #5a7777;
            }
        """)
        layout.addWidget(self.analyze_btn)
        

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #00d9ff;
                border-radius: 8px;
                background-color: #0d2d2d;
                text-align: center;
                color: #00d9ff;
                font-weight: bold;
                font-size: 12px;
                height: 30px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d9ff, stop:1 #00a0cc);
                border-radius: 6px;
            }
        """)
        layout.addWidget(self.progress_bar)
        

        log_label = QLabel("📋 Activity Log")
        log_label.setStyleSheet("""
            color: #00d9ff; 
            font-weight: bold; 
            font-size: 14px;
            padding: 5px;
        """)
        layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a1a1a;
                border: 2px solid #00d9ff;
                border-radius: 8px;
                color: #00d9ff;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.log_text)
        
        layout.addStretch()
        
    def create_map_panel(self):
        """Harita panelini oluştur"""
        self.map_panel = QGroupBox("🗺️ Map")
        layout = QVBoxLayout(self.map_panel)
        
        self.browser = QWebEngineView()
        layout.addWidget(self.browser)
        
    def load_default_map(self):
        """Varsayılan haritayı yükle"""
        default_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Fruit Tree Analysis</title>
            <style>
                body { 
                    font-family: 'Segoe UI', Arial, sans-serif; 
                    text-align: center; 
                    padding: 40px; 
                    background: linear-gradient(135deg, #0a1f2f, #0d3d4d, #0a2d3d);
                    color: #ffffff;
                    margin: 0;
                }
                .info { 
                    background: linear-gradient(145deg, rgba(0,217,255,0.1), rgba(0,160,200,0.05));
                    padding: 40px; 
                    border-radius: 25px; 
                    margin: 20px; 
                    box-shadow: 0 12px 40px rgba(0, 217, 255, 0.2);
                    border: 3px solid #00d9ff;
                    backdrop-filter: blur(10px);
                }
                .location-info { 
                    color: #00d9ff; 
                    font-size: 24px; 
                    font-weight: bold; 
                    margin-bottom: 25px;
                    text-shadow: 0 0 20px rgba(0, 217, 255, 0.5);
                }
                .fruit-icons {
                    font-size: 48px;
                    margin: 20px 0;
                    letter-spacing: 15px;
                }
                .description {
                    color: #e0e0e0;
                    line-height: 1.8;
                    font-size: 16px;
                }
                .highlight {
                    color: #00d9ff;
                    font-weight: bold;
                }
            </style>
        </head>
        <body>
            <h1 style="color: #00d9ff; font-size: 36px; text-shadow: 0 0 30px rgba(0,217,255,0.6);">
                🍊 Fruit Tree Analysis
            </h1>
            <div class="info">
                <div class="location-info">📍 Explore a location of your choice</div>
                <div class="fruit-icons">🫒 🍊 🍎</div>
                <div class="description">
                    <h3 style="color: #00d9ff;">Welcome!</h3>
                    <p>This app uses <span class="highlight">Sentinel-2 satellite imagery</span> to 
                    analyze vegetation around your selected location and display the results on a map.</p>
                    <p><strong style="color: #00d9ff;">Detected Vegetation:</strong></p>
                    <ul style="text-align: left; display: inline-block; font-size: 15px;">
                        <li>🫒 <strong style="color: #6B8E23;">Olive trees</strong> - dark green</li>
                        <li>🍊 <strong style="color: #FFA500;">Citrus trees</strong> - Orange</li>
                        <li>🍎 <strong style="color: #FF6347;">Other fruit trees</strong> - Red</li>
                        <li>🌲 <strong style="color: #2d5f3f;">Pine groups</strong></li>
                        <li>🌿 <strong style="color: #5f9ea0;">Shrub and ornamental groups</strong></li>
                    </ul>
                    <p style="margin-top: 25px;">Set your options in the left panel, then click 
                    <strong style="color: #00d9ff; font-size: 18px;">"START ANALYSIS"</strong> to begin.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        temp_path = os.path.abspath("temp_welcome.html")
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(default_html)
        
        self.browser.load(QUrl.fromLocalFile(temp_path))
        
    def start_analysis(self):
        """Analizi başlat"""
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Warning", "An analysis is already running!")
            return
            

        self.analyze_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.log_text.clear()
        

        lat = self.latitude_spin.value()
        lon = self.longitude_spin.value()
        buffer_km = self.buffer_spin.value()
        

        season_index = self.season_combo.currentIndex()
        season_names = ["Spring", "Summer", "Autumn", "Winter"]
        season = season_names[season_index]
        
        if season_index == 0:
            start_date = "2024-03-01"
            end_date = "2024-05-31"
        elif season_index == 1:
            start_date = "2024-06-01"
            end_date = "2024-08-31"
        elif season_index == 2:
            start_date = "2024-09-01"
            end_date = "2024-11-30"
        else:
            start_date = "2023-12-01"
            end_date = "2024-02-29"
        

        quality_index = self.quality_combo.currentIndex()
        if quality_index == 0:
            scale = 30
        elif quality_index == 1:
            scale = 20
        else:
            scale = 15
        

        self.worker = EarthEngineWorker(lat, lon, buffer_km, start_date, end_date, scale, season)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.error.connect(self.analysis_error)
        self.worker.start()
        
    def update_progress(self, message):
        """Progress güncelle"""
        self.log_text.append(f"• {message}")
        
    def analysis_finished(self, html_path, olive_count, citrus_count, other_count, pine_count, shrub_count):
        """Analiz tamamlandı"""
        self.log_text.append("✓ Analysis completed successfully!")
        self.browser.load(QUrl.fromLocalFile(html_path))
        

        total = olive_count + citrus_count + other_count + pine_count + shrub_count
        self.stats_label.setText(f"""
<div style="padding: 8px;">
    <div style="text-align: center; margin-bottom: 10px;">
        <span style="color: #00d9ff; font-size: 16px; font-weight: bold;">
            {total} Trees/Groups Detected
        </span>
    </div>
    <div style="font-size: 12px; line-height: 1.8;">
        <div>🫒 Olives: <strong style="color: #6B8E23;">{olive_count}</strong></div>
        <div>🍊 Citrus: <strong style="color: #FFA500;">{citrus_count}</strong></div>
        <div>🍎 Other Fruit: <strong style="color: #FF6347;">{other_count}</strong></div>
        <div>🌲 Pine: <strong style="color: #2d5f3f;">{pine_count}</strong></div>
        <div>🌿 Shrubs/Ornamental: <strong style="color: #5f9ea0;">{shrub_count}</strong></div>
    </div>
</div>
        """)
        

        self.analyze_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
    def analysis_error(self, error_message):
        """Analiz hatası"""
        self.log_text.append(f"✗ {error_message}")
        QMessageBox.critical(self, "Error", error_message)
        

        self.analyze_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())
