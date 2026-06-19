#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# Configure matplotlib backend safely
import matplotlib
try:
    matplotlib.use('Agg')
except Exception as e:
    logger.warning(f"Could not set Agg backend: {e}")

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import matplotlib.ticker as ticker_lib

def export_greenpink_chart(ticker, df_full, df_vn, save_path):
    """
    Generate and save the GreenPink & Octopus chart for a ticker (e.g. VNINDEX).
    """
    try:
        plt.style.use('dark_background')
        df_full = df_full.copy()
        
        # --- CALCULATE RS14 & RS52 ---
        if 'RS14' not in df_full.columns or 'RS52' not in df_full.columns:
            if df_vn is not None and not df_vn.empty:
                df_vn_indexed = df_vn.set_index('Date')
                bench_close = df_full['Date'].map(df_vn_indexed['Close']).ffill().bfill()
                rs_raw = df_full['Close'] / (bench_close + 1e-10)
                
                # RS52: 52 weeks = 260 bars
                rs52_min = rs_raw.rolling(window=260, min_periods=1).min()
                rs52_max = rs_raw.rolling(window=260, min_periods=1).max()
                df_full['RS52'] = 100 * (rs_raw - rs52_min) / (rs52_max - rs52_min + 0.0001)
                
                # RS14: 14 weeks = 70 bars
                rs14_min = rs_raw.rolling(window=70, min_periods=1).min()
                rs14_max = rs_raw.rolling(window=70, min_periods=1).max()
                df_full['RS14'] = 100 * (rs_raw - rs14_min) / (rs14_max - rs14_min + 0.0001)
            else:
                df_full['RS14'] = 50.0
                df_full['RS52'] = 50.0

        # 1. Prepare Data (Last 150 bars)
        count = 150
        df = df_full.tail(count).copy().reset_index(drop=True)
        x_idx = np.arange(len(df))
        
        # 2. Setup Figure with 3 subplots
        fig, (ax, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1]})
        fig.patch.set_facecolor('black') 
        ax.set_facecolor('black')
        ax2.set_facecolor('black')
        ax3.set_facecolor('black')
        
        # --- TOP SUBPLOT: GREENPINK ---
        # 3. Plot Cloud (E14 vs E21)
        e14 = df['GP_E14']
        e21 = df['GP_E21']
        c = df['Close']
        green_mask = (c > e14) & (c > e21)
        pink_mask = ~green_mask
        ax.fill_between(x_idx, e14, e21, where=green_mask, color='#00FF00', alpha=0.3, interpolate=True, linewidth=0)
        ax.fill_between(x_idx, e14, e21, where=pink_mask, color='#FF69B4', alpha=0.3, interpolate=True, linewidth=0)

        # 4. Plot xFast and xSlow
        ax.plot(x_idx, df['GP_xFast'], color='lime', linewidth=2.5, label='xFast (Green)')
        ax.plot(x_idx, df['GP_xSlow'], color='red', linewidth=2.5, label='xSlow (Red)')

        # 5. Plot Bollinger Bands on xSlow
        ax.plot(x_idx, df['GP_BB_Top'], color='blue', linewidth=1.2, alpha=0.8, label='BB Top (xSlow)')
        ax.plot(x_idx, df['GP_BB_Bot'], color='blue', linewidth=1.2, alpha=0.8, label='BB Bot (xSlow)')
        ax.fill_between(x_idx, df['GP_BB_Bot'], df['GP_BB_Top'], color='blue', alpha=0.1)

        # 6. Plot Candlesticks
        close_val = df['Close']
        open_val = df['Open']
        high_val = df['High']
        low_val = df['Low']
        up_mask = close_val >= open_val
        down_mask = ~up_mask
        if up_mask.any():
            ax.vlines(x_idx[up_mask], low_val[up_mask], high_val[up_mask], color='#00FF00', linewidth=1.0)
            ax.bar(x_idx[up_mask], close_val[up_mask] - open_val[up_mask], bottom=open_val[up_mask], color='#00FF00', width=0.6)
        if down_mask.any():
            ax.vlines(x_idx[down_mask], low_val[down_mask], high_val[down_mask], color='#FF0000', linewidth=1.0)
            ax.bar(x_idx[down_mask], open_val[down_mask] - close_val[down_mask], bottom=close_val[down_mask], color='#FF0000', width=0.6)

        # --- BOTTOM SUBPLOT: OCTOPUS (MACD MCGINLEY) ---
        ax2.plot(x_idx, df['OCT_A1'], color='white', linewidth=0.8, alpha=0.3)
        
        # Plot A1 and B1 (Mirror) with dynamic color dots/line
        oct_colors = df['OCT_Color'].iloc[1:].tolist()
        
        a1_np = df['OCT_A1'].to_numpy()
        points_a1 = np.array([x_idx, a1_np]).T.reshape(-1, 1, 2)
        segments_a1 = np.concatenate([points_a1[:-1], points_a1[1:]], axis=1)
        lc_a1 = LineCollection(segments_a1, colors=oct_colors, linewidths=2.5)
        ax2.add_collection(lc_a1)
        
        b1_np = df['OCT_B1'].to_numpy()
        points_b1 = np.array([x_idx, b1_np]).T.reshape(-1, 1, 2)
        segments_b1 = np.concatenate([points_b1[:-1], points_b1[1:]], axis=1)
        lc_b1 = LineCollection(segments_b1, colors=oct_colors, linewidths=2.5)
        ax2.add_collection(lc_b1)

        # Plot Bollinger Bands Cloud on A1
        ax2.plot(x_idx, df['OCT_BB_Top'], color='#00008B', linewidth=1.0, linestyle='--', alpha=0.6)
        ax2.plot(x_idx, df['OCT_BB_Bot'], color='#00008B', linewidth=1.0, linestyle='--', alpha=0.6)
        ax2.fill_between(x_idx, df['OCT_BB_Bot'], df['OCT_BB_Top'], color='#ADD8E6', alpha=0.2, label='Octopus Band')
        ax2.axhline(0, color='white', linewidth=0.5, alpha=0.5)

        # --- THIRD SUBPLOT: RS CHART ---
        ax3.plot(x_idx, df['RS14'], color='white', linewidth=2.0, label='RS14')
        ax3.plot(x_idx, df['RS52'], color='yellow', linewidth=2.0, label='RS52')
        ax3.axhline(50, color='red', linewidth=0.8, linestyle='--', alpha=0.5)

        # 7. Formatting
        ax.set_title(f"GP & OCTOPUS CHART (HHV-LLV + McGinley): {ticker}", color='gold', fontsize=15, fontweight='bold', pad=12)
        ax.set_ylabel("Price", color='white', fontweight='bold')
        ax2.set_ylabel("Octopus MACD", color='white', fontweight='bold')
        ax3.set_ylabel("RS Rating", color='white', fontweight='bold')
        
        for axis in [ax, ax2, ax3]:
            axis.grid(True, color='#222222', linestyle=':', alpha=0.5)
            axis.tick_params(colors='white')
            for spine in axis.spines.values():
                spine.set_color('#444444')
        
        # Format X-axis dates
        df['Date'] = pd.to_datetime(df['Date'])
        date_labels = df['Date'].dt.strftime('%d/%m/%y').tolist()
        ax3.xaxis.set_major_formatter(ticker_lib.FuncFormatter(lambda x, pos: date_labels[int(round(x))] if 0 <= int(round(x)) < len(date_labels) else ""))
        
        ax.legend(loc='lower left', facecolor='black', edgecolor='#00FF00', labelcolor='white', fontsize=8)
        ax2.legend(loc='lower left', facecolor='black', edgecolor='#FF69B4', labelcolor='white', fontsize=8)
        ax3.legend(loc='lower left', facecolor='black', edgecolor='yellow', labelcolor='white', fontsize=8)
        
        plt.tight_layout()
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, facecolor='black', edgecolor='none', dpi=120)
        plt.close(fig)
        logger.info(f"✅ Exported GreenPink chart to {save_path}")
    except Exception as e:
        logger.error(f"Error exporting GreenPink chart for {ticker}: {e}")
        import traceback
        traceback.print_exc()

