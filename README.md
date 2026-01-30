# Dynamic Server Load Balancing and Energy-Efficient Server Management in SDN

A comprehensive Software-Defined Networking (SDN) solution implementing dynamic server load balancing, predictive scaling, proactive path load balancing and energy-efficient server management using machine learning.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-blue.svg)](https://www.typescriptlang.org/)
[![Next.js](https://img.shields.io/badge/Next.js-14.0+-black.svg)](https://nextjs.org/)
[![ONOS](https://img.shields.io/badge/ONOS-SDN-green.svg)](https://opennetworking.org/onos/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Technologies Used](#technologies-used)
- [Project Structure](#project-structure)
- [Installation & Setup](#installation--setup)
- [Usage](#usage)
- [Load Balancing Algorithms](#load-balancing-algorithms)
- [Machine Learning Models](#machine-learning-models)
- [Monitoring & Visualization](#monitoring--visualization)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## 🎯 Overview

This Final Year Project (FYP) implements a sophisticated SDN-based infrastructure management system that combines:

- **Dynamic Server Load Balancing**: Intelligent distribution of traffic using the DWRS (Dynamic Weighted Round Robin Selection) algorithm
- **Predictive Scaling**: ML-powered web traffic forecasting using LSTM neural networks
- **Energy Efficiency**: Proactive and reactive server power management based on real-time metrics and predictions
- **Network Path Optimization**: TCN (Temporal Convolutional Network) models for predicting network link bandwidth usage
- **Self-Healing Infrastructure**: Automated failure detection, health checks, and server replacement
- **Real-time Monitoring**: Comprehensive dashboard with live telemetry, alerts, and analytics

The system operates across two coordinated servers:
- **Server 1**: Handles dynamic load balancing using NAT and iptables
- **Server 2**: Manages server scaling, ML predictions, network path optimization, and UI dashboard

## ✨ Key Features

### 1. **Intelligent Load Balancing**
- **DWRS Algorithm**: Dynamically calculates server weights based on CPU (55%) and Memory (45%) utilization
- **Weighted Selection**: Probabilistic server selection favoring less-loaded servers
- **Connection Draining**: Graceful 30-second connection draining before server shutdown
- **Health Monitoring**: Synthetic HTTP health checks with automatic failover

### 2. **Predictive Scaling**
- **LSTM-based Forecasting**: Hourly web traffic prediction using Bidirectional LSTM neural networks
- **Proactive Scale-Up/Down**: Automatic server provisioning based on predicted traffic patterns
- **Tiered Scaling**: 3-tier server capacity model (1 core/1GB, 2 cores/2GB, 4 cores/4GB)
- **Historical Analysis**: 5-minute high-load and 30-minute low-load reactive triggers

### 3. **Energy-Efficient Management**
- **Dynamic Power Control**: Automated server power on/off via Ansible playbooks
- **Capacity Optimization**: Matches active server capacity to predicted demand
- **Resource Thresholds**: High CPU (90%), High Memory (90%), Low CPU (3%), Low Memory (20%)
- **Stabilization Periods**: 80-second stabilization after scale-up, 30-second draining for scale-down

### 4. **Network Path Optimization**
- **TCN Models**: Temporal Convolutional Networks predict bandwidth usage per network path
- **Multi-Path Routing**: Intelligent path selection in spine-leaf topology
- **ONOS Integration**: Custom Java application for SDN flow rule management
- **Smooth Weighted Round Robin**: Deterministic path selection based on predicted congestion

### 5. **Self-Healing Infrastructure**
- **Health Checks**: Periodic synthetic HTTP requests to verify server functionality
- **Automatic Reboot**: VM hard reset for recoverable failures
- **Server Blacklisting**: Persistent tracking of failed servers to prevent reselection
- **Replacement Logic**: Capacity-aware replacement server selection

### 6. **Comprehensive Monitoring**
- **Real-time Dashboard**: Next.js web UI with live server metrics, network topology, and alerts
- **Prometheus Integration**: Centralized telemetry collection (Node Exporter, Apache Exporter)
- **Alert System**: 20+ alert types covering scaling, health, ML, and network events
- **Historical Tracking**: Database storage of hourly traffic and bandwidth measurements

## 🏗 System Architecture

![image_alt](https://github.com/HuaZheng03/FYP/blob/4c3f50ac82adff3765e2bbaa928d2b4e45b8cc87/System%20Architecture%20Diagram.png)

## 🛠 Technologies Used

### Backend
- **Python 3.8+**: Core orchestration and ML logic
- **TensorFlow/Keras**: LSTM and TCN neural network models
- **Flask**: REST API for path load balancing
- **Ansible**: Infrastructure automation and file synchronization
- **Prometheus**: Metrics collection and time-series database
- **SQLite**: Historical traffic and bandwidth storage

### SDN & Networking
- **ONOS (Open Network Operating System)**: SDN controller
- **Java 11**: ONOS application development
- **iptables**: NAT and packet forwarding (Server 1)
- **OpenFlow**: Flow rule management protocol

### Frontend
- **Next.js 14**: React-based web framework
- **TypeScript**: Type-safe frontend development
- **Tailwind CSS**: Utility-first styling
- **Recharts**: Data visualization library
- **shadcn/ui**: Component library

### Monitoring & Telemetry
- **Prometheus Node Exporter**: System metrics (CPU, memory, disk, network)
- **Apache Exporter**: HTTP request counting
- **Prometheus Python Client**: Custom metric exposition

### Machine Learning
- **scikit-learn**: Data preprocessing (MinMaxScaler)
- **NumPy/Pandas**: Data manipulation
- **LSTM (Bidirectional)**: Web traffic time-series forecasting
- **TCN (Temporal Convolutional Networks)**: Bandwidth usage prediction

## 📁 Project Structure

```
FYP/
├── DSLB_EESM-server1/                 # Server 1: Load Balancer
│   ├── data_reception/
│   │   └── server_telemetry.py        # Prometheus metric collection
│   ├── dynamic_load_balancing/
│   │   ├── DWRS.py                    # DWRS algorithm implementation
│   │   ├── nat_controller.py          # iptables NAT management
│   │   └── active_servers_status.json # Synced from Server 2
│   └── run.py                         # Main load balancing loop
│
├── DSLB_EESM-server2/                 # Server 2: Control Plane
│   ├── alerts/
│   │   ├── __init__.py
│   │   └── alerts_manager.py          # Alert system (20+ alert types)
│   ├── data_reception/
│   │   ├── server_telemetry.py        # Server metrics collection
│   │   └── network_telemetry.py       # ONOS network stats
│   ├── database/
│   │   ├── traffic_database_manager.py       # Hourly traffic storage
│   │   └── path_bandwidth_database_manager.py # Bandwidth storage
│   ├── dynamic_load_balancing/
│   │   └── link_load_balancing.py     # Network path management
│   ├── onos-apps/
│   │   └── pathloadbalancer/          # ONOS Java application
│   │       └── src/main/java/org/onosproject/pathloadbalancer/
│   │           └── PathLoadBalancerApp.java
│   ├── predict_network_link_bandwidth_usage/
│   │   ├── TCN.py                     # TCN model prediction
│   │   └── models/                    # Trained TCN models (.keras)
│   ├── server_power_status_management/
│   │   ├── server_power_status_management.py
│   │   └── *.yaml                     # Ansible playbooks (power on/off/restart)
│   ├── ui/
│   │   └── my-app/                    # Next.js dashboard
│   │       ├── app/                   # Routes and API endpoints
│   │       ├── components/            # React components
│   │       │   ├── server-overview.tsx
│   │       │   ├── network-topology.tsx
│   │       │   ├── ml-predictions.tsx
│   │       │   └── alerts-panel.tsx
│   │       └── lib/                   # Utilities
│   ├── web_traffic_time_series_forecasting/
│   │   ├── forecast_web_traffic.py    # LSTM model and training
│   │   ├── number_of_http_requests_per_hour.py # Traffic counting
│   │   ├── daily_predictions.py       # Prediction tracking
│   │   └── models/                    # Trained LSTM models
│   ├── run.py                         # Main orchestrator
│   ├── run_pathloadbalancing.py       # Network path optimization
│   ├── forecast_cache.json            # Hourly forecast cache
│   └── local_active_servers_status.json # Server status
│
└── README.md
```

## 🚀 Installation & Setup

### Prerequisites

- **Server 1**:
  - Ubuntu 20.04+ (requires root/sudo access)
  - Python 3.8+
  - Prometheus with Node Exporter on backend servers
  - SSH access to Server 2

- **Server 2**:
  - Ubuntu 20.04+
  - Python 3.8+
  - Node.js 18+ and npm
  - Docker (for ONOS controller)
  - Ansible
  - SSH access to Server 1 and backend servers

### Step 1: Clone the Repository

```bash
git clone https://github.com/HuaZheng03/FYP.git
cd FYP
```

### Step 2: Server 1 Setup (Load Balancer)

```bash
cd DSLB_EESM-server1

# Install Python dependencies
pip install -r requirements.txt  # (if requirements.txt exists)
pip install prometheus-client requests

# Configure iptables access
# Edit dynamic_load_balancing/nat_controller.py
# Update PUBLIC_IP and PUBLIC_INTERFACE

# Update Prometheus endpoints
# Edit data_reception/server_telemetry.py
# Update PROMETHEUS_URL and server IPs

# Run the load balancer (requires sudo)
sudo python3 run.py
```

### Step 3: Server 2 Setup (Control Plane)

#### 3.1 Python Environment

```bash
cd DSLB_EESM-server2

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install tensorflow keras scikit-learn pandas numpy flask prometheus-client requests ansible

# Configure server IPs and settings
# Edit run.py and update:
# - SERVER_IP_MAP (backend server IPs)
# - SERVER1_IP and SERVER1_USER (Server 1 SSH credentials)
# - Threshold values (optional)
```

#### 3.2 ONOS Controller Setup

```bash
# Pull and run ONOS Docker container
docker pull onosproject/onos:2.7-latest
docker run -d --name onos -p 8181:8181 -p 8101:8101 -p 6653:6653 onosproject/onos:2.7-latest

# Build and install PathLoadBalancer app
cd onos-apps/pathloadbalancer
mvn clean install
onos-app localhost install target/pathloadbalancer-1.0-SNAPSHOT.oar

# Configure link bandwidth (if needed)
# Edit onos_link_bandwidth_config/link_bandwidth_config.json
```

#### 3.3 Web Dashboard Setup

```bash
cd ui/my-app

# Install dependencies
npm install

# Development mode
npm run dev

# Production build
npm run build
npm start
```

### Step 4: Ansible Configuration

```bash
cd DSLB_EESM-server2/server_power_status_management

# Configure inventory
# Edit inventory.ini with your KVM host (hypervisor) SSH credentials

# The playbook.yaml file handles power on/off operations
# Edit playbook.yaml if needed to:
# - Update VM names (ubuntu-guest, apache-vm-1, apache-vm-2)
# - Modify libvirt URI if not using qemu:///system

# Test connectivity to KVM host
ansible kvm_host -i inventory.ini -m ping

# Manual test (optional)
ansible-playbook -i inventory.ini playbook.yaml -e "target_server=ubuntu-guest power_state=on"
```

## 📖 Usage

### Starting the System

**Server 2** (start first):
```bash
# Terminal 1: Main orchestrator
cd DSLB_EESM-server2
python3 run.py

# Terminal 2: Path load balancing
python3 run_pathloadbalancing.py

# Terminal 3: Web dashboard
cd ui/my-app
npm start
```

**Server 1**:
```bash
# Requires sudo for iptables management
cd DSLB_EESM-server1
sudo python3 run.py
```

### Accessing the Dashboard

Open browser and navigate to:
```
http://<server2-ip>:3000
```

Dashboard sections:
- **Overview**: System status, active servers, current traffic
- **Servers**: Detailed server metrics and health status
- **Network**: Spine-leaf topology and path utilization
- **Predictions**: ML forecast visualizations (traffic and bandwidth)

### Monitoring System Logs

**Server 1** (Load Balancer):
```
--- Running New Check at 2026-01-30 14:23:45 ---
[MONITOR] Fetching server telemetry...
[DECIDE] Running DWRS algorithm to select target server...
✅ DWRS algorithm selected server: 192.168.6.2
[ACT] Target server is unchanged (192.168.6.2).
```

**Server 2** (Orchestrator):
```
--- Running New Check @ 2026-01-30 14:23:45 ---
[1][MONITOR] Fetching current server status via Telemetry...
Hourly Web Traffic Forecast: 125000 (valid until 15:00)
[3][CHECK-SCALE] Evaluating system load for reactive scaling...
[4][ACT-SCALE] OK: System load is within sustained thresholds.
```

## ⚙️ Load Balancing Algorithms

### DWRS (Dynamic Weighted Round Robin Selection)

The DWRS algorithm dynamically calculates server weights based on real-time resource utilization:

**1. Comprehensive Load Calculation**:
```
Comprehensive_Load = (CPU_Usage × 0.55) + (Memory_Usage × 0.45)
```

**2. Weight Conversion** (inverse relationship):
```python
if load >= 100:
    weight = 1
else:
    weight = 100 - floor(load)
```

Example:
- Server A: CPU 30%, Memory 40% → Load = 34.5% → Weight = 65
- Server B: CPU 70%, Memory 80% → Load = 74.5% → Weight = 25

**3. Probabilistic Selection**:
- Generate random number: `random_pick = random(1, total_weight)`
- Iterate through servers, accumulating weights
- Select server when `cumulative_weight >= random_pick`

Result: Server A has 65/(65+25) = 72.2% selection probability

### Path Load Balancing (Smooth WRR)

For network path selection in the spine-leaf topology:

**1. Weight Calculation** (inverse of congestion):
```python
path_weight = 1.0 / (predicted_bandwidth_usage + epsilon)
```

**2. Ratio Normalization**:
```python
path_ratio = path_weight / sum_of_all_path_weights
```

**3. Smooth Weighted Round Robin**:
- Maintains current weight per path
- On each request: `current_weight[i] += ratio[i]`
- Select path with max `current_weight`
- Decrease selected path: `current_weight[selected] -= 1.0`

## 🤖 Machine Learning Models

### LSTM (Web Traffic Forecasting)

**Architecture**:
```python
Model: Sequential
├─ Bidirectional LSTM (64 units, return_sequences=True)
├─ Dropout (0.2)
├─ Bidirectional LSTM (32 units)
├─ Dropout (0.2)
├─ Dense (32, activation='relu')
└─ Dense (1, activation='linear')
```

**Training Configuration**:
- **Input**: 24-hour historical traffic data (hourly granularity)
- **Output**: Next hour's traffic prediction
- **Loss Function**: Mean Squared Error (MSE)
- **Optimizer**: Adam (learning_rate=0.001)
- **Callbacks**: EarlyStopping, ReduceLROnPlateau, ModelCheckpoint

**Features**:
- Automatic retraining when prediction error exceeds threshold
- Forecast caching (1-hour validity)
- Historical traffic database integration

### TCN (Network Bandwidth Prediction)

**Architecture**:
- Temporal Convolutional Network with dilated convolutions
- Separate model per network path (e.g., leaf6→leaf1 via spine0)
- Input: Historical bandwidth measurements
- Output: Predicted bandwidth usage

**Features**:
- Per-path model training
- Real-time prediction updates
- Integration with ONOS telemetry

## 📊 Monitoring & Visualization

### Metrics Collected

**Server Metrics** (via Prometheus):
- CPU usage percentage
- Memory usage percentage
- Total CPU cores
- Total memory (GB)
- HTTP requests per second (Apache Exporter)

**Network Metrics** (via ONOS):
- Port statistics (bytes sent/received)
- Link utilization
- Path bandwidth usage

### Alert Categories

1. **Server Power State Changes**:
   - Proactive/Reactive Scale-Up
   - Proactive/Reactive Scale-Down
   - Graceful Shutdown

2. **Health & Failover**:
   - Health Check Failed
   - Failover Initiated/Complete
   - Server Blacklisted/Recovered

3. **Resource Thresholds**:
   - High CPU/Memory
   - Low Utilization

4. **ML & Predictions**:
   - Forecast Failed
   - Model Retraining Started/Complete

5. **System Status**:
   - Prometheus Connection Failed
   - ONOS Connection Failed
   - Status Sync Success/Failed

## 🔧 Configuration

### Server Scaling Thresholds (run.py)

```python
# Reactive Scaling
HIGH_CPU_THRESHOLD = 90.0         # Scale up trigger
HIGH_MEM_THRESHOLD = 90.0
LOW_CPU_THRESHOLD = 3.0           # Scale down trigger
LOW_MEM_THRESHOLD = 20.0
HIGH_LOAD_DURATION_SECONDS = 5 * 60    # 5 minutes
LOW_LOAD_DURATION_SECONDS = 30 * 60   # 30 minutes

# Proactive Scaling
SERVER_TIERS = {
    1: range(0, 140000),          # Tier 1: ubuntu-guest (1C/1GB)
    2: range(140001, 420000),     # Tier 2: apache-vm-1 (2C/2GB)
    3: range(420001, 1000000)     # Tier 3: apache-vm-2 (4C/4GB)
}
```

### Load Balancing Weights (DWRS.py)

```python
ALPHA = 0.55  # CPU weight
BETA = 0.45   # Memory weight
```

### Path Load Balancing Mode (run_pathloadbalancing.py)

```python
LOAD_BALANCING_MODE = "prediction"  # Options: "prediction", "realtime", "hybrid"
COLLECTION_INTERVAL = 60            # seconds
```

## 📚 API Documentation

### Server 2 Path Load Balancing API

**Base URL**: `http://<server2-ip>:5000`

#### Endpoints

**GET /health**
- Check API health status
- Response: `{"status": "healthy"}`

**GET /current_weights**
- View current path weights
- Response:
```json
{
  "leaf6->leaf1": {
    "0": 0.45,
    "1": 0.55
  },
  ...
}
```

**GET /stats**
- Collection statistics
- Response:
```json
{
  "collection_count": 123,
  "last_collection_time": "2026-01-30T14:23:45Z",
  "mode": "prediction"
}
```

**POST /force_sync**
- Manually trigger ONOS sync
- Response: `{"status": "synced", "timestamp": "..."}`

### Web Dashboard API (Next.js)

**Base URL**: `http://<server2-ip>:3000/api`

**GET /api/servers**
- Fetch server telemetry

**GET /api/servers/weights**
- Calculate DWRS weights

**GET /api/network**
- Network topology data

**GET /api/predictions**
- ML forecast data

**GET /api/alerts**
- Active system alerts

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **ONOS Project**: Open Network Operating System
- **TensorFlow/Keras**: Machine learning frameworks
- **Prometheus**: Monitoring and alerting toolkit
- **Next.js**: React framework for web development
- **shadcn/ui**: Beautiful UI components

---

**Project Author**: Ling Hua Zheng  
**Institution**: Universiti Malaya  
**Academic Year**: 2025/2026  
**GitHub**: [@HuaZheng03](https://github.com/HuaZheng03)

For questions or support, please open an issue on the [GitHub repository](https://github.com/HuaZheng03/FYP/issues).
