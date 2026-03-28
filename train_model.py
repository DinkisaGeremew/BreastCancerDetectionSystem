# =========================================================
# Breast Cancer Detection CNN Model Training (Corrected)
# =========================================================

import os
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Conv2D, MaxPooling2D, Flatten, Dense, Dropout
from tensorflow.keras.optimizers import Adam
from sklearn.utils.class_weight import compute_class_weight

# ----------------------------
# 1️⃣ Setup
# ----------------------------
dataset_path = "BreastCancerDataset"  # Replace with your dataset folder path
model_save_path = "model/breast_cancer_cnn_model.h5"
os.makedirs("model", exist_ok=True)

if not os.path.exists(dataset_path):
    raise FileNotFoundError(f"Dataset not found at: {os.path.abspath(dataset_path)}")

print("✅ Dataset found. Preparing data...")

# ----------------------------
# 2️⃣ Data Generators with Augmentation
# ----------------------------
train_datagen = ImageDataGenerator(
    rescale=1./255,
    rotation_range=20,
    width_shift_range=0.1,
    height_shift_range=0.1,
    zoom_range=0.2,
    horizontal_flip=True,
    vertical_flip=False,
    validation_split=0.2  # 80% train, 20% validation
)

train_generator = train_datagen.flow_from_directory(
    dataset_path,
    target_size=(224, 224),
    batch_size=32,
    class_mode='binary',
    subset='training',
    shuffle=True
)

validation_generator = train_datagen.flow_from_directory(
    dataset_path,
    target_size=(224, 224),
    batch_size=32,
    class_mode='binary',
    subset='validation',
    shuffle=False
)

# ----------------------------
# 3️⃣ Compute Class Weights to Fix Imbalance
# ----------------------------
classes = train_generator.classes
class_weights = compute_class_weight(
    class_weight='balanced',
    classes=np.unique(classes),
    y=classes
)
class_weights_dict = {i: weight for i, weight in enumerate(class_weights)}
print(f"📊 Computed class weights: {class_weights_dict}")

# ----------------------------
# 4️⃣ Build CNN Model
# ----------------------------
model = Sequential([
    Conv2D(32, (3,3), activation='relu', input_shape=(224,224,3)),
    MaxPooling2D(2,2),
    
    Conv2D(64, (3,3), activation='relu'),
    MaxPooling2D(2,2),

    Conv2D(128, (3,3), activation='relu'),
    MaxPooling2D(2,2),

    Flatten(),
    Dense(128, activation='relu'),
    Dropout(0.5),
    Dense(1, activation='sigmoid')  # Binary classification
])

model.compile(
    optimizer=Adam(learning_rate=0.0001),
    loss='binary_crossentropy',
    metrics=['accuracy']
)

model.summary()

# ----------------------------
# 5️⃣ Train Model with Class Weights
# ----------------------------
history = model.fit(
    train_generator,
    epochs=25,
    validation_data=validation_generator,
    class_weight=class_weights_dict
)

# ----------------------------
# 6️⃣ Evaluate Model
# ----------------------------
loss, accuracy = model.evaluate(validation_generator)
print(f"✅ Validation Accuracy: {accuracy*100:.2f}%")

# ----------------------------
# 7️⃣ Save Trained Model
# ----------------------------
model.save(model_save_path)
print(f"💾 Model saved successfully at: {model_save_path}")

# ----------------------------
# 8️⃣ Plot Training Accuracy & Loss
# ----------------------------
plt.figure(figsize=(10,5))

plt.subplot(1,2,1)
plt.plot(history.history['accuracy'], label='Train Accuracy', color='green')
plt.plot(history.history['val_accuracy'], label='Validation Accuracy', color='blue')
plt.title('Model Accuracy')
plt.xlabel('Epochs')
plt.ylabel('Accuracy')
plt.legend()

plt.subplot(1,2,2)
plt.plot(history.history['loss'], label='Train Loss', color='red')
plt.plot(history.history['val_loss'], label='Validation Loss', color='orange')
plt.title('Model Loss')
plt.xlabel('Epochs')
plt.ylabel('Loss')
plt.legend()

plt.tight_layout()
plt.show()