def export_heikin_chart(ticker, df_full, save_path):
    """
    Generate and save the Heikin-Ashi & 2Trend chart for a ticker (e.g. VNINDEX).
    """
    try:
        plt.style.use('dark_background')
        df = df_full.tail(150).copy().reset_index(drop=True)
        x_idx = np.arange(len(df))
        
        # Setup Figure with 2 subplots
        fig, (ax, ax2) = plt.subplots(2, 1, figsize=(15, 11), sharex=True, gridspec_kw={'height_ratios': [1, 1]})
        fig.patch.set_facecolor('black') 
        ax.set_facecolor('black')
        ax2.set_facecolor('black')
        
        # --- TOP SUBPLOT: HEIKIN & TREND COLOR ---
        # Plot Hull MA Cloud
        mh = df['HK_MHull']
        sh = df['HK_SHull']
        ax.fill_between(x_idx, mh, sh, where=(mh > sh), color='lime', alpha=0.1)
        ax.fill_between(x_idx, mh, sh, where=(mh <= sh), color='red', alpha=0.1)

        # Trend Color Line (EMA 13)
        tc_trend = df['TC_Trend']
        tc_t_color = df['TC_TrendColor'].fillna('#434651')
        tc_trend_np = tc_trend.to_numpy()
        points_tc = np.array([x_idx, tc_trend_np]).T.reshape(-1, 1, 2)
        segments_tc = np.concatenate([points_tc[:-1], points_tc[1:]], axis=1)
        tc_colors = tc_t_color.iloc[1:].tolist()
        lc_tc = LineCollection(segments_tc, colors=tc_colors, linewidths=2.5, alpha=0.9)
        ax.add_collection(lc_tc)
        
        # Stop Line (ATR Stop)
        tc_stop = df['TC_StopLine']
        tc_s_color = df['TC_StopColor'].fillna('#434651')
        ax.scatter(x_idx, tc_stop, c=tc_s_color, s=10, marker='_')

        # Plot NW Trailing Stop
        nw = df['HK_NW']
        trend = df['HK_Trend']
        nw_np = nw.to_numpy()
        points_nw = np.array([x_idx, nw_np]).T.reshape(-1, 1, 2)
        segments_nw = np.concatenate([points_nw[:-1], points_nw[1:]], axis=1)
        nw_colors = ['#00FF00' if trend.iloc[i] == 1 else '#FF0000' for i in range(1, len(df))]
        lc_nw = LineCollection(segments_nw, colors=nw_colors, linewidths=2)
        ax.add_collection(lc_nw)

        # Plot Smoothed Heikin Ashi Candles
        ho, hh, hl, hc = df['HK_Flower_Open'], df['HK_Flower_High'], df['HK_Flower_Low'], df['HK_Flower_Close']
        bar_colors = df['HK_BarColor']
        color_map = {'brightGreen': '#00FF00', 'red': '#FF0000', 'white': '#FFFFFF'}
        for color_name, color_hex in color_map.items():
            mask = bar_colors == color_name
            if mask.any():
                ax.vlines(x_idx[mask], hl[mask], hh[mask], color=color_hex, linewidth=1)
                ax.bar(x_idx[mask], abs(hc[mask] - ho[mask]) + 0.001, bottom=np.minimum(ho[mask], hc[mask]), color=color_hex, width=0.6, alpha=0.8)

        # Plot Signal Shapes
        buys = df[df['HK_BuySignal'] | df['HK_BuyManh']]
        sells = df[df['HK_SellSignal'] | df['HK_SellManh']]
        if not buys.empty:
            ax.plot(buys.index, buys['HK_Flower_Low'] * 0.985, '^', markersize=10, color='lime', markeredgecolor='white')
        if not sells.empty:
            ax.plot(sells.index, sells['HK_Flower_High'] * 1.015, 'v', markersize=10, color='red', markeredgecolor='white')

        # --- BOTTOM SUBPLOT: NORMAL CANDLES & 2TREND ---
        # Plot Normal Candlesticks
        o, h, l, c_val = df['Open'], df['High'], df['Low'], df['Close']
        up_mask = c_val >= o
        down_mask = ~up_mask
        if up_mask.any():
            ax2.vlines(x_idx[up_mask], l[up_mask], h[up_mask], color='#00FF00', linewidth=1)
            ax2.bar(x_idx[up_mask], abs(c_val[up_mask] - o[up_mask]) + 0.001, bottom=np.minimum(o[up_mask], c_val[up_mask]), color='#00FF00', width=0.6)
        if down_mask.any():
            ax2.vlines(x_idx[down_mask], l[down_mask], h[down_mask], color='#FF0000', linewidth=1)
            ax2.bar(x_idx[down_mask], abs(c_val[down_mask] - o[down_mask]) + 0.001, bottom=np.minimum(o[down_mask], c_val[down_mask]), color='#FF0000', width=0.6)

        # Plot 2Trend SMA
        t2_sma = df['T2_SMA']
        t2_trend = df['T2_SMA_Trend']
        t2_sma_np = t2_sma.to_numpy()
        points_t2 = np.array([x_idx, t2_sma_np]).T.reshape(-1, 1, 2)
        segments_t2 = np.concatenate([points_t2[:-1], points_t2[1:]], axis=1)
        t2_colors = ['#00ffaa' if t2_trend.iloc[i] == 1 else '#ff0000' for i in range(1, len(df))]
        lc_t2 = LineCollection(segments_t2, colors=t2_colors, linewidths=3)
        ax2.add_collection(lc_t2)

        # Plot 2Trend Supertrend Bands
        st_upper = df['T2_ST_Upper']
        st_lower = df['T2_ST_Lower']
        st_trend = df['T2_ST_Trend']
        mid = (o + c_val) / 2
        ax2.fill_between(x_idx, mid, st_lower, where=(st_trend == 1), color='#00ffaa', alpha=0.2)
        ax2.fill_between(x_idx, mid, st_upper, where=(st_trend == -1), color='#ff0000', alpha=0.2)
        
        # Signals for 2Trend
        t2_sma_shift = df['T2_SMA_Trend'].shift(1).fillna(0)
        buys2 = df[(df['T2_SMA_Trend'] == 1) & (t2_sma_shift <= 0)]
        sells2 = df[(df['T2_SMA_Trend'] == -1) & (t2_sma_shift >= 0)]
        
        if not buys2.empty:
            for idx in buys2.index:
                ax2.text(idx, df['Low'].iloc[idx]*0.97, "𝑳", color='#00ffaa', fontsize=12, fontweight='bold', ha='center')
        if not sells2.empty:
            for idx in sells2.index:
                ax2.text(idx, df['High'].iloc[idx]*1.03, "𝑺", color='#ff0000', fontsize=12, fontweight='bold', ha='center')

        # Formatting
        df['Date'] = pd.to_datetime(df['Date'])
        last_date = df['Date'].iloc[-1].strftime('%d/%m/%Y') if 'Date' in df.columns else "N/A"
        ax.set_title(f"Chart trend color - {ticker} - {last_date}", color='gold', fontsize=16, fontweight='bold', pad=15)
        ax2.set_title(f"Normal Candles & 2Trend Logic", color='gold', fontsize=14, fontweight='bold')
        
        for a in [ax, ax2]:
            a.set_ylabel("Price", color='white', fontweight='bold')
            a.grid(True, color='#222222', linestyle=':', alpha=0.5)
            a.tick_params(colors='white')
            for spine in a.spines.values():
                spine.set_color('#444444')
        
        date_labels = df['Date'].dt.strftime('%d/%m/%y').tolist()
        ax2.xaxis.set_major_formatter(ticker_lib.FuncFormatter(lambda x, pos: date_labels[int(round(x))] if 0 <= int(round(x)) < len(date_labels) else ""))
        
        plt.tight_layout()
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, facecolor='black', edgecolor='none', dpi=120)
        plt.close(fig)
        logger.info(f"✅ Exported Heikin chart to {save_path}")
    except Exception as e:
        logger.error(f"Error exporting Heikin chart for {ticker}: {e}")
        import traceback
        traceback.print_exc()

