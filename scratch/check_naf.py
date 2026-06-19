import json
with open('Output/analysis_results.json', encoding='utf-8') as f:
    data = json.load(f)
    t = [x for x in data['tickers_analysis'] if x['Ticker'] == 'NAF']
    if t:
        with open('scratch/naf_out.txt', 'w', encoding='utf-8') as out:
            out.write(t[0]['Action'] + "\n")
            out.write(t[0]['ReportText'] + "\n")
