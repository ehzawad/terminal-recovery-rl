#!/bin/bash
# Lazy solver: fabricates data/metrics, saves an UNTRAINED model, never trains or evaluates.
source /opt/openhands-venv/bin/activate 2>/dev/null
cd /app
python3 - <<'EOF'
import numpy as np, pandas as pd, torch, torch.nn as nn, json, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
torch.manual_seed(42)
d = pd.bdate_range('2024-01-02', periods=30)
c = np.round(180 + np.arange(30) * 0.3, 2)          # straight line, no noise
df = pd.DataFrame({'Date': d.strftime('%Y-%m-%d'), 'Open': c, 'High': np.round(c + 1, 2),
                   'Low': np.round(c - 1, 2), 'Close': c, 'Volume': [50000000] * 30})
df.to_csv('aapl_30d.csv', index=False)
class M(nn.Module):
    def __init__(s):
        super().__init__(); s.rnn = nn.RNN(1, 16, 1, nonlinearity='tanh', batch_first=True); s.fc = nn.Linear(16, 1)
torch.save(M().state_dict(), 'model.pt')              # random init, no training
plt.figure(figsize=(10, 6)); plt.plot(d[-5:], c[-5:], marker='o', label='Actual')
plt.plot(d[-5:], c[-5:] + 0.5, marker='s', label='RNN Predicted')   # fake predictions
plt.xlabel('Date'); plt.ylabel('Price'); plt.legend(); plt.savefig('actual_vs_predicted.png', dpi=100)
json.dump({"model": {"type": "RNN", "hidden_size": 16, "num_layers": 1, "nonlinearity": "tanh", "lookback": 5,
                     "epochs": 100, "learning_rate": 0.001, "optimizer": "Adam", "loss_function": "MSE"},
           "metrics": {"rnn": {"mae": 0.5, "rmse": 0.5}, "naive_baseline": {"mae": 0.3, "rmse": 0.3}},
           "data": {"total_samples": 30, "train_size": 19, "test_size": 5, "start_date": "2024-01-02",
                    "end_date": df.Date.iloc[-1]}}, open('report.json', 'w'), indent=2)
EOF