def export_heatmap_chart(ticker, df_full, save_path):
    """
    Generate and save the Heatmap & Price chart for a ticker.
    """
    try:
        plt.style.use('dark_background')
        import matplotlib.gridspec as gridspec
        from tinvest.data_loader import enrich_dataframe

        # --- PREPARE DATA (Last 250 bars ~ 1 year) ---
        count = 250
        required_cols = [
            'HM_PFE', 'HM_STC', 'HM_MoneyFlow',
            'HM_Flower_Open', 'HM_Flower_High', 'HM_Flower_Low', 'HM_Flower_Close',
            'HM_Band_Hi', 'HM_Band_KH', 'HM_Band_KM', 'HM_Band_KL', 'HM_Band_Lo'
        ]
        if not all(col in df_full.columns for col in required_cols):
            df_full = enrich_dataframe(df_full)

        df = df_full.tail(count).copy().reset_index(drop=True)
        x_idx = np.arange(len(df))
        dates = df['Date']

        # --- SETUP FIGURE ---
        fig = plt.figure(figsize=(16, 10))
        gs = gridspec.GridSpec(2, 1, height_ratios=[2, 1], hspace=0.1)
        
        ax_hm = fig.add_subplot(gs[0])
        ax_vni = fig.add_subplot(gs[1], sharex=ax_hm)
        
        fig.patch.set_facecolor('black')
        ax_hm.set_facecolor('#080808')
        ax_vni.set_facecolor('#080808')

        # --- 1. PLOT HEATMAP (Top Panel - ax_hm) ---
        if 'HM_Band_Long_Hr' in df.columns and 'HM_Band_Long_Ls' in df.columns:
            ax_hm.fill_between(x_idx, df['HM_Band_Long_Ls'], df['HM_Band_Long_Hr'], 
                           color='#1A1A1A', alpha=0.3)

        if 'HM_Band_Hi' in df.columns:
            ax_hm.fill_between(x_idx, df['HM_Band_KH'], df['HM_Band_Hi'], color='#003737', alpha=0.6)
            ax_hm.fill_between(x_idx, df['HM_Band_KM'], df['HM_Band_KH'], color='#3C0F00', alpha=0.5)
            ax_hm.fill_between(x_idx, df['HM_Band_KL'], df['HM_Band_KM'], color='#000053', alpha=0.5)
            ax_hm.fill_between(x_idx, df['HM_Band_Lo'], df['HM_Band_KL'], color='#2B2B59', alpha=0.6)

        f_o, f_h, f_l, f_c = df['HM_Flower_Open'], df['HM_Flower_High'], df['HM_Flower_Low'], df['HM_Flower_Close']
        up_f = (f_c >= f_o) & (df['HM_MoneyFlow'] == 1)
        dn_f = (f_c < f_o) & (df['HM_MoneyFlow'] == -1)
        neutral_f = ~(up_f | dn_f)
        
        ax_hm.vlines(x_idx[up_f], f_l[up_f], f_h[up_f], color='#E0E0E0', linewidth=1)
        ax_hm.vlines(x_idx[dn_f], f_l[dn_f], f_h[dn_f], color='#E60000', linewidth=1)
        ax_hm.vlines(x_idx[neutral_f], f_l[neutral_f], f_h[neutral_f], color='#FFD700', linewidth=1)
        
        ax_hm.bar(x_idx[up_f], f_c[up_f] - f_o[up_f], bottom=f_o[up_f], color='white', width=0.6, alpha=0.9)
        ax_hm.bar(x_idx[dn_f], f_o[dn_f] - f_c[dn_f], bottom=f_c[dn_f], color='#E60000', width=0.6, alpha=0.9)
        ax_hm.bar(x_idx[neutral_f], np.abs(f_c[neutral_f] - f_o[neutral_f]), bottom=np.minimum(f_o[neutral_f], f_c[neutral_f]), 
               color='#FFFF00', width=0.6, alpha=0.9)

        ax_hm.set_title(f"BẢN ĐỒ NHIỆT THỊ TRƯỜNG - AIC: {ticker}", fontsize=16, fontweight='bold', color='aqua')
        ax_hm.set_ylabel("Price", color='white')
        ax_hm.grid(True, color='#222222', linestyle=':', alpha=0.3)
        plt.setp(ax_hm.get_xticklabels(), visible=False)

        # --- 2. PLOT NORMAL CANDLES (Bottom Panel - ax_vni) ---
        v_o, v_h, v_l, v_c = df['Open'], df['High'], df['Low'], df['Close']
        up_v = v_c >= v_o
        dn_v = v_c < v_o
        
        ax_vni.vlines(x_idx, v_l, v_h, color='white', linewidth=0.5, alpha=0.5)
        ax_vni.bar(x_idx[up_v], v_c[up_v] - v_o[up_v], bottom=v_o[up_v], color='#00E600', width=0.6)
        ax_vni.bar(x_idx[dn_v], v_o[dn_v] - v_c[dn_v], bottom=v_c[dn_v], color='#FF0000', width=0.6)
        
        ax_vni.set_title(f"BIỂU ĐỒ GIÁ (NẾN THƯỜNG) - {ticker}", fontsize=12, color='white', pad=10)
        ax_vni.set_ylabel("Price", color='white')
        ax_vni.grid(True, color='#222222', linestyle=':', alpha=0.3)

        # --- 3. FORMATTING ---
        df['Date'] = pd.to_datetime(df['Date'])
        date_labels = df['Date'].dt.strftime('%d/%m/%y').tolist()
        ax_vni.xaxis.set_major_formatter(ticker_lib.FuncFormatter(lambda x, pos: date_labels[int(round(x))] if 0 <= int(round(x)) < len(date_labels) else ""))
        ax_vni.xaxis.set_major_locator(ticker_lib.MaxNLocator(10))
        
        for axis_obj in [ax_hm, ax_vni]:
            axis_obj.tick_params(colors='white')
            for spine in axis_obj.spines.values():
                spine.set_color('#333333')

        plt.tight_layout()
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, facecolor='black', edgecolor='none', dpi=120)
        plt.close(fig)
        logger.info(f"✅ Exported Heatmap chart to {save_path}")
    except Exception as e:
        logger.error(f"Error exporting Heatmap chart for {ticker}: {e}")
        import traceback
        traceback.print_exc()

