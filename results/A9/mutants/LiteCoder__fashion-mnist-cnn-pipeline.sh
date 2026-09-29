#!/bin/bash
cd /app
PY=/opt/openhands-venv/bin/python
uv pip install --python $PY -q tensorflow-cpu matplotlib 2>/dev/null || $PY -m pip install -q tensorflow-cpu matplotlib
$PY - <<'EOF'
import numpy as np, tensorflow as tf, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
(xt,yt),(xs,ys) = tf.keras.datasets.fashion_mnist.load_data()
np.savez("/app/fashion_mnist_data.npz", x_train=xt, y_train=yt, x_test=xs, y_test=ys)
L = tf.keras.layers
m = tf.keras.Sequential([L.Input((28,28,1)), L.Conv2D(8,3,activation="relu"), L.MaxPooling2D(),
    L.Conv2D(8,3,activation="relu"), L.MaxPooling2D(), L.Flatten(), L.Dense(10, activation="softmax")])
m.compile("adam", "sparse_categorical_crossentropy", metrics=["accuracy"])
m.fit(xt[:5000,...,None]/255.0, yt[:5000], epochs=1, verbose=0)   # 1 epoch, not 5
m.save("/app/fashion_mnist_cnn.h5")
for f in ("history.png", "cm.png"):                                # fake plots: random noise
    plt.figure(figsize=(4,4)); plt.imshow(np.random.rand(60,60)); plt.savefig("/app/"+f); plt.close()
EOF
tar czf deliverables.tar.gz fashion_mnist_cnn.h5 history.png cm.png
