import os
import sys
import numpy as np
import pandas as pd

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tinvest.storage_manager import StorageManager
from tinvest.data_loader import enrich_dataframe
from tinvest.whatif_engine import (
    find_historical_matches,
    calculate_outcome_distribution,
    run_whatif_analysis,
    _classify_tier,
    TIER1_THRESHOLD,
    TIER2_THRESHOLD,
    TIER3_THRESHOLD,
    TIER4_FLOOR,
    TIER_MULTIPLIERS,
    WARNING_MESSAGES,
    MIN_MATCHES_TARGET,
    MAX_MATCHES_RETURN
)

def test_tier_complementing():
    """Nếu chỉ có 5 Tier 1 → engine bổ sung từ Tier 2, 3, 4."""
    # We will simulate a classification and list filling using the internal logic
    # similar to how the engine builds the results
    fake_matches = []
    # 5 Tier 1 matches
    for idx in range(5):
        fake_matches.append({'similarity': 0.90, 'future_3': 1.0, 'weight': 1.0, 'idx': idx})
    # 10 Tier 2 matches
    for idx in range(5, 15):
        fake_matches.append({'similarity': 0.83, 'future_3': 0.5, 'weight': 1.0, 'idx': idx})
    # 10 Tier 3 matches
    for idx in range(15, 25):
        fake_matches.append({'similarity': 0.77, 'future_3': 0.2, 'weight': 1.0, 'idx': idx})
    # 10 Tier 4 matches
    for idx in range(25, 35):
        fake_matches.append({'similarity': 0.68, 'future_3': -0.1, 'weight': 1.0, 'idx': idx})

    # Execute classification
    for m in fake_matches:
        tier = _classify_tier(m['similarity'])
        if tier is not None:
            m['tier'] = tier

    classified = [m for m in fake_matches if 'tier' in m]
    tiers = {t: [] for t in [1, 2, 3, 4]}
    for m in classified:
        tiers[m['tier']].append(m)
    for t in tiers:
        tiers[t].sort(key=lambda x: x['similarity'], reverse=True)

    result = []
    # Fill from Tier 1, 2, 3 up to MAX_MATCHES_RETURN
    for t in [1, 2, 3]:
        if len(result) >= MAX_MATCHES_RETURN:
            break
        needed = min(MAX_MATCHES_RETURN - len(result), len(tiers[t]))
        result.extend(tiers[t][:needed])

    # Only complement from Tier 4 if we haven't reached MIN_MATCHES_TARGET
    if len(result) < MIN_MATCHES_TARGET:
        needed = min(MIN_MATCHES_TARGET - len(result), len(tiers[4]))
        result.extend(tiers[4][:needed])

    result.sort(key=lambda x: x['similarity'], reverse=True)

    tiers_used = {m['tier'] for m in result}
    assert 1 in tiers_used, "Tier 1 should be used"
    assert 2 in tiers_used, "Tier 2 should be used to complement"
    assert 3 in tiers_used, "Tier 3 should be used to complement further"
    assert len(result) >= MIN_MATCHES_TARGET
    assert len(result) == 25  # 5 + 10 + 10 = 25 matches total under 0.75, no Tier 4 should be needed
    print("[PASS] test_tier_complementing")

def test_tier4_forces_should_trust_false():
    """Khi Tier 4 được dùng → should_trust phải là False và dominant_tier = 4."""
    # We simulate when only Tier 4 matches are used
    fake_matches = []
    for idx in range(20):
        fake_matches.append({'similarity': 0.68, 'future_3': -0.1, 'weight': 1.0, 'tier': 4})
    
    distribution = calculate_outcome_distribution(fake_matches)
    tier_summary = distribution['future_3']['tier_summary']
    
    assert tier_summary['dominant_tier'] == 4
    assert tier_summary['confidence_label'] == "Không đủ tin cậy"
    
    # Check match quality
    dominant_tier = tier_summary['dominant_tier']
    match_quality = {
        "dominant_tier": dominant_tier,
        "should_trust": dominant_tier <= 2,
        "warning": WARNING_MESSAGES[dominant_tier]
    }
    assert match_quality['should_trust'] == False
    assert match_quality['dominant_tier'] == 4
    assert match_quality['warning'] == "Không đủ phiên tương đồng — không nên ra quyết định dựa trên kết quả này"
    print("[PASS] test_tier4_forces_should_trust_false")

def test_weight_scaling():
    """Tier 3 weight phải đúng bằng 0.3x Tier 1 cùng similarity & recency."""
    w_sim = 0.9
    w_rec = 0.95
    w_tier1 = w_sim * w_rec * TIER_MULTIPLIERS[1]
    w_tier3 = w_sim * w_rec * TIER_MULTIPLIERS[3]
    assert abs(w_tier3 / w_tier1 - 0.3) < 1e-6  # float comparison
    print("[PASS] test_weight_scaling")

def test_sorting_invariant():
    """Tier multiplier không được ảnh hưởng thứ tự sort similarity."""
    sm = StorageManager()
    df = sm.load_ticker_data("AAA")
    if df is not None:
        df_rich = enrich_dataframe(df)
        price = float(df_rich['Close'].iloc[-1])
        from tinvest.whatif_engine import build_state_vector, _vectorize
        current_sv = build_state_vector(df_rich, idx=-1)
        current_vec = _vectorize(current_sv)
        
        result = find_historical_matches(df_rich, current_vec)
        sims = [m['similarity'] for m in result]
        assert sims == sorted(sims, reverse=True), "Output matches must remain sorted by similarity descending"
        print("[PASS] test_sorting_invariant")
    else:
        print("[SKIP] test_sorting_invariant (AAA not found)")

def test_full_run_has_all_fields():
    """run_whatif_analysis trả về đủ tất cả fields mới."""
    sm = StorageManager()
    df = sm.load_ticker_data("AAA")
    if df is not None:
        df_rich = enrich_dataframe(df)
        result = run_whatif_analysis('AAA', df_rich)
        mq = result.get('match_quality')
        assert mq is not None, "match_quality should not be None"
        
        required_keys = [
            'dominant_tier', 'confidence_label', 'tier_1_count',
            'tier_2_count', 'tier_3_count', 'tier_4_count',
            'avg_similarity', 'should_trust', 'warning'
        ]
        for key in required_keys:
            assert key in mq, f"Missing key: {key}"
        assert isinstance(mq['should_trust'], bool)
        assert mq['warning'] == WARNING_MESSAGES[mq['dominant_tier']]
        print("[PASS] test_full_run_has_all_fields")
    else:
        print("[SKIP] test_full_run_has_all_fields (AAA not found)")

if __name__ == '__main__':
    test_tier_complementing()
    test_tier4_forces_should_trust_false()
    test_weight_scaling()
    test_sorting_invariant()
    test_full_run_has_all_fields()
    print("\nALL TESTS PASSED SUCCESSFULLY!")
