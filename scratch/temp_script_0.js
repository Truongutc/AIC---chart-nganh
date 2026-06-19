
        let rawData = null;
        let searchQuery = '';
        let breadthChart = null;
        let currentChartRange = 30;
        let activeMarketIndex = 'VNINDEX';
        
        // Visibility state for Technical Report Chart lines
        const techChartVisibility = {
            SpanA: true,
            SpanB: true,
            Tenkan: true,
            Kijun: true,
            Kijun65: true,
            MA10: true,
            MA20: true,
            MA50: true
        };
        const techReportSeriesRegistry = {}; // keyed by mountId

        function toggleTechLine(key, checked) {
            techChartVisibility[key] = checked;
            // Sync all checkboxes on the page
            document.querySelectorAll(`.tech-toggle-${key}`).forEach(el => {
                el.checked = checked;
            });
            if (key === 'Kumo') {
                techChartVisibility['SpanA'] = checked;
                techChartVisibility['SpanB'] = checked;
                document.querySelectorAll(`.tech-toggle-SpanA, .tech-toggle-SpanB`).forEach(el => {
                    el.checked = checked;
                });
            }
            applyTechChartVisibility();
        }

        function applyTechChartVisibility() {
            for (const mountId in techReportSeriesRegistry) {
                const registry = techReportSeriesRegistry[mountId];
                if (!registry) continue;
                for (const key in techChartVisibility) {
                    const series = registry[key];
                    if (series) {
                        series.applyOptions({ visible: techChartVisibility[key] });
                    }
                }
            }
        }

        function getTechTogglesHtml() {
            return `
            <div class="chart-toggles-container" style="display:inline-flex; gap:6px; font-size:0.7rem; align-items:center; background:rgba(255,255,255,0.05); padding:2px 6px; border-radius:4px; border:1px solid rgba(255,255,255,0.08);">
                <label style="display:flex; align-items:center; gap:2px; cursor:pointer;"><input type="checkbox" class="tech-toggle-Kumo" ${techChartVisibility.SpanA ? 'checked' : ''} onchange="toggleTechLine('Kumo', this.checked)"> Kumo</label>
                <label style="display:flex; align-items:center; gap:2px; cursor:pointer;"><input type="checkbox" class="tech-toggle-Tenkan" ${techChartVisibility.Tenkan ? 'checked' : ''} onchange="toggleTechLine('Tenkan', this.checked)"> Tenkan</label>
                <label style="display:flex; align-items:center; gap:2px; cursor:pointer;"><input type="checkbox" class="tech-toggle-Kijun" ${techChartVisibility.Kijun ? 'checked' : ''} onchange="toggleTechLine('Kijun', this.checked)"> Kijun</label>
                <label style="display:flex; align-items:center; gap:2px; cursor:pointer;"><input type="checkbox" class="tech-toggle-Kijun65" ${techChartVisibility.Kijun65 ? 'checked' : ''} onchange="toggleTechLine('Kijun65', this.checked)"> Kijun65</label>
                <label style="display:flex; align-items:center; gap:2px; cursor:pointer;"><input type="checkbox" class="tech-toggle-MA10" ${techChartVisibility.MA10 ? 'checked' : ''} onchange="toggleTechLine('MA10', this.checked)"> MA10</label>
                <label style="display:flex; align-items:center; gap:2px; cursor:pointer;"><input type="checkbox" class="tech-toggle-MA20" ${techChartVisibility.MA20 ? 'checked' : ''} onchange="toggleTechLine('MA20', this.checked)"> MA20</label>
                <label style="display:flex; align-items:center; gap:2px; cursor:pointer;"><input type="checkbox" class="tech-toggle-MA50" ${techChartVisibility.MA50 ? 'checked' : ''} onchange="toggleTechLine('MA50', this.checked)"> MA50</label>
            </div>
            `;
        }
        
        // Pagination logic
        let displayedCount = 0;
        const PAGE_SIZE = 24;
        let filteredTickersList = [];
        let stockChartInstances = {};

        // Custom filters state (Logical AND)
        let activeCustomFilters = new Set();

        // Formatting utilities
        function formatPrice(p, isIndex = false) {
            if (p === null || p === undefined || isNaN(p) || p === 0) return "N/A";
            if (isIndex) {
                return Math.round(p / 1000).toLocaleString('vi-VN', { maximumFractionDigits: 0 });
            }
            return (p / 1000).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
        }

        function formatVolume(v) {
            if (!v || isNaN(v)) return "0";
            if (v >= 1000000) {
                return (v / 1000000).toFixed(1) + "M";
            }
            return (v / 1000).toFixed(0) + "k";
        }

        function getActionClass(actionStr) {
            if (!actionStr) return 'wait';
            const s = actionStr.toUpperCase();
            if (s.includes('RẤT NÊN') || s.includes('STRONGLY') || s.includes('ƯU TIÊN') || s.includes('RẤT MẠNH')) return 'strongly-buy';
            if (s.includes('BUY') || s.includes('YES') || s.includes('MUA') || s.includes('THAM GIA')) return 'buy';
            if (s.includes('SELL') || s.includes('BÁN') || s.includes('NO TRADE') || s.includes('ĐỨNG NGOÀI') || s.includes('HẠN CHẾ')) return 'sell';
            return 'wait';
        }

        // Tab Switching Mechanism
        function switchTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
            
            document.getElementById(tabId).classList.add('active');
            const clickedItem = document.querySelector(`.menu-item[data-tab="${tabId}"]`);
            if (clickedItem) clickedItem.classList.add('active');
            
            // Re-render chart size if switching to market tab
            if (tabId === 'market-tab' && breadthChartLwc && breadthChartLwc.chart) {
                setTimeout(() => {
                    const container = document.getElementById('breadthChartContainer');
                    if (container) {
                        breadthChartLwc.chart.resize(container.clientWidth, 400);
                    }
                }, 50);
            }
        }

        // Dropdown Menu functions
        function toggleMenuDropdown(event) {
            event.stopPropagation();
            const content = document.getElementById('menuContent');
            if (content) content.classList.toggle('show');
        }
        
        function selectMenuTab(tabId, icon, label) {
            const content = document.getElementById('menuContent');
            if (content) content.classList.remove('show');
            
            const tabIcon = document.getElementById('currentTabIcon');
            const tabLabel = document.getElementById('currentTabLabel');
            if (tabIcon) tabIcon.innerText = icon;
            if (tabLabel) tabLabel.innerText = label;
            
            switchTab(tabId);
        }

        // Fetch analysis data from local Output folder
        async function loadData() {
            try {
                const response = await fetch('./Output/analysis_results.json?t=' + new Date().getTime());
                rawData = await response.json();
                
                // Set update time
                document.getElementById('updateTimeText').innerText = `Cập nhật: ${rawData.last_update}`;
                
                // Set Vietstock cURL token status
                const vsStatus = rawData.vietstock_status || "UNKNOWN";
                const vsDot = document.getElementById('vietstockStatusDot');
                const vsText = document.getElementById('vietstockStatusText');
                if (vsDot && vsText) {
                    if (vsStatus === "VALID" || vsStatus === "LIMITED_BYPASSED") {
                        vsDot.className = "status-dot-indicator green";
                        vsText.innerText = `Kết nối: ${vsStatus === "VALID" ? "OK" : "BYPASSED"}`;
                        vsText.style.color = "var(--accent-green)";
                    } else if (vsStatus === "LIMITED") {
                        vsDot.className = "status-dot-indicator red";
                        vsText.innerText = "Kết nối: Bị giới hạn";
                        vsText.style.color = "var(--accent-red)";
                    } else if (vsStatus === "CSV_MODE") {
                        vsDot.className = "status-dot-indicator yellow";
                        vsText.innerText = "Kết nối: Nạp CSV";
                        vsText.style.color = "var(--accent-orange)";
                    } else {
                        vsDot.className = "status-dot-indicator red";
                        vsText.innerText = `Kết nối: Lỗi (${vsStatus})`;
                        vsText.style.color = "var(--accent-red)";
                    }
                }
                
                // Render Market Indices Cards (VNINDEX / HNX)
                renderMarketStatus();

                // Select VNINDEX detailed analysis and load charts by default
                selectMarketIndex('VNINDEX');

                // Initialize Breadth Chart
                initBreadthChart();

                // Filter & Render Grid
                applyCustomFilters();

                // Auto-select first ticker in Lookup view (Tab 2)
                if (rawData.tickers_analysis && rawData.tickers_analysis.length > 0) {
                    selectLookupTicker(rawData.tickers_analysis[0].Ticker);
                }
                
                // Generate portfolio inputs row structure
                generatePortfolioRows();

                // Hide loading screen
                document.getElementById('loadingOverlay').style.opacity = 0;
                setTimeout(() => {
                    document.getElementById('loadingOverlay').style.display = 'none';
                }, 300);

            } catch (error) {
                console.error("Error loading JSON:", error);
                document.getElementById('updateTimeText').innerText = "Lỗi kết nối dữ liệu";
                document.getElementById('tickersGrid').innerHTML = `
                    <div class="empty-state">
                        <p style="color: var(--accent-red); font-weight: 600;">Không thể tải dữ liệu phân tích</p>
                        <p style="font-size: 0.85rem; margin-top: 8px;">Vui lòng kiểm tra lại file Output/analysis_results.json.</p>
                    </div>
                `;
                document.getElementById('loadingOverlay').style.display = 'none';
            }
        }

        // Render Market Index status cards (VNINDEX & HNXINDEX)
        function renderMarketStatus() {
            const vnStatus = rawData.market_indices ? rawData.market_indices["VNINDEX"] : null;
            const hnxStatus = rawData.market_indices ? rawData.market_indices["HNX-INDEX"] : null;
            
            if (vnStatus) {
                renderIndexCard("vnindex-summary-card", "VNINDEX", vnStatus);
            } else {
                document.getElementById("vnindex-summary-card").innerHTML = '<div class="empty-state">Thiếu dữ liệu VNINDEX</div>';
            }
            if (hnxStatus) {
                renderIndexCard("hnxindex-summary-card", "HNX-INDEX", hnxStatus);
            } else {
                document.getElementById("hnxindex-summary-card").innerHTML = '<div class="empty-state">Thiếu dữ liệu HNX-INDEX</div>';
            }
        }
        
        function renderIndexCard(containerId, indexName, status) {
            const container = document.getElementById(containerId);
            if (!container) return;
            
            let regimeClass = '';
            if (status.regime.includes('UPTREND')) regimeClass = 'bullish';
            else if (status.regime.includes('DOWNTREND')) regimeClass = 'bearish';
            else regimeClass = 'neutral';
            
            let actionClass = getActionClass(status.action);
            let sr = status.support_resistance || { s1: 0, s2: 0, r1: 0, r2: 0 };
            
            container.innerHTML = `
                <div class="market-card-header">
                    <span class="market-index-title">${indexName}</span>
                    <span class="action-badge ${actionClass}">${status.action}</span>
                </div>
                <div class="market-price-section">
                    <div class="market-price-val">${formatPrice(status.price, true)}</div>
                    <div class="market-date-val">Ngày: ${status.date}</div>
                </div>
                <div class="market-metrics-grid">
                    <div class="market-metric-box">
                        <span class="m-label">Xu hướng chính</span>
                        <strong class="m-value ${regimeClass}">${status.regime}</strong>
                    </div>
                    <div class="market-metric-box">
                        <span class="m-label">Tỷ trọng khuyến nghị</span>
                        <strong class="m-value text-purple">${status.alloc}</strong>
                    </div>
                </div>
                <p class="alloc-note-text">${status.alloc_note}</p>
                <div class="divider-h"></div>
                <div class="market-extra-details">
                    <div class="market-extra-row">
                        <span>Hỗ trợ S1 / S2:</span>
                        <strong>${formatPrice(sr.s1, true)} / ${formatPrice(sr.s2, true)}</strong>
                    </div>
                    <div class="market-extra-row">
                        <span>Kháng cự R1 / R2:</span>
                        <strong>${formatPrice(sr.r1, true)} / ${formatPrice(sr.r2, true)}</strong>
                    </div>
                    <div class="market-extra-row">
                        <span>Bùng nổ theo đà (FTD):</span>
                        <strong class="${status.ftd_active ? 'bullish' : 'neutral'}">${status.ftd_active ? `CÓ (Ngày ${status.ftd_date})` : 'CHƯA'}</strong>
                    </div>
                    <div class="market-extra-row">
                        <span>Số ngày phân phối:</span>
                        <strong class="${status.distribution_count >= 4 ? 'bearish' : 'neutral'}">${status.distribution_count} ngày</strong>
                    </div>
                </div>
            `;
        }

        // Active Index Card Selection
        function selectMarketIndex(indexName) {
            activeMarketIndex = indexName;
            
            // Toggle active card class
            const vnCard = document.getElementById('vnindex-summary-card');
            const hnxCard = document.getElementById('hnxindex-summary-card');
            if (vnCard) vnCard.classList.toggle('active-index-card', indexName === 'VNINDEX');
            if (hnxCard) hnxCard.classList.toggle('active-index-card', indexName === 'HNX-INDEX');
            
            // Render index assessment detail
            renderMarketIndexDetail();
            
            // Load 4 charts for this index
            loadMarketCharts();
        }

        function loadMarketCharts() {
            renderAll4Charts('market', activeMarketIndex);
        }

        // Render detailed market index diagnostics
        function renderMarketIndexDetail() {
            const indexName = activeMarketIndex;
            const indexData = rawData.market_indices ? rawData.market_indices[indexName] : null;
            
            const detailSection = document.getElementById('vnindexDetailSection');
            if (!detailSection) return;
            
            const sectionTitle = detailSection.querySelector('.charts-section-title');
            if (sectionTitle) {
                sectionTitle.innerHTML = `📈 Biểu đồ Phân tích ${indexName}`;
            }
            
            if (!indexData) {
                detailSection.style.display = 'none';
                return;
            }
            detailSection.style.display = 'block';

            // Populate AI Detailed Report Card
            const aiCard = document.getElementById('marketAIReportCard');
            const aiContent = document.getElementById('marketAIReportContent');
            if (aiCard && aiContent) {
                if (indexData.ReportText) {
                    aiContent.textContent = indexData.ReportText;
                    aiCard.style.display = 'block';
                } else {
                    aiCard.style.display = 'none';
                }
            }

            // Summary Header
            const headerEl = document.getElementById('vnindexSummaryHeader');
            if (headerEl) {
                const diag = indexData.diagnostics || {};
                
                let techScore = 50;
                const diagKeys = ['ma', 'ichimoku', 'rsi', 'macd', 'adx'];
                let bullCount = 0, bearCount = 0;
                diagKeys.forEach(k => {
                    const st = (diag[k]?.status || '').toLowerCase();
                    const act = (diag[k]?.action || '').toLowerCase();
                    if (st.includes('bull') || st.includes('uptrend') || act.includes('buy') || act.includes('strong')) bullCount++;
                    else if (st.includes('bear') || st.includes('downtrend') || act.includes('sell') || act.includes('weak')) bearCount++;
                });
                techScore = Math.round(((bullCount - bearCount + diagKeys.length) / (diagKeys.length * 2)) * 100);
                techScore = Math.max(0, Math.min(100, techScore));

                let barColor = techScore >= 70 ? 'var(--accent-green)' : techScore >= 40 ? 'var(--accent-orange)' : 'var(--accent-red)';
                let regimeClass = indexData.regime.includes('UPTREND') ? 'bullish' : indexData.regime.includes('DOWNTREND') ? 'bearish' : 'neutral';

                headerEl.innerHTML = `
                    <div style="flex:1; min-width:200px;">
                        <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:8px;">
                            <span class="index-name">💎 ${indexName}</span>
                            <span class="index-price">${formatPrice(indexData.price, true)}</span>
                            <span class="action-badge ${getActionClass(indexData.action)}">${indexData.action}</span>
                            <span class="index-date">📅 ${indexData.date}</span>
                        </div>
                        <div class="rating-bar-container">
                            <div class="rating-bar-bg">
                                <div class="rating-bar-fill" style="width:${techScore}%; background:${barColor}"></div>
                            </div>
                            <div class="rating-label">Đánh giá Kỹ thuật Tổng quát: <strong style="color:${barColor}">${techScore}/100</strong></div>
                        </div>
                        <div style="margin-top:10px;">
                            <span class="${regimeClass}" style="font-weight:700; font-size:0.95rem;">Xu hướng: ${indexData.regime}</span>
                            <span style="margin-left:12px; font-size:0.85rem;">Tỷ trọng: <strong class="text-purple">${indexData.alloc}</strong></span>
                        </div>
                        <p class="alloc-note-text" style="margin-top:8px;">${indexData.alloc_note}</p>
                    </div>
                `;
            }

            // Diagnostics Grid
            const gridEl = document.getElementById('vnindexDiagGrid');
            if (gridEl) {
                const diag = indexData.diagnostics || {};
                const sr = indexData.support_resistance || { s1: 0, s2: 0, r1: 0, r2: 0 };
                const mcdx = indexData.mcdx_eval || {};
                const stateRules = indexData.state_rules || {};

                function diagClass(st, act) {
                    const s = (st + ' ' + act).toLowerCase();
                    if (s.includes('bull') || s.includes('uptrend') || s.includes('buy') || s.includes('strong')) return 'bullish';
                    if (s.includes('bear') || s.includes('downtrend') || s.includes('sell') || s.includes('weak')) return 'bearish';
                    return 'neutral';
                }

                let regimeClass = indexData.regime.includes('UPTREND') ? 'bullish' : indexData.regime.includes('DOWNTREND') ? 'bearish' : 'neutral';

                gridEl.innerHTML = `
                    <!-- Card: BỘ CHỈ BÁO ROBOT -->
                    <div class="analysis-card">
                        <h4>🤖 Bộ Chỉ Báo ROBOT</h4>
                        <div class="diag-row"><span>Xu hướng chính</span><strong class="${regimeClass}">${stateRules.primary || 'N/A'}</strong></div>
                        <div class="diag-row"><span>Xu hướng phụ</span><strong>${stateRules.secondary || 'N/A'}</strong></div>
                        <div class="diag-row"><span>Tín hiệu Robot</span><strong class="${getActionClass(stateRules.signal)}">${stateRules.signal || 'N/A'}</strong></div>
                        <div class="diag-row"><span>Trạng thái</span><strong>${stateRules.regime || 'N/A'}</strong></div>
                        <div class="diag-row"><span>Độ tin cậy</span><strong>${stateRules.confidence || 'N/A'}</strong></div>
                        <div class="diag-row"><span>Tránh mua (Avoid Entry)</span><strong class="${stateRules.avoid_entry ? 'bearish' : 'bullish'}">${stateRules.avoid_entry ? 'CÓ' : 'KHÔNG'}</strong></div>
                        <div class="diag-row"><span>Chỉ báo ADX / RSI</span><strong>${stateRules.adx !== undefined ? parseFloat(stateRules.adx).toFixed(1) : 'N/A'} / ${stateRules.rsi !== undefined ? parseFloat(stateRules.rsi).toFixed(1) : 'N/A'}</strong></div>
                        <div class="diag-row"><span>MACD Hist / Bias</span><strong>${stateRules.macd_hist !== undefined ? parseFloat(stateRules.macd_hist).toFixed(1) : 'N/A'} / ${stateRules.trend_bias !== undefined ? parseFloat(stateRules.trend_bias).toFixed(2) : 'N/A'}</strong></div>
                    </div>

                    <!-- Card: CHỈ BÁO DÒNG TIỀN MCDX -->
                    <div class="analysis-card">
                        <h4>🔥 Dòng Tiền MCDX</h4>
                        <div class="diag-row"><span>Nguồn vốn lớn (Banker)</span><strong style="color: #ff3b3b;">${mcdx.banker_pct !== undefined ? parseFloat(mcdx.banker_pct).toFixed(1) + '%' : '0.0%'}</strong></div>
                        <div class="diag-row"><span>Dòng tiền nóng (Hot)</span><strong style="color: #ffcc00;">${mcdx.hot_pct !== undefined ? parseFloat(mcdx.hot_pct).toFixed(1) + '%' : '0.0%'}</strong></div>
                        <div class="diag-row"><span>Nhỏ lẻ (Retailer)</span><strong style="color: #34c759;">${mcdx.retailer_pct !== undefined ? parseFloat(mcdx.retailer_pct).toFixed(1) + '%' : '0.0%'}</strong></div>
                        <div class="diag-row"><span>Trạng thái dòng tiền</span><strong>${mcdx.status || 'N/A'}</strong></div>
                        <div class="diag-row"><span>Hành động đề xuất</span><strong>${mcdx.action || 'N/A'}</strong></div>
                        <div class="diag-row" style="grid-column: 1 / -1; margin-top: 6px; font-size: 0.75rem; color: var(--text-secondary); line-height: 1.4;">
                            <span>Chi tiết: ${mcdx.details || 'N/A'}</span>
                        </div>
                    </div>

                    <!-- Card: CHẨN ĐOÁN KỸ THUẬT & HỖ TRỢ/KHÁNG CỰ -->
                    <div class="analysis-card">
                        <h4>🔍 Chẩn Đoán Kỹ Thuật</h4>
                        <div class="diag-row"><span>Hệ thống MA</span><strong class="${diagClass(diag.ma?.status, diag.ma?.action)}">${diag.ma?.status || 'N/A'}</strong></div>
                        <div class="diag-row"><span>Ichimoku Cloud</span><strong class="${diagClass(diag.ichimoku?.status, diag.ichimoku?.action)}">${diag.ichimoku?.status || 'N/A'}</strong></div>
                        <div class="diag-row"><span>RSI / MACD</span><strong class="${diagClass(diag.rsi?.status, diag.rsi?.action)}">${diag.rsi?.status || 'N/A'}</strong> / <strong class="${diagClass(diag.macd?.status, diag.macd?.action)}">${diag.macd?.status || 'N/A'}</strong></div>
                        <div class="diag-row"><span>Hỗ trợ S1 / S2</span><strong class="text-green">${formatPrice(sr.s1, true)} / ${formatPrice(sr.s2, true)}</strong></div>
                        <div class="diag-row"><span>Kháng cự R1 / R2</span><strong class="text-red">${formatPrice(sr.r1, true)} / ${formatPrice(sr.r2, true)}</strong></div>
                        <div class="diag-row"><span>Bản đồ nhiệt (Heatmap)</span><strong>${indexData.heatmap_eval || 'N/A'}</strong></div>
                    </div>

                    <!-- Card: TỔNG KẾT CHIẾN LƯỢC AI -->
                    <div class="analysis-card">
                        <h4>🎯 Chiến Lược AI & FTD</h4>
                        <div class="diag-row"><span>FTD (Bùng nổ theo đà)</span><strong class="${indexData.ftd_active ? 'bullish' : 'neutral'}">${indexData.ftd_active ? 'CÓ (' + indexData.ftd_date + ')' : 'CHƯA'}</strong></div>
                        <div class="diag-row"><span>Chất lượng FTD</span><strong>${indexData.ftd_quality || 'N/A'}</strong></div>
                        <div class="diag-row"><span>Phục hồi (RA) / Phân phối</span><strong>${indexData.ra_day || 0} ngày / <strong class="${indexData.distribution_count >= 4 ? 'bearish' : 'neutral'}">${indexData.distribution_count} ngày</strong></strong></div>
                        <div class="diag-row"><span>Tỷ trọng cổ phiếu tối đa</span><strong class="text-purple">${indexData.alloc || 'N/A'}</strong></div>
                        <div class="diag-row"><span>Hành động AI đề xuất</span><strong class="${getActionClass(indexData.action)}">${indexData.action || 'N/A'}</strong></div>
                        <div class="diag-row" style="grid-column: 1 / -1; margin-top: 6px; font-size: 0.75rem; color: var(--text-secondary); line-height: 1.4;">
                            <span>Kịch bản xấu nhất: Nếu thủng MA20 / Kijun, lập tức hạ tỷ trọng.</span>
                        </div>
                    </div>
                `;
            }
        }


        let breadthChartLwc = null;
        let breadthChartFsInstance = null;
        let breadthMAVisible = { MA10: true, MA20: true, MA50: true };
        let breadthVNINDEXVisible = true;
        let breadthChartActiveDays = 90;

        // Build interactive Lightweight Charts for Market Breadth
        async function createBreadthChart(containerId, isFs) {
            const container = document.getElementById(containerId);
            if (!container) return null;
            container.innerHTML = '';
            
            const data = rawData.market_breadth;
            if (!data || !data.dates) {
                container.innerHTML = '<div class="chart-error">Không có dữ liệu độ rộng thị trường</div>';
                return null;
            }
            
            // Try fetching VNINDEX candlestick history
            let vnHistory = null;
            try {
                vnHistory = await fetchHistory('VNINDEX');
            } catch(e) {
                console.warn("Could not load VNINDEX candlestick history, falling back to line chart", e);
            }
            
            // For fullscreen, let's make it fill the modal height or use a larger height
            const height = isFs ? Math.max(400, (container.offsetHeight || window.innerHeight - 150)) : 400;

            // Create Lightweight Chart
            const chart = LightweightCharts.createChart(container, {
                ...LWC_THEME,
                width: container.clientWidth,
                height: height,
                leftPriceScale: {
                    visible: true,
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    autoScale: false,
                    scaleMargins: {
                        top: 0.1,
                        bottom: 0.1,
                    },
                },
                rightPriceScale: {
                    visible: true,
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    autoScale: true,
                    scaleMargins: {
                        top: 0.1,
                        bottom: 0.1,
                    },
                }
            });
            
            // Lock left price scale between 0 and 100 for percentage breadth
            chart.priceScale('left').applyOptions({
                minPrice: 0,
                maxPrice: 100,
            });
            
            // Add lines to LEFT scale
            const ma10Series = chart.addLineSeries({
                priceScaleId: 'left',
                color: '#ffffff', // White
                lineWidth: 2,
                title: '',
                visible: breadthMAVisible.MA10
            });
            const ma20Series = chart.addLineSeries({
                priceScaleId: 'left',
                color: '#00f0ff', // Cyan (Vibrant neon contrasting color)
                lineWidth: 2,
                title: '',
                visible: breadthMAVisible.MA20
            });
            const ma50Series = chart.addLineSeries({
                priceScaleId: 'left',
                color: '#ff007f', // Fuchsia (Vibrant neon contrasting color)
                lineWidth: 2,
                title: '',
                visible: breadthMAVisible.MA50
            });
            
            // Prepare line data
            const ma10Data = [];
            const ma20Data = [];
            const ma50Data = [];
            
            for (let i = 0; i < data.dates.length; i++) {
                const ts = d2ts(data.dates[i]);
                if (data.MA10[i] !== null && data.MA10[i] !== undefined) {
                    ma10Data.push({ time: ts, value: data.MA10[i] });
                }
                if (data.MA20[i] !== null && data.MA20[i] !== undefined) {
                    ma20Data.push({ time: ts, value: data.MA20[i] });
                }
                if (data.MA50[i] !== null && data.MA50[i] !== undefined) {
                    ma50Data.push({ time: ts, value: data.MA50[i] });
                }
            }
            
            ma10Series.setData(ma10Data);
            ma20Series.setData(ma20Data);
            ma50Series.setData(ma50Data);
            
            // Add VNINDEX to RIGHT scale
            let vnSeries = null;
            if (vnHistory) {
                vnSeries = chart.addCandlestickSeries({
                    priceScaleId: 'right',
                    upColor: '#00ff6a',
                    downColor: '#ff3b3b',
                    borderUpColor: '#00ff6a',
                    borderDownColor: '#ff3b3b',
                    wickUpColor: '#00ff6a',
                    wickDownColor: '#ff3b3b',
                    title: '',
                    visible: breadthVNINDEXVisible
                });
                vnSeries.setData(ohlcv(vnHistory));
            } else if (data.VNINDEX_Closes && data.VNINDEX_Closes.length > 0) {
                // Fallback to line
                vnSeries = chart.addLineSeries({
                    priceScaleId: 'right',
                    color: '#ef4444',
                    lineWidth: 2.5,
                    title: '',
                    visible: breadthVNINDEXVisible
                });
                const vnData = [];
                for (let i = 0; i < data.dates.length; i++) {
                    if (data.VNINDEX_Closes[i]) {
                        vnData.push({ time: d2ts(data.dates[i]), value: data.VNINDEX_Closes[i] });
                    }
                }
                vnSeries.setData(vnData);
            }
            
            // Handle resizing
            const ro = new ResizeObserver(() => {
                const w = container.clientWidth;
                const h = isFs ? Math.max(400, (container.offsetHeight || window.innerHeight - 150)) : 400;
                chart.resize(w, h);
            });
            ro.observe(container);
            
            return { chart, ro, dates: data.dates, ma10Series, ma20Series, ma50Series, vnSeries };
        }

        async function initBreadthChart() {
            const res = await createBreadthChart('breadthChartContainer', false);
            if (res) {
                breadthChartLwc = res;
                // Set default view range (last 90 days)
                setBreadthChartRange(breadthChartActiveDays);
                updateBreadthToggleButtons();
            }
        }

        async function renderBreadthChartFs(mountId) {
            const res = await createBreadthChart(mountId, true);
            if (res) {
                breadthChartFsInstance = res;
                fsInstances.push(res);
                applyBreadthRange(res.chart, res.dates, breadthChartActiveDays);
            }
        }

        // Change chart range view (sets zoom/visible logical range)
        function setBreadthChartRange(days) {
            breadthChartActiveDays = days;
            
            if (breadthChartLwc && breadthChartLwc.chart) {
                applyBreadthRange(breadthChartLwc.chart, breadthChartLwc.dates, days);
            }
            if (breadthChartFsInstance && breadthChartFsInstance.chart) {
                applyBreadthRange(breadthChartFsInstance.chart, breadthChartFsInstance.dates, days);
            }
            
            updateBreadthRangeButtons(days);
        }

        function applyBreadthRange(chartObj, dates, days) {
            if (!dates || dates.length === 0) return;
            if (days >= dates.length) {
                chartObj.timeScale().fitContent();
            } else {
                const fromIndex = Math.max(0, dates.length - days);
                const toIndex = dates.length - 1;
                const fromTs = d2ts(dates[fromIndex]);
                const toTs = d2ts(dates[toIndex]);
                chartObj.timeScale().setVisibleRange({
                    from: fromTs,
                    to: toTs
                });
            }
        }

        function updateBreadthRangeButtons(days) {
            // Update normal card range buttons
            const normalCard = document.querySelector('.card .chart-controls');
            if (normalCard) {
                const buttons = normalCard.querySelectorAll('button');
                buttons.forEach(btn => {
                    btn.classList.remove('active');
                    if (days === 30 && btn.innerText.includes('30')) btn.classList.add('active');
                    else if (days === 90 && btn.innerText.includes('90')) btn.classList.add('active');
                    else if (days === 180 && btn.innerText.includes('180')) btn.classList.add('active');
                    else if (days > 360 && btn.innerText.includes('Tất cả')) btn.classList.add('active');
                });
            }

            // Update fullscreen modal range buttons
            const fsControls = document.getElementById('chartFsControls');
            if (fsControls) {
                const buttons = fsControls.querySelectorAll('.chart-controls button');
                buttons.forEach(btn => {
                    btn.classList.remove('active');
                    if (days === 30 && btn.innerText.includes('30')) btn.classList.add('active');
                    else if (days === 90 && btn.innerText.includes('90')) btn.classList.add('active');
                    else if (days === 180 && btn.innerText.includes('180')) btn.classList.add('active');
                    else if (days > 360 && btn.innerText.includes('Tất cả')) btn.classList.add('active');
                });
            }
        }

        function toggleBreadthMA(maKey) {
            breadthMAVisible[maKey] = !breadthMAVisible[maKey];
            
            // Sync visibility inside active charts
            if (breadthChartLwc) {
                const series = breadthChartLwc[maKey.toLowerCase() + 'Series'];
                if (series) {
                    series.applyOptions({ visible: breadthMAVisible[maKey] });
                }
            }
            if (breadthChartFsInstance) {
                const series = breadthChartFsInstance[maKey.toLowerCase() + 'Series'];
                if (series) {
                    series.applyOptions({ visible: breadthMAVisible[maKey] });
                }
            }
            
            updateBreadthToggleButtons();
        }

        function toggleBreadthVNINDEX() {
            breadthVNINDEXVisible = !breadthVNINDEXVisible;
            
            // Sync visibility inside active charts
            if (breadthChartLwc && breadthChartLwc.vnSeries) {
                breadthChartLwc.vnSeries.applyOptions({ visible: breadthVNINDEXVisible });
            }
            if (breadthChartFsInstance && breadthChartFsInstance.vnSeries) {
                breadthChartFsInstance.vnSeries.applyOptions({ visible: breadthVNINDEXVisible });
            }
            
            updateBreadthToggleButtons();
        }

        function updateBreadthToggleButtons() {
            const keys = ['MA10', 'MA20', 'MA50'];
            keys.forEach(key => {
                const visible = breadthMAVisible[key];
                
                // Normal card buttons
                const btnNormal = document.getElementById(`toggle-normal-${key.toLowerCase()}`);
                if (btnNormal) {
                    if (visible) {
                        btnNormal.classList.add('active');
                        btnNormal.classList.remove('inactive');
                    } else {
                        btnNormal.classList.remove('active');
                        btnNormal.classList.add('inactive');
                    }
                }
                
                // Fullscreen modal buttons
                const btnFs = document.getElementById(`toggle-fs-${key.toLowerCase()}`);
                if (btnFs) {
                    if (visible) {
                        btnFs.classList.add('active');
                        btnFs.classList.remove('inactive');
                    } else {
                        btnFs.classList.remove('active');
                        btnFs.classList.add('inactive');
                    }
                }
            });

            // Update VNINDEX toggle button
            const vniNormal = document.getElementById('toggle-normal-vnindex');
            if (vniNormal) {
                if (breadthVNINDEXVisible) {
                    vniNormal.classList.add('active');
                    vniNormal.classList.remove('inactive');
                } else {
                    vniNormal.classList.remove('active');
                    vniNormal.classList.add('inactive');
                }
            }

            const vniFs = document.getElementById('toggle-fs-vnindex');
            if (vniFs) {
                if (breadthVNINDEXVisible) {
                    vniFs.classList.add('active');
                    vniFs.classList.remove('inactive');
                } else {
                    vniFs.classList.remove('active');
                    vniFs.classList.add('inactive');
                }
            }
        }

        async function expandBreadthChart() {
            const modal = document.getElementById('chartFsModal');
            const title = document.getElementById('chartFsTitle');
            const fsMt  = document.getElementById('chartFsMount');
            const fsControls = document.getElementById('chartFsControls');
            if (!modal) return;

            title.textContent = `Độ Rộng Thị Trường (MA Lines vs VNINDEX)`;

            // Destroy previous FS instances
            fsInstances.forEach(it => { try{it.ro&&it.ro.disconnect();}catch(e){} try{it.chart&&it.chart.remove();}catch(e){} });
            fsInstances = [];
            fsMt.innerHTML = '';
            breadthChartFsInstance = null;

            // Setup FS breadth controls in header
            if (fsControls) {
                fsControls.innerHTML = `
                    <div class="ma-toggles">
                        <button id="toggle-fs-vnindex" class="btn-sm" onclick="toggleBreadthVNINDEX()">VNINDEX</button>
                        <button id="toggle-fs-ma10" class="btn-sm" onclick="toggleBreadthMA('MA10')">MA10</button>
                        <button id="toggle-fs-ma20" class="btn-sm" onclick="toggleBreadthMA('MA20')">MA20</button>
                        <button id="toggle-fs-ma50" class="btn-sm" onclick="toggleBreadthMA('MA50')">MA50</button>
                    </div>
                    <div class="chart-controls">
                        <button class="btn-sm" onclick="setBreadthChartRange(30)">30N</button>
                        <button class="btn-sm" onclick="setBreadthChartRange(90)">90N</button>
                        <button class="btn-sm" onclick="setBreadthChartRange(180)">180N</button>
                        <button class="btn-sm" onclick="setBreadthChartRange(9999)">Tất cả</button>
                    </div>
                `;
                fsControls.style.display = 'flex';
                updateBreadthToggleButtons();
                updateBreadthRangeButtons(breadthChartActiveDays);
            }

            modal.classList.add('open');

            // Wait for modal layout to settle, then render
            requestAnimationFrame(() => {
                requestAnimationFrame(async () => {
                    await renderBreadthChartFs('chartFsMount');
                });
            });
        }


        // Lookup Search autocomplete (Tab 2)
        function handleLookupSearch() {
            const input = document.getElementById('lookupSearchInput');
            const dropdown = document.getElementById('lookupSuggestions');
            const val = input.value.trim().toUpperCase();
            
            if (!val) {
                dropdown.style.display = 'none';
                return;
            }
            
            const matches = rawData.tickers_analysis.filter(t => t.Ticker.includes(val)).slice(0, 10);
            
            if (matches.length === 0) {
                dropdown.innerHTML = '<div class="suggestion-item no-match">Không tìm thấy mã nào</div>';
            } else {
                dropdown.innerHTML = matches.map(m => `
                    <div class="suggestion-item" onclick="selectLookupTicker('${m.Ticker}')">
                        <span class="s-ticker">${m.Ticker}</span>
                        <span class="s-price">${formatPrice(m.Price)}</span>
                        <span class="s-action ${getActionClass(m.Action)}">${m.Action}</span>
                    </div>
                `).join('');
            }
            dropdown.style.display = 'block';
        }

        function selectLookupTicker(ticker) {
            document.getElementById('lookupSearchInput').value = ticker;
            document.getElementById('lookupSuggestions').style.display = 'none';
            
            const tickerData = rawData.tickers_analysis.find(t => t.Ticker === ticker);
            if (tickerData) {
                renderStockDetails(tickerData, 'stockDetailsDashboard');
            }
        }

        // Shared function to render detailed stock dashboard panels & Matplotlib charts
        function renderStockDetails(t, containerId) {
            const container = document.getElementById(containerId);
            container.style.display = 'block';
            
            let riskClass = 'green';
            if (t.RiskScore >= 70) riskClass = 'red';
            else if (t.RiskScore >= 40) riskClass = 'orange';

            let vsaStatusText = t.Diagnostics.vsa.status;
            let vsaActionText = t.Diagnostics.vsa.action;
            let vsaClass = vsaStatusText.toLowerCase().includes('bear') ? 'bearish' : 
                           vsaStatusText.toLowerCase().includes('bull') ? 'bullish' : 'neutral';

            let accumClass = t.ReadyToBreak ? 'bullish' : 'neutral';

            container.innerHTML = `
                <div class="dashboard-grid">
                    <!-- BLOCK 1: Tổng quan và Khuyến nghị -->
                    <div class="card block-card">
                        <div class="block-header">
                            <div class="block-title">
                                <span class="stock-title">${t.Ticker}</span>
                                <span class="action-badge ${getActionClass(t.Action)}">${t.Action}</span>
                            </div>
                            <div class="stock-price-box">
                                <span style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 2px;">Giá hiện tại</span>
                                <span class="stock-price">${formatPrice(t.Price)}</span>
                                <span class="stock-vol">Vol: ${formatVolume(t.Volume)}</span>
                            </div>
                        </div>
                        <div class="divider-h"></div>
                        <div class="detail-metric-list">
                            <div class="detail-metric-row">
                                <span>Điểm mua gợi ý:</span>
                                <strong>${formatPrice(t.Entry)}</strong>
                            </div>
                            <div class="detail-metric-row">
                                <span>Mục tiêu chốt lời (Target 1):</span>
                                <strong class="text-green">${formatPrice(t.Target)}</strong>
                            </div>
                            ${t.Target2 ? `
                            <div class="detail-metric-row">
                                <span>Mục tiêu chốt lời (Target 2):</span>
                                <strong class="text-green">${formatPrice(t.Target2)}</strong>
                            </div>
                            ` : ''}
                            <div class="detail-metric-row">
                                <span>Cắt lỗ (Bán một phần):</span>
                                <strong class="text-red">${formatPrice(t.StopLoss)}</strong>
                            </div>
                            <div class="detail-metric-row">
                                <span>Cắt lỗ (Toàn bộ):</span>
                                <strong class="text-red">${formatPrice(t.CutlossFull)}</strong>
                            </div>
                            <div class="detail-metric-row">
                                <span>Chặn lãi (Trailing Stop):</span>
                                <strong class="text-orange">${formatPrice(t.TrailingStop)}</strong>
                            </div>
                            <div class="detail-metric-row">
                                <span>Tỷ lệ Risk/Reward:</span>
                                <strong>${t.RR}</strong>
                            </div>
                            <div class="detail-metric-row">
                                <span>Đánh giá Rủi ro:</span>
                                <span class="risk-badge">
                                    <span class="risk-dot ${riskClass}"></span>
                                    <strong>${t.RiskScore}/100 (${t.RiskPct.toFixed(1)}%)</strong>
                                </span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- BLOCK 2: Chẩn đoán Kỹ thuật -->
                    <div class="card block-card">
                        <h3 class="card-title">🔍 Chẩn đoán Kỹ thuật (M15-Day)</h3>
                        <table class="diag-table">
                            <thead>
                                <tr>
                                    <th>Công cụ/Chỉ báo</th>
                                    <th>Trạng thái</th>
                                    <th>Khuyến nghị</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr class="${t.Diagnostics.ma.status.toLowerCase().includes('bull') || t.Diagnostics.ma.action.toLowerCase().includes('buy') ? 'bullish' : t.Diagnostics.ma.status.toLowerCase().includes('bear') || t.Diagnostics.ma.action.toLowerCase().includes('sell') ? 'bearish' : ''}">
                                    <td>Hệ thống MA Lines</td>
                                    <td>${t.Diagnostics.ma.status}</td>
                                    <td>${t.Diagnostics.ma.action}</td>
                                </tr>
                                <tr class="${t.Diagnostics.ichimoku.status.toLowerCase().includes('bull') || t.Diagnostics.ichimoku.action.toLowerCase().includes('buy') ? 'bullish' : t.Diagnostics.ichimoku.status.toLowerCase().includes('bear') || t.Diagnostics.ichimoku.action.toLowerCase().includes('sell') ? 'bearish' : ''}">
                                    <td>Ichimoku Cloud</td>
                                    <td>${t.Diagnostics.ichimoku.status}</td>
                                    <td>${t.Diagnostics.ichimoku.action}</td>
                                </tr>
                                <tr class="${t.Diagnostics.rsi.status.toLowerCase().includes('bull') || t.Diagnostics.rsi.action.toLowerCase().includes('buy') ? 'bullish' : t.Diagnostics.rsi.status.toLowerCase().includes('bear') || t.Diagnostics.rsi.action.toLowerCase().includes('sell') ? 'bearish' : ''}">
                                    <td>Chỉ số Sức mạnh RSI</td>
                                    <td>${t.Diagnostics.rsi.status}</td>
                                    <td>${t.Diagnostics.rsi.action}</td>
                                </tr>
                                <tr class="${t.Diagnostics.macd.status.toLowerCase().includes('bull') || t.Diagnostics.macd.action.toLowerCase().includes('buy') ? 'bullish' : t.Diagnostics.macd.status.toLowerCase().includes('bear') || t.Diagnostics.macd.action.toLowerCase().includes('sell') ? 'bearish' : ''}">
                                    <td>Động lượng MACD</td>
                                    <td>${t.Diagnostics.macd.status}</td>
                                    <td>${t.Diagnostics.macd.action}</td>
                                </tr>
                                <tr class="${t.Diagnostics.adx.status.toLowerCase().includes('bull') || t.Diagnostics.adx.action.toLowerCase().includes('buy') ? 'bullish' : t.Diagnostics.adx.status.toLowerCase().includes('bear') || t.Diagnostics.adx.action.toLowerCase().includes('sell') ? 'bearish' : ''}">
                                    <td>Sức mạnh ADX</td>
                                    <td>${t.Diagnostics.adx.status}</td>
                                    <td>${t.Diagnostics.adx.action}</td>
                                </tr>
                                <tr class="${vsaClass}">
                                    <td>Dòng tiền VSA</td>
                                    <td>${vsaStatusText}</td>
                                    <td>${vsaActionText}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    <!-- BLOCK 3: Định giá & Nền tích lũy -->
                    <div class="card block-card">
                        <h3 class="card-title">🎯 Đánh giá Nền tích lũy & Định giá</h3>
                        <div class="eval-metrics">
                            <div class="eval-score-container">
                                <div class="eval-score-label">Điểm số Cơ Hội</div>
                                <div class="eval-score-value">${t.OpportunityScore}<span>/100</span></div>
                                <div class="eval-score-desc">${t.OpportunityDesc}</div>
                            </div>
                            <div class="divider-h"></div>
                            <div class="eval-row-detail">
                                <div class="detail-metric-row">
                                    <span>Độ an toàn nền:</span>
                                    <strong>${t.SafetyRating}/5</strong>
                                </div>
                                <div class="detail-metric-row">
                                    <span>Điểm mua gia tăng:</span>
                                    <strong>${formatPrice(t.TopupPrice)}</strong>
                                </div>
                                <div class="detail-metric-row">
                                    <span>Khuyến nghị gia tăng:</span>
                                    <span style="text-align: right; max-width: 60%;">${t.TopupDesc}</span>
                                </div>
                                <div class="detail-metric-row">
                                    <span>Chất lượng nền tích lũy:</span>
                                    <strong class="badge-text">${t.AccumulationQuality}</strong>
                                </div>
                                <div class="detail-metric-row">
                                    <span>Biên độ biến động nền:</span>
                                    <strong>${t.AccumulationRangePct.toFixed(1)}%</strong>
                                </div>
                                <div class="detail-metric-row">
                                    <span>Trạng thái nén chặt nền:</span>
                                    <strong class="${accumClass}">${t.ReadyToBreak ? 'CÓ (Chờ bùng nổ)' : 'CHƯA'}</strong>
                                </div>
                            </div>
                            ${t.AccumulationNotes && t.AccumulationNotes.length > 0 ? `
                                <div class="accum-notes-box">
                                    <strong>Ghi chú tích lũy:</strong>
                                    <ul>
                                        ${t.AccumulationNotes.map(n => `<li>${n}</li>`).join('')}
                                    </ul>
                                </div>
                            ` : ''}
                        </div>
                    </div>

                    <!-- BLOCK 4: Dòng tiền tạo lập MCDX & Xu hướng -->
                    <div class="card block-card">
                        <h3 class="card-title">📊 Dòng tiền MCDX & Đồ thị Lịch sử</h3>
                        <div class="mcdx-section">
                            <div class="mcdx-bar-labels">
                                <span class="text-red">Tạo lập (Bankers): ${t.MCDX.banker_pct}%</span>
                                <span class="text-yellow">Dòng tiền nóng: ${t.MCDX.hot_pct}%</span>
                                <span class="text-green">Nhỏ lẻ: ${t.MCDX.retailer_pct}%</span>
                            </div>
                            <div class="mcdx-bar-container">
                                <div class="mcdx-segment banker" style="width: ${t.MCDX.banker_pct}%"></div>
                                <div class="mcdx-segment hot" style="width: ${t.MCDX.hot_pct}%"></div>
                                <div class="mcdx-segment retailer" style="width: ${t.MCDX.retailer_pct}%"></div>
                            </div>
                            <div class="mcdx-eval-text">
                                <div><strong>Trạng thái dòng tiền:</strong> ${t.MCDX.status}</div>
                                <div><strong>Khuyến nghị MCDX:</strong> ${t.MCDX.action}</div>
                                <div class="text-secondary" style="font-size: 0.75rem; margin-top: 4px;">${t.MCDX.details}</div>
                            </div>
                        </div>
                        <div class="divider-h"></div>
                        <div class="mini-chart-section">
                            <strong style="font-size: 0.85rem;">Đồ thị Xu hướng Giá & Khối lượng (30 ngày gần nhất)</strong>
                            <div class="mini-chart-container">
                                <canvas id="${containerId}-miniChart"></canvas>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- BLOCK 5: Báo cáo Phân tích Chi tiết từ AI -->
                ${t.ReportText ? `
                <div class="card block-card" style="margin-top: 16px;">
                    <h3 class="card-title">📝 Báo cáo Phân tích Chi tiết từ AI</h3>
                    <div class="divider-h" style="margin: 12px 0;"></div>
                    <pre style="padding: 16px; border-radius: 8px; background: rgba(0, 0, 0, 0.22); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; white-space: pre-wrap; font-size: 0.85rem; line-height: 1.6; color: var(--text-primary); border: 1px solid var(--border-color); max-height: 500px; overflow-y: auto;">${t.ReportText}</pre>
                </div>
                ` : ''}

                <!-- 4-Panel Interactive Chart Grid -->
                <section class="card interactive-chart-section" style="margin-top: 20px;">
                    <div class="chart-panel-header">
                        <span class="chart-panel-title">📈 Biểu đồ Phân tích ${t.Ticker}</span>
                        <span class="chart-hint"><span>🖥️ Cuộn zoom · Kéo pan · ⛶ Toàn màn hình</span></span>
                    </div>
                    <div class="chart-grid-4" id="${containerId}-chartGrid" data-ticker="${t.Ticker}">
                        <div class="chart-cell">
                            <div class="chart-cell-header">
                                <span class="chart-cell-label">🌿 GP + Octopus</span>
                                <button class="chart-expand-btn" onclick="expandChart('${containerId}','gp')">⛶ Mở rộng</button>
                            </div>
                            <div class="chart-cell-body" id="${containerId}-mount-gp"></div>
                            <div class="chart-cell-evaluation" id="${containerId}-eval-gp"></div>
                            <div class="chart-cell-footer">
                                💡 <strong>Ý nghĩa:</strong> Hệ thống GreenPink kết hợp với Octopus giúp xác định động lượng dòng tiền lớn (Banker/Hot Money) và các điểm đảo chiều sớm của xu hướng giá thông qua hai đường xFast/xSlow.
                            </div>
                        </div>
                        <div class="chart-cell">
                            <div class="chart-cell-header">
                                <span class="chart-cell-label">🕯️ Heikin + 2Trend</span>
                                <button class="chart-expand-btn" onclick="expandChart('${containerId}','heikin')">⛶ Mở rộng</button>
                            </div>
                            <div class="chart-cell-body" id="${containerId}-mount-heikin"></div>
                            <div class="chart-cell-evaluation" id="${containerId}-eval-heikin"></div>
                            <div class="chart-cell-footer">
                                💡 <strong>Ý nghĩa:</strong> Sử dụng nến Heikin-Ashi để làm mịn xu hướng giá kết hợp dải Hull MA và chỉ báo NW Stop, giúp loại bỏ nhiễu ngắn hạn và xác định điểm mua/bán (Buy/Sell) mạnh mẽ.
                            </div>
                        </div>
                        <div class="chart-cell">
                            <div class="chart-cell-header">
                                <span class="chart-cell-label">🔥 Heatmap</span>
                                <button class="chart-expand-btn" onclick="expandChart('${containerId}','heatmap')">⛶ Mở rộng</button>
                            </div>
                            <div class="chart-cell-body" id="${containerId}-mount-heatmap"></div>
                            <div class="chart-cell-evaluation" id="${containerId}-eval-heatmap"></div>
                            <div class="chart-cell-footer">
                                💡 <strong>Ý nghĩa:</strong> Bản đồ nhiệt (Heatmap Bands) theo dõi các vùng cung cầu và phân phối giá của cổ phiếu, kết hợp Money Flow giúp phát hiện dòng tiền âm thầm gom hàng hoặc rút lui.
                            </div>
                        </div>
                        <div class="chart-cell">
                            <div class="chart-cell-header" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                                <div style="display:flex; align-items:center; gap:8px;">
                                    <span class="chart-cell-label">📊 Kỹ thuật</span>
                                    \${getTechTogglesHtml()}
                                </div>
                                <button class="chart-expand-btn" onclick="expandChart('${containerId}','techreport')">⛶ Mở rộng</button>
                            </div>
                            <div class="chart-cell-body" id="${containerId}-mount-techreport"></div>
                            <div class="chart-cell-evaluation" id="${containerId}-eval-techreport"></div>
                            <div class="chart-cell-footer">
                                💡 <strong>Ý nghĩa:</strong> Tổng hợp các chỉ báo xu hướng và động lượng kinh điển bao gồm Ichimoku Cloud, hệ thống MA Lines (MA10/20/50), dòng tiền MCDX, sức mạnh xu hướng ADX và chỉ báo MACD.
                            </div>
                        </div>
                    </div>
                </section>
            `;

            // Render mini chart + all 4 interactive charts simultaneously
            setTimeout(() => {
                renderMiniTrendChart(t, `${containerId}-miniChart`);
                renderAll4Charts(containerId, t.Ticker);
            }, 100);
        }

        // Render mini stock chart (price + volume)
        function renderMiniTrendChart(t, canvasId) {
            const canvasEl = document.getElementById(canvasId);
            if (!canvasEl) return;
            const ctx = canvasEl.getContext('2d');
            const hist = t.History;
            if (!hist || !hist.dates) return;

            if (stockChartInstances[canvasId]) {
                stockChartInstances[canvasId].destroy();
            }

            stockChartInstances[canvasId] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: hist.dates,
                    datasets: [
                        {
                            label: 'Giá Đóng Cửa',
                            data: hist.closes,
                            borderColor: '#8b5cf6',
                            borderWidth: 2,
                            pointRadius: 1,
                            tension: 0.15,
                            yAxisID: 'yPrice',
                            fill: false
                        },
                        {
                            label: 'Khối lượng',
                            data: hist.volumes,
                            type: 'bar',
                            backgroundColor: 'rgba(20, 184, 166, 0.15)',
                            borderWidth: 0,
                            yAxisID: 'yVol'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            backgroundColor: 'rgba(13, 19, 33, 0.95)',
                            titleColor: '#f3f4f6',
                            bodyColor: '#d1d5db',
                            borderColor: 'rgba(255,255,255,0.08)',
                            borderWidth: 1
                        }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: {
                                color: '#6b7280',
                                font: { size: 8 },
                                maxTicksLimit: 5
                            }
                        },
                        yPrice: {
                            type: 'linear',
                            position: 'left',
                            grid: { color: 'rgba(255,255,255,0.03)' },
                            ticks: {
                                color: '#6b7280',
                                font: { size: 8 },
                                callback: val => formatPrice(val)
                            }
                        },
                        yVol: {
                            type: 'linear',
                            position: 'right',
                            grid: { display: false },
                            ticks: {
                                color: '#6b7280',
                                font: { size: 7 },
                                maxTicksLimit: 3,
                                callback: val => formatVolume(val)
                            }
                        }
                    }
                }
            });
        }

        // Popup Modal functions
        function showTickerDetails(ticker) {
            const tickerData = rawData.tickers_analysis.find(t => t.Ticker === ticker);
            if (tickerData) {
                renderStockDetails(tickerData, 'modalStockDetailsContainer');
                document.getElementById('tickerDetailsModal').style.display = 'block';
                document.body.style.overflow = 'hidden'; // Lock background scrolling
            }
        }
        
        function closeTickerDetailsModal() {
            document.getElementById('tickerDetailsModal').style.display = 'none';
            document.body.style.overflow = 'auto'; // Release background scroll
            
            // Destroy modal chart instance to save memory
            const canvasId = 'modalStockDetailsContainer-miniChart';
            if (stockChartInstances[canvasId]) {
                stockChartInstances[canvasId].destroy();
                delete stockChartInstances[canvasId];
            }
        }
        
        // Hide popup if clicking outside of the content block
        window.onclick = function(event) {
            const modal = document.getElementById('tickerDetailsModal');
            const dropdown = document.getElementById('lookupSuggestions');
            const menuContent = document.getElementById('menuContent');
            
            if (event.target === modal) {
                closeTickerDetailsModal();
            }
            // Auto hide search dropdown suggestions if clicking elsewhere
            if (event.target !== document.getElementById('lookupSearchInput')) {
                if (dropdown) dropdown.style.display = 'none';
            }
            // Auto hide menu dropdown if clicking elsewhere
            if (!event.target.closest('.menu-dropdown')) {
                if (menuContent) menuContent.classList.remove('show');
            }
            // Auto hide ticker autocomplete dropdowns in portfolio
            if (!event.target.classList.contains('ticker-input')) {
                document.querySelectorAll('.ticker-autocomplete-list').forEach(el => el.style.display = 'none');
            }
        }

        // Toggle checkbox state for Custom Filters
        function toggleFilterCheckbox(filterKey) {
            const row = document.getElementById(`row-${filterKey}`);
            const checkbox = row ? row.querySelector('input[type="checkbox"]') : null;
            if (!checkbox) return;
            
            if (checkbox.checked) {
                activeCustomFilters.add(filterKey);
                row.classList.add('checked-row');
            } else {
                activeCustomFilters.delete(filterKey);
                row.classList.remove('checked-row');
            }
            
            // Automatically apply filters immediately
            applyCustomFilters();
        }

        // Apply custom filters logically using AND matching
        function applyCustomFilters() {
            let list = [...rawData.tickers_analysis];

            // Logical AND across selected checkboxes
            if (activeCustomFilters.size > 0) {
                list = list.filter(t => {
                    for (const filterKey of activeCustomFilters) {
                        if (filterKey === 'VOL_AVG10_GT_100K') {
                            const val = t.AvgVolume10 !== undefined ? t.AvgVolume10 : 0;
                            if (val <= 100000) {
                                return false;
                            }
                        } else if (filterKey === 'ACTION_YES_GREEN') {
                            const a = (t.Action || '').toUpperCase();
                            if (!a.includes('CÂN NHẮC') && !a.includes('CAN NHAC')) {
                                return false;
                            }
                        } else if (filterKey === 'ACTION_YES_PURPLE') {
                            const a = (t.Action || '').toUpperCase();
                            if (!a.includes('RẤT NÊN') && !a.includes('ƯU TIÊN') && !a.includes('RAT NEN') && !a.includes('UU TIEN')) {
                                return false;
                            }
                        } else {
                            const allowedTickers = rawData.filtered_results[filterKey] || [];
                            if (!allowedTickers.includes(t.Ticker)) {
                                return false; // Does not satisfy all selected criteria
                            }
                        }
                    }
                    return true;
                });
            }

            // Sort: BUY action first, then WAIT, then SELL, then alphabetical ticker name
            list.sort((a, b) => {
                const actionMap = { 'BUY': 1, 'WAIT': 2, 'SELL': 3 };
                const actA = actionMap[a.Action] || 99;
                const actB = actionMap[b.Action] || 99;
                
                if (actA !== actB) return actA - actB;
                return a.Ticker.localeCompare(b.Ticker);
            });

            filteredTickersList = list;
            displayedCount = 0;
            document.getElementById('tickersGrid').innerHTML = '';
            
            const countLabel = document.getElementById('filterResultsCount');
            if (countLabel) {
                countLabel.innerText = `Tìm thấy ${filteredTickersList.length} cổ phiếu phù hợp.`;
            }

            loadMore();
        }

        // Render paginated card items inside screening grid
        function loadMore() {
            const grid = document.getElementById('tickersGrid');
            const loadMoreBtn = document.getElementById('loadMoreBtn');
            
            if (filteredTickersList.length === 0) {
                grid.innerHTML = `<div class="empty-state">Không tìm thấy cổ phiếu nào khớp điều kiện.</div>`;
                loadMoreBtn.style.display = 'none';
                return;
            }

            const nextBatchLimit = Math.min(displayedCount + PAGE_SIZE, filteredTickersList.length);
            
            for (let i = displayedCount; i < nextBatchLimit; i++) {
                const t = filteredTickersList[i];
                const labels = [];
                
                // Add categories
                t.Categories.forEach(cat => {
                    if (!['EARLY', 'ADD_1', 'ADD_2', 'STRONG'].includes(cat)) {
                        labels.push({ text: rawData.categories_meta[cat] || cat, isAlert: false });
                    }
                });
                
                // Add matched custom rules (Divergences)
                t.Rules.forEach(rule => {
                    if (rule.includes('DIVERGENCE')) {
                        const ruleLabel = rawData.rules_meta[rule] || rule;
                        labels.push({ text: ruleLabel.split(' (')[0], isAlert: true });
                    }
                });

                let riskClass = 'green';
                if (t.RiskScore >= 70) riskClass = 'red';
                else if (t.RiskScore >= 40) riskClass = 'orange';

                const card = document.createElement('div');
                card.className = 'ticker-card';
                card.style.cursor = 'pointer';
                card.onclick = () => showTickerDetails(t.Ticker);
                card.innerHTML = `
                    <div class="ticker-card-header">
                        <div class="ticker-symbol">${t.Ticker}</div>
                        <span class="action-badge ${getActionClass(t.Action)}">${t.Action}</span>
                    </div>

                    <div class="price-section">
                        <div class="price-val">${formatPrice(t.Price)}</div>
                        <div class="vol-val">Vol: ${formatVolume(t.Volume)}</div>
                    </div>

                    <div class="metric-row">
                        <div class="metric-item">
                            <span class="metric-label">Điểm Mua</span>
                            <span class="metric-value">${formatPrice(t.Entry)}</span>
                        </div>
                        <div class="metric-item">
                            <span class="metric-label">Mục Tiêu</span>
                            <span class="metric-value target">${formatPrice(t.Target)}${t.Target2 ? ' / ' + formatPrice(t.Target2) : ''}</span>
                        </div>
                        <div class="metric-item">
                            <span class="metric-label">Cắt Lỗ</span>
                            <span class="metric-value stop">${formatPrice(t.StopLoss)}</span>
                        </div>
                    </div>

                    <div class="extra-stats">
                        <span>Tỷ lệ R:R: <strong style="color: white">${t.RR}</strong></span>
                        <div class="risk-rating">
                            <span>Rủi ro:</span>
                            <span class="risk-dot ${riskClass}"></span>
                            <strong style="color: white">${t.RiskScore}/100</strong>
                        </div>
                    </div>

                    ${labels.length > 0 ? `
                        <div class="tags-container">
                            ${labels.map(l => `<span class="tag ${l.isAlert ? 'alert-tag' : ''}">${l.text}</span>`).join('')}
                        </div>
                    ` : ''}
                `;
                grid.appendChild(card);
            }

            displayedCount = nextBatchLimit;
            
            if (displayedCount < filteredTickersList.length) {
                loadMoreBtn.style.display = 'block';
            } else {
                loadMoreBtn.style.display = 'none';
            }
        }

        // ==========================================
        // SETTINGS MODAL LOGIC
        // ==========================================
        const ADMIN_PASS = '2307';
        let settingsUnlocked = false;

        document.getElementById('settingsBtn').addEventListener('click', () => {
            document.getElementById('settingsModal').classList.add('active');
            document.getElementById('settingsPassword').value = '';
            document.getElementById('settingsMsg').textContent = '';
            settingsUnlocked = false;
            document.getElementById('settingsContent').style.display = 'none';
            document.getElementById('settingsLocked').style.display = 'block';
        });

        function closeSettings() {
            document.getElementById('settingsModal').classList.remove('active');
        }

        function unlockSettings() {
            const pwd = document.getElementById('settingsPassword').value;
            if (pwd === ADMIN_PASS) {
                settingsUnlocked = true;
                document.getElementById('settingsContent').style.display = 'block';
                document.getElementById('settingsLocked').style.display = 'none';
                document.getElementById('settingsMsg').innerHTML = '<span style="color:var(--accent-green)">🔓 Đã mở khóa thành công!</span>';
            } else {
                document.getElementById('settingsMsg').innerHTML = '<span style="color:var(--accent-red)">❌ Mật khẩu không đúng</span>';
            }
        }

        function saveSettings() {
            if (!settingsUnlocked) return;
            const url = document.getElementById('settingsUrl').value.trim();
            if (!url) {
                document.getElementById('settingsMsg').innerHTML = '<span style="color:var(--accent-orange)">⚠️ Vui lòng nhập URL cURL</span>';
                return;
            }
            // Save to localStorage for persistence
            localStorage.setItem('aic_vietstock_curl', url);
            document.getElementById('settingsMsg').innerHTML = '<span style="color:var(--accent-green)">✅ Đã lưu URL vào bộ nhớ trình duyệt!<br><small>Hãy cập nhật config.json trên server/repo để áp dụng cho lần chạy headless tiếp theo.</small></span>';
        }

        // Close settings modal when clicking outside
        document.getElementById('settingsModal').addEventListener('click', (e) => {
            if (e.target === document.getElementById('settingsModal')) closeSettings();
        });

        // Load saved URL on settings open
        document.getElementById('settingsBtn').addEventListener('click', () => {
            const saved = localStorage.getItem('aic_vietstock_curl');
            if (saved) document.getElementById('settingsUrl').value = saved;
        });


        // ============================================================
        //   LIGHTWEIGHT CHARTS ENGINE v2
        //   4 charts shown simultaneously, free zoom/pan (TradingView style)
        //   All panes synced — scroll one, all follow
        // ============================================================

        // State
        const historyCache  = {};  // { ticker: rawData }
        const lwcInstances  = {};  // { mountId: [{chart,ro},...] }
        let   fsInstances   = [];  // chart instances inside fullscreen
        let   marketChartTicker = 'VNINDEX';

        // Labels for fullscreen title
        const CHART_LABELS = {
            gp:         '🌿 GreenPink + Octopus',
            heikin:     '🕯️ Heikin-Ashi + 2Trend',
            heatmap:    '🔥 Bản đồ nhiệt',
            techreport: '📊 Báo cáo Kỹ thuật'
        };

        // ── LWC base theme (TradingView dark) ──
        const LWC_THEME = {
            layout:    { background: { color: '#000000' }, textColor: '#7a8599' },
            grid:      { vertLines: { color: 'rgba(255,255,255,0.025)' },
                         horzLines: { color: 'rgba(255,255,255,0.04)'  } },
            crosshair: { mode: 1 },
            timeScale: { borderColor: 'rgba(255,255,255,0.08)',
                         timeVisible: true, secondsVisible: false,
                         fixLeftEdge: false, fixRightEdge: false,
                         minBarSpacing: 5 },
            rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
            // Mouse wheel = zoom in/out at current position (not pan to past)
            handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: { time: false, price: true } },
            handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false }
        };

        // ── Utility: date string → Unix seconds ──
        function d2ts(s) { return Math.floor(new Date(s + 'T00:00:00Z').getTime() / 1000); }

        // Helper to set chart range default to 90 days from the latest date
        function applyDefaultChartRange(chartObj, dates, days = 90) {
            if (!dates || dates.length === 0) return;
            if (days >= dates.length) {
                chartObj.timeScale().fitContent();
            } else {
                const fromIndex = Math.max(0, dates.length - days);
                const toIndex = dates.length - 1;
                const fromTs = d2ts(dates[fromIndex]);
                const toTs = d2ts(dates[toIndex]);
                chartObj.timeScale().setVisibleRange({
                    from: fromTs,
                    to: toTs
                });
            }
        }

        // ── Detect price scale: indices store raw points (>50), stocks store price/1000 ──
        function priceScale(data) {
            // Keep prices raw (stocks are already divided by 1000 in history JSON, indices are raw)
            return 1;
        }

        // ── Build OHLCV array from history data ──
        function ohlcv(data) {
            const sc = priceScale(data);
            const out = [];
            for (let i = 0; i < data.dates.length; i++) {
                const o = data.opens[i], c = data.closes[i],
                      h = data.highs[i], l = data.lows[i];
                if (!o || !c) continue;
                out.push({ time: d2ts(data.dates[i]),
                    open: o*sc, high: h*sc, low: l*sc, close: c*sc });
            }
            return out;
        }

        // ── Build line series data from a named column ──
        // defaultScale: 1000 for stocks (price/1000 units), auto-overridden for indices
        function lineData(data, col, defaultScale = 1000) {
            const out = [];
            if (!data[col]) return out;
            // For price-based indicators (MA, BB) use same scale as OHLCV
            // For oscillators (RS, OCT, ADX, MACD) defaultScale is passed as 1
            const sc = (defaultScale === 1000) ? priceScale(data) : defaultScale;
            for (let i = 0; i < data.dates.length; i++) {
                const v = data[col][i];
                if (v === null || v === undefined) continue;
                out.push({ time: d2ts(data.dates[i]), value: v * sc });
            }
            return out;
        }

        // ── Lazy-fetch per-ticker history JSON ──
        async function fetchHistory(ticker) {
            if (historyCache[ticker]) return historyCache[ticker];
            const r = await fetch(`./Output/history/${ticker}.json?t=` + new Date().getTime());
            if (!r.ok) throw new Error(`HTTP ${r.status} for ${ticker}`);
            historyCache[ticker] = await r.json();
            return historyCache[ticker];
        }

        // ── Show loading state in a cell ──
        function cellLoading(mountId, msg = 'Đang tải...') {
            const el = document.getElementById(mountId);
            if (el) el.innerHTML =
                `<div class="lwc-loading"><div class="lwc-spinner"></div><span>${msg}</span></div>`;
        }
        function cellError(mountId, msg) {
            const el = document.getElementById(mountId);
            if (el) el.innerHTML =
                `<div class="lwc-loading" style="color:#6b7280;font-size:0.75rem;text-align:center;padding:12px;">⚠️ ${msg}</div>`;
        }

        // ── Destroy all LWC instances in a mount ──
        function destroyMount(mountId) {
            (lwcInstances[mountId] || []).forEach(item => {
                try { item.ro && item.ro.disconnect(); } catch(e){}
                try { item.chart && item.chart.remove();  } catch(e){}
            });
            delete lwcInstances[mountId];
            const el = document.getElementById(mountId);
            if (el) el.innerHTML = '';
        }

        // ── Create a LWC chart inside a cell-body div ──
        function mkChart(hostEl, h, dates = null, extraOpts = {}) {
            hostEl.style.height = h + 'px';
            const chart = LightweightCharts.createChart(hostEl, {
                ...LWC_THEME, width: hostEl.clientWidth || 100, height: h, ...extraOpts
            });
            let rangeSet = false;
            const ro = new ResizeObserver(() => {
                const w = hostEl.clientWidth;
                if (w > 0) {
                    chart.resize(w, hostEl.offsetHeight || h);
                    if (dates && !rangeSet) {
                        rangeSet = true;
                        requestAnimationFrame(() => {
                            applyDefaultChartRange(chart, dates, 90);
                        });
                    }
                }
            });
            ro.observe(hostEl);
            return { chart, ro };
        }

        // ── Sync visible range across an array of charts ──
        function syncCharts(charts) {
            let busy = false;
            charts.forEach((c, i) => {
                c.timeScale().subscribeVisibleLogicalRangeChange(r => {
                    if (busy || !r) return;
                    busy = true;
                    charts.forEach((o, j) => {
                        if (j !== i) try { o.timeScale().setVisibleLogicalRange(r); } catch(e){}
                    });
                    busy = false;
                });
            });
        }

        // ── Attach resize observer shorthand ──
        function roAttach(chart, el) {
            const ro = new ResizeObserver(() =>
                chart.resize(el.clientWidth, el.offsetHeight || chart.options().height));
            ro.observe(el);
            return ro;
        }

        // ================================================================
        //  renderGPChart  — in a cell body div (mountId), returns primary chart
        // ================================================================
        function renderGPChart(mountId, data, instances) {
            const root = document.getElementById(mountId);
            if (!root) return null;
            root.innerHTML = ''; root.style.display = 'flex'; root.style.flexDirection = 'column';

            const h1 = 360, h2 = 120, h3 = 120;

            const d1 = document.createElement('div'); d1.style.cssText = `flex:none;height:${h1}px;`;
            const d2 = document.createElement('div'); d2.style.cssText = `flex:none;height:${h2}px;border-top:1px solid rgba(255,255,255,0.04);`;
            const d3 = document.createElement('div'); d3.style.cssText = `flex:none;height:${h3}px;border-top:1px solid rgba(255,255,255,0.04);`;
            root.append(d1, d2, d3);

            // Pane 1: Candles + GreenPink cloud + xFast/xSlow + BB
            const {chart: c1, ro: ro1} = mkChart(d1, h1, data.dates, { crosshair: { horzLine: { visible: false, labelVisible: false } } });
            instances.push({chart: c1, ro: ro1});

            // BB bands (behind everything)
            if (data.GP_BB_Top) c1.addLineSeries({color:'rgba(68,136,255,0.45)',lineWidth:1,lineStyle:2,priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'GP_BB_Top'));
            if (data.GP_BB_Bot) c1.addLineSeries({color:'rgba(68,136,255,0.45)',lineWidth:1,lineStyle:2,priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'GP_BB_Bot'));

            // GP Cloud: colored fill between xFast (green) and xSlow (red)
            if (data.GP_xFast && data.GP_xSlow) {
                const sc = priceScale(data);
                const gpBullish = [], gpBearish = [], gpMask = [];
                for (let i = 0; i < data.dates.length; i++) {
                    const f = data.GP_xFast[i], s = data.GP_xSlow[i];
                    if (f === null || s === null || f === undefined || s === undefined) continue;
                    const t = d2ts(data.dates[i]);
                    const top = Math.max(f, s) * sc;
                    const bot = Math.min(f, s) * sc;
                    if (f >= s) {
                        gpBullish.push({time: t, value: top});
                        gpBearish.push({time: t, value: null});
                    } else {
                        gpBullish.push({time: t, value: null});
                        gpBearish.push({time: t, value: top});
                    }
                    gpMask.push({time: t, value: bot});
                }
                c1.addAreaSeries({
                    topColor: 'rgba(0, 255, 0, 0.35)', bottomColor: 'rgba(0, 255, 0, 0.05)',
                    lineColor: '#00ff00', lineWidth: 2,
                    priceLineVisible: false, lastValueVisible: false, title: ''
                }).setData(gpBullish);
                c1.addAreaSeries({
                    topColor: 'rgba(255, 105, 180, 0.35)', bottomColor: 'rgba(255, 105, 180, 0.05)',
                    lineColor: '#ff69b4', lineWidth: 2,
                    priceLineVisible: false, lastValueVisible: false, title: ''
                }).setData(gpBearish);
                c1.addAreaSeries({
                    topColor: '#000000', bottomColor: '#000000',
                    lineColor: 'rgba(0,0,0,0)', lineWidth: 1, lineVisible: false,
                    priceLineVisible: false, lastValueVisible: false, title: ''
                }).setData(gpMask);
            } else {
                if (data.GP_xFast) c1.addLineSeries({color:'#00ff00',lineWidth:2,priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'GP_xFast'));
                if (data.GP_xSlow) c1.addLineSeries({color:'#ff69b4',lineWidth:2,priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'GP_xSlow'));
            }

            // Candles on top
            c1.addCandlestickSeries({
                upColor:'#00ff6a',downColor:'#ff3b3b',
                borderUpColor:'#00ff6a',borderDownColor:'#ff3b3b',
                wickUpColor:'#00ff6a',wickDownColor:'#ff3b3b',
                priceLineVisible: false, lastValueVisible: false
            }).setData(ohlcv(data));

            // Pane 2: Octopus (A1 histogram colored + B1 dashed)
            const {chart: c2, ro: ro2} = mkChart(d2, h2, null, { crosshair: { horzLine: { visible: false, labelVisible: false } } });
            instances.push({chart: c2, ro: ro2});
            if (data.OCT_A1) {
                const octData = data.dates.map((dt, i) => {
                    const v = data.OCT_A1[i];
                    if (v === null || v === undefined) return null;
                    const col = data.OCT_Color ? data.OCT_Color[i] : '#808080';
                    return { time: d2ts(dt), value: v, color: col };
                }).filter(Boolean);
                c2.addHistogramSeries({
                    priceLineVisible: false, lastValueVisible: true, title: ''
                }).setData(octData);
            }
            if (data.OCT_B1) c2.addLineSeries({color:'#a78bfa',lineWidth:1.5,lineStyle:2,priceLineVisible:false,lastValueVisible:true,title: ''}).setData(lineData(data,'OCT_B1',1));
            // zero baseline
            if (data.dates.length > 0) {
                c2.addLineSeries({color:'rgba(255,255,255,0.12)',lineWidth:1,priceLineVisible:false,lastValueVisible:false})
                  .setData([{time:d2ts(data.dates[0]),value:0},{time:d2ts(data.dates[data.dates.length-1]),value:0}]);
            }

            // Pane 3: RS13 / RS52
            const {chart: c3, ro: ro3} = mkChart(d3, h3, null, { crosshair: { horzLine: { visible: false, labelVisible: false } } });
            instances.push({chart: c3, ro: ro3});
            if (data.RS13) c3.addLineSeries({color:'#ffffff',lineWidth:1.5,title: '',priceLineVisible:false,lastValueVisible:true}).setData(lineData(data,'RS13',1));
            if (data.RS52) c3.addLineSeries({color:'#fbbf24',lineWidth:1.5,title: '',priceLineVisible:false,lastValueVisible:true}).setData(lineData(data,'RS52',1));
            // 50 reference
            if (data.dates.length > 0) {
                c3.addLineSeries({color:'rgba(239,68,68,0.4)',lineWidth:1,lineStyle:1,priceLineVisible:false,lastValueVisible:false})
                  .setData([{time:d2ts(data.dates[0]),value:50},{time:d2ts(data.dates[data.dates.length-1]),value:50}]);
            }

            syncCharts([c1,c2,c3]);
            applyDefaultChartRange(c1, data.dates, 90);
            return c1;
        }

        // ================================================================
        //  renderHeikinChart  — Heikin-Ashi + 2Trend
        // ================================================================
        function renderHeikinChart(mountId, data, instances) {
            const root = document.getElementById(mountId);
            if (!root) return null;
            root.innerHTML = ''; root.style.display = 'flex'; root.style.flexDirection = 'column';

            const h1 = 320, h2 = 280;
            const d1 = document.createElement('div'); d1.style.cssText = `flex:none;height:${h1}px;`;
            const d2 = document.createElement('div'); d2.style.cssText = `flex:none;height:${h2}px;border-top:1px solid rgba(255,255,255,0.04);`;
            root.append(d1, d2);

            // Pane 1: Heikin-Ashi candles + Hull + NW stop + TC trend + TC cloud
            const {chart: c1, ro: ro1} = mkChart(d1, h1, data.dates, { crosshair: { horzLine: { visible: false, labelVisible: false } } });
            instances.push({chart:c1,ro:ro1});

            // TC Cloud: fill between TC_Trend and TC_StopLine (like TrendColor PineScript cloud)
            if (data.TC_Trend && data.TC_StopLine) {
                const sc = priceScale(data);
                const tcCloudBull = [], tcCloudBear = [], tcMask = [];
                for (let i = 0; i < data.dates.length; i++) {
                    const tr = data.TC_Trend[i], sl = data.TC_StopLine[i];
                    if (tr === null || sl === null || tr === undefined || sl === undefined) continue;
                    const t = d2ts(data.dates[i]);
                    // T=1 means bullish (stopline below trend), T=-1 means bearish
                    const tcT = data.TC_T ? data.TC_T[i] : (tr > sl ? 1 : -1);
                    const top = Math.max(tr, sl) * sc;
                    const bot = Math.min(tr, sl) * sc;
                    if (tcT >= 0) {
                        tcCloudBull.push({time: t, value: top});
                        tcCloudBear.push({time: t, value: null});
                    } else {
                        tcCloudBull.push({time: t, value: null});
                        tcCloudBear.push({time: t, value: top});
                    }
                    tcMask.push({time: t, value: bot});
                }
                c1.addAreaSeries({
                    topColor: 'rgba(39,194,46,0.22)', bottomColor: 'rgba(39,194,46,0.01)',
                    lineColor: 'rgba(39,194,46,0.6)', lineWidth: 1.5,
                    priceLineVisible: false, title: ''
                }).setData(tcCloudBull);
                c1.addAreaSeries({
                    topColor: 'rgba(255,0,0,0.18)', bottomColor: 'rgba(255,0,0,0.01)',
                    lineColor: 'rgba(255,0,0,0.5)', lineWidth: 1.5,
                    priceLineVisible: false, title: ''
                }).setData(tcCloudBear);
                c1.addAreaSeries({
                    topColor: '#000000', bottomColor: '#000000',
                    lineColor: 'rgba(0,0,0,0)', lineWidth: 0,
                    priceLineVisible: false, lastValueVisible: false, title: ''
                }).setData(tcMask);
            } else if (data.TC_Trend) {
                c1.addLineSeries({color:'#f59e0b',lineWidth:2,title: ''}).setData(lineData(data,'TC_Trend'));
            }

            if (data.HK_Flower_Open && data.HK_Flower_Close) {
                const hk = c1.addCandlestickSeries({
                    upColor:'#00ff6a',downColor:'#ff3b3b',
                    borderUpColor:'#00ff6a',borderDownColor:'#ff3b3b',
                    wickUpColor:'#00ff6a',wickDownColor:'#ff3b3b'
                });
                const hkArr = [];
                const hkSc = priceScale(data);
                for (let i = 0; i < data.dates.length; i++) {
                    const ho = data.HK_Flower_Open[i], hc = data.HK_Flower_Close[i],
                          hh = data.HK_Flower_High[i], hl = data.HK_Flower_Low[i];
                    if (!ho||!hc) continue;
                    const col = data.HK_BarColor && data.HK_BarColor[i];
                    const clr = col==='brightGreen'?'#00ff6a':col==='red'?'#ff3b3b':'#ffffff';
                    hkArr.push({time:d2ts(data.dates[i]),
                        open:ho*hkSc,high:hh*hkSc,low:hl*hkSc,close:hc*hkSc,
                        color:clr,borderColor:clr,wickColor:clr});
                }
                hk.setData(hkArr);

                // Buy/sell markers on HK
                const markers = [];
                for (let i = 0; i < data.dates.length; i++) {
                    const isBuy = (data.HK_BuySignal && data.HK_BuySignal[i]) || (data.HK_BuyManh && data.HK_BuyManh[i]);
                    const isSell = (data.HK_SellSignal && data.HK_SellSignal[i]) || (data.HK_SellManh && data.HK_SellManh[i]);
                    if (isBuy) {
                        markers.push({time:d2ts(data.dates[i]),position:'belowBar',color:'#00ff6a',shape:'arrowUp',text:'B'});
                    }
                    if (isSell) {
                        markers.push({time:d2ts(data.dates[i]),position:'aboveBar',color:'#ff3b3b',shape:'arrowDown',text:'S'});
                    }
                }
                if (markers.length) hk.setMarkers(markers.sort((a,b)=>a.time-b.time));
            }
            if (data.HK_MHull) c1.addLineSeries({color:'rgba(0,255,106,0.45)',lineWidth:1,title: '',priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'HK_MHull'));
            if (data.HK_SHull) c1.addLineSeries({color:'rgba(255,59,59,0.45)',lineWidth:1,title: '',priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'HK_SHull'));
            if (data.HK_NW)    c1.addLineSeries({color:'#38bdf8',lineWidth:2,title: '',priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'HK_NW'));

            // Pane 2: Normal candles + 2Trend SMA (colored by trend state) + signals
            const {chart: c2, ro: ro2} = mkChart(d2, h2, null, { crosshair: { horzLine: { visible: false, labelVisible: false } } });
            instances.push({chart:c2,ro:ro2});
            const cs2 = c2.addCandlestickSeries({
                upColor:'#00ff6a',downColor:'#ff3b3b',
                borderUpColor:'#00ff6a',borderDownColor:'#ff3b3b',
                wickUpColor:'#00ff6a',wickDownColor:'#ff3b3b',
                priceLineVisible: false, lastValueVisible: false
            });
            cs2.setData(ohlcv(data));

            // 2Trend SMA with color per-bar based on trend state
            if (data.T2_SMA && data.T2_SMA_Trend) {
                const smaColorData = [];
                const sc2 = priceScale(data);
                for (let i = 0; i < data.dates.length; i++) {
                    const v = data.T2_SMA[i], s = data.T2_SMA_Trend[i];
                    if (v === null || v === undefined) continue;
                    smaColorData.push({time: d2ts(data.dates[i]), value: v * sc2,
                        color: s > 0 ? '#00ffaa' : s < 0 ? '#ff3b3b' : '#888888'});
                }
                c2.addLineSeries({lineWidth:2.5, title: '', priceLineVisible:false, lastValueVisible:false}).setData(smaColorData);
            } else if (data.T2_SMA) {
                c2.addLineSeries({color:'#00ffaa',lineWidth:3,title: '',priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'T2_SMA'));
            }
            if (data.T2_ST_Lower) c2.addLineSeries({color:'rgba(0,255,170,0.4)',lineWidth:1,lineStyle:2,priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'T2_ST_Lower'));
            if (data.T2_ST_Upper) c2.addLineSeries({color:'rgba(255,59,59,0.4)',lineWidth:1,lineStyle:2,priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'T2_ST_Upper'));

            // 2Trend Buy/Sell signal markers (crossover of trend_state through 0)
            if (data.T2_SMA_Trend && data.T2_SMA) {
                const t2Markers = [];
                const sc2m = priceScale(data);
                for (let i = 1; i < data.dates.length; i++) {
                    const prev = data.T2_SMA_Trend[i-1], curr = data.T2_SMA_Trend[i];
                    const smaV = data.T2_SMA[i];
                    if (prev === null || curr === null || smaV === null) continue;
                    // crossover: -1 or 0 → 1 = Buy
                    if (prev <= 0 && curr > 0) {
                        t2Markers.push({time: d2ts(data.dates[i]), position:'belowBar', color:'#00ffaa', shape:'triangleUp', text:'𝑳'});
                    }
                    // crossunder: 1 or 0 → -1 = Sell
                    if (prev >= 0 && curr < 0) {
                        t2Markers.push({time: d2ts(data.dates[i]), position:'aboveBar', color:'#ff3b3b', shape:'triangleDown', text:'𝑺'});
                    }
                }
                if (t2Markers.length) cs2.setMarkers(t2Markers.sort((a,b)=>a.time-b.time));
            }

            syncCharts([c1,c2]);
            applyDefaultChartRange(c1, data.dates, 90);
            return c1;
        }

        // ================================================================
        //  renderHeatmapChart  — Bản đồ nhiệt
        // ================================================================
        function renderHeatmapChart(mountId, data, instances) {
            const root = document.getElementById(mountId);
            if (!root) return null;
            root.innerHTML = ''; root.style.display = 'flex'; root.style.flexDirection = 'column';

            const h1 = 400, h2 = 200;
            const d1 = document.createElement('div'); d1.style.cssText = `flex:none;height:${h1}px;`;
            const d2 = document.createElement('div'); d2.style.cssText = `flex:none;height:${h2}px;border-top:1px solid rgba(255,255,255,0.04);`;
            root.append(d1, d2);

            // Pane 1: Heatmap bands + Flower candles
            const {chart: c1, ro: ro1} = mkChart(d1, h1, data.dates);
            instances.push({chart:c1,ro:ro1});

            [
                {col:'HM_Band_Hi',color:'rgba(0,255,106,0.45)'},
                {col:'HM_Band_KH',color:'rgba(34,211,238,0.45)'},
                {col:'HM_Band_KM',color:'rgba(251,191,36,0.45)'},
                {col:'HM_Band_KL',color:'rgba(249,115,22,0.45)'},
                {col:'HM_Band_Lo',color:'rgba(255,59,59,0.45)'},
            ].forEach(b => {
                if (data[b.col]) c1.addLineSeries({color:b.color,lineWidth:1,lineStyle:2}).setData(lineData(data,b.col));
            });

            if (data.HM_Flower_Open && data.HM_Flower_Close) {
                const fcs = c1.addCandlestickSeries({
                    upColor:'#ffffff',downColor:'#ff3b3b',
                    borderUpColor:'#ffffff',borderDownColor:'#ff3b3b',
                    wickUpColor:'#ffffff',wickDownColor:'#ff3b3b'
                });
                const fArr = [];
                const fSc = priceScale(data);
                for (let i = 0; i < data.dates.length; i++) {
                    const fo=data.HM_Flower_Open[i],fc=data.HM_Flower_Close[i],
                          fh=data.HM_Flower_High[i],fl=data.HM_Flower_Low[i];
                    if (!fo||!fc) continue;
                    const mf = data.HM_MoneyFlow&&data.HM_MoneyFlow[i];
                    const up = fc>=fo;
                    const clr = (up&&mf===1)?'#ffffff':(!up&&mf===-1)?'#ff3b3b':'#fbbf24';
                    fArr.push({time:d2ts(data.dates[i]),
                        open:fo*fSc,high:fh*fSc,low:fl*fSc,close:fc*fSc,
                        color:clr,borderColor:clr,wickColor:clr});
                }
                fcs.setData(fArr);
            }

            // Pane 2: Normal candles (reference)
            const {chart: c2, ro: ro2} = mkChart(d2, h2);
            instances.push({chart:c2,ro:ro2});
            c2.addCandlestickSeries({
                upColor:'#00ff6a',downColor:'#ff3b3b',
                borderUpColor:'#00ff6a',borderDownColor:'#ff3b3b',
                wickUpColor:'#00ff6a',wickDownColor:'#ff3b3b'
            }).setData(ohlcv(data));

            syncCharts([c1,c2]);
            applyDefaultChartRange(c1, data.dates, 90);
            return c1;
        }

        // ================================================================
        //  renderTechReportChart  — Candlestick+Ichimoku+MCDX+ADX+MACD
        // ================================================================
        function renderTechReportChart(mountId, data, instances) {
            const root = document.getElementById(mountId);
            if (!root) return null;
            root.innerHTML = ''; root.style.display = 'flex'; root.style.flexDirection = 'column';

            const h1 = 300, h2 = 100, h3 = 100, h4 = 100;
            const mk = (h, border=true) => {
                const d = document.createElement('div');
                d.style.cssText = `flex:none;height:${h}px;${border?'border-top:1px solid rgba(255,255,255,0.04);':''}`;
                root.appendChild(d); return d;
            };
            const d1 = mk(h1,false), d2 = mk(h2), d3 = mk(h3), d4 = mk(h4);

            // Pane 1: Candles + MA + Ichimoku
            const {chart: c1, ro: ro1} = mkChart(d1, h1, data.dates);
            instances.push({chart:c1,ro:ro1});

            // Initialize registry for this mount to manage line visibility toggles
            techReportSeriesRegistry[mountId] = {};

            // Ichimoku Kumo Cloud: colored fill between SpanA and SpanB (green when SpanA>SpanB, red otherwise)
            // Uses two area series (green cloud top, red cloud top) rendering cloud background
            if (data.SpanA && data.SpanB) {
                const sc = priceScale(data);
                const bullishCloud = [], bearishCloud = [], maskCloud = [];
                for (let i = 0; i < data.dates.length; i++) {
                    const a = data.SpanA[i], b = data.SpanB[i];
                    if (a === null || b === null || a === undefined || b === undefined) continue;
                    const t = d2ts(data.dates[i]);
                    const top = Math.max(a, b) * sc;
                    const bot = Math.min(a, b) * sc;
                    if (a >= b) {
                        bullishCloud.push({time: t, value: top});
                        bearishCloud.push({time: t, value: null});
                    } else {
                        bullishCloud.push({time: t, value: null});
                        bearishCloud.push({time: t, value: top});
                    }
                    maskCloud.push({time: t, value: bot});
                }
                const sKumoGreen = c1.addAreaSeries({
                    topColor: 'rgba(0,255,106,0.22)', bottomColor: 'rgba(0,255,106,0.01)',
                    lineColor: 'rgba(0,255,106,0.65)', lineWidth: 1.5,
                    title: '', visible: techChartVisibility.SpanA, priceLineVisible: false
                });
                sKumoGreen.setData(bullishCloud);
                techReportSeriesRegistry[mountId].SpanA = sKumoGreen;
                const sKumoRed = c1.addAreaSeries({
                    topColor: 'rgba(255,59,59,0.22)', bottomColor: 'rgba(255,59,59,0.01)',
                    lineColor: 'rgba(255,59,59,0.65)', lineWidth: 1.5,
                    title: '', visible: techChartVisibility.SpanB, priceLineVisible: false
                });
                sKumoRed.setData(bearishCloud);
                techReportSeriesRegistry[mountId].SpanB = sKumoRed;
                const sKumoMask = c1.addAreaSeries({
                    topColor: '#000000', bottomColor: '#000000',
                    lineColor: 'rgba(0,0,0,0)', lineWidth: 1, lineVisible: false,
                    title: '', visible: techChartVisibility.SpanA || techChartVisibility.SpanB, priceLineVisible: false, lastValueVisible: false
                });
                sKumoMask.setData(maskCloud);
            } else {
                if (data.SpanA) {
                    const sSpanA = c1.addLineSeries({color:'rgba(0,255,106,0.65)',lineWidth:2,title: '',visible:techChartVisibility.SpanA,priceLineVisible:false});
                    sSpanA.setData(lineData(data,'SpanA'));
                    techReportSeriesRegistry[mountId].SpanA = sSpanA;
                }
                if (data.SpanB) {
                    const sSpanB = c1.addLineSeries({color:'rgba(255,59,59,0.65)',lineWidth:2,title: '',visible:techChartVisibility.SpanB,priceLineVisible:false});
                    sSpanB.setData(lineData(data,'SpanB'));
                    techReportSeriesRegistry[mountId].SpanB = sSpanB;
                }
            }
            
            // Bright neon colors for other indicator lines (with priceLineVisible disabled to declutter)
            if (data.Tenkan) {
                const sTenkan = c1.addLineSeries({color:'#00d2ff',lineWidth:1.2,title: '',visible:techChartVisibility.Tenkan,priceLineVisible:false});
                sTenkan.setData(lineData(data,'Tenkan'));
                techReportSeriesRegistry[mountId].Tenkan = sTenkan;
            }
            if (data.Kijun) {
                const sKijun = c1.addLineSeries({color:'#ff2a5f',lineWidth:1.2,title: '',visible:techChartVisibility.Kijun,priceLineVisible:false});
                sKijun.setData(lineData(data,'Kijun'));
                techReportSeriesRegistry[mountId].Kijun = sKijun;
            }
            if (data.Kijun65) {
                const sKijun65 = c1.addLineSeries({color:'#ff9f00',lineWidth:1.5,lineStyle:2,title: '',visible:techChartVisibility.Kijun65,priceLineVisible:false});
                sKijun65.setData(lineData(data,'Kijun65'));
                techReportSeriesRegistry[mountId].Kijun65 = sKijun65;
            }

            if (data.MA10) {
                const sMA10 = c1.addLineSeries({color:'#ffffff',lineWidth:1.5,title: '',visible:techChartVisibility.MA10,priceLineVisible:false});
                sMA10.setData(lineData(data,'MA10'));
                techReportSeriesRegistry[mountId].MA10 = sMA10;
            }
            if (data.MA20) {
                const sMA20 = c1.addLineSeries({color:'#00f589',lineWidth:2,title: '',visible:techChartVisibility.MA20,priceLineVisible:false});
                sMA20.setData(lineData(data,'MA20'));
                techReportSeriesRegistry[mountId].MA20 = sMA20;
            }
            if (data.MA50) {
                const sMA50 = c1.addLineSeries({color:'#ffd700',lineWidth:2,title: '',visible:techChartVisibility.MA50,priceLineVisible:false});
                sMA50.setData(lineData(data,'MA50'));
                techReportSeriesRegistry[mountId].MA50 = sMA50;
            }

            c1.addCandlestickSeries({
                upColor:'#00ff6a',downColor:'#ff3b3b',
                borderUpColor:'#00ff6a',borderDownColor:'#ff3b3b',
                wickUpColor:'#00ff6a',wickDownColor:'#ff3b3b'
            }).setData(ohlcv(data));

            // Pane 2: MCDX Stacked Area Chart (Layered Retailer, Hot Money, Banker)
            const {chart: c2, ro: ro2} = mkChart(d2, h2);
            instances.push({chart:c2,ro:ro2});
            
            // Retailer (Green) constant 20
            const greenData = data.dates.map(dt => ({ time: d2ts(dt), value: 20.0 }));
            c2.addAreaSeries({
                topColor: 'rgba(52, 211, 153, 0.4)',
                bottomColor: 'rgba(52, 211, 153, 0.05)',
                lineColor: '#34d399',
                lineWidth: 1,
                priceLineVisible: false,
                title: ''
            }).setData(greenData);

            // Hot Money (Yellow)
            if (data.MCDX_HotMoney) {
                c2.addAreaSeries({
                    topColor: 'rgba(251, 191, 36, 0.65)',
                    bottomColor: 'rgba(251, 191, 36, 0.1)',
                    lineColor: '#fbbf24',
                    lineWidth: 1,
                    priceLineVisible: false,
                    title: ''
                }).setData(lineData(data, 'MCDX_HotMoney', 1));
            }

            // Banker (Red)
            if (data.MCDX_Banker) {
                c2.addAreaSeries({
                    topColor: 'rgba(244, 63, 94, 0.85)',
                    bottomColor: 'rgba(244, 63, 94, 0.2)',
                    lineColor: '#f43f5e',
                    lineWidth: 1,
                    priceLineVisible: false,
                    title: ''
                }).setData(lineData(data, 'MCDX_Banker', 1));
            }

            // Banker MA (White/Gray)
            if (data.MCDX_Banker_MA) {
                c2.addLineSeries({
                    color: '#ffffff',
                    lineWidth: 1.5,
                    priceLineVisible: false,
                    title: ''
                }).setData(lineData(data, 'MCDX_Banker_MA', 1));
            }

            c2.priceScale('right').applyOptions({
                scaleMargins: {
                    top: 0,
                    bottom: 0,
                },
            });

            // Pane 3: ADX with Dynamic Color Segments
            const {chart: c3, ro: ro3} = mkChart(d3, h3);
            instances.push({chart:c3,ro:ro3});
            
            if (data.ADX) {
                const adxData = [];
                for (let i = 0; i < data.dates.length; i++) {
                    const dt = data.dates[i];
                    const val = data.ADX[i];
                    if (val === null || val === undefined) continue;
                    
                    const prevVal = i > 0 ? data.ADX[i-1] : null;
                    const diPlus = data.DI_Plus ? data.DI_Plus[i] : 0;
                    const diMinus = data.DI_Minus ? data.DI_Minus[i] : 0;
                    
                    let color = '#c084fc'; // Default purple
                    if (val <= 20) {
                        color = '#eab308'; // Orange for Range
                    } else if (diPlus >= diMinus) {
                        if (prevVal !== null && val < prevVal) {
                            color = '#00ff6a'; // Green if falling
                        } else {
                            color = '#ffffff'; // White if rising
                        }
                    } else {
                        color = '#ef4444'; // Red if DI- > DI+
                    }
                    
                    adxData.push({
                        time: d2ts(dt),
                        value: val,
                        color: color
                    });
                }
                c3.addLineSeries({
                    lineWidth: 4,
                    title: '',
                    priceLineVisible: false
                }).setData(adxData);
            }
            if (data.DI_Plus) c3.addLineSeries({color:'#34d399',lineWidth:1.5,title: '',priceLineVisible:false}).setData(lineData(data,'DI_Plus',1));
            if (data.DI_Minus)c3.addLineSeries({color:'#f87171',lineWidth:1.5,title: '',priceLineVisible:false}).setData(lineData(data,'DI_Minus',1));
            if (data.dates.length > 0)
                c3.addLineSeries({color:'rgba(255,255,255,0.18)',lineWidth:1,lineStyle:1,priceLineVisible:false})
                  .setData([{time:d2ts(data.dates[0]),value:25},{time:d2ts(data.dates[data.dates.length-1]),value:25}]);

            // Pane 4: MACD
            const {chart: c4, ro: ro4} = mkChart(d4, h4);
            instances.push({chart:c4,ro:ro4});
            if (data.MACD_Hist) {
                const hArr = data.dates.map((dt,i) => {
                    const v = data.MACD_Hist[i];
                    if (v===null||v===undefined) return null;
                    return {time:d2ts(dt), value:v,
                        color: v>=0?'rgba(52,211,153,0.7)':'rgba(248,113,113,0.7)'};
                }).filter(Boolean);
                c4.addHistogramSeries({priceLineVisible:false,title: ''}).setData(hArr);
            }
            if (data.MACD)        c4.addLineSeries({color:'#60a5fa',lineWidth:1.5,title: '',priceLineVisible:false}).setData(lineData(data,'MACD',1));
            if (data.MACD_Signal) c4.addLineSeries({color:'#fb923c',lineWidth:1.5,title: '',priceLineVisible:false}).setData(lineData(data,'MACD_Signal',1));

            syncCharts([c1,c2,c3,c4]);
            applyDefaultChartRange(c1, data.dates, 90);
            return c1;
        }

        // ================================================================
        //  renderAll4Charts  — render all 4 simultaneously in a grid prefix
        //  mountPrefix: e.g. 'market' → ids: marketMount-gp, marketMount-heikin ...
        //               or a containerId like 'stockDetailsDashboard'
        // ================================================================
        async function renderAll4Charts(mountPrefix, ticker) {
            const ids = ['gp','heikin','heatmap','techreport'];
            const renders = {
                gp: renderGPChart, heikin: renderHeikinChart,
                heatmap: renderHeatmapChart, techreport: renderTechReportChart
            };

            // Show loading in all cells
            ids.forEach(type => {
                const mid = `${mountPrefix}-mount-${type}`;
                destroyMount(mid);
                cellLoading(mid, `Tải ${ticker}...`);
            });

            let data;
            try { data = await fetchHistory(ticker); }
            catch(e) {
                ids.forEach(type => cellError(`${mountPrefix}-mount-${type}`,
                    `Chưa có dữ liệu ${ticker}. Hãy chạy Actions để tạo Output/history/${ticker}.json`));
                return;
            }

            // Render each chart and collect primary chart instances for cross-sync
            const primaryCharts = [];
            ids.forEach(type => {
                const mid = `${mountPrefix}-mount-${type}`;
                const inst = [];
                lwcInstances[mid] = inst;
                const primary = renders[type](mid, data, inst);
                if (primary) primaryCharts.push(primary);
            });

            // Cross-chart time-scale sync (all 4 primary panes scroll together)
            syncCharts(primaryCharts);

            // Update evaluations for each chart cell
            updateChartEvaluations(mountPrefix, ticker);
        }

        // ── Helper to determine evaluation badge color and content ──
        function getEvalBadge(status) {
            if (!status) return '';
            const s = status.toLowerCase();
            let cls = 'neutral';
            let label = status;
            if (s.includes('bull') || s.includes('uptrend') || s.includes('buy') || s.includes('tăng') || s.includes('tích cực') || s.includes('mạnh')) {
                cls = 'bullish';
            } else if (s.includes('bear') || s.includes('downtrend') || s.includes('sell') || s.includes('giảm') || s.includes('tiêu cực') || s.includes('yếu')) {
                cls = 'bearish';
            }
            return `<span class="eval-badge-inline ${cls}">${label}</span>`;
        }

        // ── Populate dynamic evaluations for each chart cell ──
        function updateChartEvaluations(mountPrefix, ticker) {
            const isMarket = mountPrefix === 'market';
            const ids = ['gp', 'heikin', 'heatmap', 'techreport'];

            let indexData = null;
            let stockData = null;
            if (isMarket) {
                indexData = rawData.market_indices ? rawData.market_indices[ticker] : null;
            } else {
                stockData = rawData.tickers_analysis.find(t => t.Ticker === ticker);
            }

            ids.forEach(type => {
                const evalEl = document.getElementById(`${mountPrefix}-eval-${type}`);
                if (!evalEl) return;

                let html = '';
                if (isMarket) {
                    if (!indexData) {
                        evalEl.innerHTML = '<div>Chưa có dữ liệu đánh giá</div>';
                        return;
                    }
                    const diag = indexData.diagnostics || {};
                    const sr = indexData.support_resistance || { s1: 0, s2: 0, r1: 0, r2: 0 };
                    const stateRules = indexData.state_rules || {};
                    const mcdx = indexData.mcdx_eval || {};
                    
                    if (type === 'gp') {
                        html = `
                            <div class="eval-title">🎯 Đánh giá Động lượng Dòng tiền (GreenPink + Octopus)</div>
                            <div class="eval-row"><span>Xu hướng chính:</span> <strong>${indexData.regime} ${getEvalBadge(indexData.regime)}</strong></div>
                            <div class="eval-row"><span>Tín hiệu Robot:</span> <strong>${stateRules.signal || 'N/A'} (Độ tin cậy: ${stateRules.confidence || 'N/A'})</strong></div>
                            <div class="eval-row"><span>Tránh mua (Avoid Entry):</span> <strong>${stateRules.avoid_entry ? 'CÓ' : 'KHÔNG'} ${getEvalBadge(stateRules.avoid_entry ? 'Rủi ro cao' : 'An toàn')}</strong></div>
                            <div class="eval-row"><span>Bùng nổ theo đà (FTD):</span> <strong>${indexData.ftd_active ? `CÓ (Ngày ${indexData.ftd_date})` : 'CHƯA'} ${getEvalBadge(indexData.ftd_active ? 'Tích cực' : 'Trung lập')}</strong></div>
                            <div class="eval-row"><span>Số ngày phân phối:</span> <strong class="${indexData.distribution_count >= 4 ? 'text-red' : 'text-primary'}">${indexData.distribution_count} ngày ${getEvalBadge(indexData.distribution_count >= 4 ? 'Rủi ro cao' : 'An toàn')}</strong></div>
                        `;
                    } else if (type === 'heikin') {
                        html = `
                            <div class="eval-title">🎯 Đánh giá Xu hướng Giá (Heikin-Ashi & MA Lines)</div>
                            <div class="eval-row"><span>Xu hướng nến mịn Heikin-Ashi:</span> <strong>${indexData.regime} ${getEvalBadge(indexData.regime)}</strong></div>
                            <div class="eval-row"><span>Chẩn đoán hệ thống MA Lines:</span> <strong>${diag.ma?.status || 'N/A'} ${getEvalBadge(diag.ma?.status)}</strong></div>
                            <div class="eval-row"><span>Hành động đề xuất (MA):</span> <strong>${diag.ma?.action || 'N/A'}</strong></div>
                            <div class="eval-row"><span>Khoảng cách MA20 / ADX:</span> <strong>${stateRules.dist_ma20 !== undefined ? parseFloat(stateRules.dist_ma20).toFixed(1) + '%' : 'N/A'} / ${stateRules.adx !== undefined ? parseFloat(stateRules.adx).toFixed(1) : 'N/A'}</strong></div>
                        `;
                    } else if (type === 'heatmap') {
                        html = `
                            <div class="eval-title">🎯 Phân tích Vùng Cung Cầu & Cản (Heatmap)</div>
                            <div class="eval-row"><span>Trạng thái Vùng cung cầu (Heatmap):</span> <strong>${indexData.heatmap_eval || 'N/A'} ${getEvalBadge(indexData.heatmap_eval)}</strong></div>
                            <div class="eval-row"><span>Vùng Hỗ trợ gần nhất:</span> <strong>S1: ${formatPrice(sr.s1, true)} | S2: ${formatPrice(sr.s2, true)}</strong></div>
                            <div class="eval-row"><span>Vùng Kháng cự gần nhất:</span> <strong>R1: ${formatPrice(sr.r1, true)} | R2: ${formatPrice(sr.r2, true)}</strong></div>
                            <div class="eval-row"><span>Chiến lược Phân bổ Vốn:</span> <strong>Tối đa ${indexData.alloc} CP</strong></div>
                        `;
                    } else if (type === 'techreport') {
                        html = `
                            <div class="eval-title">🎯 Tổng hợp Báo cáo Kỹ thuật đa chỉ báo (Tech Report)</div>
                            <div class="eval-row"><span>Ichimoku Cloud:</span> <strong>${diag.ichimoku?.status || 'N/A'} ${getEvalBadge(diag.ichimoku?.status)}</strong></div>
                            <div class="eval-row"><span>Dòng tiền Tạo lập (MCDX):</span> <strong>${mcdx.status || 'N/A'} ${getEvalBadge(mcdx.status)}</strong></div>
                            <div class="eval-row"><span>Chi tiết MCDX:</span> <strong>Banker: ${mcdx.banker_pct !== undefined ? parseFloat(mcdx.banker_pct).toFixed(1) + '%' : '0.0%'} | Hot: ${mcdx.hot_pct !== undefined ? parseFloat(mcdx.hot_pct).toFixed(1) + '%' : '0.0%'} | Nhỏ lẻ: ${mcdx.retailer_pct !== undefined ? parseFloat(mcdx.retailer_pct).toFixed(1) + '%' : '0.0%'}</strong></div>
                            <div class="eval-row"><span>Động lượng RSI / MACD:</span> <strong>RSI: ${diag.rsi?.status || 'N/A'} | MACD: ${diag.macd?.status || 'N/A'} (Hist: ${stateRules.macd_hist !== undefined ? parseFloat(stateRules.macd_hist).toFixed(1) : 'N/A'})</strong></div>
                        `;
                    }
                } else {
                    if (!stockData) {
                        evalEl.innerHTML = '<div>Chưa có dữ liệu đánh giá cổ phiếu</div>';
                        return;
                    }
                    const diag = stockData.Diagnostics || {};
                    const mcdx = stockData.MCDX || {};

                    if (type === 'gp') {
                        html = `
                            <div class="eval-title">🎯 Đánh giá Động lượng Dòng tiền (GreenPink + Octopus)</div>
                            <div class="eval-row"><span>Dòng tiền VSA:</span> <strong>${diag.vsa?.status || 'N/A'} ${getEvalBadge(diag.vsa?.status)}</strong></div>
                            <div class="eval-row"><span>Hành động dòng tiền (VSA):</span> <strong>${diag.vsa?.action || 'N/A'}</strong></div>
                            <div class="eval-row"><span>Điểm số Cơ Hội (Opportunity):</span> <strong>${stockData.OpportunityScore}/10 (${stockData.OpportunityDesc})</strong></div>
                        `;
                    } else if (type === 'heikin') {
                        html = `
                            <div class="eval-title">🎯 Đánh giá Xu hướng Giá (Heikin-Ashi & Breakout)</div>
                            <div class="eval-row"><span>Hệ thống MA Lines:</span> <strong>${diag.ma?.status || 'N/A'} ${getEvalBadge(diag.ma?.status)}</strong></div>
                            <div class="eval-row"><span>Mức nén chặt nền:</span> <strong>${stockData.ReadyToBreak ? 'CÓ (Chờ bùng nổ)' : 'CHƯA'} ${getEvalBadge(stockData.ReadyToBreak ? 'Tích cực' : 'Trung lập')}</strong></div>
                            <div class="eval-row"><span>Gợi ý Hành động:</span> <strong>${diag.ma?.action || 'N/A'}</strong></div>
                        `;
                    } else if (type === 'heatmap') {
                        html = `
                            <div class="eval-title">🎯 Đánh giá Vùng Tích Lũy & Định Giá (Heatmap)</div>
                            <div class="eval-row"><span>Chất lượng Nền tích lũy:</span> <strong>${stockData.AccumulationQuality} ${getEvalBadge(stockData.AccumulationQuality)}</strong></div>
                            <div class="eval-row"><span>Biên tích lũy nền:</span> <strong>${stockData.AccumulationRangePct?.toFixed(1)}% (Độ an toàn: ${stockData.SafetyRating}/5 sao)</strong></div>
                            <div class="eval-row"><span>Vùng gợi ý:</span> <strong>Mua quanh: ${formatPrice(stockData.Entry)} | Mục tiêu: ${formatPrice(stockData.Target)} | Cắt lỗ: ${formatPrice(stockData.StopLoss)}</strong></div>
                        `;
                    } else if (type === 'techreport') {
                        html = `
                            <div class="eval-title">🎯 Tổng hợp Báo cáo Kỹ thuật đa chỉ báo (Tech Report)</div>
                            <div class="eval-row"><span>Ichimoku Cloud:</span> <strong>${diag.ichimoku?.status || 'N/A'} ${getEvalBadge(diag.ichimoku?.status)}</strong></div>
                            <div class="eval-row"><span>Dòng tiền Tạo lập (MCDX):</span> <strong>Banker: ${mcdx.banker_pct}% | Hot Money: ${mcdx.hot_pct}% | Nhỏ lẻ: ${mcdx.retailer_pct}%</strong></div>
                            <div class="eval-row"><span>Động lượng RSI / MACD:</span> <strong>RSI: ${diag.rsi?.status || 'N/A'} | MACD: ${diag.macd?.status || 'N/A'}</strong></div>
                            <div class="eval-row"><span>Động lượng ADX (Sức mạnh):</span> <strong>${diag.adx?.status || 'N/A'} ${getEvalBadge(diag.adx?.status)}</strong></div>
                        `;
                    }
                }
                evalEl.innerHTML = html;
            });
        }

        // ================================================================
        //  EXPAND / FULLSCREEN
        // ================================================================
        // Store current expand context for re-render on resize
        let _fsCtx = null;

        function expandChart(mountPrefix, chartType) {
            const modal = document.getElementById('chartFsModal');
            const title = document.getElementById('chartFsTitle');
            const fsMt  = document.getElementById('chartFsMount');
            if (!modal) return;

            // Resolve ticker from state
            let ticker;
            if (mountPrefix === 'market') {
                ticker = marketChartTicker;
            } else {
                // stock containerId → find ticker from history cache or element
                ticker = null;
                // Try to read from the chartGrid id stored on the grid element
                const grid = document.getElementById(`${mountPrefix}-chartGrid`);
                if (grid && grid.dataset.ticker) ticker = grid.dataset.ticker;
            }
            if (!ticker || !historyCache[ticker]) {
                alert('Dữ liệu chưa được tải. Hãy mở chart thường trước.'); return;
            }

            _fsCtx = { mountPrefix, chartType, ticker };
            title.textContent = `${CHART_LABELS[chartType] || chartType} — ${ticker}`;

            // Inject toggles if techreport is expanded
            const fsControls = document.getElementById('chartFsControls');
            if (fsControls) {
                if (chartType === 'techreport') {
                    fsControls.style.display = 'block';
                    fsControls.innerHTML = getTechTogglesHtml();
                } else {
                    fsControls.style.display = 'none';
                    fsControls.innerHTML = '';
                }
            }

            // Destroy previous FS instances
            fsInstances.forEach(it => { try{it.ro&&it.ro.disconnect();}catch(e){} try{it.chart&&it.chart.remove();}catch(e){} });
            fsInstances = [];
            fsMt.innerHTML = '';

            modal.classList.add('open');

            // Wait for modal to be visible, then render at full size
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    const renders = {
                        gp: renderGPChartFs, heikin: renderHeikinChartFs,
                        heatmap: renderHeatmapChartFs, techreport: renderTechReportChartFs
                    };
                    const fn = renders[chartType];
                    if (fn) fn('chartFsMount', historyCache[ticker], fsInstances);
                });
            });
        }

        function closeChartFullscreen() {
            document.getElementById('chartFsModal').classList.remove('open');
            const fsControls = document.getElementById('chartFsControls');
            if (fsControls) {
                fsControls.style.display = 'none';
                fsControls.innerHTML = '';
            }
            fsInstances.forEach(it => { try{it.ro&&it.ro.disconnect();}catch(e){} try{it.chart&&it.chart.remove();}catch(e){} });
            fsInstances = [];
            breadthChartFsInstance = null;
            document.getElementById('chartFsMount').innerHTML = '';
        }

        // ESC to close
        document.addEventListener('keydown', e => { if (e.key === 'Escape') closeChartFullscreen(); });

        // ── Fullscreen variants (larger heights) ──
        function renderGPChartFs(mountId, data, instances) {
            const root = document.getElementById(mountId);
            root.innerHTML = ''; root.style.display='flex'; root.style.flexDirection='column';
            const total = root.offsetHeight || window.innerHeight - 120;
            const h1=Math.round(total*0.55), h2=Math.round(total*0.225), h3=Math.round(total*0.225);
            const mk=(h,b=true)=>{const d=document.createElement('div');d.style.cssText=`flex:none;height:${h}px;${b?'border-top:1px solid rgba(255,255,255,0.04);':''}`;root.appendChild(d);return d;};
            const d1=mk(h1,false),d2=mk(h2),d3=mk(h3);
            const {chart:c1,ro:r1}=mkChart(d1,h1,data.dates, { crosshair: { horzLine: { visible: false, labelVisible: false } } }); instances.push({chart:c1,ro:r1});
            // BB bands
            if(data.GP_BB_Top)c1.addLineSeries({color:'rgba(68,136,255,0.45)',lineWidth:1,lineStyle:2,priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'GP_BB_Top'));
            if(data.GP_BB_Bot)c1.addLineSeries({color:'rgba(68,136,255,0.45)',lineWidth:1,lineStyle:2,priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'GP_BB_Bot'));
            // GP cloud fill
            if(data.GP_xFast&&data.GP_xSlow){
                const sc=priceScale(data);
                const gpBullish = [], gpBearish = [], gpMask = [];
                for(let i=0;i<data.dates.length;i++){
                    const f=data.GP_xFast[i],s=data.GP_xSlow[i];
                    if(f===null||s===null||f===undefined||s===undefined)continue;
                    const t=d2ts(data.dates[i]);
                    const top = Math.max(f, s) * sc;
                    const bot = Math.min(f, s) * sc;
                    if(f>=s){
                        gpBullish.push({time:t,value:top});
                        gpBearish.push({time:t,value:null});
                    }else{
                        gpBullish.push({time:t,value:null});
                        gpBearish.push({time:t,value:top});
                    }
                    gpMask.push({time:t,value:bot});
                }
                c1.addAreaSeries({topColor:'rgba(57,255,20,0.2)',bottomColor:'rgba(57,255,20,0.01)',lineColor:'#39ff14',lineWidth:2,priceLineVisible:false,lastValueVisible:false,title: ''}).setData(gpBullish);
                c1.addAreaSeries({topColor:'rgba(255,68,68,0.2)',bottomColor:'rgba(255,68,68,0.01)',lineColor:'#ff4444',lineWidth:2,priceLineVisible:false,lastValueVisible:false,title: ''}).setData(gpBearish);
                c1.addAreaSeries({topColor:'#000000',bottomColor:'#000000',lineColor:'rgba(0,0,0,0)',lineWidth:0,priceLineVisible:false,lastValueVisible:false,title: ''}).setData(gpMask);
            }
            else{if(data.GP_xFast)c1.addLineSeries({color:'#39ff14',lineWidth:2,priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'GP_xFast'));if(data.GP_xSlow)c1.addLineSeries({color:'#ff4444',lineWidth:2,priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'GP_xSlow'));}
            // Candles on top
            c1.addCandlestickSeries({upColor:'#00ff6a',downColor:'#ff3b3b',borderUpColor:'#00ff6a',borderDownColor:'#ff3b3b',wickUpColor:'#00ff6a',wickDownColor:'#ff3b3b',priceLineVisible:false,lastValueVisible:false}).setData(ohlcv(data));
            // Octopus pane
            const {chart:c2,ro:r2}=mkChart(d2,h2, null, { crosshair: { horzLine: { visible: false, labelVisible: false } } }); instances.push({chart:c2,ro:r2});
            if(data.OCT_A1) {
                const octData = data.dates.map((dt, i) => {
                    const v = data.OCT_A1[i];
                    if (v === null || v === undefined) return null;
                    const col = data.OCT_Color ? data.OCT_Color[i] : '#808080';
                    return { time: d2ts(dt), value: v, color: col };
                }).filter(Boolean);
                c2.addHistogramSeries({priceLineVisible:false,lastValueVisible:true,title: ''}).setData(octData);
            }
            if(data.OCT_B1)c2.addLineSeries({color:'#a78bfa',lineWidth:1.5,lineStyle:2,priceLineVisible:false,lastValueVisible:true,title: ''}).setData(lineData(data,'OCT_B1',1));
            if(data.dates.length>0)c2.addLineSeries({color:'rgba(255,255,255,0.12)',lineWidth:1,priceLineVisible:false,lastValueVisible:false}).setData([{time:d2ts(data.dates[0]),value:0},{time:d2ts(data.dates[data.dates.length-1]),value:0}]);
            // RS pane
            const {chart:c3,ro:r3}=mkChart(d3,h3, null, { crosshair: { horzLine: { visible: false, labelVisible: false } } }); instances.push({chart:c3,ro:r3});
            if(data.RS13)c3.addLineSeries({color:'#ffffff',lineWidth:1.5,title: '',priceLineVisible:false,lastValueVisible:true}).setData(lineData(data,'RS13',1));
            if(data.RS52)c3.addLineSeries({color:'#fbbf24',lineWidth:1.5,title: '',priceLineVisible:false,lastValueVisible:true}).setData(lineData(data,'RS52',1));
            if(data.dates.length>0)c3.addLineSeries({color:'rgba(239,68,68,0.4)',lineWidth:1,lineStyle:1,priceLineVisible:false,lastValueVisible:false}).setData([{time:d2ts(data.dates[0]),value:50},{time:d2ts(data.dates[data.dates.length-1]),value:50}]);
            syncCharts([c1,c2,c3]); applyDefaultChartRange(c1, data.dates, 90);
        }

        function renderHeikinChartFs(mountId, data, instances) {
            const root=document.getElementById(mountId);
            root.innerHTML=''; root.style.display='flex'; root.style.flexDirection='column';
            const total=root.offsetHeight||window.innerHeight-120;
            const h1=Math.round(total*0.55),h2=Math.round(total*0.45);
            const mk=(h,b=true)=>{const d=document.createElement('div');d.style.cssText=`flex:none;height:${h}px;${b?'border-top:1px solid rgba(255,255,255,0.04);':''}`;root.appendChild(d);return d;};
            const d1=mk(h1,false),d2=mk(h2);
            const {chart:c1,ro:r1}=mkChart(d1,h1,data.dates, { crosshair: { horzLine: { visible: false, labelVisible: false } } }); instances.push({chart:c1,ro:r1});
            // TC Cloud
            if(data.TC_Trend&&data.TC_StopLine){
                const sc=priceScale(data);
                const tcCloudBull = [], tcCloudBear = [], tcMask = [];
                for(let i=0;i<data.dates.length;i++){
                    const tr=data.TC_Trend[i],sl=data.TC_StopLine[i];
                    if(tr===null||sl===null||tr===undefined||sl===undefined)continue;
                    const t=d2ts(data.dates[i]);
                    const tcT=data.TC_T?data.TC_T[i]:(tr>sl?1:-1);
                    const top = Math.max(tr, sl) * sc;
                    const bot = Math.min(tr, sl) * sc;
                    if(tcT>=0){
                        tcCloudBull.push({time:t,value:top});
                        tcCloudBear.push({time:t,value:null});
                    }else{
                        tcCloudBull.push({time:t,value:null});
                        tcCloudBear.push({time:t,value:top});
                    }
                    tcMask.push({time:t,value:bot});
                }
                c1.addAreaSeries({topColor:'rgba(39,194,46,0.22)',bottomColor:'rgba(39,194,46,0.01)',lineColor:'rgba(39,194,46,0.6)',lineWidth:1.5,priceLineVisible:false}).setData(tcCloudBull);
                c1.addAreaSeries({topColor:'rgba(255,0,0,0.18)',bottomColor:'rgba(255,0,0,0.01)',lineColor:'rgba(255,0,0,0.5)',lineWidth:1.5,priceLineVisible:false}).setData(tcCloudBear);
                c1.addAreaSeries({
                    topColor: '#000000', bottomColor: '#000000',
                    lineColor: 'rgba(0,0,0,0)', lineWidth: 0,
                    priceLineVisible: false, lastValueVisible: false, title: ''
                }).setData(tcMask);
            }
            else if(data.TC_Trend)c1.addLineSeries({color:'#f59e0b',lineWidth:2.5}).setData(lineData(data,'TC_Trend'));
            if(data.HK_Flower_Open&&data.HK_Flower_Close){
                const hk=c1.addCandlestickSeries({upColor:'#00ff6a',downColor:'#ff3b3b',borderUpColor:'#00ff6a',borderDownColor:'#ff3b3b',wickUpColor:'#00ff6a',wickDownColor:'#ff3b3b'});
                const arr=[]; const hkSc=priceScale(data); for(let i=0;i<data.dates.length;i++){const ho=data.HK_Flower_Open[i],hc=data.HK_Flower_Close[i],hh=data.HK_Flower_High[i],hl=data.HK_Flower_Low[i]; if(!ho||!hc)continue; const col=data.HK_BarColor&&data.HK_BarColor[i]; const clr=col==='brightGreen'?'#00ff6a':col==='red'?'#ff3b3b':'#ffffff'; arr.push({time:d2ts(data.dates[i]),open:ho*hkSc,high:hh*hkSc,low:hl*hkSc,close:hc*hkSc,color:clr,borderColor:clr,wickColor:clr}); }
                hk.setData(arr);
            }
            if(data.HK_NW) c1.addLineSeries({color:'#38bdf8',lineWidth:2,priceLineVisible:false,lastValueVisible:false}).setData(lineData(data,'HK_NW'));
            const {chart:c2,ro:r2}=mkChart(d2,h2, null, { crosshair: { horzLine: { visible: false, labelVisible: false } } }); instances.push({chart:c2,ro:r2});
            const cs2fs=c2.addCandlestickSeries({upColor:'#00ff6a',downColor:'#ff3b3b',borderUpColor:'#00ff6a',borderDownColor:'#ff3b3b',wickUpColor:'#00ff6a',wickDownColor:'#ff3b3b',priceLineVisible:false,lastValueVisible:false});
            cs2fs.setData(ohlcv(data));
            if(data.T2_SMA&&data.T2_SMA_Trend){const scd=[],sc2=priceScale(data);for(let i=0;i<data.dates.length;i++){const v=data.T2_SMA[i],s=data.T2_SMA_Trend[i];if(v===null||v===undefined)continue;scd.push({time:d2ts(data.dates[i]),value:v*sc2,color:s>0?'#00ffaa':s<0?'#ff3b3b':'#888888'});}c2.addLineSeries({lineWidth:2.5,priceLineVisible:false}).setData(scd);}else if(data.T2_SMA)c2.addLineSeries({color:'#00ffaa',lineWidth:3}).setData(lineData(data,'T2_SMA'));
            if(data.T2_ST_Lower)c2.addLineSeries({color:'rgba(0,255,170,0.4)',lineWidth:1,lineStyle:2}).setData(lineData(data,'T2_ST_Lower'));
            if(data.T2_ST_Upper)c2.addLineSeries({color:'rgba(255,59,59,0.4)',lineWidth:1,lineStyle:2}).setData(lineData(data,'T2_ST_Upper'));
            if(data.T2_SMA_Trend&&data.T2_SMA){const t2m=[];for(let i=1;i<data.dates.length;i++){const p=data.T2_SMA_Trend[i-1],c=data.T2_SMA_Trend[i];if(p===null||c===null)continue;if(p<=0&&c>0)t2m.push({time:d2ts(data.dates[i]),position:'belowBar',color:'#00ffaa',shape:'triangleUp',text:'𝑳'});if(p>=0&&c<0)t2m.push({time:d2ts(data.dates[i]),position:'aboveBar',color:'#ff3b3b',shape:'triangleDown',text:'𝑺'});}if(t2m.length)cs2fs.setMarkers(t2m.sort((a,b)=>a.time-b.time));}
            syncCharts([c1,c2]); applyDefaultChartRange(c1, data.dates, 90);
        }

        function renderHeatmapChartFs(mountId, data, instances) {
            const root=document.getElementById(mountId);
            root.innerHTML=''; root.style.display='flex'; root.style.flexDirection='column';
            const total=root.offsetHeight||window.innerHeight-120;
            const h1=Math.round(total*0.68),h2=Math.round(total*0.32);
            const mk=(h,b=true)=>{const d=document.createElement('div');d.style.cssText=`flex:none;height:${h}px;${b?'border-top:1px solid rgba(255,255,255,0.04);':''}`;root.appendChild(d);return d;};
            const d1=mk(h1,false),d2=mk(h2);
            const {chart:c1,ro:r1}=mkChart(d1,h1,data.dates); instances.push({chart:c1,ro:r1});
            [{col:'HM_Band_Hi',color:'rgba(0,255,106,0.4)'},{col:'HM_Band_KH',color:'rgba(34,211,238,0.4)'},{col:'HM_Band_KM',color:'rgba(251,191,36,0.4)'},{col:'HM_Band_KL',color:'rgba(249,115,22,0.4)'},{col:'HM_Band_Lo',color:'rgba(255,59,59,0.4)'}]
            .forEach(b=>{if(data[b.col])c1.addLineSeries({color:b.color,lineWidth:1,lineStyle:2}).setData(lineData(data,b.col));});
            if(data.HM_Flower_Open&&data.HM_Flower_Close){
                const fcs=c1.addCandlestickSeries({upColor:'#ffffff',downColor:'#ff3b3b',borderUpColor:'#ffffff',borderDownColor:'#ff3b3b',wickUpColor:'#ffffff',wickDownColor:'#ff3b3b'});
                const arr=[]; const fSc=priceScale(data); for(let i=0;i<data.dates.length;i++){const fo=data.HM_Flower_Open[i],fc=data.HM_Flower_Close[i],fh=data.HM_Flower_High[i],fl=data.HM_Flower_Low[i]; if(!fo||!fc)continue; const mf=data.HM_MoneyFlow&&data.HM_MoneyFlow[i]; const up=fc>=fo; const clr=(up&&mf===1)?'#ffffff':(!up&&mf===-1)?'#ff3b3b':'#fbbf24'; arr.push({time:d2ts(data.dates[i]),open:fo*fSc,high:fh*fSc,low:fl*fSc,close:fc*fSc,color:clr,borderColor:clr,wickColor:clr}); }
                fcs.setData(arr);
            }
            const {chart:c2,ro:r2}=mkChart(d2,h2); instances.push({chart:c2,ro:r2});
            c2.addCandlestickSeries({upColor:'#00ff6a',downColor:'#ff3b3b',borderUpColor:'#00ff6a',borderDownColor:'#ff3b3b',wickUpColor:'#00ff6a',wickDownColor:'#ff3b3b'}).setData(ohlcv(data));
            syncCharts([c1,c2]); applyDefaultChartRange(c1, data.dates, 90);
        }

        function renderTechReportChartFs(mountId, data, instances) {
            const root = document.getElementById(mountId);
            if (!root) return;
            root.innerHTML = ''; root.style.display = 'flex'; root.style.flexDirection = 'column';
            const total = root.offsetHeight || window.innerHeight - 120;
            const h1 = Math.round(total * 0.46), h2 = Math.round(total * 0.18), h3 = Math.round(total * 0.18), h4 = Math.round(total * 0.18);
            const mk = (h, b = true) => {
                const d = document.createElement('div');
                d.style.cssText = `flex:none;height:${h}px;${b?'border-top:1px solid rgba(255,255,255,0.04);':''}`;
                root.appendChild(d); return d;
            };
            const d1 = mk(h1, false), d2 = mk(h2), d3 = mk(h3), d4 = mk(h4);
            const {chart: c1, ro: r1} = mkChart(d1, h1, data.dates);
            instances.push({chart: c1, ro: r1});

            // Initialize registry for this mount to manage line visibility toggles
            techReportSeriesRegistry[mountId] = {};

            // Ichimoku Kumo Cloud: colored fill between SpanA and SpanB
            if (data.SpanA && data.SpanB) {
                const sc = priceScale(data);
                const bullishCloud = [], bearishCloud = [], maskCloud = [];
                for (let i = 0; i < data.dates.length; i++) {
                    const a = data.SpanA[i], b = data.SpanB[i];
                    if (a === null || b === null || a === undefined || b === undefined) continue;
                    const t = d2ts(data.dates[i]);
                    const top = Math.max(a, b) * sc;
                    const bot = Math.min(a, b) * sc;
                    if (a >= b) {
                        bullishCloud.push({time: t, value: top});
                        bearishCloud.push({time: t, value: null});
                    } else {
                        bullishCloud.push({time: t, value: null});
                        bearishCloud.push({time: t, value: top});
                    }
                    maskCloud.push({time: t, value: bot});
                }
                const sKumoG = c1.addAreaSeries({topColor:'rgba(0,255,106,0.22)',bottomColor:'rgba(0,255,106,0.01)',lineColor:'rgba(0,255,106,0.65)',lineWidth:1.5,title: '',visible:techChartVisibility.SpanA,priceLineVisible:false});
                sKumoG.setData(bullishCloud); techReportSeriesRegistry[mountId].SpanA = sKumoG;
                const sKumoR = c1.addAreaSeries({topColor:'rgba(255,59,59,0.22)',bottomColor:'rgba(255,59,59,0.01)',lineColor:'rgba(255,59,59,0.65)',lineWidth:1.5,title: '',visible:techChartVisibility.SpanB,priceLineVisible:false});
                sKumoR.setData(bearishCloud); techReportSeriesRegistry[mountId].SpanB = sKumoR;
                const sKumoM = c1.addAreaSeries({
                    topColor: '#000000', bottomColor: '#000000',
                    lineColor: 'rgba(0,0,0,0)', lineWidth: 0,
                    title: '', visible: techChartVisibility.SpanA || techChartVisibility.SpanB, priceLineVisible: false, lastValueVisible: false
                });
                sKumoM.setData(maskCloud);
            } else {
                if (data.SpanA) {
                    const sSpanA = c1.addLineSeries({color:'rgba(0,255,106,0.65)',lineWidth:2,title: '',visible:techChartVisibility.SpanA,priceLineVisible:false});
                    sSpanA.setData(lineData(data,'SpanA')); techReportSeriesRegistry[mountId].SpanA = sSpanA;
                }
                if (data.SpanB) {
                    const sSpanB = c1.addLineSeries({color:'rgba(255,59,59,0.65)',lineWidth:2,title: '',visible:techChartVisibility.SpanB,priceLineVisible:false});
                    sSpanB.setData(lineData(data,'SpanB')); techReportSeriesRegistry[mountId].SpanB = sSpanB;
                }
            }
            
            // Bright neon colors for other indicator lines (with priceLineVisible disabled to declutter)
            if (data.Tenkan) {
                const sTenkan = c1.addLineSeries({color:'#00d2ff',lineWidth:1.2,title: '',visible:techChartVisibility.Tenkan,priceLineVisible:false});
                sTenkan.setData(lineData(data,'Tenkan'));
                techReportSeriesRegistry[mountId].Tenkan = sTenkan;
            }
            if (data.Kijun) {
                const sKijun = c1.addLineSeries({color:'#ff2a5f',lineWidth:1.2,title: '',visible:techChartVisibility.Kijun,priceLineVisible:false});
                sKijun.setData(lineData(data,'Kijun'));
                techReportSeriesRegistry[mountId].Kijun = sKijun;
            }
            if (data.Kijun65) {
                const sKijun65 = c1.addLineSeries({color:'#ff9f00',lineWidth:1.5,lineStyle:2,title: '',visible:techChartVisibility.Kijun65,priceLineVisible:false});
                sKijun65.setData(lineData(data,'Kijun65'));
                techReportSeriesRegistry[mountId].Kijun65 = sKijun65;
            }

            if (data.MA10) {
                const sMA10 = c1.addLineSeries({color:'#ffffff',lineWidth:1.5,title: '',visible:techChartVisibility.MA10,priceLineVisible:false});
                sMA10.setData(lineData(data,'MA10'));
                techReportSeriesRegistry[mountId].MA10 = sMA10;
            }
            if (data.MA20) {
                const sMA20 = c1.addLineSeries({color:'#00f589',lineWidth:2,title: '',visible:techChartVisibility.MA20,priceLineVisible:false});
                sMA20.setData(lineData(data,'MA20'));
                techReportSeriesRegistry[mountId].MA20 = sMA20;
            }
            if (data.MA50) {
                const sMA50 = c1.addLineSeries({color:'#ffd700',lineWidth:2,title: '',visible:techChartVisibility.MA50,priceLineVisible:false});
                sMA50.setData(lineData(data,'MA50'));
                techReportSeriesRegistry[mountId].MA50 = sMA50;
            }

            c1.addCandlestickSeries({
                upColor:'#00ff6a',downColor:'#ff3b3b',
                borderUpColor:'#00ff6a',borderDownColor:'#ff3b3b',
                wickUpColor:'#00ff6a',wickDownColor:'#ff3b3b'
            }).setData(ohlcv(data));

            // Pane 2: MCDX Stacked Area Chart
            const {chart: c2, ro: r2} = mkChart(d2, h2);
            instances.push({chart: c2, ro: r2});
            
            const greenData = data.dates.map(dt => ({ time: d2ts(dt), value: 20.0 }));
            c2.addAreaSeries({
                topColor: 'rgba(52, 211, 153, 0.4)',
                bottomColor: 'rgba(52, 211, 153, 0.05)',
                lineColor: '#34d399',
                lineWidth: 1,
                priceLineVisible: false,
                title: ''
            }).setData(greenData);

            if (data.MCDX_HotMoney) {
                c2.addAreaSeries({
                    topColor: 'rgba(251, 191, 36, 0.65)',
                    bottomColor: 'rgba(251, 191, 36, 0.1)',
                    lineColor: '#fbbf24',
                    lineWidth: 1,
                    priceLineVisible: false,
                    title: ''
                }).setData(lineData(data, 'MCDX_HotMoney', 1));
            }

            if (data.MCDX_Banker) {
                c2.addAreaSeries({
                    topColor: 'rgba(244, 63, 94, 0.85)',
                    bottomColor: 'rgba(244, 63, 94, 0.2)',
                    lineColor: '#f43f5e',
                    lineWidth: 1,
                    priceLineVisible: false,
                    title: ''
                }).setData(lineData(data, 'MCDX_Banker', 1));
            }

            if (data.MCDX_Banker_MA) {
                c2.addLineSeries({
                    color: '#ffffff',
                    lineWidth: 1.5,
                    priceLineVisible: false,
                    title: ''
                }).setData(lineData(data, 'MCDX_Banker_MA', 1));
            }

            c2.priceScale('right').applyOptions({
                scaleMargins: {
                    top: 0,
                    bottom: 0,
                },
            });

            // Pane 3: ADX with Dynamic Color Segments
            const {chart: c3, ro: r3} = mkChart(d3, h3);
            instances.push({chart: c3, ro: r3});
            
            if (data.ADX) {
                const adxData = [];
                for (let i = 0; i < data.dates.length; i++) {
                    const dt = data.dates[i];
                    const val = data.ADX[i];
                    if (val === null || val === undefined) continue;
                    
                    const prevVal = i > 0 ? data.ADX[i-1] : null;
                    const diPlus = data.DI_Plus ? data.DI_Plus[i] : 0;
                    const diMinus = data.DI_Minus ? data.DI_Minus[i] : 0;
                    
                    let color = '#c084fc';
                    if (val <= 20) {
                        color = '#eab308';
                    } else if (diPlus >= diMinus) {
                        if (prevVal !== null && val < prevVal) {
                            color = '#00ff6a';
                        } else {
                            color = '#ffffff';
                        }
                    } else {
                        color = '#ef4444';
                    }
                    
                    adxData.push({
                        time: d2ts(dt),
                        value: val,
                        color: color
                    });
                }
                c3.addLineSeries({
                    lineWidth: 2.5,
                    title: '',
                    priceLineVisible: false
                }).setData(adxData);
            }
            if (data.DI_Plus) c3.addLineSeries({color:'#34d399',lineWidth:1.5,title: '',priceLineVisible:false}).setData(lineData(data,'DI_Plus',1));
            if (data.DI_Minus)c3.addLineSeries({color:'#f87171',lineWidth:1.5,title: '',priceLineVisible:false}).setData(lineData(data,'DI_Minus',1));
            if (data.dates.length > 0)
                c3.addLineSeries({color:'rgba(255,255,255,0.18)',lineWidth:1,lineStyle:1,priceLineVisible:false})
                  .setData([{time:d2ts(data.dates[0]),value:25},{time:d2ts(data.dates[data.dates.length-1]),value:25}]);

            // Pane 4: MACD
            const {chart: c4, ro: r4} = mkChart(d4, h4);
            instances.push({chart: c4, ro: r4});
            if (data.MACD_Hist) {
                const hArr = data.dates.map((dt,i) => {
                    const v = data.MACD_Hist[i];
                    if (v===null||v===undefined) return null;
                    return {time:d2ts(dt), value:v,
                        color: v>=0?'rgba(52,211,153,0.7)':'rgba(248,113,113,0.7)'};
                }).filter(Boolean);
                c4.addHistogramSeries({priceLineVisible:false,title: ''}).setData(hArr);
            }
            if (data.MACD)        c4.addLineSeries({color:'#60a5fa',lineWidth:1.5,title: '',priceLineVisible:false}).setData(lineData(data,'MACD',1));
            if (data.MACD_Signal) c4.addLineSeries({color:'#fb923c',lineWidth:1.5,title: '',priceLineVisible:false}).setData(lineData(data,'MACD_Signal',1));

            syncCharts([c1, c2, c3, c4]);
            applyDefaultChartRange(c1, data.dates, 90);
        }

        // ================================================================
        //  PORTFOLIO EVALUATION LOGIC
        // ================================================================
        function generatePortfolioRows() {
            const container = document.getElementById('portfolio-stocks-list');
            if (!container) return;
            
            let html = [];
            for (let i = 1; i <= 10; i++) {
                html.push(`
                    <div class="portfolio-stock-row">
                        <div style="position:relative;">
                            <input type="text" id="port-t-${i}" class="ticker-input" placeholder="Mã" oninput="handleTickerAutocomplete(this, ${i})" autocomplete="off">
                            <div id="port-auto-${i}" class="ticker-autocomplete-list"></div>
                        </div>
                        <input type="text" id="port-q-${i}" placeholder="Số lượng" oninput="formatNumberInput(this)">
                        <input type="text" id="port-p-${i}" placeholder="Giá vốn TB" oninput="formatNumberInput(this)">
                    </div>
                `);
            }
            container.innerHTML = html.join('');
        }
        
        function handleTickerAutocomplete(inputEl, rowIndex) {
            let value = inputEl.value.trim().toUpperCase();
            let container = document.getElementById(`port-auto-${rowIndex}`);
            if (!container) return;
            
            if (!value || !rawData || !rawData.tickers_analysis) {
                container.style.display = 'none';
                return;
            }
            
            let matches = rawData.tickers_analysis.filter(t => t.Ticker.includes(value)).slice(0, 5);
            if (matches.length === 0) {
                container.style.display = 'none';
                return;
            }
            
            container.innerHTML = matches.map(t => `<div class="ticker-autocomplete-item" onclick="selectTickerAutocomplete('${t.Ticker}', ${rowIndex})">${t.Ticker}</div>`).join('');
            container.style.display = 'block';
        }
        
        function selectTickerAutocomplete(ticker, rowIndex) {
            document.getElementById(`port-t-${rowIndex}`).value = ticker;
            document.getElementById(`port-auto-${rowIndex}`).style.display = 'none';
        }
        
        function formatNumberInput(inputEl) {
            let value = inputEl.value.replace(/,/g, '');
            if (!value) return;
            if (isNaN(value)) {
                inputEl.value = value.replace(/[^0-9.]/g, '');
                return;
            }
            let parts = value.split('.');
            if (parts[0] !== "" && !isNaN(parts[0])) {
                parts[0] = Number(parts[0]).toLocaleString('en-US');
            }
            inputEl.value = parts.join('.');
        }
        
        function runPortfolioEvaluation() {
            if (!rawData || !rawData.tickers_analysis) {
                alert("Dữ liệu hệ thống chưa được nạp. Vui lòng đợi trong giây lát hoặc tải lại trang.");
                return;
            }
            
            // Show loading
            document.getElementById('portfolio-results-placeholder').style.display = 'none';
            document.getElementById('portfolio-results-container').style.display = 'none';
            document.getElementById('portfolio-results-loading').style.display = 'block';
            document.getElementById('port-copy-btn').style.display = 'none';
            
            setTimeout(() => {
                try {
                    let cash_on_hand = parseFloat(document.getElementById('port-nav').value.replace(/,/g, '')) || 0;
                    let w_target = (parseFloat(document.getElementById('port-w-target').value) || 100) / 100;
                    let n_tickers = parseInt(document.getElementById('port-n-tickers').value) || 3;
                    let r_cl = (parseFloat(document.getElementById('port-cutloss').value) || 7) / 100;
                    
                    if (n_tickers <= 0) {
                        alert("Số lượng mã phải lớn hơn 0.");
                        resetPortfolioUI();
                        return;
                    }
                    
                    let tickers_data = [];
                    for (let i = 1; i <= 10; i++) {
                        let ticker = document.getElementById(`port-t-${i}`).value.trim().toUpperCase();
                        let qty = parseFloat(document.getElementById(`port-q-${i}`).value.replace(/,/g, '')) || 0;
                        let avgPrice = parseFloat(document.getElementById(`port-p-${i}`).value.replace(/,/g, '')) || 0;
                        if (ticker) {
                            tickers_data.push({ ticker, quantity: qty, avg_price: avgPrice });
                        }
                    }
                    
                    if (tickers_data.length === 0) {
                        alert("Vui lòng nhập ít nhất 1 mã cổ phiếu.");
                        resetPortfolioUI();
                        return;
                    }
                    
                    let report_lines = [];
                    report_lines.push("BÁO CÁO ĐÁNH GIÁ DANH MỤC ĐẦU TƯ");
                    report_lines.push("=".repeat(50));
                    
                    let total_market_value = 0;
                    let total_cost_value = 0;
                    let pre_results = [];
                    
                    for (let item of tickers_data) {
                        let ticker = item.ticker;
                        let q_i = item.quantity;
                        let p_avg_input = item.avg_price;
                        
                        let tData = rawData.tickers_analysis.find(t => t.Ticker === ticker);
                        if (!tData) {
                            pre_results.push({ ticker, valid: false, msg: `Không tìm thấy mã ${ticker} trong hệ thống.` });
                            continue;
                        }
                        
                        let p_now_vnd = tData.Price;
                        let p_sup_vnd = tData.Support1 || p_now_vnd * 0.95;
                        let p_res_vnd = tData.Resistance1 || p_now_vnd * 1.05;
                        let p_ts_vnd = tData.TrailingStop || p_sup_vnd;
                        
                        let p_avg_vnd = p_avg_input < 1000 ? p_avg_input * 1000 : p_avg_input;
                        
                        let trend_desc = tData.TrendStatus || "Sideway";
                        let trend_i = 0;
                        if (trend_desc.includes("Uptrend")) trend_i = 1;
                        else if (trend_desc.includes("Downtrend")) trend_i = -1;
                        
                        let market_val = q_i * p_now_vnd;
                        let cost_val = q_i * p_avg_vnd;
                        
                        total_market_value += market_val;
                        total_cost_value += cost_val;
                        
                        pre_results.push({
                            ticker, valid: true, q: q_i, p_avg_vnd, p_now_vnd,
                            p_sup_vnd, p_res_vnd, p_ts_vnd, trend: trend_i, trend_desc,
                            market_val, cost_val, tData
                        });
                    }
                    
                    let nav_current = cash_on_hand + total_market_value;
                    let nav_cost = cash_on_hand + total_cost_value;
                    
                    if (nav_current <= 0) {
                        alert("Tổng tài sản (Tiền mặt + Cổ phiếu) phải lớn hơn 0.");
                        resetPortfolioUI();
                        return;
                    }
                    
                    let v_max_i = (nav_current * w_target) / n_tickers;
                    let risk_max_nav = 0.03 * nav_current;
                    let portfolio_risk_total = 0;
                    let results = [];
                    
                    for (let item of pre_results) {
                        if (!item.valid) {
                            results.push(item);
                            continue;
                        }
                        
                        let ticker = item.ticker;
                        let q_i = item.q;
                        let p_avg_vnd = item.p_avg_vnd;
                        let p_now_vnd = item.p_now_vnd;
                        let p_sup_vnd = item.p_sup_vnd;
                        let p_res_vnd = item.p_res_vnd;
                        let p_ts_vnd = item.p_ts_vnd;
                        let trend_i = item.trend;
                        let tData = item.tData;
                        
                        let pl_pct = p_avg_vnd > 0 ? (p_now_vnd - p_avg_vnd) / p_avg_vnd : 0;
                        let w_curr = item.market_val / nav_current;
                        
                        let tech_weak = tData.TechWeak !== undefined ? tData.TechWeak : false;
                        let sideways_near_res = tData.SidewaysNearRes !== undefined ? tData.SidewaysNearRes : false;
                        
                        let p_sl_vnd = p_ts_vnd > 0 ? p_ts_vnd : p_sup_vnd * 0.97;
                        let sl_source = "Hệ thống tư vấn";
                        
                        let current_risk_amt = p_avg_vnd > p_sl_vnd ? q_i * (p_avg_vnd - p_sl_vnd) : 0;
                        portfolio_risk_total += current_risk_amt;
                        
                        results.push({
                            ticker, valid: true, q: q_i, p_avg_vnd, p_now_vnd,
                            p_sup_vnd, p_res_vnd, p_ts_vnd, trend: trend_i, trend_desc: item.trend_desc,
                            pl_pct, w_curr, m_val: item.market_val,
                            tech_weak, sideways_near_res,
                            current_risk: current_risk_amt, p_sl_vnd, sl_source, tData
                        });
                    }
                    
                    report_lines.push("1. ĐÁNH GIÁ CHẤT LƯỢNG TÀI SẢN (TỔNG QUAN)");
                    report_lines.push(`- Tổng Tài Sản Hiện Tại (NAV): ${nav_current.toLocaleString('vi-VN')} VND`);
                    report_lines.push(`  + Tiền mặt đang có: ${cash_on_hand.toLocaleString('vi-VN')} VND (${((cash_on_hand/nav_current)*100).toFixed(1)}%)`);
                    report_lines.push(`  + Giá trị cổ phiếu: ${total_market_value.toLocaleString('vi-VN')} VND (${((total_market_value/nav_current)*100).toFixed(1)}%)`);
                    report_lines.push(`- Tổng Giá Vốn Cổ Phiếu: ${total_cost_value.toLocaleString('vi-VN')} VND`);
                    
                    let total_profit = total_market_value - total_cost_value;
                    let total_profit_pct = total_cost_value > 0 ? (total_profit / total_cost_value * 100) : 0;
                    let sign = total_profit > 0 ? "+" : "";
                    report_lines.push(`- Lợi Nhuận Trạng Thái Cổ Phiếu: ${sign}${total_profit.toLocaleString('vi-VN')} VND (${sign}${total_profit_pct.toFixed(1)}%)`);
                    report_lines.push(`- Tổng rủi ro tiềm ẩn (Số tiền mất nếu hit SL): ${portfolio_risk_total.toLocaleString('vi-VN')} VND (${((portfolio_risk_total/nav_current)*100).toFixed(1)}% NAV)`);
                    
                    report_lines.push("\nNhận xét cân đối:");
                    let alertsHtml = [];
                    
                    if ((total_market_value/nav_current) > w_target) {
                        let text = `[!] QUÁ TỶ TRỌNG CỔ PHIẾU: Tỷ trọng hiện tại (${((total_market_value/nav_current)*100).toFixed(1)}%) vượt mức khuyến cáo (${(w_target*100).toFixed(0)}%). Cần chốt lời/hạ tỷ trọng.`;
                        report_lines.push("  " + text);
                        alertsHtml.push(`<div class="port-alert danger">⚠️ <strong>QUÁ TỶ TRỌNG CỔ PHIẾU:</strong> Tỷ trọng hiện tại (${((total_market_value/nav_current)*100).toFixed(1)}%) vượt mức khuyến cáo (${(w_target*100).toFixed(0)}%). Cần chốt lời/hạ tỷ trọng để bảo vệ vốn.</div>`);
                    } else {
                        let text = `[v] TỶ TRỌNG AN TOÀN: Tỷ lệ phân bổ cổ phiếu (${((total_market_value/nav_current)*100).toFixed(1)}%) đang nằm trong mức khuyến cáo (${(w_target*100).toFixed(0)}%).`;
                        report_lines.push("  " + text);
                        alertsHtml.push(`<div class="port-alert success">✅ <strong>TỶ TRỌNG AN TOÀN:</strong> Tỷ lệ phân bổ cổ phiếu (${((total_market_value/nav_current)*100).toFixed(1)}%) đang nằm trong mức khuyến cáo (${(w_target*100).toFixed(0)}%).</div>`);
                    }
                    
                    if (portfolio_risk_total > risk_max_nav) {
                        let text = "[!] CẢNH BÁO RỦI RO: Rủi ro tổng đang VƯỢT QUÁ 3% NAV. Ưu tiên số 1 là giảm tỷ trọng các mã vi phạm hoặc cắt lỗ ngay lập tức để bảo vệ vốn.";
                        report_lines.push("  " + text);
                        alertsHtml.push(`<div class="port-alert danger">🔥 <strong>CẢNH BÁO RỦI RO:</strong> Rủi ro tổng đang VƯỢT QUÁ 3% NAV. Ưu tiên số 1 là giảm tỷ trọng các mã vi phạm hoặc cắt lỗ ngay lập tức để bảo vệ vốn.</div>`);
                    } else {
                        let text = "[v] RỦI RO KIỂM SOÁT TỐT: Rủi ro tổng trong tầm kiểm soát (< 3% NAV).";
                        report_lines.push("  " + text);
                        alertsHtml.push(`<div class="port-alert success">✅ <strong>RỦI RO KIỂM SOÁT TỐT:</strong> Rủi ro tổng nằm trong tầm kiểm soát an toàn (${((portfolio_risk_total/nav_current)*100).toFixed(1)}% NAV &lt; 3%).</div>`);
                    }
                    
                    let valid_tickers = results.filter(r => r.valid);
                    if (valid_tickers.length > n_tickers) {
                        let text = `[!] DANH MỤC DÀN TRẢI: Bạn đang cầm ${valid_tickers.length} mã, vượt quá số lượng tối ưu là ${n_tickers} mã. Khuyên dùng: Tỉa cỏ trồng hoa, bán bớt các mã gãy trend/yếu.`;
                        report_lines.push("  " + text);
                        alertsHtml.push(`<div class="port-alert warning">⚠️ <strong>DANH MỤC DÀN TRẢI:</strong> Bạn đang cầm ${valid_tickers.length} mã, vượt quá số lượng tối ưu là ${n_tickers} mã. Khuyên dùng: "Tỉa cỏ trồng hoa", tập trung vốn vào các mã Leader khỏe.</div>`);
                    }
                    
                    report_lines.push("\n2. ĐÁNH GIÁ CHI TIẾT TỪNG MÃ (Tư duy xử lý)");
                    
                    let tableRowsHtml = [];
                    
                    for (let res of results) {
                        if (!res.valid) {
                            report_lines.push(`- ${res.ticker}: Lỗi dữ liệu - ${res.msg}`);
                            tableRowsHtml.push(`
                                <tr style="opacity:0.6;">
                                    <td><strong>${res.ticker}</strong></td>
                                    <td colspan="7" class="text-red" style="text-align:center;">Lỗi dữ liệu: ${res.msg}</td>
                                </tr>
                            `);
                            continue;
                        }
                        
                        let t = res.ticker;
                        let q_i = res.q;
                        let p_avg_vnd = res.p_avg_vnd;
                        let p_now_vnd = res.p_now_vnd;
                        let p_sup_vnd = res.p_sup_vnd;
                        let p_res_vnd = res.p_res_vnd;
                        let pl_pct = res.pl_pct;
                        let w_curr = res.w_curr;
                        let tData = res.tData;
                        
                        let pl_sign = pl_pct > 0 ? "+" : "";
                        let h_rating = tData.OpportunityDesc || "BT";
                        let h_score = tData.OpportunityScore || 0;
                        
                        let state = tData.Action || "WAIT";
                        let sr_signal = tData.StateSignal || "Chưa có tín hiệu dứt khoát";
                        let avoid_entry = tData.AvoidEntry || false;
                        let anti_trap = tData.AntiTrap || false;
                        
                        let sig_upper = sr_signal.toUpperCase();
                        if (avoid_entry && (sig_upper.startsWith("MUA") || sig_upper.startsWith("GIA TĂNG"))) {
                            if (anti_trap) {
                                sr_signal = "BLOCK (Rủi ro Fomo: Đợi chỉnh)";
                                sig_upper = sr_signal.toUpperCase();
                            }
                        }
                        
                        res.state_sig = sig_upper;
                        
                        // Calculation of Action
                        let status_desc = h_rating;
                        let action = "HOLD";
                        let q_action = 0;
                        let p_action_vnd = 0;
                        let reason = "";
                        
                        if (w_curr > w_target/n_tickers) {
                            status_desc = "Quá Tỷ Trọng";
                        } else if (pl_pct < -0.05) {
                            status_desc = "Đang Lỗ/Yếu";
                        }
                        
                        let risk_score = tData.RiskScore || 50;
                        
                        // Rule 1: Stoploss/Trailing stop violation
                        if (p_now_vnd < res.p_sl_vnd) {
                            action = "BÁN HẾT (100%)";
                            q_action = q_i;
                            p_action_vnd = p_now_vnd;
                            reason = `Vi phạm điểm cắt lỗ/chặn lãi (${res.sl_source}).`;
                        }
                        // Rule 2: Core AI Signal (Take Profit / Exit / Trap)
                        else if (
                            (sig_upper.includes("CHỐT") || sig_upper.includes("THOÁT") || sig_upper.includes("CHẠY") || sig_upper.includes("BLOCK")) &&
                            !(["STRONG", "ADD_2", "ADD_1"].includes(state) && risk_score <= 75 && !anti_trap)
                        ) {
                            if (sig_upper.includes("BLOCK") || sig_upper.includes("50%")) {
                                action = "CHỐT LỜI (50%)";
                                q_action = q_i * 0.5;
                            } else {
                                action = "CHỐT LỜI/THOÁT";
                                q_action = q_i;
                            }
                            p_action_vnd = p_now_vnd;
                            reason = `Đồng bộ AI lõi: ${sr_signal}.`;
                        }
                        // Rule 3: Downtrend / Broken Trend
                        else if (h_score <= 20 || sig_upper.includes("DOWNTREND") || sig_upper.includes("ĐỨNG NGOÀI")) {
                            if (pl_pct < 0) {
                                action = "CẮT LỖ (Gãy Trend)";
                                q_action = q_i;
                                p_action_vnd = p_now_vnd;
                                reason = "Cổ phiếu gãy trend/Downtrend. Cắt bỏ dứt khoát.";
                            } else {
                                action = "CHỐT LỜI/THOÁT";
                                q_action = q_i;
                                p_action_vnd = p_now_vnd;
                                reason = "Trend đảo chiều xấu, ưu tiên chốt lãi bảo vệ vốn.";
                            }
                        }
                        // Rule 4: Portfolio Allocation Weight Limit
                        else if (w_curr > (w_target / n_tickers) + 0.05) { // 5% tolerance
                            action = "HẠ TỶ TRỌNG";
                            let excess_value = (q_i * p_now_vnd) - v_max_i;
                            q_action = excess_value / p_now_vnd;
                            p_action_vnd = p_now_vnd;
                            if (["STRONG", "ADD_2", "ADD_1"].includes(state)) {
                                reason = `Cổ phiếu khỏe (${state}) nhưng tỷ trọng (${(w_curr*100).toFixed(1)}%) quá lớn, ưu tiên hạ bớt.`;
                            } else {
                                reason = `Tỷ trọng hiện tại (${(w_curr*100).toFixed(1)}%) vượt quá mức an toàn.`;
                            }
                        }
                        // Rule 5: Cost Averaging Down (When losing)
                        else if (pl_pct < -0.04) {
                            if (pl_pct < -0.10 || (p_now_vnd - p_sup_vnd) / p_now_vnd > 0.10) {
                                action = "CẮT LỖ BỚT";
                                q_action = q_i * 0.5;
                                p_action_vnd = p_now_vnd;
                                reason = "Lỗ > 10% hoặc xa hỗ trợ > 10%. Tuyệt đối không TBG.";
                            } else if (p_now_vnd <= p_sup_vnd * 1.02) { // near support zone
                                let current_loss_abs = q_i * (p_avg_vnd - p_now_vnd);
                                let X_max = (risk_max_nav - current_loss_abs) / 0.07;
                                
                                if (X_max <= 0) {
                                    action = "KHÔNG TBG";
                                    reason = "Lỗ hiện tại đã chiếm hết hạn mức rủi ro 3% NAV.";
                                } else if (h_score >= 40) {
                                    let q_add_max = X_max / p_sup_vnd;
                                    q_action = Math.min(q_add_max, Math.max(0, (v_max_i - q_i * p_now_vnd) / p_sup_vnd));
                                    if (q_action > 0) {
                                        action = "MUA TBG XUỐNG";
                                        p_action_vnd = p_sup_vnd;
                                        reason = `Về hỗ trợ (${(p_sup_vnd/1000).toFixed(1)}), Sức khỏe tốt. Mua giảm giá vốn.`;
                                    } else {
                                        action = "CHỜ ĐỢI";
                                        reason = "Đã hết mức tỷ trọng cho phép để trung bình giá.";
                                    }
                                } else {
                                    action = "CHỜ ĐỢI";
                                    reason = "Ở hỗ trợ nhưng cổ phiếu yếu (<40đ), rủi ro thủng nền cao.";
                                }
                            } else {
                                action = "CHỜ VỀ HỖ TRỢ";
                                reason = `Đang lơ lửng, đợi nhúng về vùng ${(p_sup_vnd/1000).toFixed(1)}.`;
                            }
                        }
                        // Rule 6: Buy Increments (For healthy holdings)
                        else if (["STRONG", "ADD_2", "ADD_1"].includes(state) && risk_score <= 75 && !anti_trap) {
                            if (w_curr < (w_target / n_tickers) * 0.8) {
                                action = "MUA GIA TĂNG";
                                q_action = (v_max_i - q_i * p_now_vnd) / p_now_vnd;
                                p_action_vnd = p_now_vnd;
                                reason = `Phân tích đơn lẻ: Vị thế ${state} khỏe. Gia tăng tỷ trọng.`;
                            } else {
                                action = "HOLD";
                                reason = "Vị thế đang khỏe nhưng đã đủ tỷ trọng. Gồng lãi.";
                            }
                        }
                        // Rule 7: Core Signal Fallback buy
                        else if (
                            sig_upper.includes("MUA") || sig_upper.includes("GIA TĂNG") ||
                            (sig_upper.includes("TREND") && pl_pct > 0.03 && h_score >= 60)
                        ) {
                            if (w_curr < (w_target / n_tickers) * 0.8) {
                                action = "MUA GIA TĂNG";
                                q_action = (v_max_i - q_i * p_now_vnd) / p_now_vnd;
                                p_action_vnd = p_now_vnd > p_sup_vnd * 1.05 ? p_sup_vnd : p_now_vnd;
                                reason = `Đồng bộ AI lõi: ${sr_signal}. Nhặt thêm tại ${(p_action_vnd/1000).toFixed(1)}.`;
                            } else {
                                action = "HOLD";
                                reason = "Trend khỏe nhưng đã đủ tỷ trọng. Tiếp tục gồng lãi.";
                            }
                        }
                        
                        if (!reason) {
                            reason = "Duy trì vị thế hiện tại, theo dõi thêm.";
                        }
                        
                        res.action = action;
                        res.q_action = q_action;
                        res.p_action_vnd = p_action_vnd;
                        res.reason = reason;
                        res.status_desc = status_desc;
                        
                        let desc = `- ${t}: Đang chiếm ${(w_curr*100).toFixed(1)}% NAV. Lãi/lỗ: ${pl_sign}${(pl_pct*100).toFixed(1)}%. `;
                        desc += `Chất lượng KT: ${h_rating} (${h_score}đ). Tín hiệu AI: ${sr_signal.toUpperCase()}. `;
                        desc += `Hướng xử lý chiến lược: ${action} (${reason})`;
                        report_lines.push(desc);
                        
                        // Row variables
                        let pl_str = `${pl_pct > 0 ? '+' : ''}${(pl_pct*100).toFixed(1)}%`;
                        let pl_class = pl_pct > 0 ? 'text-green' : (pl_pct < 0 ? 'text-red' : '');
                        let q_curr_str = Math.round(q_i).toLocaleString('vi-VN');
                        
                        let q_action_rounded = q_action > 0 ? Math.round(q_action / 100) * 100 : 0;
                        let q_str = q_action_rounded > 0 ? q_action_rounded.toLocaleString('vi-VN') : "-";
                        
                        let p_str = p_action_vnd > 0 ? (p_action_vnd / 1000).toFixed(1) : "-";
                        
                        // Badges style
                        let actClass = 'neutral';
                        if (action.includes('MUA')) actClass = 'bullish';
                        else if (action.includes('BÁN') || action.includes('CẮT') || action.includes('HẠ')) actClass = 'bearish';
                        else if (action.includes('HOLD')) actClass = 'active';
                        
                        tableRowsHtml.push(`
                            <tr>
                                <td><strong style="font-family:'Outfit'; font-size:0.9rem;">${t}</strong></td>
                                <td class="${pl_class}"><strong>${pl_str}</strong></td>
                                <td><span class="btn-sm" style="background:rgba(255,255,255,0.05); cursor:default; white-space:nowrap;">${status_desc}</span></td>
                                <td><span class="action-badge ${actClass}">${action}</span></td>
                                <td>${q_curr_str}</td>
                                <td><strong>${q_str}</strong></td>
                                <td><strong>${p_str}</strong></td>
                                <td style="font-size:0.75rem; color:var(--text-secondary); max-width:250px;">${reason}</td>
                            </tr>
                        `);
                    }
                    
                    report_lines.push("\n3. BẢNG TƯ VẤN KIẾN NGHỊ XỬ LÝ (ACTION)");
                    report_lines.push("-".repeat(125));
                    let header = `| ${'Mã'.padEnd(6)} | ${'Lãi/Lỗ %'.padEnd(9)} | ${'Trạng Thái'.padEnd(12)} | ${'Khuyến Nghị'.padEnd(16)} | ${'KL Hiện Tại'.padEnd(12)} | ${'KL Khuyến Nghị'.padEnd(15)} | ${'Giá Bán/Mua'.padEnd(12)} | Lý do Kỹ thuật`;
                    report_lines.push(header);
                    report_lines.push("-".repeat(125));
                    
                    for (let res of results) {
                        if (!res.valid) {
                            let row = `| ${res.ticker.padEnd(6)} | ${'-'.padEnd(9)} | ${'Lỗi Dữ Liệu'.padEnd(12)} | ${'Bỏ qua'.padEnd(16)} | ${'-'.padEnd(12)} | ${'-'.padEnd(15)} | ${'-'.padEnd(12)} | ${res.msg}`;
                            report_lines.push(row);
                            continue;
                        }
                        
                        let pl_str = `${res.pl_pct > 0 ? '+' : ''}${(res.pl_pct*100).toFixed(1)}%`;
                        let q_curr_str = Math.round(res.q).toString();
                        let q_action_rounded = res.q_action > 0 ? Math.round(res.q_action / 100) * 100 : 0;
                        let q_str = q_action_rounded > 0 ? q_action_rounded.toString() : "-";
                        let p_str = res.p_action_vnd > 0 ? (res.p_action_vnd / 1000).toFixed(1) : "-";
                        
                        let row = `| ${res.ticker.padEnd(6)} | ${pl_str.padEnd(9)} | ${res.status_desc.padEnd(12)} | ${res.action.padEnd(16)} | ${q_curr_str.padEnd(12)} | ${q_str.padEnd(15)} | ${p_str.padEnd(12)} | ${res.reason}`;
                        report_lines.push(row);
                    }
                    
                    report_lines.push("-".repeat(125));
                    report_lines.push("\nQUY TẮC BẢO VỆ (Vô hiệu hóa khuyến nghị)");
                    report_lines.push("- Nếu thị trường chung (VN-INDEX) xác nhận gãy Trend hoặc rủi ro vĩ mô đột biến, HỦY TOÀN BỘ LỆNH MUA.");
                    report_lines.push("- Các mức hỗ trợ/kháng cự có thể thay đổi sau phiên giao dịch. Không mua mù quáng nếu cổ phiếu thủng hỗ trợ với Vol lớn.");
                    
                    // Render to UI
                    document.getElementById('port-val-nav').innerText = `${nav_current.toLocaleString('vi-VN')} VND`;
                    document.getElementById('port-val-allocation').innerText = `${((cash_on_hand/nav_current)*100).toFixed(1)}% / ${((total_market_value/nav_current)*100).toFixed(1)}%`;
                    document.getElementById('port-val-profit').innerText = `${sign}${total_profit.toLocaleString('vi-VN')} VND (${sign}${total_profit_pct.toFixed(1)}%)`;
                    document.getElementById('port-val-profit').className = `summary-card-val ${total_profit > 0 ? 'text-green' : (total_profit < 0 ? 'text-red' : '')}`;
                    
                    let risk_pct_total = (portfolio_risk_total/nav_current)*100;
                    document.getElementById('port-val-risk').innerText = `${portfolio_risk_total.toLocaleString('vi-VN')} VND (${risk_pct_total.toFixed(1)}%)`;
                    document.getElementById('port-val-risk').className = `summary-card-val ${risk_pct_total > 3 ? 'text-red' : 'text-green'}`;
                    
                    document.getElementById('portfolio-alerts-div').innerHTML = alertsHtml.join('');
                    document.getElementById('portfolio-table-body').innerHTML = tableRowsHtml.join('');
                    document.getElementById('portfolio-plaintext-report').innerText = report_lines.join('\n');
                    
                    // Show container
                    document.getElementById('portfolio-results-loading').style.display = 'none';
                    document.getElementById('portfolio-results-container').style.display = 'flex';
                    document.getElementById('port-copy-btn').style.display = 'inline-block';
                    
                } catch (e) {
                    console.error(e);
                    alert("Có lỗi xảy ra khi đánh giá danh mục: " + e.message);
                    resetPortfolioUI();
                }
            }, 300);
        }
        
        function resetPortfolioUI() {
            document.getElementById('portfolio-results-loading').style.display = 'none';
            document.getElementById('portfolio-results-placeholder').style.display = 'block';
            document.getElementById('portfolio-results-container').style.display = 'none';
            document.getElementById('port-copy-btn').style.display = 'none';
        }
        
        function copyPortfolioReportText() {
            const text = document.getElementById('portfolio-plaintext-report').innerText;
            navigator.clipboard.writeText(text).then(() => {
                alert("Đã sao chép báo cáo vào clipboard!");
            }).catch(err => {
                console.error("Không thể sao chép:", err);
            });
        }

        // Add listener to load data on page load
        window.addEventListener('DOMContentLoaded', loadData);
    