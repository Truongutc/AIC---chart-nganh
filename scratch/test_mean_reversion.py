import os
import sys
import numpy as np
import pandas as pd

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tinvest.whatif_engine import (
    DEFAULT_WEIGHT_CONFIG,
    _calc_trend_exhaustion,
    _select_diverse_matches,
    _calc_temporal_diversity,
    build_state_vector,
    _vectorize,
    MIN_MATCH_GAP_SESSIONS,
    MIN_MATCHES_TARGET,
    MAX_MATCHES_RETURN
)

def test_trend_exhaustion_bounds():
    # Test trend exhaustion calculation on a dummy series of Close prices
    col_arrays = {
        'Close': np.array([100.0] * 10)
    }
    # With index < 10 (EXHAUSTION_RET_PERIOD = 10), it should return 0.0
    res = _calc_trend_exhaustion(col_arrays, 5)
    assert res == 0.0
    print("[PASS] test_trend_exhaustion_bounds")


def test_trend_exhaustion_extreme_drop():
    # Make a series of 110 bars. First 100 are stable, last 10 drops significantly.
    close = [100.0] * 100 + [50.0] * 10
    col_arrays = {
        'Close': np.array(close)
    }
    # Calculate for index 109
    res = _calc_trend_exhaustion(col_arrays, 109)
    # The return over last 10 bars at 109 is (50 - 100)/100 = -50%
    # The historical returns before index 100 are all 0%.
    # Therefore, the z-score should be extremely negative, clipped to -1.0.
    assert res == -1.0
    print("[PASS] test_trend_exhaustion_extreme_drop")


def test_select_diverse_matches_gap():
    # Create tiers with clustered matches
    tiers = {
        1: [
            {'idx': 100, 'similarity': 0.95, 'tier': 1},
            {'idx': 102, 'similarity': 0.94, 'tier': 1},  # Clustered with 100
            {'idx': 110, 'similarity': 0.93, 'tier': 1},
        ],
        2: [], 3: [], 4: []
    }
    selected = _select_diverse_matches(tiers)
    indices = [m['idx'] for m in selected]
    # idx 102 should be filtered out in Pass 1 if 100 is selected, because gap is 2 < 5
    # Wait, does Pass 2 pull it back in? Let's check: Pass 2 relaxes if total matches < MIN_MATCHES_TARGET.
    # Here len(selected) = 2 (indices 100 and 110), which is < MIN_MATCHES_TARGET (20).
    # So Pass 2 will indeed pull 102 back in!
    # To test pure Pass 1 filtering, let's create enough matches (> 20) so that relaxed fill is not triggered,
    # or check the behavior specifically.
    # Let's create 25 matches that are spread out, and some that are clustered.
    
    tiers_large = {t: [] for t in [1, 2, 3, 4]}
    # Add 22 spread out matches
    for i in range(22):
        tiers_large[1].append({'idx': i * 10, 'similarity': 0.95 - i * 0.01, 'tier': 1})
    # Add a clustered match to index 0 (e.g. index 2)
    tiers_large[1].append({'idx': 2, 'similarity': 0.94, 'tier': 1})
    
    selected_large = _select_diverse_matches(tiers_large)
    selected_indices = [m['idx'] for m in selected_large]
    
    # Since we have > 20 matches from Pass 1 (we have 22), Pass 2 (relaxed fill) won't be needed to reach 20.
    # Pass 1 selected 22 matches. So idx 2 should NOT be in selected_indices because it's clustered with 0.
    assert 2 not in selected_indices
    assert 0 in selected_indices
    print("[PASS] test_select_diverse_matches_gap")


def test_select_diverse_matches_relaxed_fill():
    # If we have very few matches overall, e.g. only 3 matches that are clustered,
    # relaxed fill should still include them so we don't end up with empty matches.
    tiers = {
        1: [
            {'idx': 100, 'similarity': 0.95, 'tier': 1},
            {'idx': 102, 'similarity': 0.94, 'tier': 1},
        ],
        2: [
            {'idx': 104, 'similarity': 0.83, 'tier': 2},
        ],
        3: [], 4: []
    }
    selected = _select_diverse_matches(tiers)
    assert len(selected) == 3
    indices = {m['idx'] for m in selected}
    assert indices == {100, 102, 104}
    print("[PASS] test_select_diverse_matches_relaxed_fill")