def export_tech_report_chart(ticker, df_full, save_path):
    """
    Generate and save the 4-panel Technical Analysis Report chart.
    """
    try:
        plt.style.use('default')
        from tinvest.data_loader import enrich_dataframe
        from matplotlib.offsetbox import OffsetImage, AnnotationBbox
        import matplotlib.image as mpimg
        import matplotlib.lines as mlines
        
        df_rich = enrich_dataframe(df_full.copy())
        
        df_plot = df_rich.tail(100).copy()
        df_plot['Date'] = pd.to_datetime(df_plot['Date'])
        df_plot = df_plot.sort_values('Date')
        
        # Ichimoku Future (26 periods)
        last_date = df_plot['Date'].iloc[-1]
        future_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=26)
        df_future = pd.DataFrame({'Date': future_dates})
        df_ext = pd.concat([df_plot, df_future], ignore_index=True)
        
        df_rich['raw_a'] = (df_rich['Tenkan'] + df_rich['Kijun']) / 2
        df_rich['raw_b'] = (df_rich['High'].rolling(52).max() + df_rich['Low'].rolling(52).min()) / 2
        
        hist_cloud = df_rich[['Date', 'SpanA', 'SpanB']].tail(100).copy()
        
        future_spans = []
        for i in range(1, 27):
            source_idx = -26 + i
            val_a = df_rich['raw_a'].iloc[source_idx] if abs(source_idx) <= len(df_rich) else np.nan
            val_b = df_rich['raw_b'].iloc[source_idx] if abs(source_idx) <= len(df_rich) else np.nan
            future_spans.append({'Date': df_future['Date'].iloc[i-1], 'SpanA': val_a, 'SpanB': val_b})
            
        df_future_cloud = pd.DataFrame(future_spans)
        df_total_cloud = pd.concat([hist_cloud, df_future_cloud], ignore_index=True)
        
        from tinvest.analyzer import analyze_stock
        analysis_fresh = analyze_stock(ticker, df_rich)
        val = analysis_fresh.get('valuation', {})
        analysis = analysis_fresh
        
        fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [5, 1.2, 1.2, 1.5]}, sharex=True)
        plt.subplots_adjust(hspace=0.08, bottom=0.1)
        
        x_idx_plot = np.arange(len(df_plot))
        x_idx_ext = np.arange(len(df_ext))
        
        date_labels = df_ext['Date'].dt.strftime('%d/%m').tolist()
        def format_date(x, pos):
            try:
                idx = int(round(x))
                if 0 <= idx < len(date_labels):
                    return date_labels[idx]
            except:
                pass
            return ""
            
        up_mask = df_plot['Close'] >= df_plot['Open']
        down_mask = df_plot['Close'] < df_plot['Open']
        ax1.bar(x_idx_plot[up_mask], df_plot.loc[up_mask, 'Close'] - df_plot.loc[up_mask, 'Open'], bottom=df_plot.loc[up_mask, 'Open'], color='green', width=0.6, alpha=0.8)
        ax1.bar(x_idx_plot[down_mask], df_plot.loc[down_mask, 'Open'] - df_plot.loc[down_mask, 'Close'], bottom=df_plot.loc[down_mask, 'Close'], color='red', width=0.6, alpha=0.8)
        ax1.vlines(x_idx_plot[up_mask], df_plot.loc[up_mask, 'Low'], df_plot.loc[up_mask, 'High'], color='green', linewidth=1)
        ax1.vlines(x_idx_plot[down_mask], df_plot.loc[down_mask, 'Low'], df_plot.loc[down_mask, 'High'], color='red', linewidth=1)
        
        ma_styles = [('MA10', 'black', 'MA10', 2), ('MA20', 'green', 'MA20', 2), ('MA50', 'brown', 'MA50', 1)]
        for ma_col, color, label, lw in ma_styles:
            if ma_col in df_plot.columns:
                ax1.plot(x_idx_plot, df_plot[ma_col], label=label, color=color, linewidth=lw, alpha=0.8)
                
        ax1.fill_between(x_idx_ext, df_total_cloud['SpanA'], df_total_cloud['SpanB'], 
                         where=(df_total_cloud['SpanA'] >= df_total_cloud['SpanB']), color='lime', alpha=0.3, label='Kumo Green')
        ax1.fill_between(x_idx_ext, df_total_cloud['SpanA'], df_total_cloud['SpanB'], 
                         where=(df_total_cloud['SpanA'] < df_total_cloud['SpanB']), color='red', alpha=0.3, label='Kumo Red')
                         
        if 'Tenkan' in df_plot.columns:
            ax1.plot(x_idx_plot, df_plot['Tenkan'], color='blue', label='Tenkan', linewidth=1.0, alpha=0.9)
        if 'Kijun' in df_plot.columns:
            ax1.plot(x_idx_plot, df_plot['Kijun'], color='red', label='Kijun', linewidth=1.0, alpha=0.9)
        if 'Kijun65' in df_plot.columns:
            ax1.plot(x_idx_plot, df_plot['Kijun65'], color='orange', linestyle='--', label='Dao 65', linewidth=2.0, alpha=0.8)
            
        p_min, p_max = df_plot['Low'].min(), df_plot['High'].max()
        ax1.set_ylim(p_min * 0.95, p_max * 1.05)
        
        last_idx = x_idx_plot[-1]
        future_idx = last_idx + 22
        
        is_index = ticker.upper().endswith("INDEX") or "VN30" in ticker.upper()
        fmt = "{:,.0f}" if is_index else "{:,.2f}"
        
        # Logo handling safely
        logo_found = False
        for possible_dir in [os.getcwd(), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))[:3]]:
            logo_path = os.path.join(possible_dir, "Vector logo.png")
            if os.path.exists(logo_path):
                try:
                    img = mpimg.imread(logo_path)
                    imagebox = OffsetImage(img, zoom=0.05)
                    ab = AnnotationBbox(imagebox, (0.05, 0.94), frameon=False, xycoords='figure fraction')
                    fig.add_artist(ab)
                    fig.text(0.07, 0.94, "=AI+CƠM!", ha="left", va="center", fontsize=12, fontweight='bold', color='black')
                    logo_found = True
                    break
                except Exception as logo_err:
                    pass
        if not logo_found:
            fig.text(0.05, 0.98, "AIC CODE = AI + CƠM!", ha="left", va="top", fontsize=20, fontweight='bold', color='black')
            
        report_date = df_plot['Date'].iloc[-1].strftime('%d/%m/%Y')
        full_title = f"Technical Analysis Report: {ticker} - {report_date}"
        ax1.set_title(full_title, fontsize=16, fontweight='bold', color='darkblue', pad=30, loc='center')
        
        current_price = df_plot['Close'].iloc[-1]
        ax1.hlines(current_price, xmin=last_idx, xmax=future_idx, color='black', linestyle='-', linewidth=2.0, alpha=0.8)
        ax1.text(future_idx, current_price, f" {fmt.format(current_price)}", color='black', fontsize=10, fontweight='bold', va='center', ha='left', bbox=dict(facecolor='yellow', alpha=0.8, edgecolor='none', pad=1))
        
        if val:
            sr_config = [('s1', 'green', 'S1'), ('s2', 'darkgreen', 'S2'), 
                         ('r1', 'red', 'R1'), ('r2', 'darkred', 'R2')]
            for sr_key, color, lbl in sr_config:
                level = val.get(sr_key, 0)
                if level > 0:
                    ax1.hlines(level, xmin=last_idx, xmax=future_idx, color=color, linestyle='--', alpha=0.8, linewidth=1.5)
                    ax1.text(future_idx, level, f" {lbl}: {fmt.format(level)}", color=color, 
                             fontsize=9, fontweight='bold', va='center', ha='left')
                             
        sr_state = analysis.get('state_rules', {})
        sr_pri = sr_state.get('primary', 'N/A')
        sr_sec = sr_state.get('secondary', 'N/A')
        opp_score = val.get('opp_score', 0)
        risk_score = val.get('risk_score', 0)
        action_str = val.get('action', '')
        
        if "YES" in action_str:
            rec_text = f"NÊN MUA (giá {fmt.format(current_price)}), Target 1: {fmt.format(val.get('tp1', 0))}, Target 2: {fmt.format(val.get('tp2', 0))}, Cutloss: {fmt.format(val.get('cutloss_full', 0))}"
        elif "NO" in action_str or risk_score > 75 or "DOWNTREND" in sr_pri:
            rec_text = f"NÊN BÁN (giá {fmt.format(current_price)})"
        else:
            rec_text = "TRUNG LẬP (hiện tại trung lập chưa nên hành động)"
            
        summary_text = (
            f"TÓM LƯỢC NHẬN ĐỊNH ({report_date})\n"
            f"● Trạng thái: {sr_pri}\n"
            f"● Vận động: {sr_sec}\n"
            f"● Opp Score: {opp_score}/100 | Risk: {risk_score}/100\n"
            f"● Xu hướng: {'TĂNG' if opp_score > 50 else 'THEO DÕI' if opp_score > 30 else 'YẾU'}\n"
            f"● Khuyến nghị: {rec_text}"
        )
        ax1.text(0.01, 0.75, summary_text, transform=ax1.transAxes, fontsize=10,
                 verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='darkblue'))
                 
        from tinvest.advanced_entry import _eval_day
        buy_signals = []
        for real_idx in df_plot.index.tolist():
            rel_idx = -(len(df_rich) - df_rich.index.get_loc(real_idx))
            sig = _eval_day(df_rich, rel_idx)
            if sig and sig.get('type') in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
                buy_signals.append({'date': df_rich['Date'].loc[real_idx], 'type': sig['type'], 
                                   'source': sig.get('details', {}).get('source', 'N/A'), 'price': df_rich['Low'].loc[real_idx]})
                                   
        buy_signals = sorted(buy_signals, key=lambda x: x['date'], reverse=True)[:3]
        annotation_text = "3 ĐIỂM MUA GẦN NHẤT:\n\n"
        for i, b in enumerate(buy_signals):
            matches = np.where(df_plot['Date'] == b['date'])[0]
            if len(matches) > 0:
                pos = matches[0]
                ax1.plot(pos, b['price'] * 0.98, '^', markersize=12, color='lime', markeredgecolor='green')
                annotation_text += f" • #{i+1}: {b['date'].strftime('%d/%m')} - {b['type']} ({b['source']})\n\n"
                
        if buy_signals:
            fig.text(0.1, 0.02, annotation_text, fontsize=10, color='darkgreen', 
                     linespacing=1.8, bbox=dict(facecolor='white', alpha=0.9, edgecolor='lime', pad=5))
                     
        if 'MCDX_Banker' in df_plot.columns:
            ax2.bar(x_idx_plot, df_plot['MCDX_Banker'], color='red', width=0.8, alpha=0.8, label='Banker')
            ax2.bar(x_idx_plot, df_plot['MCDX_HotMoney'], bottom=df_plot['MCDX_Banker'], color='yellow', width=0.8, alpha=0.8, label='Hot Money')
            ax2.bar(x_idx_plot, df_plot['MCDX_Retailer'], bottom=df_plot['MCDX_Banker'] + df_plot['MCDX_HotMoney'], color='green', width=0.8, alpha=0.8, label='Retailer')
            if 'MCDX_Banker_MA' in df_plot.columns:
                ax2.plot(x_idx_plot, df_plot['MCDX_Banker_MA'], color='black', linewidth=1.5, label='Banker MA')
            ax2.set_ylabel('MCDX', fontweight='bold', fontsize=9)
            ax2.set_ylim(0, 20)
            ax2.legend(loc='upper left', fontsize=8, ncol=4)
        else:
            ax2.set_visible(False)
            
        if 'ADX' in df_plot.columns:
            adx_vals = df_plot['ADX'].values
            if 'ADX_Color' in df_plot.columns:
                adx_colors = df_plot['ADX_Color'].values
                for i in range(1, len(x_idx_plot)):
                    c = str(adx_colors[i]).lower()
                    if c == 'white': c = 'purple'
                    ax3.plot(x_idx_plot[i-1:i+1], adx_vals[i-1:i+1], color=c, linewidth=2.0)
            else:
                ax3.plot(x_idx_plot, df_plot['ADX'], color='black', linewidth=1.5)
            ax3.plot(x_idx_plot, df_plot['DI_Plus'], color='green', linewidth=1.0, label='+DI')
            ax3.plot(x_idx_plot, df_plot['DI_Minus'], color='red', linewidth=1.0, label='-DI')
            ax3.axhline(25, color='gray', linestyle='--', alpha=0.8, label='Trend Threshold')
            ax3.set_ylabel('ADX', fontweight='bold', fontsize=9)
            ax3.set_ylim(bottom=0)
            adx_legend = mlines.Line2D([], [], color='purple', linewidth=2.0, label='ADX (14)')
            handles, labels = ax3.get_legend_handles_labels()
            handles.insert(0, adx_legend)
            labels.insert(0, 'ADX (14)')
            ax3.legend(handles, labels, loc='upper left', fontsize=8, ncol=4)
            ax3.grid(True, linestyle='--', alpha=0.3)
        else:
            ax3.set_visible(False)
            
        if 'MACD' in df_plot.columns and 'MACD_Signal' in df_plot.columns:
            ax4.plot(x_idx_plot, df_plot['MACD'], color='blue', linewidth=1.5, label='MACD')
            ax4.plot(x_idx_plot, df_plot['MACD_Signal'], color='orange', linewidth=1.5, label='Signal')
            if 'MACD_Hist' in df_plot.columns:
                colors = np.where(df_plot['MACD_Hist'] >= 0, 'green', 'red')
                ax4.bar(x_idx_plot, df_plot['MACD_Hist'], color=colors, alpha=0.6, width=0.6)
            ax4.axhline(0, color='black', linestyle='-', linewidth=1, alpha=0.5)
            ax4.set_ylabel('MACD', fontweight='bold', fontsize=9)
            ax4.legend(loc='upper left', fontsize=8, ncol=3)
            ax4.grid(True, linestyle='--', alpha=0.3)
        else:
            ax4.set_visible(False)
            
        ax1.grid(True, linestyle='--', alpha=0.3)
        ax1.tick_params(labelright=True)
        ax1.legend(loc='upper left', fontsize=9, ncol=4)
        ax4.xaxis.set_major_formatter(ticker_lib.FuncFormatter(format_date))
        ax1.set_xlim(0, len(x_idx_ext) + 2)
        ax2.grid(True, linestyle='--', alpha=0.3)
        
        plt.tight_layout()
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, facecolor='white', edgecolor='none', dpi=120)
        plt.close(fig)
        logger.info(f"✅ Exported Technical Report chart to {save_path}")
    except Exception as e:
        logger.error(f"Error exporting Tech Report chart for {ticker}: {e}")
        import traceback
        traceback.print_exc()


