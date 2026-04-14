"""
AutoResearch — Mutable Training Script
This file is modified by the experiment loop.
Each experiment tries a different approach and reports metrics.

Returns: dict with 'metrics' and 'model_config' keys
"""

import numpy as np
from sklearn.metrics import f1_score
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import VotingClassifier
from sklearn.model_selection import cross_val_score
import xgboost as xgb
from sklearn.ensemble import StackingClassifier
from imblearn.combine import SMOTEENN
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.calibration import CalibratedClassifierCV

from prepare import load_data, split_data, evaluate


def run_experiment():
    """Run one training experiment. Returns metrics dict."""
    X, y = load_data()
    X_train, X_test, y_train, y_test = split_data(X, y)

    # --- EXPERIMENT: Stacked Ensemble with Top Performing Models ---
    
    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Apply SMOTE with moderate oversampling
    smote = SMOTE(sampling_strategy=0.4, random_state=42, k_neighbors=3)
    X_train_balanced, y_train_balanced = smote.fit_resample(X_train_scaled, y_train)
    
    # Define base models (using configurations from best performing experiments)
    base_models = [
        ('rf', RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            class_weight='balanced',
            random_state=42
        )),
        ('et', ExtraTreesClassifier(
            n_estimators=200,
            max_depth=12,
            min_samples_split=5,
            min_samples_leaf=2,
            class_weight='balanced',
            random_state=42
        )),
        ('mlp', MLPClassifier(
            hidden_layer_sizes=(200, 100, 50),
            activation='relu',
            solver='adam',
            alpha=0.0001,
            learning_rate='adaptive',
            learning_rate_init=0.001,
            max_iter=500,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=20,
            random_state=42
        ))
    ]
    
    # Meta-learner (simple and robust)
    meta_learner = LogisticRegression(
        class_weight='balanced',
        random_state=42,
        max_iter=1000
    )
    
    # Create stacking classifier
    stacking_model = StackingClassifier(
        estimators=base_models,
        final_estimator=meta_learner,
        cv=3,  # 3-fold CV for meta-features
        stack_method='predict_proba',  # Use probabilities as meta-features
        n_jobs=-1
    )
    
    # Apply sample weights to emphasize minority class
    sample_weights = np.where(y_train_balanced == 1, 8, 1)
    
    # Fit the stacking model
    stacking_model.fit(X_train_balanced, y_train_balanced, sample_weight=sample_weights)
    
    # Calibrate probabilities for better threshold optimization
    calibrated_model = CalibratedClassifierCV(
        stacking_model,
        method='isotonic',
        cv=3
    )
    calibrated_model.fit(X_train_balanced, y_train_balanced, sample_weight=sample_weights)
    
    # Make predictions
    y_pred = calibrated_model.predict(X_test_scaled)
    y_prob = calibrated_model.predict_proba(X_test_scaled)[:, 1]

    metrics = evaluate(y_test, y_pred, y_prob)

    config = {
        "model_type": "StackingClassifier",
        "base_models": ["RandomForest", "ExtraTrees", "MLPClassifier"],
        "meta_learner": "LogisticRegression",
        "feature_engineering": "StandardScaler",
        "oversampling": "SMOTE_moderate_40_percent",
        "calibration": "isotonic_regression",
        "sample_weighting": "8x_minority_class",
        "stacking_params": {
            "cv": 3,
            "stack_method": "predict_proba"
        },
        "smote_params": {
            "sampling_strategy": 0.4,
            "k_neighbors": 3
        },
        "base_model_configs": {
            "rf": {"n_estimators": 200, "max_depth": 10, "class_weight": "balanced"},
            "et": {"n_estimators": 200, "max_depth": 12, "class_weight": "balanced"},
            "mlp": {"hidden_layers": [200, 100, 50], "early_stopping": True}
        },
        "notes": "Stacked ensemble combining Random Forest, Extra Trees, and Neural Network as base models with Logistic Regression meta-learner, using probability-based stacking, isotonic calibration, and 8x sample weighting for minority class"
    }

    return {"metrics": metrics, "model_config": config}


if __name__ == "__main__":
    result = run_experiment()
    import json
    print(json.dumps(result, indent=2))