def test_select_diverse_matches_tier4():
    # Test that Tier 4 is used to complement if Tier 1/2/3 matches are fewer than MIN_MATCHES_TARGET.
    tiers = {
        1: [{'idx': i * 10, 'similarity': 0.95, 'tier': 1} for i in range(5)],
        2: [{'idx': 100 + i * 10, 'similarity': 0.83, 'tier': 2} for i in range(5)],
        3: [{'idx': 200 + i * 10, 'similarity': 0.77, 'tier': 3} for i in range(5)],
        4: [{'idx': 300 + i * 10, 'similarity': 0.68, 'tier': 4} for i in range(10)]
    }
    # Total Tier 1/2/3 is 15. We need 20 matches.
    # So 5 matches from Tier 4 should be pulled in.
    selected = _select_diverse_matches(tiers)
    assert len(selected) == 20
    t4_count = sum(1 for m in selected if m['tier'] == 4)
    assert t4_count == 5
    print("[PASS] test_select_diverse_matches_tier4")


def test_temporal_diversity_metrics():
    # Test the clustering and diversity score calculation
    matches = [
        {'idx': 100},
        {'idx': 102},  # Cluster 1
        {'idx': 150},
        {'idx': 155},  # Cluster 2
        {'idx': 300},  # Cluster 3
    ]
    res = _calc_temporal_diversity(matches)
    assert res['num_clusters'] == 3
    assert res['span_sessions'] == 200
    assert res['diversity_score'] == 0.60
    assert res['warning'] is None  # clusters = 3, warning is only when clusters < 3
    print("[PASS] test_temporal_diversity_metrics")


def test_default_weights_presence():
    import tinvest.whatif_engine as wfe
    print("IMPORTED FROM:", wfe.__file__)
    print("DEFAULT_WEIGHT_CONFIG KEYS:", list(wfe.DEFAULT_WEIGHT_CONFIG.keys()))
    assert "rsi_diverge" in DEFAULT_WEIGHT_CONFIG
    assert DEFAULT_WEIGHT_CONFIG["rsi_diverge"] == 4.0
    assert "trend_exhaustion" in DEFAULT_WEIGHT_CONFIG
    assert DEFAULT_WEIGHT_CONFIG["trend_exhaustion"] == 4.0
    
    # Test state vector computation includes trend_exhaustion
    # Let's create a minimal DataFrame
    data = {
        'Date': pd.date_range(start='2026-01-01', periods=120),
        'Close': [100.0] * 120,
        'Open': [100.0] * 120,
        'High': [100.0] * 120,
        'Low': [100.0] * 120,
        'Volume': [1000.0] * 120,
        'MA10': [100.0] * 120,
        'MA20': [100.0] * 120,
        'MA50': [100.0] * 120,
        'MA100': [100.0] * 120,
        'MA200': [100.0] * 120,
        'ATR14': [1.0] * 120,
        'RSI': [50.0] * 120,
        'MACD': [0.0] * 120,
        'MACD_Signal': [0.0] * 120,
        'MACD_Hist': [0.0] * 120,
        'MCDX_Banker': [0.0] * 120,
        'MCDX_HotMoney': [0.0] * 120,
    }
    df = pd.DataFrame(data)
    from tinvest.data_loader import enrich_dataframe
    df_rich = enrich_dataframe(df)
    
    sv = build_state_vector(df_rich, idx=-1)
    assert "trend_exhaustion" in sv
    vec = _vectorize(sv)
    # Check that sorting order of keys is correct and we can retrieve keys
    keys = sorted(sv.keys())
    idx = keys.index("trend_exhaustion")
    # Since Close has been flat, trend_exhaustion is 0.0
    assert sv["trend_exhaustion"] == 0.0
    print("[PASS] test_default_weights_presence")


if __name__ == "__main__":
    test_trend_exhaustion_bounds()
    test_trend_exhaustion_extreme_drop()
    test_select_diverse_matches_gap()
    test_select_diverse_matches_relaxed_fill()
    test_select_diverse_matches_tier4()
    test_temporal_diversity_metrics()
    test_default_weights_presence()
    print("All tests passed successfully!")
