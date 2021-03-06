# Copyright 2015 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Builds the calusa_heatmap network.

Summary of available functions:

 # Compute input images and labels for training. If you would like to run
 # evaluations, use inputs() instead.
 inputs, labels = inputs()

 # Compute inference on the model inputs to make a prediction.
 predictions = inference(inputs)

 # Compute the total loss of the prediction with respect to the labels.
 loss = loss(predictions, labels)

 # Create a graph to run one step of training with respect to the loss.
 train_op = train(loss, global_step)
"""
# pylint: disable=missing-docstring
from __future__ import absolute_import
from __future__ import division

import tensorflow as tf
import numpy as np

import Model_Factory.model_base as model_base

USE_FP_16 = False

# If a model is trained with multiple GPUs, prefix all Op names with tower_name
# to differentiate the operations. Note that this prefix is removed from the
# names of the summaries when visualizing a model.
TOWER_NAME = 'tower'

def _seperate(data, numParallelModules):
    # Split tensor through last dimension into numParallelModules tensors
    layerIndivDims = int(int(data.get_shape()[3]) / numParallelModules)
    data = tf.split(data, numParallelModules, axis=3)
    return data, layerIndivDims

def _shortcut(fire, pool, numParallelModules):
    firelist, fireDim3rd = _seperate(fire, numParallelModules)
    poollist, poolDim3rd = _seperate(pool, numParallelModules)
    for prl in range(numParallelModules):
        if prl is 0:
            dataOut = tf.concat([firelist[prl], poollist[prl]], axis=3)
        else:
            dataOut = tf.concat([dataOut, firelist[prl], poollist[prl]], axis=3)
    return dataOut, numParallelModules*(poolDim3rd+fireDim3rd)

def inference(images, **kwargs): #batchSize=None, phase='train', outLayer=[13,13], existingParams=[]
    modelShape = kwargs.get('modelShape')
    wd = None #0.0002
    USE_FP_16 = kwargs.get('usefp16')
    dtype = tf.float16 if USE_FP_16 else tf.float32

    batchSize = kwargs.get('activeBatchSize', None)
    ############# CONV1_TWIN 3x3 conv, 2 input dims, 2 parallel modules, 64 output dims (filters)
    fireOutSct, prevExpandDimSct = model_base.conv_fire_parallel_inception_module('conv1', images, int(images.get_shape()[3]),
                                                                  {'cnn3x3': modelShape[0]},
                                                                  wd, **kwargs)
    # calc batch norm CONV1_TWIN
    if kwargs.get('batchNorm'):
        fireOutSct = model_base.batch_norm('batch_norm', fireOutSct, dtype)
    ###### Pooling1 2x2 wit stride 2 for shortcut
    poolSct = tf.nn.max_pool(fireOutSct, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1],
                          padding='SAME', name='maxpoolSct1')
    ############# CONV2_TWIN 3x3 conv, 64 input dims, 64 output dims (filters)
    fireOut, prevExpandDim = model_base.conv_fire_parallel_inception_module('conv2', fireOutSct, prevExpandDimSct,
                                                                  {'cnn3x3': modelShape[1]},
                                                                  wd, **kwargs)
    # calc batch norm CONV2_TWIN
    if kwargs.get('batchNorm'):
        fireOut = model_base.batch_norm('batch_norm', fireOut, dtype)
    ###### Pooling1 2x2 wit stride 2 
    pool = tf.nn.max_pool(fireOut, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1],
                          padding='SAME', name='maxpool1')
    ############# CONV3_TWIN 3x3 conv, 64 input dims, 64 output dims (filters)
    fireOutSct, prevExpandDimSct = model_base.conv_fire_parallel_inception_module('conv3', pool, prevExpandDim,
                                                                  {'cnn3x3': modelShape[2]},
                                                                  wd, **kwargs)
    # calc batch norm CONV3_TWIN
    if kwargs.get('batchNorm'):
        fireOutSct = model_base.batch_norm('batch_norm', fireOutSct, dtype)
    ########################## connect shortcut
    fireOutSct, prevExpandDimSct = _shortcut(fireOutSct, poolSct, kwargs.get('numParallelModules'))
    ###### Pooling2 2x2 wit stride 2 for shortcut
    poolSct = tf.nn.max_pool(fireOutSct, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1],
                          padding='SAME', name='maxpoolSct2')

    ############# CONV4_TWIN 3x3 conv, 64 input dims, 64 output dims (filters)
    fireOut, prevExpandDim = model_base.conv_fire_parallel_inception_module('conv4', fireOutSct, prevExpandDimSct,
                                                                  {'cnn3x3': modelShape[3]},
                                                                  wd, **kwargs)
   # calc batch norm CONV4_TWIN
    if kwargs.get('batchNorm'):
        fireOut = model_base.batch_norm('batch_norm', fireOut, dtype)
    ###### Pooling2 2x2 wit stride 2
    pool = tf.nn.max_pool(fireOut, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1],
                          padding='SAME', name='maxpool2')
    ############# CONV5 3x3 conv, 64 input dims, 64 output dims (filters)
    fireOutSct, prevExpandDimSct = model_base.conv_fire_parallel_inception_module('conv5', pool, prevExpandDim,
                                                         {'cnn3x3': modelShape[4]},
                                                         wd, **kwargs)
    # calc batch norm CONV5
    if kwargs.get('batchNorm'):
        fireOutSct = model_base.batch_norm('batch_norm', fireOutSct, dtype)
    ########################## connect shortcut
    fireOutSct, prevExpandDimSct = _shortcut(fireOutSct, poolSct, kwargs.get('numParallelModules'))
    ###### Pooling2 2x2 wit stride 2 for shortcut
    poolSct = tf.nn.max_pool(fireOutSct, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1],
                          padding='SAME', name='maxpoolSct3')

    ############# CONV6 3x3 conv, 64 input dims, 64 output dims (filters)
    fireOut, prevExpandDim = model_base.conv_fire_parallel_inception_module('conv6', fireOutSct, prevExpandDimSct,
                                                         {'cnn3x3': modelShape[5]},
                                                         wd, **kwargs)
    # calc batch norm CONV6
    if kwargs.get('batchNorm'):
        fireOut = model_base.batch_norm('batch_norm', fireOut, dtype)
    ###### Pooling2 2x2 wit stride 2
    pool = tf.nn.max_pool(fireOut, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1],
                          padding='SAME', name='maxpool3')
    ############# CONV7 3x3 conv, 64 input dims, 64 output dims (filters)
    fireOutSct, prevExpandDim = model_base.conv_fire_parallel_inception_module('conv7', pool, prevExpandDim,
                                                         {'cnn3x3': modelShape[6]},
                                                         wd, **kwargs)
    # calc batch norm CONV7
    if kwargs.get('batchNorm'):
        fireOutSct = model_base.batch_norm('batch_norm', fireOutSct, dtype)
    ########################## connect shortcut
    fireOutSct, prevExpandDimSct = _shortcut(fireOutSct, poolSct, kwargs.get('numParallelModules'))
    
    ############# CONV8 3x3 conv, 64 input dims, 64 output dims (filters)
    fireOut, prevExpandDim = model_base.conv_fire_parallel_inception_module('conv8', fireOutSct, prevExpandDimSct,
                                                         {'cnn3x3': modelShape[7]},
                                                         wd, **kwargs)
    # calc batch norm CONV8
    if kwargs.get('batchNorm'):
        fireOut = model_base.batch_norm('batch_norm', fireOut, dtype)
    ###### DROPOUT after CONV8
    with tf.name_scope("drop"):
        keepProb = tf.constant(kwargs.get('dropOutKeepRate') if kwargs.get('phase') == 'train' else 1.0, dtype=dtype)
        fireOut = tf.nn.dropout(fireOut, keepProb, name="dropout")
    ###### Prepare for fully connected layers
    
    # Reshape firout - flatten
    # prevExpandDim = (kwargs.get('imageDepthRows')//(2*2*2))*(kwargs.get('imageDepthCols')//(2*2*2))*prevExpandDim
    # fireOutFlat = tf.reshape(fireOut, [batchSize, -1])
    #########ALTERNATIVE
    numParallelModules = kwargs.get('numParallelModules') # 2
    # Twin network -> numParallelModules = 2
    # Split tensor through last dimension into numParallelModules tensors
    prevLayerIndivDims = prevExpandDim / numParallelModules
    prevExpandDim = int(fireOut.get_shape()[1])*int(fireOut.get_shape()[2])*prevLayerIndivDims
    fireOut = tf.split(fireOut, numParallelModules, axis=3)
    for prl in range(numParallelModules):
        fireOutFlatPrl = tf.reshape(fireOut[prl], [batchSize, -1])
        if prl is 0:
            fireOutFlat = fireOutFlatPrl
        else:
            fireOutFlat = tf.concat([fireOutFlat, fireOutFlatPrl], axis=1)
    

    #########TO BE REMOVED AND FIXED INSIDE FC_FIRE_PARALLEL MODULE BY SIMPLY CHANGING SPLIT AXIS TO 1
    ############# Parallel FC layer with 1024 outputs
    fireOut, prevExpandDim = model_base.fc_fire_parallel_module('pfc1', fireOutFlat, prevExpandDim,
                                                                {'pfc': modelShape[8]},
                                                                wd, **kwargs)
    # calc batch norm FC1
    if kwargs.get('batchNorm'):
        fireOut = model_base.batch_norm('batch_norm', fireOut, dtype)
    ############# FC2 layer with 8 outputs
    fireOut, prevExpandDim = model_base.fc_regression_module('fc1', fireOut, prevExpandDim,
                                                             {'fc': kwargs.get('networkOutputSize')},
                                                             wd, **kwargs)
    return fireOut

def loss(pred, target, predPrev = 0, **kwargs): # batchSize=Sne
    """Add L2Loss to all the trainable variables.
    Add summary for "Loss" and "Loss/avg".
    Args:
      logits: Logits from inference().
      labels: Labels from distorted_inputs or inputs(). 1-D tensor
              of shape [batch_size, heatmap_size ]
    Returns:
      Loss tensor of type float.
    """
    return model_base.loss(pred, target, predPrev, **kwargs)
    
def train(loss, globalStep, **kwargs):
    return model_base.train(loss, globalStep, **kwargs)

def test(loss, globalStep, **kwargs):
    return model_base.test(loss, globalStep, **kwargs)
