# Author: Niranjan R.
# Echo-Acoustic Haptic Compass - Simulation Backend

from flask import Flask, render_template, request, jsonify
import math
import mysql.connector
from datetime import datetime
import numpy as np
from sklearn.cluster import KMeans
import matplotlib
matplotlib.use('Agg') # Required for server-side plotting without a GUI
import matplotlib.pyplot as plt
import os

app = Flask(__name__)

# System Constants
SPEED_OF_SOUND = 343.0  # v in m/s
FREQUENCY = 40000.0     # f in Hz

# MySQL Configuration (Update with your local credentials)
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'password',  # <-- UPDATE THIS TO YOUR MYSQL PASSWORD
    'database': 'echotag_db'
}

def initialize_database():
    """Checks if the database/tables exist, and creates them if they don't."""
    try:
        setup_conn = mysql.connector.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password']
        )
        setup_cursor = setup_conn.cursor()
        
        setup_cursor.execute("CREATE DATABASE IF NOT EXISTS echotag_db;")
        setup_cursor.execute("USE echotag_db;")
        setup_cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                object_id VARCHAR(50),
                x_coord FLOAT,
                y_coord FLOAT,
                distance_mm FLOAT,
                phase_shift FLOAT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        setup_conn.commit()
        setup_cursor.close()
        setup_conn.close()
        print("✅ Database is ready and connected.")
        
    except mysql.connector.Error as err:
        print(f"❌ Database Setup Error: {err}")

@app.route('/')
def index():
    """Serves the main simulator dashboard."""
    return render_template('index.html')

@app.route('/calculate_apls', methods=['POST'])
def calculate_apls():
    """Calculates APSL and logs tracking data to MySQL."""
    data = request.get_json()
    distance_mm = data.get('distance_mm', 0)
    x = data.get('x', 0)
    y = data.get('y', 0)
    obj_id = data.get('object_id', 'Keys')
    
    distance_m = distance_mm / 1000.0
    
    # Calculate Phase Shift: Δφ = (d * 4 * π * f) / v
    if distance_m >= 0:
        delta_phi = (distance_m * 4 * math.pi * FREQUENCY) / SPEED_OF_SOUND
    else:
        delta_phi = 0.0

    # Log coordinates for path analysis
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = """INSERT INTO search_logs (object_id, x_coord, y_coord, distance_mm, phase_shift) 
                   VALUES (%s, %s, %s, %s, %s)"""
        cursor.execute(query, (obj_id, x, y, distance_mm, delta_phi))
        conn.commit()
        cursor.close()
        conn.close()
    except mysql.connector.Error as err:
        print(f"DBMS Error: {err}")

    return jsonify({
        'distance_mm': round(distance_mm, 2),
        'phase_shift_radians': round(delta_phi, 4)
    })

@app.route('/analyze_path', methods=['GET'])
def analyze_path():
    """Applies K-Means clustering to search logs and generates a Matplotlib graph."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT x_coord, y_coord FROM search_logs")
        logs = cursor.fetchall()
        conn.close()

        if len(logs) < 15:
            return jsonify({'error': 'Insufficient data points. Move the tracker more to log data.'})

        coords = np.array([[row['x_coord'], row['y_coord']] for row in logs])
        
        # K-Means Clustering for hesitation zones
        kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
        kmeans.fit(coords)
        
        # Generate High-Quality Matplotlib Graph
        plt.figure(figsize=(8, 5))
        plt.scatter(coords[:, 0], coords[:, 1], c=kmeans.labels_, cmap='viridis', alpha=0.5, label='Search Path')
        plt.scatter(kmeans.cluster_centers_[:, 0], kmeans.cluster_centers_[:, 1], 
                    s=200, c='red', marker='X', label='Hesitation Zones (Centroids)')
        plt.title('K-Means Path Analysis of Haptic Navigation')
        plt.xlabel('X Coordinate (pixels)')
        plt.ylabel('Y Coordinate (pixels)')
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # Save graph
        graph_path = 'static/graphs/cluster_plot.png'
        os.makedirs(os.path.dirname(graph_path), exist_ok=True)
        plt.savefig(graph_path, dpi=300, bbox_inches='tight')
        plt.close()

        return jsonify({
            'success': True,
            'graph_url': f'/{graph_path}?t={datetime.now().timestamp()}'
        })

    except Exception as e:
         return jsonify({'error': str(e)})

if __name__ == '__main__':
    initialize_database()
    app.run(debug=True, port=5000)