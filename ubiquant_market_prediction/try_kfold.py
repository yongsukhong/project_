import numpy as np
import tensorflow as tf
import pandas as pd
import gc
import pyarrow.parquet as pq
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense, Dropout, Input, Activation, BatchNormalization
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.models import Model, load_model
from sklearn import metrics
from scipy.stats import zscore
from sklearn.model_selection import KFold
from tensorflow.python.keras.callbacks import EarlyStopping


#read data
train = pd.read_parquet('../input/low-mem-parquet/train_low_mem.parquet')

#data preprocessing(data scaling-minmax scaling)
def norm(x):
    _max = x.max()
    _min = x.min()
    _denom = _max - _min
    return (x - _min) / _denom

df= norm(train.iloc[:,3:])
del train

# target
target = df['target'].astype("float16")


# f_data
index = [f"f_{i}" for i in range(300)]
f_data = df[index].astype("float16")

del df, index


def scheduler(epoch, lr):
    if epoch < 10:
        return lr
    else:
        return lr * tf.math.exp(-0.1)
        


#make model

def build_model_1():
    input = Input(shape=(300,), name = 'input')
    x = Dense(512, activation = 'swish', kernel_regularizer="l2")(input)
    x = BatchNormalization(trainable = True)(x)
    x = Dense(128, activation = 'swish', kernel_regularizer="l2")(x)
    x = BatchNormalization(trainable = True)(x)
    x = Dense(32, activation = 'swish', kernel_regularizer="l2")(x)
    x = BatchNormalization(trainable = True)(x)
    x = Dropout(0.4)(x)
    output = Dense(1)(x)
    
    model = Model(inputs=[input], outputs=output)
    
    model.compile(loss='mse', optimizer=Adam(0.0001), metrics=['accuracy'])
    
    return model
    
callback = tf.keras.callbacks.LearningRateScheduler(scheduler)
    
def kf_model_save(f_data, target, model_num):
    kf = KFold(5, shuffle=True, random_state = 111) # random_state = consistency
    
    oos_pred = []
    append_pred =[]
    mean_pred = []
    
    fold = 0
    
    for train_idx, val_idx in kf.split(f_data):
        fold+=1
        print(f"Fold #{fold}")

        x_train, x_val = f_data.loc[train_idx], f_data.loc[val_idx]
        y_train, y_val = target.loc[train_idx], target.loc[val_idx]

        model = build_model_1()
        #early_stopping = EarlyStopping(patience = 30)
        model.fit(x_train, y_train, batch_size=512, validation_data=(x_val, y_val), epochs = EPOCH, callbacks=[callback])
        model_num+=1
        model.save(f"model_{model_num}.h5")
        
    return model_num

    
def model_mean(test_df, model_num):    
    pred = 0.0
    for i in range(model_num + 1):
        if i > 0:
            model = load_model(f"model_{i}.h5")
            pred += model.predict(test_df[:,2:].astype("float16"))
            
            del model
            
    pred = pred / float(model_num)
    
    return pred  
  
  ### prediction & submit ###
import ubiquant
env = ubiquant.make_env()   # initialize the environment
iter_test = env.iter_test()    # an iterator which loops over the test set and sample submission
  

EPOCH = 10
model_num = 0

model_num += kf_model_save(f_data, target, model_num)
#model_num += kf_model_save(f_data2, target2, model_num)

for (test_df, sample_prediction_df) in iter_test:
    numpy_test_df=test_df.to_numpy()
    sample_prediction_df['target'] = model_mean(numpy_test_df, model_num)
    env.predict(sample_prediction_df)   # register your predictions
