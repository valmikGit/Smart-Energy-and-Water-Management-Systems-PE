# Smart Energy Management System - Network Intrusion Detection Pipeline

This directory contains the implementation of a Machine Learning-based Network Intrusion Detection System (NIDS) designed for Smart Energy Management Systems. The pipeline processes network traffic data (PCAP files), extracts features, and applies various Machine Learning models to detect malicious activities.

## Project Overview

The system is designed to classify network traffic into:
*   **Secure (Normal):** Legitimate traffic.
*   **Non-Secure (Attack):** Malicious traffic including Sparta, Scan (A/sU), and MQTT Bruteforce attacks.

The pipeline consists of three main stages:
1.  **Data Processing:** Converting raw PCAP files into structured CSV datasets with Packet, Uniflow, and Biflow features.
2.  **Binary Classification:** Distinguishing between Secure and Non-Secure traffic using Support Vector Machines (SVM).
3.  **Multi-class Classification:** Identifying the specific type of attack using XGBoost.

---

## 1. Data Processing Pipeline

### Feature Extraction
*   **File:** `pcap_to_csv.ipynb`
*   **Description:** This script uses `scapy` to parse raw `.pcap` files and extract three types of feature sets:
    *   **Packet Features:** Raw packet-level details (Source/Dest IP, Ports, Protocol, Length, TTL, TCP Flags).
    *   **Uniflow Features:** Aggregated statistics for unidirectional flows (Packet count, Total bytes, Mean bytes).
    *   **Biflow Features:** Aggregated statistics for bidirectional flows (ignoring direction).
*   **Input:** Raw PCAP files (`normal.pcap`, `sparta.pcap`, etc.).
*   **Output:** CSV files stored in `packet_features/`, `uniflow_features/`, and `biflow_features/`.

---

## 2. Exploratory Data Analysis (EDA)

Several notebooks are dedicated to understanding the data distribution and characteristics:

*   **`class_imbalance_check_eda.ipynb`**: Analyzes the distribution of normal vs. attack traffic to identify class imbalance issues.
*   **`linear_separability_check_eda.ipynb`**: Investigates whether the data is linearly separable, which informs the choice between Linear and Non-linear models.
*   **`task_2_eda.ipynb`**: General exploratory data analysis for Task 2 (likely an intermediate analysis phase).

---

## 3. Binary Classification (Secure vs. Non-Secure)

The goal of this stage is to detect if the network is under attack.

### Core Models
*   **Non-linear SVM (SGD Approximation)**
    *   **File:** `task_3_binary_classification_secure_non_secure.ipynb`
    *   **Details:** Trains a Soft-Margin SVM using Stochastic Gradient Descent (`SGDClassifier` with `loss='hinge'`).
    *   **Training Strategy:** Batch-wise training (streaming chunks of CSVs) to handle large datasets that don't fit in memory.
    *   **Preprocessing:** Standard Scaling (`StandardScaler`) applied per chunk.

*   **Linear SVM**
    *   **File:** `task_3_binary_classification_secure_non_secure_linear_svm.ipynb`
    *   **Details:** Implements a Linear SVM model, suitable if the data proves to be linearly separable.

### Hyperparameter Optimization
To improve model performance, Bayesian Optimization and Grid Search were employed:

*   **Bayesian Optimization (Linear SVM):**
    *   **File:** `linear_svm_bayesian_optimization.ipynb`
    *   **Method:** Uses `scikit-optimize` (`gp_minimize`) to tune hyperparameters like `alpha` (regularization), `eta0` (learning rate), and `l1_ratio`.
    *   **Objective:** Minimize negative F1-score on a validation set.

*   **Bayesian Optimization (Non-linear SVM):**
    *   **Files:**
        *   `non_linear_svm_bayesian_optimization_subsampling.ipynb`
        *   `non_linear_svm_bayesian_optimization_equal_subsampling.ipynb`
    *   **Method:** Similar to the linear version but tunes parameters for the RBF kernel approximation or the SGD classifier mimicking non-linear behavior. Subsampling is used to speed up the expensive optimization process.

*   **Grid Search:**
    *   **Files:** `non_linear_svm_grid_search_cv.ipynb`, `non_linear_svm_gridsearchcv_subsampling.ipynb`
    *   **Method:** Traditional Grid Search Cross-Validation (`GridSearchCV`) to explore a fixed grid of hyperparameters.

---

## 4. Multi-class Classification (Attack Type Detection)

Once an attack is detected, this stage identifies the specific attack type (e.g., Sparta, MQTT Bruteforce).

### Core Model: XGBoost
*   **File:** `task_3_multi_class_attack_classification.ipynb`
*   **Algorithm:** Gradient Boosted Decision Trees (XGBoost).
*   **Target:** Multi-class target variable (`attack_type`).
*   **Training Strategy:** Incremental training (`xgb.train` with `xgb_model` parameter) over batches of data chunks.
*   **Features:** Uses numeric features from Packet, Uniflow, and Biflow datasets.

### Optimization
*   **File:** `multi_class_attack_classification_bayesian_optimization.ipynb`
*   **Details:** Applies Bayesian Optimization to tune XGBoost hyperparameters such as `eta` (learning rate), `max_depth`, and `num_boost_round`.

---

## 5. Utilities & Cleanup

Helper scripts are used to maintain a clean workspace during batch processing:

*   **`clean_up_*.ipynb/py`**: Various scripts (e.g., `clean_up_for_roc.py`, `clean_up_multi_class_bayesian_optimization.ipynb`) designed to remove temporary files (like chunked CSVs or temp models) generated during the training and optimization processes.
*   **`linear_separability_clean_up.py`**: Specific cleanup for the linear separability experiments.

---

## Requirements

*   Python 3.x
*   **Libraries:** `pandas`, `numpy`, `scikit-learn`, `scapy`, `xgboost`, `scikit-optimize` (skopt).