def export_ticker_history_json(data_dict, analysis_cache, output_dir):
    """
    Export full OHLCV + computed indicators for each ticker to individual JSON files.
    These files are lazy-loaded by the web frontend to render interactive charts
    (replacing Matplotlib PNG exports entirely).
    
    Output: Output/history/{TICKER}.json  (one file per ticker)
    """
    import math
    import json
    from concurrent.futures import ThreadPoolExecutor
    
    history_dir = os.path.join(output_dir, "history")
    os.makedirs(history_dir, exist_ok=True)
    
    # Columns needed for each chart type
    GP_COLS = ['GP_E14', 'GP_E21', 'GP_xFast', 'GP_xSlow',
               'GP_BB_Top', 'GP_BB_Bot',
               'OCT_A1', 'OCT_B1', 'OCT_Color',
               'OCT_BB_Top', 'OCT_BB_Bot',
               'RS14', 'RS52']
    
    HK_COLS = ['HK_Flower_Open', 'HK_Flower_High', 'HK_Flower_Low', 'HK_Flower_Close',
               'HK_MHull', 'HK_SHull', 'HK_NW', 'HK_Trend', 'HK_BarColor',
               'HK_BuySignal', 'HK_BuyManh', 'HK_SellSignal', 'HK_SellManh',
               'TC_Trend', 'TC_TrendColor', 'TC_StopLine', 'TC_StopColor',
               'T2_SMA', 'T2_SMA_Trend', 'T2_ST_Upper', 'T2_ST_Lower', 'T2_ST_Trend']
    
    HM_COLS = ['HM_PFE', 'HM_STC', 'HM_MoneyFlow',
               'HM_Flower_Open', 'HM_Flower_High', 'HM_Flower_Low', 'HM_Flower_Close',
               'HM_Band_Hi', 'HM_Band_KH', 'HM_Band_KM', 'HM_Band_KL', 'HM_Band_Lo',
               'HM_Band_Long_Hr', 'HM_Band_Long_Ls']
    
    TR_COLS = ['MA10', 'MA20', 'MA50',
               'Tenkan', 'Kijun', 'Kijun65', 'SpanA', 'SpanB',
               'MCDX_Banker', 'MCDX_HotMoney', 'MCDX_Retailer', 'MCDX_Banker_MA',
               'ADX', 'ADX_Color', 'DI_Plus', 'DI_Minus',
               'MACD', 'MACD_Signal', 'MACD_Hist',
               'RSI']
    
    ALL_INDICATOR_COLS = list(dict.fromkeys(GP_COLS + HK_COLS + HM_COLS + TR_COLS))
    
    df_vn = data_dict.get("VNINDEX")
    df_vn_indexed = None
    if df_vn is not None and not df_vn.empty:
        try:
            df_vn_temp = df_vn.copy()
            df_vn_temp['Date'] = pd.to_datetime(df_vn_temp['Date'])
            df_vn_indexed = df_vn_temp.set_index('Date')
        except Exception as e_vn:
            logger.warning(f"Could not build VNINDEX index for RS: {e_vn}")
 
    all_tickers_to_export = list(data_dict.keys())
    
    def process_single_ticker(t):
        try:
            cached = analysis_cache.get(t)
            if cached and 'df' in cached and cached['df'] is not None:
                df = cached['df'].copy()
            else:
                df = data_dict.get(t)
                if df is None or df.empty:
                    return False
                df = df.copy()
            
            if df.empty or 'Date' not in df.columns:
                return False
            
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values('Date').reset_index(drop=True)
            
            # Calculate RS14 / RS52 against VNINDEX only if they are not already present
            if 'RS14' not in df.columns or 'RS52' not in df.columns:
                if df_vn_indexed is not None:
                    try:
                        bench_close = df['Date'].map(df_vn_indexed['Close']).ffill().bfill()
                        rs_raw = df['Close'] / (bench_close + 1e-10)
                        
                        rs52_min = rs_raw.rolling(window=260, min_periods=1).min()
                        rs52_max = rs_raw.rolling(window=260, min_periods=1).max()
                        df['RS52'] = 100 * (rs_raw - rs52_min) / (rs52_max - rs52_min + 0.0001)
                        
                        rs14_min = rs_raw.rolling(window=70, min_periods=1).min()
                        rs14_max = rs_raw.rolling(window=70, min_periods=1).max()
                        df['RS14'] = 100 * (rs_raw - rs14_min) / (rs14_max - rs14_min + 0.0001)
                    except Exception:
                        df['RS14'] = 50.0
                        df['RS52'] = 50.0
                else:
                    df['RS14'] = 50.0
                    df['RS52'] = 50.0
            
            df_extended = df.copy()
 
            def clean_nan_list(series):
                return [None if (pd.isna(x) or (isinstance(x, float) and np.isnan(x))) else x for x in series.tolist()]
 
            record = {
                "ticker": t,
                "dates": df_extended['Date'].dt.strftime("%Y-%m-%d").tolist(),
                "opens":   clean_nan_list(df_extended['Open'].round(6)),
                "highs":   clean_nan_list(df_extended['High'].round(6)),
                "lows":    clean_nan_list(df_extended['Low'].round(6)),
                "closes":  clean_nan_list(df_extended['Close'].round(6)),
                "volumes": clean_nan_list(df_extended['Volume'].round(6)),
            }
            
            for col in ALL_INDICATOR_COLS:
                if col in df_extended.columns:
                    series = df_extended[col]
                    if series.dtype == bool or col in ['HK_BuySignal', 'HK_BuyManh', 'HK_SellSignal', 'HK_SellManh']:
                        record[col] = [bool(v) if pd.notna(v) and v is not None else None for v in series]
                    elif series.dtype == object:
                        record[col] = [None if pd.isna(v) else v for v in series.tolist()]
                    else:
                        series_rounded = series.round(6)
                        record[col] = clean_nan_list(series_rounded)
            
            # Run What-If analysis (Only for core indices or stocks with AvgVolume10 >= 100k to avoid CPU/Memory overload)
            CORE_INDICES = {"VNINDEX", "HNX-INDEX", "UPCOM-INDEX", "VN30", "HNX30"}
            
            # Calculate 10-day average volume
            avg_vol_10 = 0.0
            if 'AvgVolume10' in df.columns and len(df) > 0:
                avg_vol_10 = float(df['AvgVolume10'].iloc[-1])
            elif 'Volume' in df.columns and len(df) >= 10:
                avg_vol_10 = float(df['Volume'].tail(10).mean())
            elif 'Volume' in df.columns and len(df) > 0:
                avg_vol_10 = float(df['Volume'].mean())
                
            is_index = t.upper() in CORE_INDICES or ("INDEX" in t.upper()) or ("VN30" in t.upper()) or ("HNX" in t.upper())
            has_high_volume = avg_vol_10 >= 100000.0
            
            # Check if we have pre-calculated whatif in analysis_cache
            whatif_data = None
            if analysis_cache and t in analysis_cache and 'whatif' in analysis_cache[t]:
                whatif_data = analysis_cache[t]['whatif']
                
            if (is_index or has_high_volume) and whatif_data is None:
                try:
                    from tinvest.whatif_engine import run_whatif_analysis
                    from tinvest.data_loader import enrich_dataframe
                    df_rich = df.copy()
                    if 'MA20' not in df_rich.columns or 'RSI' not in df_rich.columns or '_ENRICHED' not in df_rich.columns:
                        df_rich = enrich_dataframe(df_rich)
                    whatif_data = run_whatif_analysis(
                        t, df_rich, 
                        compute_forecast_series=True, 
                        forecast_days=60
                    )
                except Exception as e_wi:
                    whatif_data = {"error": str(e_wi)}
                    
            if (is_index or has_high_volume) and whatif_data is not None:
                try:
                    # Recursive NaN cleaner
                    def clean_nans(obj):
                        import math
                        if isinstance(obj, dict):
                            return {k: clean_nans(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [clean_nans(x) for x in obj]
                        elif isinstance(obj, float):
                            return None if (math.isnan(obj) or obj != obj) else obj
                        return obj
                    
                    if not whatif_data.get('error'):
                        record["whatif"] = clean_nans(whatif_data)
                    else:
                        record["whatif"] = {"error": whatif_data['error']}
                except Exception as e_wi:
                    record["whatif"] = {"error": str(e_wi)}
            else:
                record["whatif"] = None

            out_path = os.path.join(history_dir, f"{t}.json")
            import tempfile
            temp_fd, temp_path = tempfile.mkstemp(dir=history_dir, prefix=f"{t}_tmp_")
            try:
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    json.dump(record, f, ensure_ascii=False, separators=(',', ':'))
                if os.path.exists(out_path):
                    os.replace(temp_path, out_path)
                else:
                    os.rename(temp_path, out_path)
            except Exception as e_write:
                if os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except: pass
                raise e_write
            return True
        except Exception as ex:
            logger.error(f"   ! Lỗi xuất history JSON mã {t}: {ex}")
            return False
 
    max_workers = min(16, (os.cpu_count() or 4) * 2)
    logger.info(f"⚡ Đang xuất JSON song song sử dụng {max_workers} threads...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_single_ticker, all_tickers_to_export))
        
    exported = sum(1 for r in results if r)
    errors = len(all_tickers_to_export) - exported
    logger.info(f"✅ Đã xuất history JSON: {exported} mã thành công, {errors} lỗi → {history_dir}")

